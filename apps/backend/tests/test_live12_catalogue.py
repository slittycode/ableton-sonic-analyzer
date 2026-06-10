"""Unit tests for the Live 12 addressable-target catalogue.

Three layers covered here:

1. `Live12Catalogue` API surface against the hand-authored 3-device fixture
   (`tests/fixtures/live12_catalogue/three_device_catalogue.json`).
2. Generator behavior against the vendored 2-file fixture
   (`tests/fixtures/live12_catalogue/upstream/bank_definitions_fixture.py` +
   `tests/fixtures/live12_catalogue/expected_saturator.json`).
3. Regression safety net: every device named in the curated
   `prompts/live12_device_catalog.json` is recognized by the generated
   `data/live12_catalogue.json` -- guards the validator from silently dropping
   a Gemini recommendation whose device exists in the prompt-side curated
   catalog but is missing from the proof-gate source catalogue.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from live12_catalogue import (
    CatalogueShapeError,
    Live12Catalogue,
    DEFAULT_CATALOGUE_PATH,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "live12_catalogue"
_THREE_DEVICE_FIXTURE = _FIXTURE_DIR / "three_device_catalogue.json"
_FIXTURE_BANK_DEFINITIONS_PY = (
    _FIXTURE_DIR / "upstream" / "bank_definitions_fixture.py"
)
_FIXTURE_EXPECTED_SATURATOR = _FIXTURE_DIR / "expected_saturator.json"
_CURATED_CATALOG = (
    Path(__file__).resolve().parents[1] / "prompts" / "live12_device_catalog.json"
)


def _load_generator_module():
    """Load `scripts/build_live12_catalogue.py` without putting `scripts/` on
    the package path permanently — keeps the generator clearly out of the
    backend's normal import surface."""
    spec = importlib.util.spec_from_file_location(
        "build_live12_catalogue",
        _REPO_ROOT / "scripts" / "build_live12_catalogue.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Live12CatalogueApiTests(unittest.TestCase):
    """Covers has_device / has_parameter / parameter_spec / fuzzy_resolve."""

    def setUp(self) -> None:
        self.catalogue = Live12Catalogue.from_path(_THREE_DEVICE_FIXTURE)

    def test_loads_all_three_devices(self):
        classes = sorted(d.class_name for d in self.catalogue.devices)
        self.assertEqual(classes, ["Eq8", "Operator", "Saturator"])

    def test_has_device_exact_class(self):
        self.assertTrue(self.catalogue.has_device("Saturator"))
        self.assertTrue(self.catalogue.has_device("Eq8"))
        self.assertTrue(self.catalogue.has_device("Operator"))

    def test_has_device_case_insensitive(self):
        self.assertTrue(self.catalogue.has_device("saturator"))
        self.assertTrue(self.catalogue.has_device("SATURATOR"))
        self.assertTrue(self.catalogue.has_device("  saturator  "))

    def test_has_device_resolves_display_name_alias(self):
        # "Eq8" is the canonical class; "EQ Eight" is the Ableton UI label.
        # Gemini cites the UI form; the catalogue must accept both.
        self.assertTrue(self.catalogue.has_device("EQ Eight"))
        self.assertTrue(self.catalogue.has_device("eq eight"))

    def test_has_device_rejects_unknown(self):
        self.assertFalse(self.catalogue.has_device("Saturation Color"))
        self.assertFalse(self.catalogue.has_device(""))
        self.assertFalse(self.catalogue.has_device(None))  # type: ignore[arg-type]

    def test_canonical_device_returns_class_name_for_display_alias(self):
        self.assertEqual(self.catalogue.canonical_device("EQ Eight"), "Eq8")
        self.assertEqual(self.catalogue.canonical_device("Saturator"), "Saturator")
        self.assertIsNone(self.catalogue.canonical_device("Nope"))

    def test_has_parameter_exact_match(self):
        self.assertTrue(self.catalogue.has_parameter("Saturator", "Drive"))
        self.assertTrue(self.catalogue.has_parameter("EQ Eight", "1 Frequency A"))
        self.assertTrue(self.catalogue.has_parameter("Operator", "Volume"))

    def test_has_parameter_rejects_unknown_parameter(self):
        self.assertFalse(self.catalogue.has_parameter("Saturator", "HiCut"))
        self.assertFalse(self.catalogue.has_parameter("Saturator", "Drives"))

    def test_has_parameter_rejects_unknown_device(self):
        self.assertFalse(self.catalogue.has_parameter("Nope", "Drive"))

    def test_parameter_spec_returns_full_metadata_when_known(self):
        spec = self.catalogue.parameter_spec("Operator", "Volume")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.type, "float")
        self.assertEqual(spec.min, -36.0)
        self.assertEqual(spec.max, 6.0)
        self.assertEqual(spec.unit, "dB")
        self.assertEqual(spec.default, 0.0)
        self.assertTrue(spec.has_range())
        # Range gate exercises in_range with both bounds present.
        self.assertTrue(spec.in_range(-12.0))
        self.assertFalse(spec.in_range(-40.0))
        self.assertFalse(spec.in_range(12.0))

    def test_parameter_spec_returns_name_only_when_no_range(self):
        spec = self.catalogue.parameter_spec("Saturator", "Drive")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.name, "Drive")
        self.assertIsNone(spec.min)
        self.assertIsNone(spec.max)
        self.assertFalse(spec.has_range())
        # in_range with no bounds is True — range gate is inert when unknown.
        self.assertTrue(spec.in_range(100.0))
        self.assertTrue(spec.in_range(-100.0))

    def test_parameter_spec_returns_none_for_unknown(self):
        self.assertIsNone(self.catalogue.parameter_spec("Saturator", "Nope"))
        self.assertIsNone(self.catalogue.parameter_spec("Nope", "Drive"))

    def test_fuzzy_resolve_handles_minor_typo(self):
        # "Drives" -> "Drive" (single trailing char)
        resolution = self.catalogue.fuzzy_resolve("Saturator", "Drives")
        self.assertEqual(resolution, ("Saturator", "Drive"))

    def test_fuzzy_resolve_handles_display_name_device(self):
        resolution = self.catalogue.fuzzy_resolve("EQ Eight", "1 Frequencies A")
        self.assertEqual(resolution, ("Eq8", "1 Frequency A"))

    def test_fuzzy_resolve_returns_exact_match_unchanged(self):
        resolution = self.catalogue.fuzzy_resolve("Saturator", "Drive")
        self.assertEqual(resolution, ("Saturator", "Drive"))

    def test_fuzzy_resolve_returns_none_for_far_match(self):
        # "TotalGarbage" is too far from any of {"Drive", "Output", "Dry/Wet"}.
        self.assertIsNone(self.catalogue.fuzzy_resolve("Saturator", "TotalGarbage"))

    def test_fuzzy_resolve_returns_none_for_unknown_device(self):
        self.assertIsNone(self.catalogue.fuzzy_resolve("Nope", "Drive"))


