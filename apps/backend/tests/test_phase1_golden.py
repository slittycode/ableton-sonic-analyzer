"""Golden-snapshot regression gate for default-mode ``analyze.py`` output.

This runs ``analyze.py`` on a fixed, deterministic procedural fixture and asserts the
emitted JSON matches a committed golden snapshot within tolerance. It is a safety net for
changes to ``analyze.py`` / the DSP feature modules: any unintended drift in any output
field surfaces as a failed assertion that names the drifted path.

Determinism vs portability: the default analyze path (no ``--separate`` / ``--transcribe``)
is pure-DSP and contains no RNG / ML / timestamps; output was byte-identical across 5
repeated runs *in one environment*. Across environments it is not bit-identical: analyze.py
rounds every output float (1-4 decimals), and a different BLAS/thread order on the CI runner
can push a raw value across a rounding boundary, flipping the last digit by a whole step.
The comparator therefore tolerates one rounding step at each field's own precision (see
``_numbers_equal``) plus proportional/absolute float slack -- enough to be portable, while
still biting any change larger than a field's reported resolution and every
string/enum/key/list-length change. One field is excluded:
``melodyDetail.midiFile`` is the path of a transient MIDI artifact analyze writes next to
the input, so it varies per run/location and carries no measurement. Exclude a field by
adding its exact dotted path to ``EXCLUDED_PATHS`` rather than loosening the global
tolerance; excluded paths are stored in the golden as a placeholder so the key-set check
still holds and the comparator skips their values.

Regenerating the golden after an *intentional* output change (one command, from
``apps/backend/``):

    UPDATE_PHASE1_GOLDEN=1 ./venv/bin/python -m unittest tests.test_phase1_golden

The main gate test never writes; only ``test_zzz_regenerate_golden`` writes, and only when
that env var is set.
"""

import copy
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

# Numeric tolerance. Two numbers are equal iff
#   abs(a-g) <= max(ABS_TOL, REL_TOL*abs(g), one rounding step at g's decimal precision).
# The rounding-step term is the load-bearing one for cross-environment portability:
# analyze.py rounds every output float (1-4 decimals), and a different BLAS/thread order on
# another machine can nudge a raw value across a rounding boundary, flipping the last digit
# by a whole step (e.g. 135.4 -> 135.5). Absorbing one step at each field's own precision
# tolerates that while still biting changes larger than a field's reported resolution, plus
# every string/enum/key/list-length change (which are environment-stable).
ABS_TOL = 1e-3
REL_TOL = 1e-3

# Cap on reported mismatches so a large-array drift can't produce a multi-thousand-line
# failure (and so the comparator stops descending once the point is made).
MAX_REPORTED = 40

# Exact dotted paths to skip during comparison. Populated only from the determinism
# calibration when a field is shown to vary run-to-run / per-environment. Excluded paths
# are stored in the golden as the placeholder below (keeping the key-set check intact).
#   melodyDetail.midiFile -> absolute path of a transient MIDI artifact (per-run/location).
EXCLUDED_PATHS: set[str] = {"melodyDetail.midiFile"}
_EXCLUDED_PLACEHOLDER = "<excluded: non-deterministic per-run value>"


def _write_golden_fixture(path: Path, sample_rate: int = 44_100, duration_seconds: float = 6.0) -> None:
    """Deterministic A-minor harmonic bed (copied from test_analyze._write_key_fixture).

    Inlined rather than imported to keep this module self-contained and free of the
    cross-test-module import-path fragility the rest of the suite avoids. No RNG.
    """
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
    """Run analyze.py and return (stdout, stderr). Raises AssertionError on non-zero exit.

    Inlined from test_analyze._run_analyze for self-containment.
    """
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


def _join(path: str, key: str) -> str:
    return key if not path else f"{path}.{key}"


def _fmt(value: object) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


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
    # +1e-9 absorbs binary-float error when comparing clean decimal values at the step
    # boundary (e.g. 0.90 - 0.89 == 0.010000000000000009, just over a 0.01 step).
    return abs(a - g) <= max(ABS_TOL, REL_TOL * abs(g), rounding_step) + 1e-9


