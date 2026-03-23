import json
import os
import tempfile
import unittest
import wave

import numpy as np


def _create_test_wav(path: str, duration: float = 2.0, sr: int = 44100) -> None:
    """Write a short sine-wave WAV file for testing."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # 440 Hz sine + 1000 Hz harmonic
    signal = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 1000 * t)
    pcm = (signal * 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


class SpectrogramGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="spectral_viz_test_")
        self.audio_path = os.path.join(self.temp_dir.name, "test.wav")
        _create_test_wav(self.audio_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_spectrograms_produces_mel_png_only(self) -> None:
        from spectral_viz import generate_spectrograms

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_spectrograms(self.audio_path, out_dir)

        self.assertIn("spectrogram_mel", result)
        self.assertNotIn("spectrogram_chroma", result)

        for kind, path in result.items():
            self.assertTrue(os.path.isfile(path), f"{kind} file missing: {path}")
            size = os.path.getsize(path)
            self.assertGreater(size, 1000, f"{kind} PNG suspiciously small: {size} bytes")

    def test_mel_spectrogram_is_valid_png(self) -> None:
        from spectral_viz import generate_spectrograms

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_spectrograms(self.audio_path, out_dir)
        with open(result["spectrogram_mel"], "rb") as f:
            header = f.read(8)
        # PNG magic bytes
        self.assertEqual(header[:4], b"\x89PNG")


class SpectralTimeSeriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="spectral_viz_test_")
        self.audio_path = os.path.join(self.temp_dir.name, "test.wav")
        _create_test_wav(self.audio_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_compute_returns_all_required_keys(self) -> None:
        from spectral_viz import compute_spectral_time_series

        ts = compute_spectral_time_series(self.audio_path)

        required_keys = {
            "timePoints",
            "spectralCentroid",
            "spectralRolloff",
            "spectralBandwidth",
            "spectralFlatness",
            "sampleRate",
            "hopLength",
            "originalFrameCount",
            "downsampledTo",
        }
        self.assertEqual(required_keys, set(ts.keys()))

    def test_all_feature_arrays_same_length_as_time_points(self) -> None:
        from spectral_viz import compute_spectral_time_series

        ts = compute_spectral_time_series(self.audio_path)
        n = len(ts["timePoints"])
        self.assertGreater(n, 0)
        for key in ("spectralCentroid", "spectralRolloff", "spectralBandwidth", "spectralFlatness"):
            self.assertEqual(len(ts[key]), n, f"{key} length mismatch")

    def test_downsampling_respects_max_points(self) -> None:
        from spectral_viz import compute_spectral_time_series

        ts = compute_spectral_time_series(self.audio_path, max_points=50)
        self.assertLessEqual(ts["downsampledTo"], 50)
        self.assertEqual(len(ts["timePoints"]), ts["downsampledTo"])

    def test_short_audio_returns_fewer_than_max_points(self) -> None:
        from spectral_viz import compute_spectral_time_series

        # 2-second file at 44100/1024 hop ≈ 86 frames, less than default 500
        ts = compute_spectral_time_series(self.audio_path)
        self.assertLess(ts["downsampledTo"], 500)
        self.assertEqual(ts["originalFrameCount"], ts["downsampledTo"])

    def test_time_series_is_json_serializable(self) -> None:
        from spectral_viz import compute_spectral_time_series

        ts = compute_spectral_time_series(self.audio_path)
        serialized = json.dumps(ts)
        roundtripped = json.loads(serialized)
        self.assertEqual(ts, roundtripped)

    def test_centroid_in_reasonable_range_for_known_signal(self) -> None:
        from spectral_viz import compute_spectral_time_series

        # 440 Hz + 1000 Hz signal → centroid should be between 400 and 2000 Hz
        ts = compute_spectral_time_series(self.audio_path)
        mean_centroid = sum(ts["spectralCentroid"]) / len(ts["spectralCentroid"])
        self.assertGreater(mean_centroid, 400)
        self.assertLess(mean_centroid, 2000)

    def test_flatness_in_zero_to_one_range(self) -> None:
        from spectral_viz import compute_spectral_time_series

        ts = compute_spectral_time_series(self.audio_path)
        for v in ts["spectralFlatness"]:
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)


class GenerateAllArtifactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="spectral_viz_test_")
        self.audio_path = os.path.join(self.temp_dir.name, "test.wav")
        _create_test_wav(self.audio_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_all_produces_two_artifacts(self) -> None:
        from spectral_viz import generate_all_artifacts

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_all_artifacts(self.audio_path, out_dir)

        self.assertIn("spectrogram_mel", result)
        self.assertNotIn("spectrogram_chroma", result)
        self.assertIn("spectral_time_series", result)
        self.assertEqual(len(result), 2)
        for path in result.values():
            self.assertTrue(os.path.isfile(path))

    def test_time_series_json_file_is_valid(self) -> None:
        from spectral_viz import generate_all_artifacts

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_all_artifacts(self.audio_path, out_dir)

        with open(result["spectral_time_series"]) as f:
            ts = json.load(f)
        self.assertIn("timePoints", ts)
        self.assertIn("spectralCentroid", ts)

    def test_uses_temp_dir_when_output_dir_omitted(self) -> None:
        from spectral_viz import generate_all_artifacts

        result = generate_all_artifacts(self.audio_path)
        for path in result.values():
            self.assertTrue(os.path.isfile(path))


class CQTSpectrogramTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="spectral_viz_test_")
        self.audio_path = os.path.join(self.temp_dir.name, "test.wav")
        _create_test_wav(self.audio_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_cqt_produces_valid_png(self) -> None:
        from spectral_viz import generate_cqt_spectrogram

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_cqt_spectrogram(self.audio_path, out_dir)
        self.assertIn("spectrogram_cqt", result)
        path = result["spectrogram_cqt"]
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(4), b"\x89PNG")

    def test_cqt_png_has_reasonable_size(self) -> None:
        from spectral_viz import generate_cqt_spectrogram

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_cqt_spectrogram(self.audio_path, out_dir)
        size = os.path.getsize(result["spectrogram_cqt"])
        self.assertGreater(size, 1000)


class HPSSSpectrogramTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="spectral_viz_test_")
        self.audio_path = os.path.join(self.temp_dir.name, "test.wav")
        _create_test_wav(self.audio_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_hpss_produces_two_pngs(self) -> None:
        from spectral_viz import generate_hpss_spectrograms

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_hpss_spectrograms(self.audio_path, out_dir)
        self.assertIn("spectrogram_harmonic", result)
        self.assertIn("spectrogram_percussive", result)
        for path in result.values():
            self.assertTrue(os.path.isfile(path))

    def test_hpss_pngs_are_valid(self) -> None:
        from spectral_viz import generate_hpss_spectrograms

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_hpss_spectrograms(self.audio_path, out_dir)
        for path in result.values():
            with open(path, "rb") as f:
                self.assertEqual(f.read(4), b"\x89PNG")


class OnsetStrengthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="spectral_viz_test_")
        self.audio_path = os.path.join(self.temp_dir.name, "test.wav")
        _create_test_wav(self.audio_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_compute_returns_required_keys(self) -> None:
        from spectral_viz import compute_onset_strength

        result = compute_onset_strength(self.audio_path)
        for key in ("timePoints", "onsetStrength", "sampleRate", "hopLength",
                     "originalFrameCount", "downsampledTo"):
            self.assertIn(key, result)

    def test_onset_arrays_same_length_as_time_points(self) -> None:
        from spectral_viz import compute_onset_strength

        result = compute_onset_strength(self.audio_path)
        self.assertEqual(len(result["timePoints"]), len(result["onsetStrength"]))

    def test_onset_values_are_non_negative(self) -> None:
        from spectral_viz import compute_onset_strength

        result = compute_onset_strength(self.audio_path)
        for v in result["onsetStrength"]:
            self.assertGreaterEqual(v, 0.0)

    def test_onset_is_json_serializable(self) -> None:
        from spectral_viz import compute_onset_strength

        result = compute_onset_strength(self.audio_path)
        roundtripped = json.loads(json.dumps(result))
        self.assertEqual(result, roundtripped)


class ChromaDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="spectral_viz_test_")
        self.audio_path = os.path.join(self.temp_dir.name, "test.wav")
        _create_test_wav(self.audio_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_compute_returns_required_keys(self) -> None:
        from spectral_viz import compute_chroma_data

        result = compute_chroma_data(self.audio_path)
        for key in ("timePoints", "pitchClasses", "chroma", "sampleRate",
                     "hopLength", "originalFrameCount", "downsampledTo"):
            self.assertIn(key, result)

    def test_chroma_has_12_pitch_classes(self) -> None:
        from spectral_viz import compute_chroma_data

        result = compute_chroma_data(self.audio_path)
        self.assertEqual(len(result["pitchClasses"]), 12)
        self.assertEqual(len(result["chroma"]), 12)

    def test_chroma_rows_match_time_points_length(self) -> None:
        from spectral_viz import compute_chroma_data

        result = compute_chroma_data(self.audio_path)
        n = len(result["timePoints"])
        for i, row in enumerate(result["chroma"]):
            self.assertEqual(len(row), n, f"chroma row {i} length mismatch")

    def test_chroma_values_in_zero_to_one_range(self) -> None:
        from spectral_viz import compute_chroma_data

        result = compute_chroma_data(self.audio_path)
        for row in result["chroma"]:
            for v in row:
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0001)  # small tolerance for rounding

    def test_chroma_is_json_serializable(self) -> None:
        from spectral_viz import compute_chroma_data

        result = compute_chroma_data(self.audio_path)
        roundtripped = json.loads(json.dumps(result))
        self.assertEqual(result, roundtripped)


class ChromaEnhancementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="spectral_viz_test_")
        self.audio_path = os.path.join(self.temp_dir.name, "test.wav")
        _create_test_wav(self.audio_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_produces_png_and_json(self) -> None:
        from spectral_viz import generate_chroma_enhancement

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_chroma_enhancement(self.audio_path, out_dir)

        self.assertIn("spectrogram_chroma", result)
        self.assertIn("chroma_interactive", result)
        for path in result.values():
            self.assertTrue(os.path.isfile(path))
        # PNG header check
        with open(result["spectrogram_chroma"], "rb") as f:
            self.assertEqual(f.read(4), b"\x89PNG")

    def test_json_has_required_keys(self) -> None:
        from spectral_viz import generate_chroma_enhancement

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_chroma_enhancement(self.audio_path, out_dir)
        with open(result["chroma_interactive"]) as f:
            data = json.load(f)
        for key in ("timePoints", "pitchClasses", "chroma", "sampleRate",
                     "hopLength", "originalFrameCount", "downsampledTo"):
            self.assertIn(key, data)
        self.assertEqual(len(data["pitchClasses"]), 12)
        self.assertEqual(len(data["chroma"]), 12)


class OnsetEnhancementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="spectral_viz_test_")
        self.audio_path = os.path.join(self.temp_dir.name, "test.wav")
        _create_test_wav(self.audio_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_produces_png_and_json(self) -> None:
        from spectral_viz import generate_onset_enhancement

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_onset_enhancement(self.audio_path, out_dir)

        self.assertIn("spectrogram_onset", result)
        self.assertIn("onset_strength", result)
        for path in result.values():
            self.assertTrue(os.path.isfile(path))
        # PNG header check
        with open(result["spectrogram_onset"], "rb") as f:
            self.assertEqual(f.read(4), b"\x89PNG")

    def test_json_has_required_keys(self) -> None:
        from spectral_viz import generate_onset_enhancement

        out_dir = os.path.join(self.temp_dir.name, "out")
        result = generate_onset_enhancement(self.audio_path, out_dir)
        with open(result["onset_strength"]) as f:
            data = json.load(f)
        for key in ("timePoints", "onsetStrength", "sampleRate",
                     "hopLength", "originalFrameCount", "downsampledTo"):
            self.assertIn(key, data)
        self.assertEqual(len(data["timePoints"]), len(data["onsetStrength"]))


if __name__ == "__main__":
    unittest.main()
