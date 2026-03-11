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


class AnalyzeStructuralSnapshotTests(unittest.TestCase):
    FIXTURE_DURATION_SECONDS = 6.0
    SAMPLE_RATE = 44_100

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.analyze_path = cls.repo_root / "analyze.py"
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="sonic_analyzer_test_")
        cls.fixture_path = Path(cls.temp_dir.name) / "fixture.wav"
        cls._write_fixture(cls.fixture_path)

        try:
            completed = subprocess.run(
                [sys.executable, str(cls.analyze_path), str(cls.fixture_path), "--yes"],
                cwd=cls.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            raise AssertionError(
                "analyze.py failed for the generated fixture.\n"
                f"stdout:\n{cls._snippet(error.stdout)}\n"
                f"stderr:\n{cls._snippet(error.stderr)}"
            ) from error

        cls.stdout = completed.stdout
        cls.stderr = completed.stderr

        try:
            cls.payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                "analyze.py did not emit valid JSON for the generated fixture.\n"
                f"stdout:\n{cls._snippet(completed.stdout)}\n"
                f"stderr:\n{cls._snippet(completed.stderr)}"
            ) from error

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    @classmethod
    def _write_fixture(cls, path: Path) -> None:
        total_samples = int(cls.SAMPLE_RATE * cls.FIXTURE_DURATION_SECONDS)
        signal = np.zeros(total_samples, dtype=np.float32)
        burst_length = int(0.08 * cls.SAMPLE_RATE)
        burst_period = int(0.5 * cls.SAMPLE_RATE)

        for start in range(0, total_samples, burst_period):
            stop = min(start + burst_length, total_samples)
            burst_sample_count = stop - start
            time_axis = np.arange(burst_sample_count, dtype=np.float32) / cls.SAMPLE_RATE
            envelope = np.linspace(1.0, 0.0, burst_sample_count, dtype=np.float32)
            burst = 0.35 * np.sin(2 * np.pi * 440.0 * time_axis) * envelope
            signal[start:stop] = burst

        stereo = np.stack([signal, signal], axis=1)
        pcm = np.clip(stereo, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16)

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(cls.SAMPLE_RATE)
            wav_file.writeframes(pcm.tobytes())

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


if __name__ == "__main__":
    unittest.main()
