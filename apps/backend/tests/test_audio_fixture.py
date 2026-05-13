import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np


EXPECTED_TOP_LEVEL_KEYS = {
    "bpm", "bpmConfidence", "bpmPercival", "bpmAgreement",
    "bpmDoubletime", "bpmSource", "bpmRawOriginal",
    "key", "keyConfidence", "keyProfile", "tuningFrequency", "tuningCents",
    "timeSignature", "timeSignatureSource",
    "timeSignatureConfidence", "durationSeconds", "sampleRate",
    "lufsIntegrated", "lufsRange", "lufsMomentaryMax", "lufsShortTermMax",
    "lufsCurve",
    "truePeak", "plr", "crestFactor",
    "dynamicSpread", "dynamicCharacter", "textureCharacter", "stereoDetail",
    "monoCompatible", "spectralBalance", "spectralBalanceTimeSeries",
    "spectralDetail", "stemAnalysis", "transientDensityDetail", "saturationDetail",
    "snareDetail", "hihatDetail",
    "rhythmDetail", "melodyDetail", "transcriptionDetail",
    "pitchDetail", "grooveDetail", "beatsLoudness", "rhythmTimeline",
    "sidechainDetail", "acidDetail", "reverbDetail",
    "vocalDetail", "supersawDetail", "bassDetail", "kickDetail",
    "genreDetail", "effectsDetail", "synthesisCharacter",
    "danceability", "structure", "arrangementDetail",
    "segmentLoudness", "segmentSpectral", "segmentStereo", "segmentKey",
    "chordDetail", "perceptual", "essentiaFeatures",
}

EXPECTED_SPECTRAL_BANDS = {
    "subBass", "lowBass", "lowMids", "mids",
    "upperMids", "highs", "brilliance",
}


