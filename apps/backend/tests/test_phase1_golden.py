"""Regression gate over default-mode ``analyze.py`` output.

Runs ``analyze.py`` on a fixed deterministic fixture and asserts two things against a
committed golden:

1. **Contract / structure** -- the exact set of top-level keys and each one's type category
   (null / bool / number / str / list / dict). Catches added/removed fields, a field
   changing type, or a detector silently returning null.
2. **Core measurement values** -- a curated set of environment-stable, high-value Phase 1
   measurements (BPM, key, loudness, true-peak, crest, spectral balance, stereo), compared
   with tolerance.
3. **Nested key structure (``keyTree``)** -- a recursive, structure-only snapshot of every
   nested key the analyzer emitted (dicts recurse; lists of objects record the union of
   element keys; values reduce to type categories). This is the executable cross-app
   contract source: the frontend parity gate
   (``apps/ui/tests/services/phase1ContractParity.test.ts``) walks the committed keyTree
   to demand every nested backend field exists in the frontend fixture/parser — killing
   the silent-field-drop class (CLAUDE.md tripwires #3/#4) at the *nested* level where
   the 2026-05-30 audit found it. Nested *value* categories are compared loosely
   (null/bool/number/str form one class — cross-runner null flips are measurement noise);
   container-shape changes always bite. Goldens that predate keyTree skip this gate
   visibly until the next regeneration arms it.

Why not snapshot the whole output? The fixture WAV is bit-identical across machines, but a
different CPU/BLAS/FFT order on the CI runner produces last-bit-different floats. For most
scalar measurements that is absorbed by tolerance, but many *fine-grained* fields
(per-beat accent patterns, per-frame spectral series, MFCC/chroma vectors, onset counts)
sit on discrete decision boundaries and flip wholesale between machines. Snapshotting those
makes the gate flaky, not protective. A local fragility probe (tiny PCM noise) was used to
pick the curated set: only fields that never flip under perturbation are compared by value;
everything else is still covered structurally (presence + type).

Regenerating the golden after an *intentional* change (one command, from ``apps/backend/``):

    UPDATE_PHASE1_GOLDEN=1 ./venv/bin/python -m unittest tests.test_phase1_golden

The main gate test never writes; only ``test_zzz_regenerate_golden`` writes, and only when
that env var is set.
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np


_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ANALYZE_PY = _BACKEND_ROOT / "analyze.py"
_GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "golden" / "phase1_default.json"
_UPDATE_ENV = "UPDATE_PHASE1_GOLDEN"
_MISSING = object()

# Curated, environment-stable measurements compared by value. Chosen from a fragility probe
# (tiny-PCM-noise perturbation): these never crossed a tolerance/decision boundary, whereas
# fine-grained arrays/counts/vectors did and are intentionally left to the structural check.
CORE_PATHS = (
    "bpm", "key", "keyConfidence", "timeSignature", "timeSignatureSource",
    "durationSeconds", "sampleRate",
    "lufsIntegrated", "lufsRange", "lufsMomentaryMax", "lufsShortTermMax",
    "truePeak", "plr", "crestFactor", "monoCompatible",
    "spectralBalance.subBass", "spectralBalance.lowBass", "spectralBalance.lowMids",
    "spectralBalance.mids", "spectralBalance.upperMids", "spectralBalance.highs",
    "spectralBalance.brilliance",
    "stereoDetail.stereoCorrelation", "stereoDetail.stereoWidth",
    "stereoDetail.subBassCorrelation", "stereoDetail.subBassMono",
)

# Dotted paths (``[]`` segment for list descent, e.g. "rhythmDetail.tempoCurve[].bpm")
# whose keyTree subtree is recorded as "pruned" and never compared. The documented
# one-line loosening path if arming the keyTree gate flushes out a genuinely
# runner-unstable subtree. Deliberately empty: the fixture is synthetic and
# deterministic, and an empty set keeps the gate honest.
KEYTREE_PRUNE_PATHS: frozenset[str] = frozenset()

# Nested scalar leaves whose categories are interchangeable in the keyTree
# comparison: a nested rt60 flipping null<->number across runners is measurement
# noise, not a contract change. Container<->scalar changes always bite. Top-level
# types stay exact via the (untouched) topLevelTypes check.
_SCALAR_CATS = frozenset({"null", "bool", "number", "str"})
# Leaf markers for lists that record no element structure: "list" (empty at
# baseline — nothing observable) and "scalarList" (scalar/mixed elements — no
# droppable keys; lengths are exactly the runner-unstable quantity).
_LIST_LEAVES = frozenset({"list", "scalarList"})

# Numeric tolerance. Two numbers are equal iff
#   abs(a-g) <= max(ABS_TOL, REL_TOL*abs(g), one rounding step at g's decimal precision).
# The rounding-step term absorbs the dominant cross-environment difference: analyze.py rounds
# every output float (1-4 decimals), and a different BLAS/thread order can nudge a raw value
# across a rounding boundary, flipping the last digit by a whole step (e.g. 135.4 -> 135.5).
ABS_TOL = 1e-3
REL_TOL = 1e-3


def _write_golden_fixture(path: Path, sample_rate: int = 44_100, duration_seconds: float = 6.0) -> None:
    """Deterministic A-minor harmonic bed (copied from test_analyze._write_key_fixture). No RNG."""
    total_samples = int(sample_rate * duration_seconds)
    time_axis = np.arange(total_samples, dtype=np.float32) / sample_rate
    signal = (
        0.45 * np.sin(2 * np.pi * 220.0 * time_axis)
        + 0.3 * np.sin(2 * np.pi * 261.63 * time_axis)
        + 0.3 * np.sin(2 * np.pi * 329.63 * time_axis)
        + 0.18 * np.sin(2 * np.pi * 440.0 * time_axis)
    ).astype(np.float32)
    envelope = np.linspace(1.0, 0.8, total_samples, dtype=np.float32)

    stereo = np.stack([signal * envelope, signal * envelope], axis=1)
    pcm = np.clip(stereo, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def _run_analyze(analyze_path: Path, fixture_path: Path, extra_args: list[str]) -> tuple[str, str]:
    """Run analyze.py and return (stdout, stderr). Raises AssertionError on non-zero exit."""
    try:
        completed = subprocess.run(
            [sys.executable, str(analyze_path), str(fixture_path), "--yes"] + extra_args,
            cwd=analyze_path.parent,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise AssertionError(
            f"analyze.py {' '.join(extra_args)} failed.\n"
            f"stdout:\n{error.stdout[:800]}\n"
            f"stderr:\n{error.stderr[:800]}"
        ) from error
    return completed.stdout, completed.stderr


def _fmt(value: object) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _type_cat(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _dotted_get(payload: object, path: str) -> object:
    current = payload
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


def _merge_trees(a: object, b: object) -> object:
    """Union-merge two keyTree nodes (used across list-of-object elements).

    Union rather than first-element so the recorded element structure is
    insensitive to element order and to which element happens to carry an
    optional key. Scalar-category conflicts prefer the non-null category
    (deterministic for a deterministic payload, and immaterial because the
    comparison treats all scalar categories as one class).
    """
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for key, value in b.items():
            out[key] = _merge_trees(out[key], value) if key in out else value
        return out
    if a == b:
        return a
    if a == "null":
        return b
    return a


def _key_tree(value: object, path: str = "") -> object:
    """Recursive, structure-only snapshot of a Phase 1 payload (no values).

    Encoding (consumed by ``_compare_key_tree`` here and by the frontend
    parity gate in apps/ui/tests/services/phase1ContractParity.test.ts):

    - dict                          -> ``{key: subtree}``
    - non-empty list of dicts       -> ``{"[]": union-merge of element trees}``
    - empty list                    -> ``"list"`` (no element structure observable)
    - list of scalars / mixed list  -> ``"scalarList"``
    - scalar                        -> its ``_type_cat`` category string
    - path in KEYTREE_PRUNE_PATHS   -> ``"pruned"`` (never compared)
    """
    if path in KEYTREE_PRUNE_PATHS:
        return "pruned"
    if isinstance(value, dict):
        return {
            key: _key_tree(child, f"{path}.{key}" if path else key)
            for key, child in value.items()
        }
    if isinstance(value, list):
        if not value:
            return "list"
        if all(isinstance(entry, dict) for entry in value):
            merged: object = _key_tree(value[0], f"{path}[]")
            for entry in value[1:]:
                merged = _merge_trees(merged, _key_tree(entry, f"{path}[]"))
            return {"[]": merged}
        return "scalarList"
    return _type_cat(value)


def _tree_label(node: object) -> str:
    if isinstance(node, dict):
        return "list-of-objects" if "[]" in node else "dict"
    return str(node)


def _compare_key_tree(golden_node: object, actual_node: object, path: str = "") -> list[str]:
    """Tree-vs-tree comparison; returns human-readable mismatch lines (empty == match).

    Bites on container-shape changes (key added/removed, dict<->scalar,
    list-of-objects<->scalars). Stays silent on the known runner-noise axes:
    nested scalar-category flips (null<->number etc.), empty-vs-populated lists,
    and anything under a pruned path.
    """
    out: list[str] = []
    label = path or "<root>"
    if golden_node == "pruned" or actual_node == "pruned":
        return out

    golden_is_dict = isinstance(golden_node, dict)
    actual_is_dict = isinstance(actual_node, dict)

    if golden_is_dict and actual_is_dict:
        golden_is_list = "[]" in golden_node
        actual_is_list = "[]" in actual_node
        if golden_is_list != actual_is_list:
            out.append(f"keyTree {label}: {_tree_label(golden_node)} -> {_tree_label(actual_node)}")
            return out
        if golden_is_list:
            return _compare_key_tree(golden_node["[]"], actual_node["[]"], f"{path}[]")
        golden_keys = set(golden_node)
        actual_keys = set(actual_node)
        for key in sorted(golden_keys - actual_keys):
            out.append(f"keyTree {label}: key removed: {key}")
        for key in sorted(actual_keys - golden_keys):
            out.append(f"keyTree {label}: key added: {key}")
        for key in sorted(golden_keys & actual_keys):
            out.extend(
                _compare_key_tree(golden_node[key], actual_node[key], f"{path}.{key}" if path else key)
            )
        return out

    if golden_is_dict != actual_is_dict:
        # Tolerated pairing: list-of-objects vs an empty-at-baseline list, in
        # either direction (counts flipping to/from zero is runner noise).
        dict_node = golden_node if golden_is_dict else actual_node
        leaf_node = actual_node if golden_is_dict else golden_node
        if isinstance(dict_node, dict) and "[]" in dict_node and leaf_node == "list":
            return out
        out.append(f"keyTree {label}: {_tree_label(golden_node)} -> {_tree_label(actual_node)}")
        return out

    # Both leaves.
    if golden_node == actual_node:
        return out
    if golden_node in _SCALAR_CATS and actual_node in _SCALAR_CATS:
        return out
    if golden_node in _LIST_LEAVES and actual_node in _LIST_LEAVES:
        return out
    out.append(f"keyTree {label}: {_tree_label(golden_node)} -> {_tree_label(actual_node)}")
    return out


def _decimals(value: float) -> int:
    """Decimal places in the shortest round-trip repr (0 for ints / scientific notation)."""
    text = repr(float(value))
    if "e" in text or "E" in text:
        return 0
    return len(text.split(".")[1]) if "." in text else 0


def _numbers_equal(golden: float, actual: float) -> bool:
    g = float(golden)
    a = float(actual)
    if math.isnan(g) or math.isnan(a):
        return math.isnan(g) and math.isnan(a)
    if math.isinf(g) or math.isinf(a):
        return g == a  # both +inf or both -inf
    rounding_step = 10.0 ** (-_decimals(g))
    # +1e-9 absorbs binary-float error comparing clean decimals at the step boundary
    # (e.g. 0.90 - 0.89 == 0.010000000000000009, just over a 0.01 step).
    return abs(a - g) <= max(ABS_TOL, REL_TOL * abs(g), rounding_step) + 1e-9


def _value_equal(golden: object, actual: object) -> bool:
    # bool before number: isinstance(True, int) is True, so a number path would accept True==1.
    if isinstance(golden, bool) or isinstance(actual, bool):
        return isinstance(golden, bool) and isinstance(actual, bool) and golden == actual
    if isinstance(golden, (int, float)) and isinstance(actual, (int, float)):
        return _numbers_equal(golden, actual)
    return golden == actual


def compare(golden: dict, actual: dict) -> list[str]:
    """Return human-readable mismatch lines (empty == match)."""
    out: list[str] = []

    expected_keys = set(golden["topLevelKeys"])
    actual_keys = set(actual)
    for key in sorted(expected_keys - actual_keys):
        out.append(f"top-level key removed: {key}")
    for key in sorted(actual_keys - expected_keys):
        out.append(f"top-level key added: {key}")

    expected_types = golden["topLevelTypes"]
    for key in sorted(expected_keys & actual_keys):
        expected = expected_types.get(key)
        actual_cat = _type_cat(actual[key])
        if expected != actual_cat:
            out.append(f"{key}: type {expected} -> {actual_cat}")

    for path in sorted(golden["coreValues"]):
        golden_value = golden["coreValues"][path]
        actual_value = _dotted_get(actual, path)
        if actual_value is _MISSING:
            out.append(f"{path}: missing in output")
        elif not _value_equal(golden_value, actual_value):
            out.append(f"{path}: {_fmt(golden_value)} != {_fmt(actual_value)}")

    return out


def build_golden(actual: dict) -> dict:
    core: dict[str, object] = {}
    for path in CORE_PATHS:
        value = _dotted_get(actual, path)
        if value is _MISSING:
            raise AssertionError(f"core path {path!r} not present in analyze.py output")
        core[path] = value
    return {
        "topLevelKeys": sorted(actual),
        "topLevelTypes": {key: _type_cat(value) for key, value in actual.items()},
        "coreValues": core,
        "keyTree": _key_tree(actual),
    }


class Phase1GoldenRegressionTests(unittest.TestCase):
    """Runs analyze.py once (default mode) and compares to the committed golden."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="phase1_golden_")
        cls.fixture_path = Path(cls._tmp.name) / "fixture.wav"
        _write_golden_fixture(cls.fixture_path)
        stdout, stderr = _run_analyze(_ANALYZE_PY, cls.fixture_path, [])
        try:
            cls.actual = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                "analyze.py did not emit valid JSON for the golden fixture.\n"
                f"stderr:\n{stderr[:800]}"
            ) from error

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_phase1_output_matches_golden(self) -> None:
        if os.environ.get(_UPDATE_ENV):
            self.skipTest(f"{_UPDATE_ENV} set; golden written by test_zzz_regenerate_golden")
        if not _GOLDEN_PATH.exists():
            self.fail(
                f"Golden snapshot missing at {_GOLDEN_PATH}.\n"
                f"Generate it with: {_UPDATE_ENV}=1 ./venv/bin/python -m unittest tests.test_phase1_golden"
            )
        golden = json.loads(_GOLDEN_PATH.read_text())
        mismatches = compare(golden, self.actual)
        if mismatches:
            self.fail(
                "Phase 1 analyze.py output drifted from the golden snapshot.\n"
                "If this change is intentional, regenerate with "
                f"{_UPDATE_ENV}=1 ./venv/bin/python -m unittest tests.test_phase1_golden\n\n"
                + "\n".join(mismatches)
            )

    def test_phase1_keytree_matches_golden(self) -> None:
        """Nested-structure gate (docstring item 3): the cross-app contract source.

        Separate from the main gate so a golden that predates ``keyTree`` skips
        VISIBLY (dormant, not silently green) until the next regeneration arms
        it — the frontend parity gate's nested check (Gate A3) arms off the same
        fixture key at the same moment.
        """
        if os.environ.get(_UPDATE_ENV):
            self.skipTest(f"{_UPDATE_ENV} set; golden written by test_zzz_regenerate_golden")
        if not _GOLDEN_PATH.exists():
            self.fail(
                f"Golden snapshot missing at {_GOLDEN_PATH}.\n"
                f"Generate it with: {_UPDATE_ENV}=1 ./venv/bin/python -m unittest tests.test_phase1_golden"
            )
        golden = json.loads(_GOLDEN_PATH.read_text())
        if "keyTree" not in golden:
            self.skipTest(
                "golden predates keyTree — nested-structure enforcement is DORMANT. Arm it by "
                f"regenerating: {_UPDATE_ENV}=1 ./venv/bin/python -m unittest tests.test_phase1_golden"
            )
        mismatches = _compare_key_tree(golden["keyTree"], _key_tree(self.actual))
        if mismatches:
            self.fail(
                "Phase 1 nested key structure drifted from the golden keyTree.\n"
                "If this change is intentional, regenerate with "
                f"{_UPDATE_ENV}=1 ./venv/bin/python -m unittest tests.test_phase1_golden\n"
                "and sync the frontend (the parity gate in "
                "apps/ui/tests/services/phase1ContractParity.test.ts names what to update).\n\n"
                + "\n".join(mismatches)
            )

    def test_zzz_regenerate_golden(self) -> None:
        if not os.environ.get(_UPDATE_ENV):
            self.skipTest(f"set {_UPDATE_ENV}=1 to regenerate the golden snapshot")
        _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GOLDEN_PATH.write_text(json.dumps(build_golden(self.actual), indent=2, sort_keys=True) + "\n")
        self.skipTest(f"regenerated golden snapshot at {_GOLDEN_PATH}")


