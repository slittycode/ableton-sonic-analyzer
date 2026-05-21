"""Regression gate over default-mode ``analyze.py`` output.

Runs ``analyze.py`` on a fixed deterministic fixture and asserts two things against a
committed golden:

1. **Contract / structure** -- the exact set of top-level keys and each one's type category
   (null / bool / number / str / list / dict). Catches added/removed fields, a field
   changing type, or a detector silently returning null.
2. **Core measurement values** -- a curated set of environment-stable, high-value Phase 1
   measurements (BPM, key, loudness, true-peak, crest, spectral balance, stereo), compared
   with tolerance.

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


if __name__ == "__main__":
    unittest.main()