def _write_smoke_fixture(
    path: Path,
    sample_rate: int = 44_100,
    duration_seconds: float = 8.0,
) -> None:
    """Composite fixture: A-minor triad + 120 BPM clicks + gentle fade."""
    total_samples = int(sample_rate * duration_seconds)
    time_axis = np.arange(total_samples, dtype=np.float32) / sample_rate

    harmonic = (
        0.30 * np.sin(2 * np.pi * 220.00 * time_axis)
        + 0.20 * np.sin(2 * np.pi * 261.63 * time_axis)
        + 0.20 * np.sin(2 * np.pi * 329.63 * time_axis)
        + 0.10 * np.sin(2 * np.pi * 440.00 * time_axis)
    ).astype(np.float32)

    bpm = 120.0
    beat_interval = int(round(sample_rate * 60.0 / bpm))
    click_samples = max(8, int(round(sample_rate * 10.0 / 1000.0)))
    click_shape = np.hanning(click_samples).astype(np.float32)
    clicks = np.zeros(total_samples, dtype=np.float32)
    for start in range(0, total_samples, beat_interval):
        stop = min(total_samples, start + click_samples)
        clicks[start:stop] += 0.7 * click_shape[: stop - start]

    envelope = np.linspace(1.0, 0.85, total_samples, dtype=np.float32)
    signal = (harmonic + clicks) * envelope

    stereo = np.stack([signal, signal], axis=1)
    pcm = np.clip(stereo, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def _run_analyze(analyze_path: Path, fixture_path: Path) -> tuple[str, str]:
    try:
        completed = subprocess.run(
            [sys.executable, str(analyze_path), str(fixture_path), "--yes"],
            cwd=analyze_path.parent,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise AssertionError(
            f"analyze.py failed.\nstdout:\n{error.stdout[:800]}\n"
            f"stderr:\n{error.stderr[:800]}"
        ) from error
    return completed.stdout, completed.stderr


class AudioFixtureSmokeTest(unittest.TestCase):
    """End-to-end smoke test: deterministic composite fixture -> full analyze.py -> pinned value assertions."""

    SAMPLE_RATE = 44_100
    FIXTURE_DURATION = 8.0

    EXPECTED_BPM = 120.0
    EXPECTED_BPM_TOLERANCE = 1.0
    EXPECTED_LUFS = -8.9
    EXPECTED_LUFS_TOLERANCE = 0.5
    EXPECTED_LUFS_RANGE = 0.8
    EXPECTED_LUFS_RANGE_TOLERANCE = 0.5
    EXPECTED_TRUE_PEAK = 1.0
    EXPECTED_TRUE_PEAK_TOLERANCE = 0.1
    EXPECTED_PLR = 9.9
    EXPECTED_PLR_TOLERANCE = 0.7
    EXPECTED_CREST_FACTOR = 11.0
    EXPECTED_CREST_FACTOR_TOLERANCE = 0.5

    EXPECTED_SPECTRAL = {
        "subBass": -21.5,
        "lowBass": -8.1,
        "lowMids": -9.6,
        "mids": -46.4,
        "upperMids": -67.2,
        "highs": -77.1,
        "brilliance": -78.4,
    }
    SPECTRAL_TOLERANCE = 2.0

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.analyze_path = cls.repo_root / "analyze.py"
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="sonic_analyzer_smoke_")
        cls.fixture_path = Path(cls.temp_dir.name) / "smoke_fixture.wav"
        _write_smoke_fixture(cls.fixture_path, cls.SAMPLE_RATE, cls.FIXTURE_DURATION)

        stdout, stderr = _run_analyze(cls.analyze_path, cls.fixture_path)
        try:
            cls.result = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                "analyze.py did not emit valid JSON for the smoke fixture.\n"
                f"stdout:\n{stdout[:800]}\nstderr:\n{stderr[:800]}"
            ) from error

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    # -- Tier 1: Exact-match fields --

    def test_sample_rate_exact(self) -> None:
        self.assertEqual(self.result["sampleRate"], self.SAMPLE_RATE)

    def test_time_signature_exact(self) -> None:
        self.assertEqual(self.result["timeSignature"], "4/4")
        self.assertEqual(self.result["timeSignatureSource"], "assumed_four_four")
        self.assertEqual(self.result["timeSignatureConfidence"], 0.0)

    def test_mono_compatible_exact(self) -> None:
        self.assertTrue(self.result["monoCompatible"])

    def test_bpm_agreement_exact(self) -> None:
        self.assertTrue(self.result["bpmAgreement"])
        self.assertFalse(self.result["bpmDoubletime"])
        self.assertEqual(self.result["bpmSource"], "rhythm_extractor_confirmed")

    # -- Tier 2: Tight-tolerance numeric fields --

    def test_duration(self) -> None:
        self.assertAlmostEqual(
            self.result["durationSeconds"],
            self.FIXTURE_DURATION,
            delta=0.15,
        )

    def test_bpm(self) -> None:
        self.assertAlmostEqual(
            self.result["bpm"],
            self.EXPECTED_BPM,
            delta=self.EXPECTED_BPM_TOLERANCE,
        )

    def test_lufs_integrated(self) -> None:
        self.assertAlmostEqual(
            self.result["lufsIntegrated"],
            self.EXPECTED_LUFS,
            delta=self.EXPECTED_LUFS_TOLERANCE,
        )

    def test_lufs_range(self) -> None:
        self.assertAlmostEqual(
            self.result["lufsRange"],
            self.EXPECTED_LUFS_RANGE,
            delta=self.EXPECTED_LUFS_RANGE_TOLERANCE,
        )

    def test_true_peak(self) -> None:
        self.assertAlmostEqual(
            self.result["truePeak"],
            self.EXPECTED_TRUE_PEAK,
            delta=self.EXPECTED_TRUE_PEAK_TOLERANCE,
        )

    def test_plr(self) -> None:
        self.assertAlmostEqual(
            self.result["plr"],
            self.EXPECTED_PLR,
            delta=self.EXPECTED_PLR_TOLERANCE,
        )

    def test_crest_factor(self) -> None:
        self.assertAlmostEqual(
            self.result["crestFactor"],
            self.EXPECTED_CREST_FACTOR,
            delta=self.EXPECTED_CREST_FACTOR_TOLERANCE,
        )

    def test_stereo_detail(self) -> None:
        stereo = self.result["stereoDetail"]
        self.assertIsInstance(stereo, dict)
        self.assertAlmostEqual(stereo["stereoWidth"], 0.0, delta=0.01)
        self.assertAlmostEqual(stereo["stereoCorrelation"], 1.0, delta=0.01)

    # -- Tier 3: Key detection --

    def test_key_detection(self) -> None:
        self.assertIn(self.result["key"], {"A Minor", "C Major"})
        self.assertIsInstance(self.result["keyConfidence"], (int, float))
        self.assertGreater(self.result["keyConfidence"], 0.3)

    # -- Tier 4: Spectral balance bands --

    def test_spectral_balance_bands(self) -> None:
        spectral = self.result["spectralBalance"]
        self.assertIsInstance(spectral, dict)
        self.assertEqual(set(spectral.keys()), EXPECTED_SPECTRAL_BANDS)

        for band, expected_value in self.EXPECTED_SPECTRAL.items():
            with self.subTest(band=band):
                self.assertAlmostEqual(
                    spectral[band],
                    expected_value,
                    delta=self.SPECTRAL_TOLERANCE,
                    msg=f"spectralBalance.{band} drifted from pinned value",
                )

    # -- Tier 5: Detail objects --

    def test_rhythm_detail(self) -> None:
        rhythm = self.result["rhythmDetail"]
        self.assertIsInstance(rhythm, dict)
        beat_grid = rhythm.get("beatGrid")
        self.assertIsInstance(beat_grid, list)
        self.assertGreater(len(beat_grid), 10)
        beat_positions = rhythm.get("beatPositions")
        self.assertIsInstance(beat_positions, list)
        self.assertEqual(len(beat_positions), len(beat_grid))
        self.assertTrue(all(p in {1, 2, 3, 4} for p in beat_positions))
        downbeats = rhythm.get("downbeats")
        self.assertIsInstance(downbeats, list)
        self.assertGreater(len(downbeats), 0)

    def test_groove_detail(self) -> None:
        groove = self.result["grooveDetail"]
        self.assertIsInstance(groove, dict)

    def test_beats_loudness(self) -> None:
        beats = self.result["beatsLoudness"]
        self.assertIsInstance(beats, dict)

    def test_structure(self) -> None:
        structure = self.result["structure"]
        self.assertIsInstance(structure, dict)
        segments = structure.get("segments")
        self.assertIsInstance(segments, list)
        self.assertGreater(len(segments), 0)

    def test_danceability(self) -> None:
        dance = self.result["danceability"]
        self.assertIsInstance(dance, dict)
        self.assertIn("danceability", dance)
        self.assertIsInstance(dance["danceability"], (int, float))
        self.assertGreaterEqual(dance["danceability"], 0.0)
        self.assertLessEqual(dance["danceability"], 3.0)

    def test_dynamic_character(self) -> None:
        dc = self.result["dynamicCharacter"]
        self.assertIsInstance(dc, dict)

    def test_texture_character(self) -> None:
        tc = self.result["textureCharacter"]
        self.assertIsInstance(tc, dict)

    def test_acid_detail_negative(self) -> None:
        acid = self.result["acidDetail"]
        self.assertIsInstance(acid, dict)
        self.assertFalse(acid["isAcid"])

    def test_reverb_detail_negative(self) -> None:
        reverb = self.result["reverbDetail"]
        self.assertIsInstance(reverb, dict)
        self.assertFalse(reverb["isWet"])

    def test_remaining_detail_fields_populated(self) -> None:
        for field in ("bassDetail", "kickDetail", "genreDetail", "effectsDetail",
                      "synthesisCharacter", "perceptual", "essentiaFeatures"):
            with self.subTest(field=field):
                self.assertIsNotNone(
                    self.result[field],
                    f"{field} should be populated in full mode",
                )

    def test_chord_detail_present(self) -> None:
        self.assertIn("chordDetail", self.result)

    # -- Tier 6: Expected nulls --

    def test_transcription_detail_null(self) -> None:
        self.assertIsNone(self.result["transcriptionDetail"])

    def test_pitch_detail_null(self) -> None:
        self.assertIsNone(self.result["pitchDetail"])

    # -- Tier 7: Schema completeness --

    def test_output_contains_all_expected_keys(self) -> None:
        self.assertEqual(
            set(self.result.keys()),
            EXPECTED_TOP_LEVEL_KEYS,
            "Output schema diverged from expected top-level keys.",
        )


if __name__ == "__main__":
    unittest.main()
