import json
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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

    def test_rhythm_detail_exposes_full_grid_downbeats_and_bar_positions(self) -> None:
        rhythm_detail = self.payload["rhythmDetail"]
        self.assertIsInstance(rhythm_detail, dict)

        beat_grid = rhythm_detail.get("beatGrid")
        beat_positions = rhythm_detail.get("beatPositions")
        downbeats = rhythm_detail.get("downbeats")

        self.assertIsInstance(beat_grid, list)
        self.assertGreater(len(beat_grid), 0)
        self.assertTrue(all(isinstance(value, (int, float)) for value in beat_grid))
        self.assertTrue(
            all(abs(float(value) - round(float(value), 3)) < 1e-9 for value in beat_grid)
        )

        self.assertIsInstance(beat_positions, list)
        self.assertEqual(len(beat_positions), len(beat_grid))
        self.assertTrue(all(isinstance(value, int) for value in beat_positions))
        self.assertTrue(all(value in {1, 2, 3, 4} for value in beat_positions))
        self.assertEqual(
            beat_positions,
            [((index % 4) + 1) for index in range(len(beat_grid))],
        )

        self.assertIsInstance(downbeats, list)
        self.assertEqual(downbeats, beat_grid[::4])


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


class AnalyzeTranscriptionHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.analyze_path = cls.repo_root / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_module_under_test", cls.analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py for direct helper tests.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_extract_basic_pitch_notes_excludes_confidence_below_noise_floor(self) -> None:
        raw_events = [
            {"pitchMidi": 48, "onsetSeconds": 0.0, "durationSeconds": 0.2, "confidence": 0.04},
            {"pitchMidi": 50, "onsetSeconds": 0.3, "durationSeconds": 0.2, "confidence": 0.05},
            {"pitchMidi": 52, "onsetSeconds": 0.6, "durationSeconds": 0.2, "confidence": 0.06},
        ]

        notes, midi_values, confidence_values = self.analyze._extract_basic_pitch_notes(
            "ignored.wav",
            "full_mix",
            lambda _source_path, _model_path: (None, None, raw_events),
            "fake_model",
        )

        self.assertEqual([note["pitchMidi"] for note in notes], [50, 52])
        self.assertEqual(midi_values, [50, 52])
        self.assertEqual(confidence_values, [0.05, 0.06])

    def test_deduplicate_transcription_notes_prefers_bass_for_low_register_overlap(self) -> None:
        notes = [
            {
                "pitchMidi": 47,
                "pitchName": "B2",
                "onsetSeconds": 0.0,
                "durationSeconds": 0.4,
                "confidence": 0.61,
                "stemSource": "other",
            },
            {
                "pitchMidi": 48,
                "pitchName": "C3",
                "onsetSeconds": 0.02,
                "durationSeconds": 0.25,
                "confidence": 0.57,
                "stemSource": "bass",
            },
        ]

        deduplicated = self.analyze._deduplicate_transcription_notes(notes)

        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0]["stemSource"], "bass")
        self.assertEqual(deduplicated[0]["durationSeconds"], 0.4)

    def test_deduplicate_transcription_notes_prefers_other_for_high_register_overlap(self) -> None:
        notes = [
            {
                "pitchMidi": 60,
                "pitchName": "C4",
                "onsetSeconds": 1.0,
                "durationSeconds": 0.22,
                "confidence": 0.66,
                "stemSource": "bass",
            },
            {
                "pitchMidi": 61,
                "pitchName": "C#4",
                "onsetSeconds": 1.01,
                "durationSeconds": 0.3,
                "confidence": 0.51,
                "stemSource": "other",
            },
        ]

        deduplicated = self.analyze._deduplicate_transcription_notes(notes)

        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0]["stemSource"], "other")
        self.assertEqual(deduplicated[0]["durationSeconds"], 0.3)

    def test_deduplicate_transcription_notes_keeps_higher_confidence_for_near_duplicate_pitch(self) -> None:
        notes = [
            {
                "pitchMidi": 64,
                "pitchName": "E4",
                "onsetSeconds": 2.0,
                "durationSeconds": 0.15,
                "confidence": 0.55,
                "stemSource": "bass",
            },
            {
                "pitchMidi": 64,
                "pitchName": "E4",
                "onsetSeconds": 2.02,
                "durationSeconds": 0.25,
                "confidence": 0.81,
                "stemSource": "other",
            },
        ]

        deduplicated = self.analyze._deduplicate_transcription_notes(notes)

        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(deduplicated[0]["stemSource"], "other")
        self.assertEqual(deduplicated[0]["confidence"], 0.81)
        self.assertEqual(deduplicated[0]["durationSeconds"], 0.25)

    def test_transcription_detail_caps_stem_aware_output_at_500_notes(self) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="sonic_analyzer_transcription_cap_")
        self.addCleanup(temp_dir.cleanup)
        bass_path = Path(temp_dir.name) / "bass.wav"
        other_path = Path(temp_dir.name) / "other.wav"
        bass_path.write_bytes(b"bass")
        other_path.write_bytes(b"other")

        bass_events = [
            {
                "pitchMidi": 36 + (idx % 12),
                "onsetSeconds": idx * 0.05,
                "durationSeconds": 0.2 + (idx % 5) * 0.01,
                "confidence": 0.2 + (idx / 1000.0),
            }
            for idx in range(300)
        ]
        other_events = [
            {
                "pitchMidi": 60 + (idx % 12),
                "onsetSeconds": 20.0 + (idx * 0.05),
                "durationSeconds": 0.25 + (idx % 5) * 0.01,
                "confidence": 0.25 + (idx / 1000.0),
            }
            for idx in range(300)
        ]

        result, stderr = self._run_basic_pitch_analysis(
            event_map={str(bass_path): bass_events, str(other_path): other_events},
            stem_paths={"bass": str(bass_path), "other": str(other_path)},
        )

        transcription = result["transcriptionDetail"]
        self.assertEqual(transcription["fullMixFallback"], False)
        self.assertEqual(transcription["noteCount"], 500)
        self.assertEqual(len(transcription["notes"]), 500)
        self.assertIn("[warn] transcriptionDetail: truncated to 500 notes (was 600)", stderr)

    def test_transcription_detail_caps_full_mix_output_at_200_notes_and_warns(self) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="sonic_analyzer_transcription_full_mix_")
        self.addCleanup(temp_dir.cleanup)
        audio_path = Path(temp_dir.name) / "track.wav"
        audio_path.write_bytes(b"mix")

        raw_events = [
            {
                "pitchMidi": 36 + ((idx * 3) % 48),
                "onsetSeconds": idx * 0.12,
                "durationSeconds": 0.05 + (idx % 3) * 0.01,
                "confidence": 0.1 + (idx / 1000.0),
            }
            for idx in range(260)
        ]

        result, stderr = self._run_basic_pitch_analysis(
            event_map={str(audio_path): raw_events},
            audio_path=str(audio_path),
            stem_paths=None,
        )

        transcription = result["transcriptionDetail"]
        self.assertEqual(transcription["fullMixFallback"], True)
        self.assertEqual(transcription["noteCount"], 200)
        self.assertEqual(len(transcription["notes"]), 200)
        self.assertIn(
            "[warn] transcriptionDetail: running on full mix — quality may be low for dense material",
            stderr,
        )
        self.assertIn("[warn] transcriptionDetail: truncated to 200 notes (was 260)", stderr)

    def test_transcription_detail_sets_full_mix_fallback_for_missing_or_invalid_stems(self) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="sonic_analyzer_transcription_fallback_")
        self.addCleanup(temp_dir.cleanup)
        audio_path = Path(temp_dir.name) / "track.wav"
        bass_path = Path(temp_dir.name) / "bass.wav"
        other_path = Path(temp_dir.name) / "other.wav"
        audio_path.write_bytes(b"mix")
        bass_path.write_bytes(b"bass")
        other_path.write_bytes(b"other")

        raw_events = [{"pitchMidi": 48, "onsetSeconds": 0.1, "durationSeconds": 0.2, "confidence": 0.9}]

        none_result, _ = self._run_basic_pitch_analysis(
            event_map={str(audio_path): raw_events},
            audio_path=str(audio_path),
            stem_paths=None,
        )
        empty_result, _ = self._run_basic_pitch_analysis(
            event_map={str(audio_path): raw_events},
            audio_path=str(audio_path),
            stem_paths={},
        )
        unusable_result, _ = self._run_basic_pitch_analysis(
            event_map={str(audio_path): raw_events},
            audio_path=str(audio_path),
            stem_paths={"bass": str(Path(temp_dir.name) / "missing.wav")},
        )
        stem_result, _ = self._run_basic_pitch_analysis(
            event_map={str(bass_path): raw_events, str(other_path): raw_events},
            audio_path=str(audio_path),
            stem_paths={"bass": str(bass_path), "other": str(other_path)},
        )

        self.assertTrue(none_result["transcriptionDetail"]["fullMixFallback"])
        self.assertTrue(empty_result["transcriptionDetail"]["fullMixFallback"])
        self.assertTrue(unusable_result["transcriptionDetail"]["fullMixFallback"])
        self.assertFalse(stem_result["transcriptionDetail"]["fullMixFallback"])

    def _run_basic_pitch_analysis(
        self,
        *,
        event_map: dict[str, list[dict]],
        audio_path: str | None = None,
        stem_paths: dict | None = None,
    ) -> tuple[dict, str]:
        if audio_path is None:
            audio_path = next(iter(event_map.keys()))

        def fake_predict(source_path: str, _model_path: str):
            return None, None, event_map.get(source_path, [])

        fake_inference_module = SimpleNamespace(predict=fake_predict)
        fake_basic_pitch_module = SimpleNamespace(
            ICASSP_2022_MODEL_PATH="fake_model_path",
            inference=fake_inference_module,
        )

        stderr_buffer = io.StringIO()
        with (
            mock.patch.dict(
                sys.modules,
                {
                    "basic_pitch": fake_basic_pitch_module,
                    "basic_pitch.inference": fake_inference_module,
                },
            ),
            mock.patch("sys.stderr", stderr_buffer),
        ):
            result = self.analyze.analyze_transcription_basic_pitch(audio_path, stem_paths=stem_paths)

        return result, stderr_buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