class CatalogueShapeValidationTests(unittest.TestCase):
    """Shape errors raise CatalogueShapeError with useful messages."""

    def test_rejects_missing_required_top_level_key(self):
        data = json.loads(_THREE_DEVICE_FIXTURE.read_text(encoding="utf-8"))
        data.pop("schema_version")
        with self.assertRaises(CatalogueShapeError) as ctx:
            Live12Catalogue.from_dict(data)
        self.assertIn("schema_version", str(ctx.exception))

    def test_rejects_wrong_schema_version(self):
        data = json.loads(_THREE_DEVICE_FIXTURE.read_text(encoding="utf-8"))
        data["schema_version"] = "2"
        with self.assertRaises(CatalogueShapeError):
            Live12Catalogue.from_dict(data)

    def test_rejects_bad_commit_sha(self):
        data = json.loads(_THREE_DEVICE_FIXTURE.read_text(encoding="utf-8"))
        data["source_commit"] = "not-a-sha"
        with self.assertRaises(CatalogueShapeError):
            Live12Catalogue.from_dict(data)

    def test_rejects_unknown_category(self):
        data = json.loads(_THREE_DEVICE_FIXTURE.read_text(encoding="utf-8"))
        data["devices"][0]["category"] = "exotic"
        with self.assertRaises(CatalogueShapeError):
            Live12Catalogue.from_dict(data)

    def test_rejects_duplicate_class(self):
        data = json.loads(_THREE_DEVICE_FIXTURE.read_text(encoding="utf-8"))
        data["devices"].append(dict(data["devices"][0]))
        with self.assertRaises(CatalogueShapeError):
            Live12Catalogue.from_dict(data)