class GoldenComparatorMetaTests(unittest.TestCase):
    """Proves the gate bites (and doesn't over-bite). Pure-Python, no analyze run."""

    @staticmethod
    def _golden() -> dict:
        return {
            "topLevelKeys": ["bpm", "key", "monoCompatible", "spectralBalance", "stemAnalysis"],
            "topLevelTypes": {
                "bpm": "number", "key": "str", "monoCompatible": "bool",
                "spectralBalance": "dict", "stemAnalysis": "null",
            },
            "coreValues": {
                "bpm": 135.4, "key": "A Minor", "monoCompatible": True,
                "spectralBalance.subBass": -12.5,
            },
        }

    @staticmethod
    def _actual() -> dict:
        return {
            "bpm": 135.4, "key": "A Minor", "monoCompatible": True,
            "spectralBalance": {"subBass": -12.5}, "stemAnalysis": None,
        }

    def test_identical_payload_matches(self) -> None:
        self.assertEqual(compare(self._golden(), self._actual()), [])

    def test_core_value_drift_beyond_tolerance_is_reported(self) -> None:
        actual = self._actual()
        actual["bpm"] = 136.5
        mismatches = compare(self._golden(), actual)
        self.assertTrue(any(m.startswith("bpm:") for m in mismatches), mismatches)

    def test_core_within_tolerance_nudge_is_silent(self) -> None:
        # A one-step cross-env rounding flip on a 1-decimal field must not bite.
        actual = self._actual()
        actual["bpm"] = 135.5
        self.assertEqual(compare(self._golden(), actual), [])

    def test_string_core_drift_is_reported(self) -> None:
        actual = self._actual()
        actual["key"] = "C Major"
        self.assertTrue(any(m.startswith("key:") for m in compare(self._golden(), actual)))

    def test_removed_and_added_top_level_keys_reported(self) -> None:
        actual = self._actual()
        del actual["key"]
        actual["newField"] = 1.0
        mismatches = compare(self._golden(), actual)
        self.assertTrue(any("removed: key" in m for m in mismatches), mismatches)
        self.assertTrue(any("added: newField" in m for m in mismatches), mismatches)

    def test_top_level_type_change_reported(self) -> None:
        actual = self._actual()
        actual["stemAnalysis"] = {"kick": {}}  # null -> dict (e.g. separation accidentally ran)
        self.assertTrue(any(m.startswith("stemAnalysis: type null -> dict") for m in compare(self._golden(), actual)))

    def test_missing_core_path_reported(self) -> None:
        actual = self._actual()
        actual["spectralBalance"] = {}  # subBass gone
        mismatches = compare(self._golden(), actual)
        self.assertTrue(any("spectralBalance.subBass: missing" in m for m in mismatches), mismatches)

    def test_bool_core_not_equal_to_number(self) -> None:
        actual = self._actual()
        actual["monoCompatible"] = 1  # bool True vs int 1 must bite
        self.assertTrue(any(m.startswith("monoCompatible:") for m in compare(self._golden(), actual)))

    def test_numbers_equal_rounding_and_nonfinite(self) -> None:
        self.assertTrue(_numbers_equal(135.4, 135.5))      # one 0.1 step -> tolerated
        self.assertFalse(_numbers_equal(135.4, 135.7))     # >1 step -> bites
        self.assertTrue(_numbers_equal(0.89, 0.90))        # one 0.01 step -> tolerated
        self.assertFalse(_numbers_equal(0.89, 0.92))       # >1 step -> bites
        self.assertTrue(_numbers_equal(float("nan"), float("nan")))
        self.assertFalse(_numbers_equal(float("nan"), 1.0))
        self.assertTrue(_numbers_equal(float("inf"), float("inf")))
        self.assertFalse(_numbers_equal(float("inf"), float("-inf")))


