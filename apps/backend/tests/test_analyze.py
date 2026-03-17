import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np


EXPECTED_SPECTRAL_BANDS = {
    "subBass",
    "lowBass",
    "mids",
    "upperMids",
    "highs",
    "brilliance",
}

# Top-level keys emitted by both full and fast modes — the shared output contract.
EXPECTED_TOP_LEVEL_KEYS = {
    "bpm", "bpmConfidence", "bpmPercival", "bpmAgreement",
    "key", "keyConfidence", "timeSignature", "durationSeconds", "sampleRate",
    "lufsIntegrated", "lufsRange", "truePeak", "crestFactor",
    "dynamicSpread", "dynamicCharacter", "stereoDetail", "spectralBalance",
    "spectralDetail", "rhythmDetail", "melodyDetail", "transcriptionDetail",
    "grooveDetail", "sidechainDetail", "effectsDetail", "synthesisCharacter",
    "danceability", "structure", "arrangementDetail",
    "segmentLoudness", "segmentSpectral", "segmentStereo", "segmentKey",
    "chordDetail", "perceptual", "essentiaFeatures",
}

# Fields fast mode populates with real values.
FAST_MODE_POPULATED_FIELDS = {
    "bpm", "bpmConfidence", "bpmPercival", "bpmAgreement",
    "key", "keyConfidence", "timeSignature", "durationSeconds", "sampleRate",
    "lufsIntegrated", "lufsRange", "truePeak", "crestFactor",
}

# Fields fast mode intentionally skips — must be None in fast output.
FAST_MODE_NULL_FIELDS = EXPECTED_TOP_LEVEL_KEYS - FAST_MODE_POPULATED_FIELDS


def _write_test_fixture(path: Path, sample_rate: int = 44_100, duration_seconds: float = 6.0) -> None:
    """Write a synthetic WAV fixture: periodic 440 Hz bursts with amplitude envelope."""
    total_samples = int(sample_rate * duration_seconds)
    signal = np.zeros(total_samples, dtype=np.float32)
    burst_length = int(0.08 * sample_rate)
    burst_period = int(0.5 * sample_rate)

    for start in range(0, total_samples, burst_period):
        stop = min(start + burst_length, total_samples)
        burst_sample_count = stop - start
        time_axis = np.arange(burst_sample_count, dtype=np.float32) / sample_rate
        envelope = np.linspace(1.0, 0.0, burst_sample_count, dtype=np.float32)
        burst = 0.35 * np.sin(2 * np.pi * 440.0 * time_axis) * envelope
        signal[start:stop] = burst

    stereo = np.stack([signal, signal], axis=1)
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


class AnalyzeStructuralSnapshotTests(unittest.TestCase):
    FIXTURE_DURATION_SECONDS = 6.0
    SAMPLE_RATE = 44_100

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.analyze_path = cls.repo_root / "analyze.py"
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="sonic_analyzer_test_")
        cls.fixture_path = Path(cls.temp_dir.name) / "fixture.wav"
        _write_test_fixture(cls.fixture_path, cls.SAMPLE_RATE, cls.FIXTURE_DURATION_SECONDS)
        cls.stdout, cls.stderr = _run_analyze(cls.analyze_path, cls.fixture_path, [])

        try:
            cls.payload = json.loads(cls.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                "analyze.py did not emit valid JSON for the generated fixture.\n"
                f"stdout:\n{cls.stdout[:800]}\n"
                f"stderr:\n{cls.stderr[:800]}"
            ) from error

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    @staticmethod
    def _snippet(text: str, max_chars: int = 800) -> str:
        normalized = (text or "").strip()
        if not normalized:
            return "<empty>"
        return normalized[:max_chars]

    def test_output_contains_expected_raw_top_level_fields(self) -> None:
        for key in (
            "bpm",
            "key",
            "timeSignature",
            "durationSeconds",
            "sampleRate",
            "lufsIntegrated",
            "truePeak",
            "stereoDetail",
            "spectralBalance",
        ):
            self.assertIn(
                key,
                self.payload,
                f"Missing top-level key {key!r}.\nstdout:\n{self._snippet(self.stdout)}",
            )

    def test_core_fields_are_present_with_plausible_types(self) -> None:
        self.assertIsInstance(self.payload["bpm"], (int, float))
        self.assertGreater(self.payload["bpm"], 0)
        self.assertIsInstance(self.payload["key"], str)
        self.assertTrue(self.payload["key"].strip())
        self.assertIsInstance(self.payload["timeSignature"], str)
        self.assertTrue(self.payload["timeSignature"].strip())
        self.assertIsInstance(self.payload["sampleRate"], (int, float))
        self.assertGreater(self.payload["sampleRate"], 0)
        self.assertIsInstance(self.payload["lufsIntegrated"], (int, float))
        self.assertTrue(np.isfinite(self.payload["lufsIntegrated"]))
        self.assertIsInstance(self.payload["truePeak"], (int, float))
        self.assertTrue(np.isfinite(self.payload["truePeak"]))

    def test_duration_is_close_to_fixture_length(self) -> None:
        self.assertIsInstance(self.payload["durationSeconds"], (int, float))
        self.assertAlmostEqual(
            self.payload["durationSeconds"],
            self.FIXTURE_DURATION_SECONDS,
            delta=0.15,
        )

    def test_stereo_detail_contains_numeric_width_and_correlation(self) -> None:
        stereo_detail = self.payload["stereoDetail"]
        self.assertIsInstance(stereo_detail, dict)
        self.assertIn("stereoWidth", stereo_detail)
        self.assertIn("stereoCorrelation", stereo_detail)
        self.assertIsInstance(stereo_detail["stereoWidth"], (int, float))
        self.assertTrue(np.isfinite(stereo_detail["stereoWidth"]))
        self.assertGreaterEqual(stereo_detail["stereoWidth"], 0.0)
        self.assertLessEqual(stereo_detail["stereoWidth"], 2.0)
        self.assertIsInstance(stereo_detail["stereoCorrelation"], (int, float))
        self.assertTrue(np.isfinite(stereo_detail["stereoCorrelation"]))
        self.assertGreaterEqual(stereo_detail["stereoCorrelation"], -1.0)
        self.assertLessEqual(stereo_detail["stereoCorrelation"], 1.0)

    def test_spectral_balance_has_six_numeric_bands(self) -> None:
        spectral_balance = self.payload["spectralBalance"]
        self.assertIsInstance(spectral_balance, dict)
        self.assertEqual(set(spectral_balance.keys()), EXPECTED_SPECTRAL_BANDS)

        for band_name, value in spectral_balance.items():
            self.assertIsInstance(value, (int, float), f"{band_name} should be numeric")
            self.assertTrue(np.isfinite(value), f"{band_name} should be finite")