class CatalogueGeneratorTests(unittest.TestCase):
    """Generator unit tests against the vendored 2-file fixture."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_generator_module()
        cls.fixture_text = _FIXTURE_BANK_DEFINITIONS_PY.read_text(encoding="utf-8")
        cls.expected_saturator = json.loads(
            _FIXTURE_EXPECTED_SATURATOR.read_text(encoding="utf-8")
        )

    def _build(self) -> dict:
        return self.module.build_catalogue_from_text(
            bank_definitions_text=self.fixture_text,
            source_commit="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            generated_at="2026-05-28T00:00:00Z",
        )

    def test_extracts_expected_device_count(self):
        catalogue = self._build()
        # The fixture defines 4 device classes: AudioEffectGroupDevice (RACK),
        # Saturator, Eq8, Operator.
        self.assertEqual(len(catalogue["devices"]), 4)
        class_names = {d["class"] for d in catalogue["devices"]}
        self.assertEqual(
            class_names,
            {"AudioEffectGroupDevice", "Saturator", "Eq8", "Operator"},
        )

    def test_extracts_expected_saturator_parameter_count(self):
        catalogue = self._build()
        sat = next(d for d in catalogue["devices"] if d["class"] == "Saturator")
        expected = {p["name"] for p in self.expected_saturator["devices"][0]["parameters"]}
        actual = {p["name"] for p in sat["parameters"]}
        self.assertEqual(actual, expected)

    def test_handles_use_chains(self):
        catalogue = self._build()
        operator = next(d for d in catalogue["devices"] if d["class"] == "Operator")
        names = {p["name"] for p in operator["parameters"]}
        # `use("Osc A Wave").with_name("Wave").if_parameter("Oscillator")...`
        # use+if_parameter+else_use args are parameter names; with_name and
        # has_value args are NOT.
        self.assertIn("Osc A Wave", names)
        self.assertIn("Osc B Wave", names)
        self.assertIn("Oscillator", names)
        # "Wave" was a with_name() argument and "Osc A" was a has_value()
        # argument — neither should be in the parameter set.
        self.assertNotIn("Wave", names)
        self.assertNotIn("Osc A", names)

    def test_handles_rack_banks_reference(self):
        catalogue = self._build()
        rack = next(
            d for d in catalogue["devices"] if d["class"] == "AudioEffectGroupDevice"
        )
        names = sorted(p["name"] for p in rack["parameters"])
        self.assertEqual(names, ["Macro 1", "Macro 2", "Macro 3", "Macro 4"])

    def test_display_name_and_category_applied(self):
        catalogue = self._build()
        eq = next(d for d in catalogue["devices"] if d["class"] == "Eq8")
        self.assertEqual(eq["displayName"], "EQ Eight")
        self.assertEqual(eq["category"], "audio_effect")
        operator = next(d for d in catalogue["devices"] if d["class"] == "Operator")
        self.assertEqual(operator["category"], "instrument")
        rack = next(
            d for d in catalogue["devices"] if d["class"] == "AudioEffectGroupDevice"
        )
        self.assertEqual(rack["category"], "rack")

    def test_generator_output_is_canonical_sorted(self):
        catalogue = self._build()
        class_names = [d["class"] for d in catalogue["devices"]]
        self.assertEqual(class_names, sorted(class_names))
        for device in catalogue["devices"]:
            param_names = [p["name"] for p in device["parameters"]]
            self.assertEqual(param_names, sorted(param_names))

    def test_generator_output_validates_against_catalogue_loader(self):
        catalogue = self._build()
        # The catalogue module's stdlib validator is the schema enforcer.
        # If the generator output drifts from the schema, this fails.
        Live12Catalogue.from_dict(catalogue)


class DefaultCataloguePathTests(unittest.TestCase):
    """The on-disk catalogue at data/live12_catalogue.json must load cleanly
    and cover the upstream's full device set."""

    def test_default_catalogue_loads(self):
        catalogue = Live12Catalogue.from_path(DEFAULT_CATALOGUE_PATH)
        self.assertGreater(len(catalogue.devices), 50)

    def test_default_catalogue_includes_expected_devices(self):
        catalogue = Live12Catalogue.from_path(DEFAULT_CATALOGUE_PATH)
        for expected_class in (
            "Saturator",
            "Eq8",
            "Operator",
            "GlueCompressor",
            "Compressor2",
            "AutoFilter",
            "Reverb",
        ):
            self.assertTrue(
                catalogue.has_device(expected_class),
                f"default catalogue missing canonical class {expected_class!r}",
            )

    def test_default_catalogue_recognizes_curated_native_catalog_devices(self):
        """Regression safety net: every NATIVE device in the prompt-side
        curated catalog (`prompts/live12_device_catalog.json`) must be
        recognized by `Live12Catalogue.has_device()` in the generated source
        catalogue.

        Without this, the validator could silently drop a Gemini
        recommendation whose native device exists in the prompt-side curated
        catalog but is missing from the proof-gate source catalogue. If this
        fails, update the `DISPLAY_NAMES` map in
        `scripts/build_live12_catalogue.py` so the source catalogue
        alias-resolves the curated catalog's device name to a canonical Live
        class.

        Max for Live devices are explicitly out of scope per GOAL: the upstream
        MIDI Remote Scripts do not catalog M4L devices, and the validator
        falls back to the existing curated check for them. They are filtered
        out of this comparison.
        """
        catalogue = Live12Catalogue.from_path(DEFAULT_CATALOGUE_PATH)
        curated = json.loads(_CURATED_CATALOG.read_text(encoding="utf-8"))
        missing: list[str] = []
        for device in curated["devices"]:
            if device.get("family") == "MAX_FOR_LIVE":
                continue
            name = device["name"]
            if not catalogue.has_device(name):
                missing.append(name)
        self.assertEqual(
            missing,
            [],
            (
                "These NATIVE curated devices are not recognized by the source "
                "catalogue (data/live12_catalogue.json). Add a displayName "
                "alias in scripts/build_live12_catalogue.py and regenerate: "
                + ", ".join(missing)
            ),
        )