class KeyTreeMetaTests(unittest.TestCase):
    """Proves the keyTree gate bites (and doesn't over-bite). Pure-Python, no analyze run."""

    @staticmethod
    def _payload() -> dict:
        return {
            "bpm": 135.4,
            "reverbDetail": {
                "rt60": 1.2,
                "isWet": True,
                "perBandRt60": {"low": 1.4, "highs": None},
                "preDelayMs": 22.5,
            },
            "lufsCurve": {
                "shortTerm": [{"t": 0.0, "lufs": -12.4}, {"t": 3.0, "lufs": -9.1}],
                "momentary": [],
            },
            "spectralDetail": {"mfcc": [-512.4, 110.2]},
            "hihatDetail": None,
        }

    def test_generation_shape(self) -> None:
        self.assertEqual(
            _key_tree(self._payload()),
            {
                "bpm": "number",
                "reverbDetail": {
                    "rt60": "number",
                    "isWet": "bool",
                    "perBandRt60": {"low": "number", "highs": "null"},
                    "preDelayMs": "number",
                },
                "lufsCurve": {
                    "shortTerm": {"[]": {"t": "number", "lufs": "number"}},
                    "momentary": "list",
                },
                "spectralDetail": {"mfcc": "scalarList"},
                "hihatDetail": "null",
            },
        )

    def test_union_merge_across_heterogeneous_elements(self) -> None:
        # An optional key carried by only one element (and null in another)
        # must still be recorded, with the non-null category winning.
        tree = _key_tree({"peaks": [{"time": 1.0}, {"time": 2.0, "strength": 0.5}, {"strength": None}]})
        self.assertEqual(tree, {"peaks": {"[]": {"time": "number", "strength": "number"}}})

    def test_identical_payload_matches(self) -> None:
        self.assertEqual(_compare_key_tree(_key_tree(self._payload()), _key_tree(self._payload())), [])

    def test_nested_key_removed_bites(self) -> None:
        actual = self._payload()
        del actual["reverbDetail"]["preDelayMs"]
        mismatches = _compare_key_tree(_key_tree(self._payload()), _key_tree(actual))
        self.assertEqual(mismatches, ["keyTree reverbDetail: key removed: preDelayMs"])

    def test_nested_key_added_bites(self) -> None:
        actual = self._payload()
        actual["reverbDetail"]["earlyReflections"] = 0.4
        mismatches = _compare_key_tree(_key_tree(self._payload()), _key_tree(actual))
        self.assertEqual(mismatches, ["keyTree reverbDetail: key added: earlyReflections"])

    def test_nested_null_to_number_is_silent(self) -> None:
        actual = self._payload()
        actual["reverbDetail"]["perBandRt60"]["highs"] = 0.5  # null -> number: runner noise
        self.assertEqual(_compare_key_tree(_key_tree(self._payload()), _key_tree(actual)), [])

    def test_nested_scalar_to_dict_bites(self) -> None:
        actual = self._payload()
        actual["reverbDetail"]["preDelayMs"] = {"median": 22.5}
        mismatches = _compare_key_tree(_key_tree(self._payload()), _key_tree(actual))
        self.assertEqual(mismatches, ["keyTree reverbDetail.preDelayMs: number -> dict"])

    def test_nested_dict_to_null_bites(self) -> None:
        actual = self._payload()
        actual["reverbDetail"]["perBandRt60"] = None
        mismatches = _compare_key_tree(_key_tree(self._payload()), _key_tree(actual))
        self.assertEqual(mismatches, ["keyTree reverbDetail.perBandRt60: dict -> null"])

    def test_list_element_key_removed_bites(self) -> None:
        actual = self._payload()
        actual["lufsCurve"]["shortTerm"] = [{"t": 0.0}, {"t": 3.0}]
        mismatches = _compare_key_tree(_key_tree(self._payload()), _key_tree(actual))
        self.assertEqual(mismatches, ["keyTree lufsCurve.shortTerm[]: key removed: lufs"])

    def test_empty_actual_list_of_objects_is_silent(self) -> None:
        # Element count flipping to zero on another runner is noise, not drift.
        actual = self._payload()
        actual["lufsCurve"]["shortTerm"] = []
        self.assertEqual(_compare_key_tree(_key_tree(self._payload()), _key_tree(actual)), [])

    def test_empty_golden_list_populated_later_is_silent(self) -> None:
        actual = self._payload()
        actual["lufsCurve"]["momentary"] = [{"t": 0.0, "lufs": -11.8}]
        self.assertEqual(_compare_key_tree(_key_tree(self._payload()), _key_tree(actual)), [])

    def test_objects_list_to_scalar_list_bites(self) -> None:
        actual = self._payload()
        actual["lufsCurve"]["shortTerm"] = [-12.4, -9.1]
        mismatches = _compare_key_tree(_key_tree(self._payload()), _key_tree(actual))
        self.assertEqual(mismatches, ["keyTree lufsCurve.shortTerm: list-of-objects -> scalarList"])

    def test_scalar_list_to_objects_list_bites(self) -> None:
        golden_payload = self._payload()
        actual = self._payload()
        actual["spectralDetail"]["mfcc"] = [{"band": 0, "value": -512.4}]
        mismatches = _compare_key_tree(_key_tree(golden_payload), _key_tree(actual))
        self.assertEqual(mismatches, ["keyTree spectralDetail.mfcc: scalarList -> list-of-objects"])

    def test_pruned_path_is_silent(self) -> None:
        golden_tree = _key_tree(self._payload())
        golden_tree["reverbDetail"] = "pruned"
        actual = self._payload()
        actual["reverbDetail"] = {"completely": "different"}
        self.assertEqual(_compare_key_tree(golden_tree, _key_tree(actual)), [])