class AnalyzeFastStructuralSnapshotTests(unittest.TestCase):
    """Parallel snapshot tests for --fast mode.

    Fast mode is expected to populate core fields (BPM, key, loudness, dynamics)
    and leave all detail/structure fields as None. Tests assert both that the fast
    path completes correctly and that it is intentionally different from full mode
    in exactly the ways the implementation promises.
    """

    FIXTURE_DURATION_SECONDS = 6.0
    SAMPLE_RATE = 44_100

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.analyze_path = cls.repo_root / "analyze.py"
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="sonic_analyzer_fast_test_")
        cls.fixture_path = Path(cls.temp_dir.name) / "fixture.wav"
        _write_test_fixture(cls.fixture_path, cls.SAMPLE_RATE, cls.FIXTURE_DURATION_SECONDS)
        cls.stdout, cls.stderr = _run_analyze(cls.analyze_path, cls.fixture_path, ["--fast"])

        try:
            cls.payload = json.loads(cls.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                "analyze.py --fast did not emit valid JSON.\n"
                f"stdout:\n{cls.stdout[:800]}\n"
                f"stderr:\n{cls.stderr[:800]}"
            ) from error

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_output_schema_matches_full_mode(self) -> None:
        """Fast mode must emit the same top-level key set as full mode."""
        self.assertEqual(
            set(self.payload.keys()),
            EXPECTED_TOP_LEVEL_KEYS,
            "Fast mode output schema diverged from full mode. Update EXPECTED_TOP_LEVEL_KEYS "
            "if the output contract changed intentionally.",
        )

    def test_core_fields_are_populated(self) -> None:
        """Core fields must be non-None with plausible types."""
        numeric_fields = {
            "bpm", "bpmConfidence", "durationSeconds", "sampleRate",
            "lufsIntegrated", "truePeak", "crestFactor",
        }
        for field in numeric_fields:
            with self.subTest(field=field):
                value = self.payload[field]
                self.assertIsNotNone(value, f"{field!r} should be populated in fast mode")
                self.assertIsInstance(value, (int, float), f"{field!r} should be numeric")
                self.assertTrue(np.isfinite(value), f"{field!r} should be finite")

        self.assertIsInstance(self.payload["key"], str)
        self.assertTrue(self.payload["key"].strip(), "key should be a non-empty string")
        self.assertIsInstance(self.payload["timeSignature"], str)
        self.assertTrue(self.payload["timeSignature"].strip(), "timeSignature should be non-empty")

    def test_duration_matches_fixture(self) -> None:
        """Regression: audio must actually be loaded and measured correctly in fast mode."""
        self.assertAlmostEqual(
            self.payload["durationSeconds"],
            self.FIXTURE_DURATION_SECONDS,
            delta=0.15,
            msg="durationSeconds should match the fixture length — audio loading may be broken",
        )

    def test_detail_fields_are_null(self) -> None:
        """Fast mode must set all non-core detail fields to None.

        This is the core contract: fast mode trades detail for speed. If any of
        these fields are non-None, the fast path ran more analysis than intended.
        """
        for field in sorted(FAST_MODE_NULL_FIELDS):
            with self.subTest(field=field):
                self.assertIsNone(
                    self.payload[field],
                    f"{field!r} should be None in fast mode — fast path may have run full analysis",
                )

    def test_bpm_is_in_plausible_range(self) -> None:
        """BPM from fast mode should land in a realistic musical range."""
        bpm = self.payload["bpm"]
        self.assertGreater(bpm, 40, "BPM suspiciously low — fast path BPM extraction may be broken")
        self.assertLess(bpm, 300, "BPM suspiciously high — fast path BPM extraction may be broken")

    def test_sample_rate_matches_fixture(self) -> None:
        """Regression: sampleRate in output must reflect the actual fixture sample rate."""
        self.assertEqual(
            self.payload["sampleRate"],
            self.SAMPLE_RATE,
            "sampleRate should match the fixture — audio loading or sample rate passthrough broken",
        )


if __name__ == "__main__":
    unittest.main()