class UiParameterAliasTests(unittest.TestCase):
    """Curated UI-spelling resolution (`resolve_ui_parameter`) and UI-only
    recognition (`is_ui_only_parameter`) against the real shipped catalogue.

    These are the prompt-sanctioned spellings observed warning live on
    2026-06-10 (VTSS + DJ Metatron runs) — each must now resolve, while
    invented parameters must keep returning None.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogue = Live12Catalogue.from_path(DEFAULT_CATALOGUE_PATH)

    def test_eq_eight_band_spellings_resolve_to_a_curve(self):
        cases = {
            "Band 8 Gain": "8 Gain A",
            "Band 1 Frequency": "1 Frequency A",
            "Band 3 Filter Type": "3 Filter Type A",
            "Band 5 Q": "5 Resonance A",  # UI "Q" is the source's Resonance
        }
        for ui_name, source_name in cases.items():
            with self.subTest(ui_name=ui_name):
                self.assertEqual(
                    self.catalogue.resolve_ui_parameter("EQ Eight", ui_name),
                    ("Eq8", source_name),
                )

    def test_operator_spellings_resolve(self):
        cases = {
            "Oscillator A Coarse": "A Coarse",
            "Oscillator B Level": "Osc-B Level",
            "Amp Envelope Decay": "Ae Decay",
            "Unison Amount": "Spread",
            "Filter Frequency": "Filter Freq",
        }
        for ui_name, source_name in cases.items():
            with self.subTest(ui_name=ui_name):
                self.assertEqual(
                    self.catalogue.resolve_ui_parameter("Operator", ui_name),
                    ("Operator", source_name),
                )

    def test_reverb_spellings_resolve(self):
        self.assertEqual(
            self.catalogue.resolve_ui_parameter("Reverb", "Low Cut"),
            ("Reverb", "In LoCut"),
        )
        self.assertEqual(
            self.catalogue.resolve_ui_parameter("Reverb", "High Cut"),
            ("Reverb", "In HiCut"),
        )

    def test_exact_source_names_resolve_to_themselves(self):
        self.assertEqual(
            self.catalogue.resolve_ui_parameter("EQ Eight", "8 Gain A"),
            ("Eq8", "8 Gain A"),
        )

    def test_invented_parameters_do_not_resolve(self):
        for device, parameter in (
            ("EQ Eight", "Band 9 Gain"),  # EQ Eight has 8 bands
            ("EQ Eight", "Totally Invented Knob"),
            ("Operator", "Wavetable Position"),  # wrong-device vocabulary
            ("Reverb", "Wander"),
        ):
            with self.subTest(device=device, parameter=parameter):
                self.assertIsNone(
                    self.catalogue.resolve_ui_parameter(device, parameter)
                )

    def test_unknown_device_does_not_resolve(self):
        self.assertIsNone(
            self.catalogue.resolve_ui_parameter("Not A Device", "Band 1 Gain")
        )

    def test_scale_name_is_ui_only(self):
        # The Scale device's scale selector is a real UI control but not an
        # automatable DeviceParameter, so the extraction cannot list it.
        self.assertTrue(self.catalogue.is_ui_only_parameter("Scale", "Scale Name"))
        self.assertTrue(
            self.catalogue.is_ui_only_parameter("Scale", "Use Current Scale")
        )
        self.assertFalse(self.catalogue.is_ui_only_parameter("Scale", "Base"))
        self.assertFalse(
            self.catalogue.is_ui_only_parameter("EQ Eight", "Scale Name")
        )


if __name__ == "__main__":
    unittest.main()