def _diff(golden: object, actual: object, path: str, out: list[str]) -> None:
    """Recursively collect mismatches between golden and actual into ``out`` (capped)."""
    if len(out) >= MAX_REPORTED or path in EXCLUDED_PATHS:
        return

    # None first.
    if golden is None or actual is None:
        if not (golden is None and actual is None):
            out.append(f"{path or '<root>'}: {_fmt(golden)} != {_fmt(actual)}")
        return

    # bool before number: in Python isinstance(True, int) is True and True == 1, so a
    # number branch would silently accept a bool/int swap.
    if isinstance(golden, bool) or isinstance(actual, bool):
        if not (isinstance(golden, bool) and isinstance(actual, bool) and golden == actual):
            out.append(f"{path or '<root>'}: {_fmt(golden)} != {_fmt(actual)}")
        return

    if isinstance(golden, str) or isinstance(actual, str):
        if not (isinstance(golden, str) and isinstance(actual, str) and golden == actual):
            out.append(f"{path or '<root>'}: {_fmt(golden)} != {_fmt(actual)}")
        return

    if isinstance(golden, (int, float)) or isinstance(actual, (int, float)):
        if not (
            isinstance(golden, (int, float))
            and isinstance(actual, (int, float))
            and _numbers_equal(golden, actual)
        ):
            out.append(f"{path or '<root>'}: {_fmt(golden)} != {_fmt(actual)}")
        return

    if isinstance(golden, dict) or isinstance(actual, dict):
        if not (isinstance(golden, dict) and isinstance(actual, dict)):
            out.append(f"{path or '<root>'}: type mismatch dict vs {type(actual).__name__}")
            return
        golden_keys = set(golden)
        actual_keys = set(actual)
        for key in sorted(golden_keys - actual_keys):
            if len(out) >= MAX_REPORTED:
                return
            out.append(f"{_join(path, key)}: missing in actual (removed key)")
        for key in sorted(actual_keys - golden_keys):
            if len(out) >= MAX_REPORTED:
                return
            out.append(f"{_join(path, key)}: unexpected in actual (added key)")
        for key in sorted(golden_keys & actual_keys):
            if len(out) >= MAX_REPORTED:
                return
            _diff(golden[key], actual[key], _join(path, key), out)
        return

    if isinstance(golden, list) or isinstance(actual, list):
        if not (isinstance(golden, list) and isinstance(actual, list)):
            out.append(f"{path or '<root>'}: type mismatch list vs {type(actual).__name__}")
            return
        if len(golden) != len(actual):
            out.append(f"{path or '<root>'}: list length {len(golden)} != {len(actual)}")
            return
        for index, (gv, av) in enumerate(zip(golden, actual)):
            if len(out) >= MAX_REPORTED:
                return
            _diff(gv, av, f"{path}[{index}]", out)
        return

    # Fallback for any non-JSON scalar.
    if golden != actual:
        out.append(f"{path or '<root>'}: {_fmt(golden)} != {_fmt(actual)}")


def diff(golden: object, actual: object) -> list[str]:
    """Return a (capped) list of human-readable mismatch lines; empty means match."""
    out: list[str] = []
    _diff(golden, actual, "", out)
    if len(out) >= MAX_REPORTED:
        out = out[:MAX_REPORTED]
        out.append(f"... (further mismatches truncated at {MAX_REPORTED})")
    return out


def _with_excluded_placeholders(payload: dict) -> dict:
    """Copy ``payload`` with each present EXCLUDED_PATHS leaf set to the placeholder.

    Keeps the excluded key in the golden (so the dict key-set check still passes) while
    not committing the volatile value. The comparator skips the value either way.
    """
    result = copy.deepcopy(payload)
    for dotted in EXCLUDED_PATHS:
        parts = dotted.split(".")
        node = result
        for key in parts[:-1]:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break
        if isinstance(node, dict) and parts[-1] in node:
            node[parts[-1]] = _EXCLUDED_PLACEHOLDER
    return result


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
        mismatches = diff(golden, self.actual)
        if mismatches:
            self.fail(
                "Phase 1 analyze.py output drifted from the golden snapshot.\n"
                "If this change is intentional, regenerate with "
                f"{_UPDATE_ENV}=1 ./venv/bin/python -m unittest tests.test_phase1_golden\n\n"
                + "\n".join(mismatches)
            )

    def test_zzz_regenerate_golden(self) -> None:
        if not os.environ.get(_UPDATE_ENV):
            self.skipTest(f"set {_UPDATE_ENV}=1 to regenerate the golden snapshot")
        _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = _with_excluded_placeholders(self.actual)
        _GOLDEN_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        self.skipTest(f"regenerated golden snapshot at {_GOLDEN_PATH}")