class BuildPhase1KeySupersetTests(unittest.TestCase):
    """The third hand-maintained reconstruction layer, made executable.

    ``_build_phase1`` in server_phase1.py rebuilds the HTTP-facing Phase 1
    payload as an explicit dict literal — an analyze.py top-level key that is
    never added there silently vanishes before the frontend can even see it,
    which neither the golden gates above (analyze.py output) nor the frontend
    parity gates (fixture/parser) can observe. This pins: every golden
    top-level key is forwarded, plus the declared envelope additions.
    """

    def test_build_phase1_forwards_every_golden_key(self) -> None:
        if not _GOLDEN_PATH.exists():
            self.skipTest(f"golden snapshot missing at {_GOLDEN_PATH}")
        from server_phase1 import _build_phase1

        golden = json.loads(_GOLDEN_PATH.read_text())
        built_keys = set(_build_phase1({}))
        missing = sorted(set(golden["topLevelKeys"]) - built_keys)
        self.assertEqual(
            missing,
            [],
            "_build_phase1 (server_phase1.py) does not forward these analyze.py "
            f"top-level keys, so they never reach the frontend: {missing}",
        )
        # The declared envelope-level additions the frontend parity gate
        # allowlists (ENVELOPE_ADDED_KEYS in phase1ContractParity.test.ts).
        self.assertLessEqual({"stereoWidth", "stereoCorrelation"}, built_keys)


if __name__ == "__main__":
    unittest.main()