class GoldenComparatorMetaTests(unittest.TestCase):
    """Proves the comparator bites (and doesn't over-bite). Pure-Python, no analyze run."""

    @staticmethod
    def _golden() -> dict:
        return {
            "bpm": 120.0,
            "key": "A minor",
            "monoCompatible": True,
            "stemAnalysis": None,
            "spectralBalance": {"subBass": -12.5, "highs": -30.0},
            "beatGrid": [0.5, 1.0, 1.5, 2.0],
        }

    def test_numeric_drift_beyond_tolerance_is_reported(self) -> None:
        golden = self._golden()
        actual = copy.deepcopy(golden)
        actual["bpm"] = 120.0 + 10 * max(ABS_TOL, REL_TOL * 120.0)
        mismatches = diff(golden, actual)
        self.assertTrue(any(m.startswith("bpm:") for m in mismatches), mismatches)

    def test_within_tolerance_nudge_is_silent(self) -> None:
        golden = self._golden()
        actual = copy.deepcopy(golden)
        actual["bpm"] = 120.0 + 0.5 * max(ABS_TOL, REL_TOL * 120.0)
        self.assertEqual(diff(golden, actual), [])

    def test_identical_payloads_match(self) -> None:
        golden = self._golden()
        self.assertEqual(diff(golden, copy.deepcopy(golden)), [])

    def test_added_and_removed_keys_reported(self) -> None:
        golden = self._golden()
        actual = copy.deepcopy(golden)
        actual["newField"] = 1.0
        del actual["key"]
        mismatches = diff(golden, actual)
        self.assertTrue(any("newField" in m and "added" in m for m in mismatches), mismatches)
        self.assertTrue(any("key" in m and "removed" in m for m in mismatches), mismatches)

    def test_list_length_drift_reported(self) -> None:
        golden = self._golden()
        actual = copy.deepcopy(golden)
        actual["beatGrid"] = [0.5, 1.0]
        mismatches = diff(golden, actual)
        self.assertTrue(any(m.startswith("beatGrid:") and "length" in m for m in mismatches), mismatches)

    def test_nan_inf_bool_branches(self) -> None:
        nan = float("nan")
        inf = float("inf")
        self.assertEqual(diff({"x": nan}, {"x": nan}), [])        # both NaN -> equal
        self.assertEqual(diff({"x": inf}, {"x": inf}), [])        # both +inf -> equal
        self.assertNotEqual(diff({"x": nan}, {"x": 1.0}), [])     # NaN vs number
        self.assertNotEqual(diff({"x": inf}, {"x": -inf}), [])    # +inf vs -inf
        self.assertNotEqual(diff({"x": True}, {"x": 1}), [])      # bool vs int
        self.assertNotEqual(diff({"x": False}, {"x": 0.0}), [])   # bool vs float

    def test_type_mismatch_reported(self) -> None:
        self.assertNotEqual(diff({"x": {"a": 1}}, {"x": [1]}), [])  # dict vs list
        self.assertNotEqual(diff({"x": "s"}, {"x": 1.0}), [])       # str vs number
        self.assertNotEqual(diff({"x": 1.0}, {"x": None}), [])      # number vs None

    def test_rounding_boundary_flip_is_tolerated_but_real_change_bites(self) -> None:
        # 1-decimal field (step 0.1): a one-step cross-env flip is tolerated, >1 step bites.
        self.assertEqual(diff({"x": 135.4}, {"x": 135.5}), [])
        self.assertNotEqual(diff({"x": 135.4}, {"x": 135.6}), [])
        # 2-decimal field (step 0.01): one-step tolerated, larger bites.
        self.assertEqual(diff({"x": 0.89}, {"x": 0.90}), [])
        self.assertNotEqual(diff({"x": 0.89}, {"x": 0.92}), [])
        # Small-magnitude 1-decimal value (the case the tight tolerance used to fail on).
        self.assertEqual(diff({"x": 0.2}, {"x": 0.3}), [])
        self.assertNotEqual(diff({"x": 0.2}, {"x": 0.5}), [])

    def test_excluded_path_is_ignored(self) -> None:
        self.assertIn("melodyDetail.midiFile", EXCLUDED_PATHS)
        golden = {"melodyDetail": {"midiFile": _EXCLUDED_PLACEHOLDER, "confidence": 0.5}}
        actual = {"melodyDetail": {"midiFile": "/tmp/whatever/x_melody.mid", "confidence": 0.5}}
        self.assertEqual(diff(golden, actual), [])
        # A non-excluded sibling still bites.
        actual["melodyDetail"]["confidence"] = 0.9
        self.assertNotEqual(diff(golden, actual), [])

    def test_with_excluded_placeholders_sets_leaf(self) -> None:
        payload = {"melodyDetail": {"midiFile": "/tmp/abc/x_melody.mid", "confidence": 0.5}}
        result = _with_excluded_placeholders(payload)
        self.assertEqual(result["melodyDetail"]["midiFile"], _EXCLUDED_PLACEHOLDER)
        self.assertEqual(result["melodyDetail"]["confidence"], 0.5)
        self.assertEqual(payload["melodyDetail"]["midiFile"], "/tmp/abc/x_melody.mid")  # unmutated

    def test_cap_truncation(self) -> None:
        golden = {f"k{i:03d}": float(i) for i in range(200)}
        actual = {key: value + 5.0 for key, value in golden.items()}
        mismatches = diff(golden, actual)
        self.assertLessEqual(len(mismatches), MAX_REPORTED + 1)
        self.assertTrue(any("truncated" in m for m in mismatches), mismatches)


if __name__ == "__main__":
    unittest.main()
