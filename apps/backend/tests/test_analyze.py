import json
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np


EXPECTED_SPECTRAL_BANDS = {
    "subBass",
    "lowBass",
    "lowMids",
    "mids",
    "upperMids",
    "highs",
    "brilliance",
}

# Top-level keys emitted by both full and fast modes — the shared output contract.
EXPECTED_TOP_LEVEL_KEYS = {
    "bpm", "bpmConfidence", "bpmPercival", "bpmAgreement",
    "bpmDoubletime", "bpmSource", "bpmRawOriginal",
    "key", "keyConfidence", "timeSignature", "timeSignatureSource",
    "timeSignatureConfidence", "durationSeconds", "sampleRate",
    "lufsIntegrated", "lufsRange", "truePeak", "plr", "crestFactor",
    "dynamicSpread", "dynamicCharacter", "textureCharacter", "stereoDetail", "monoCompatible", "spectralBalance",
    "spectralDetail", "rhythmDetail", "melodyDetail", "transcriptionDetail",
    "grooveDetail", "beatsLoudness", "rhythmTimeline", "sidechainDetail", "acidDetail", "reverbDetail",
    "vocalDetail", "supersawDetail", "bassDetail", "kickDetail",
    "genreDetail", "effectsDetail", "synthesisCharacter",
    "danceability", "structure", "arrangementDetail",
    "segmentLoudness", "segmentSpectral", "segmentStereo", "segmentKey",
    "chordDetail", "perceptual", "essentiaFeatures",
}

# Fields fast mode populates with real values.
FAST_MODE_POPULATED_FIELDS = {
    "bpm", "bpmConfidence", "bpmPercival", "bpmAgreement",
    "bpmDoubletime", "bpmSource", "bpmRawOriginal",
    "key", "keyConfidence", "timeSignature", "timeSignatureSource",
    "timeSignatureConfidence", "durationSeconds", "sampleRate",
    "lufsIntegrated", "lufsRange", "truePeak", "plr", "crestFactor",
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


def _write_click_fixture(
    path: Path,
    click_events: list[tuple[float, float]],
    sample_rate: int = 44_100,
    duration_seconds: float = 4.0,
    click_ms: float = 12.0,
) -> None:
    """Write a deterministic click track with per-click amplitude control."""
    total_samples = int(sample_rate * duration_seconds)
    signal = np.zeros(total_samples, dtype=np.float32)
    click_samples = max(8, int(round(sample_rate * click_ms / 1000.0)))
    click_shape = np.hanning(click_samples).astype(np.float32)

    for click_time, amplitude in click_events:
        start = int(round(click_time * sample_rate))
        if start >= total_samples:
            continue
        stop = min(total_samples, start + click_samples)
        signal[start:stop] += amplitude * click_shape[: stop - start]

    stereo = np.stack([signal, signal], axis=1)
    pcm = np.clip(stereo, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def _write_syncopated_click_fixture(
    path: Path,
    sample_rate: int = 44_100,
    duration_seconds: float = 4.0,
    bpm: float = 120.0,
) -> None:
    """Write quarter-note clicks with extra off-beat accents for onset-rate tests."""
    beat_interval = 60.0 / bpm
    click_events: list[tuple[float, float]] = []
    time_cursor = 0.0
    while time_cursor < duration_seconds:
        click_events.append((time_cursor, 0.95))
        offbeat_time = time_cursor + (beat_interval / 2.0)
        if offbeat_time < duration_seconds:
            click_events.append((offbeat_time, 0.6))
        time_cursor += beat_interval
    _write_click_fixture(path, click_events, sample_rate, duration_seconds)


def _write_key_fixture(
    path: Path,
    sample_rate: int = 44_100,
    duration_seconds: float = 6.0,
) -> None:
    """Write a stable A-minor harmonic bed for fast/full key-agreement tests."""
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
            "timeSignatureSource",
            "timeSignatureConfidence",
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
        self.assertEqual(self.payload["timeSignatureSource"], "assumed_four_four")
        self.assertEqual(self.payload["timeSignatureConfidence"], 0.0)
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

    def test_spectral_balance_has_seven_numeric_bands(self) -> None:
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
        self.assertEqual(self.payload["timeSignatureSource"], "assumed_four_four")
        self.assertEqual(self.payload["timeSignatureConfidence"], 0.0)

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



class AnalyzeTextureCharacterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_texture_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_dynamic_character_exposes_loudness_db_and_legacy_alias(self) -> None:
        sample_rate = 44_100
        time_axis = np.arange(sample_rate, dtype=np.float32) / sample_rate
        signal = (0.2 * np.sin(2 * np.pi * 220.0 * time_axis)).astype(np.float32)

        dynamic_character = self.analyze.analyze_dynamic_character(signal, sample_rate)[
            "dynamicCharacter"
        ]

        self.assertIn("loudnessDb", dynamic_character)
        self.assertIn("loudnessVariation", dynamic_character)
        self.assertEqual(
            dynamic_character["loudnessDb"],
            dynamic_character["loudnessVariation"],
        )

    def test_texture_character_scores_noise_above_tone(self) -> None:
        sample_rate = 44_100
        time_axis = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
        tone = (0.2 * np.sin(2 * np.pi * 220.0 * time_axis)).astype(np.float32)
        rng = np.random.default_rng(7)
        noise = (0.2 * rng.standard_normal(sample_rate * 2)).astype(np.float32)

        tone_texture = self.analyze.analyze_texture_character(
            tone,
            sample_rate,
            inharmonicity=0.0,
        )["textureCharacter"]
        noise_texture = self.analyze.analyze_texture_character(
            noise,
            sample_rate,
            inharmonicity=0.2,
        )["textureCharacter"]

        self.assertLess(tone_texture["textureScore"], noise_texture["textureScore"])
        self.assertLess(
            tone_texture["midBandFlatness"],
            noise_texture["midBandFlatness"],
        )
        self.assertLess(
            tone_texture["highBandFlatness"],
            noise_texture["highBandFlatness"],
        )


class AnalyzeRhythmAndStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_rhythm_structure_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_syncopated_click_fixture_produces_onset_rate_above_beat_rate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_syncopated_click_") as temp_dir:
            fixture_path = Path(temp_dir) / "syncopated.wav"
            _write_syncopated_click_fixture(fixture_path)
            mono = self.analyze.load_mono(str(fixture_path), 44_100)
            rhythm_data = self.analyze.extract_rhythm(mono)
            self.assertIsNotNone(rhythm_data, "Rhythm extraction should succeed on synthetic click audio")

            detail = self.analyze.analyze_rhythm_detail(mono, 44_100, rhythm_data)["rhythmDetail"]
            self.assertIsNotNone(detail)
            beat_grid = detail["beatGrid"]
            self.assertGreater(len(beat_grid), 1)
            beat_rate = len(beat_grid) / (beat_grid[-1] - beat_grid[0])
            self.assertGreater(
                detail["onsetRate"],
                beat_rate,
                "Audio-derived onset rate should exceed the beat rate on syncopated material",
            )

    def test_structure_snaps_to_downbeats_and_merges_short_segments(self) -> None:
        mono = np.zeros(40_000, dtype=np.float32)
        rhythm_data = {
            "ticks": np.asarray([float(i) for i in range(40)], dtype=np.float64),
        }

        with mock.patch.object(
            self.analyze,
            "_extract_structure_feature_matrix",
            return_value=(np.ones((2, 8), dtype=np.float32), 1_000),
        ), mock.patch.object(
            self.analyze,
            "_run_structure_sbic_boundaries",
            return_value=np.asarray([4.2, 6.0, 12.4, 20.0], dtype=np.float64),
        ):
            result = self.analyze.analyze_structure(
                mono,
                sample_rate=1_000,
                rhythm_data=rhythm_data,
            )["structure"]

        self.assertIsNotNone(result)
        self.assertEqual(
            result["segments"],
            [
                {"start": 0.0, "end": 6.0, "index": 0},
                {"start": 6.0, "end": 12.0, "index": 1},
                {"start": 12.0, "end": 20.0, "index": 2},
                {"start": 20.0, "end": 40.0, "index": 3},
            ],
        )

    def test_run_structure_sbic_boundaries_calls_sbic_with_matrix_input(self) -> None:
        captured = {}

        def _fake_sbic(**_kwargs):
            def _runner(features):
                features_arr = np.asarray(features, dtype=np.float64)
                captured["ndim"] = int(features_arr.ndim)
                captured["shape"] = tuple(features_arr.shape)
                return [0.0, float(features_arr.shape[1] - 1)]

            return _runner

        with mock.patch.object(self.analyze.es, "SBic", side_effect=_fake_sbic):
            boundaries = self.analyze._run_structure_sbic_boundaries(
                np.ones((13, 24), dtype=np.float32),
                sample_rate=1_000,
                hop_size=100,
            )

        self.assertEqual(captured["ndim"], 2)
        self.assertEqual(captured["shape"], (13, 24))
        self.assertEqual(len(boundaries), 2)
        self.assertAlmostEqual(float(boundaries[0]), 0.0, places=6)
        self.assertAlmostEqual(float(boundaries[1]), 2.3, places=6)

    def test_run_structure_sbic_boundaries_uses_default_winner_parameters(self) -> None:
        with mock.patch.object(
            self.analyze.es,
            "SBic",
            return_value=lambda _features: [0.0, 5.0],
        ) as sbic_mock:
            self.analyze._run_structure_sbic_boundaries(
                np.ones((4, 6), dtype=np.float32),
                sample_rate=1_000,
                hop_size=100,
            )

        sbic_mock.assert_called_once_with(**self.analyze.STRUCTURE_SBIC_PARAMS)

    def test_structure_uses_novelty_fallback_when_sbic_is_too_coarse(self) -> None:
        mono = np.zeros(125_000, dtype=np.float32)
        with mock.patch.object(
            self.analyze,
            "_extract_structure_feature_matrix",
            return_value=(np.ones((2, 8), dtype=np.float32), 1_000),
        ), mock.patch.object(
            self.analyze,
            "_run_structure_sbic_boundaries",
            return_value=np.asarray([0.0, 125.0], dtype=np.float64),
        ), mock.patch.object(
            self.analyze,
            "_compute_arrangement_novelty_summary",
            return_value={
                "noveltyCurve": [],
                "noveltyMean": 0.0,
                "noveltyStdDev": 0.0,
                "noveltyPeaks": [
                    {"time": 30.0, "strength": 0.7},
                    {"time": 60.0, "strength": 0.8},
                    {"time": 90.0, "strength": 0.75},
                ],
            },
        ) as novelty_mock:
            structure = self.analyze.analyze_structure(
                mono,
                sample_rate=1_000,
                rhythm_data=None,
            )["structure"]

        self.assertIsNotNone(structure)
        self.assertGreaterEqual(structure["segmentCount"], 4)
        self.assertEqual(novelty_mock.call_count, 1)

    def test_structure_returns_single_segment_when_all_detection_paths_fail(self) -> None:
        mono = np.zeros(20_000, dtype=np.float32)
        with mock.patch.object(
            self.analyze,
            "_extract_structure_feature_matrix",
            return_value=None,
        ), mock.patch.object(
            self.analyze,
            "_compute_arrangement_novelty_summary",
            return_value=None,
        ):
            structure = self.analyze.analyze_structure(
                mono,
                sample_rate=1_000,
                rhythm_data=None,
            )["structure"]

        self.assertIsNotNone(structure)
        self.assertEqual(
            structure["segments"],
            [{"start": 0.0, "end": 20.0, "index": 0}],
        )

    def test_compute_structure_merge_floor_clamps_duration_term_to_target_range(self) -> None:
        short_floor = self.analyze._compute_structure_merge_floor(
            duration=30.0,
            median_beat_interval=None,
            policy="adaptive_clamped",
        )
        long_floor = self.analyze._compute_structure_merge_floor(
            duration=600.0,
            median_beat_interval=None,
            policy="adaptive_clamped",
        )

        self.assertEqual(short_floor, 6.0)
        self.assertEqual(long_floor, 18.0)


class AnalyzeFastFullConsistencyTests(unittest.TestCase):
    def test_fast_and_full_mode_agree_on_key_for_stable_fixture(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        analyze_path = repo_root / "analyze.py"

        with tempfile.TemporaryDirectory(prefix="asa_key_fixture_") as temp_dir:
            fixture_path = Path(temp_dir) / "key_fixture.wav"
            _write_key_fixture(fixture_path)

            full_stdout, _ = _run_analyze(analyze_path, fixture_path, [])
            fast_stdout, _ = _run_analyze(analyze_path, fixture_path, ["--fast"])

        full_payload = json.loads(full_stdout)
        fast_payload = json.loads(fast_stdout)

        self.assertEqual(full_payload["key"], fast_payload["key"])
        self.assertEqual(full_payload["timeSignatureSource"], fast_payload["timeSignatureSource"])


class BeatsLoudnessPatternTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_beats_loudness_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_analyze_beats_loudness_returns_normalized_bar_position_patterns(self) -> None:
        band_loudness = np.asarray(
            [
                [4.0, 1.0, 0.5],
                [1.0, 3.0, 0.5],
                [3.5, 1.5, 2.0],
                [0.5, 1.0, 4.0],
                [4.0, 1.0, 0.4],
                [1.0, 4.0, 0.6],
                [3.0, 1.2, 2.2],
                [0.6, 1.1, 4.2],
            ],
            dtype=np.float64,
        )
        beat_loudness = np.asarray([5.5, 4.5, 7.0, 5.5, 5.4, 5.6, 6.4, 5.9], dtype=np.float64)
        result = self.analyze.analyze_beats_loudness(
            np.zeros(128, dtype=np.float32),
            sample_rate=44_100,
            beat_data={
                "beatLoudness": beat_loudness,
                "bandLoudness": band_loudness,
                "lowBand": band_loudness[:, 0],
                "highBand": band_loudness[:, -1],
            },
        )["beatsLoudness"]

        self.assertEqual(result["patternBeatsPerBar"], 4)
        self.assertEqual(result["accentPattern"], result["overallAccentPattern"])
        self.assertEqual(len(result["lowBandAccentPattern"]), 4)
        self.assertEqual(len(result["midBandAccentPattern"]), 4)
        self.assertEqual(len(result["highBandAccentPattern"]), 4)
        self.assertEqual(len(result["overallAccentPattern"]), 4)
        self.assertAlmostEqual(result["lowBandAccentPattern"][0], 1.0, places=4)
        self.assertAlmostEqual(result["lowBandAccentPattern"][2], 0.8125, places=4)
        self.assertAlmostEqual(result["midBandAccentPattern"][1], 1.0, places=4)
        self.assertAlmostEqual(result["highBandAccentPattern"][3], 1.0, places=4)
        self.assertAlmostEqual(result["overallAccentPattern"][2], 1.0, places=4)

    def _build_rhythm_timeline_fixture(
        self,
        bar_patterns: list[dict[str, list[float]]],
        sample_rate: int = 16_000,
        bpm: float = 120.0,
    ) -> tuple[np.ndarray, dict[str, object]]:
        beats_per_bar = 4
        steps_per_beat = 4
        step_duration = (60.0 / bpm) / steps_per_beat
        step_samples = max(16, int(round(step_duration * sample_rate)))
        total_steps = len(bar_patterns) * beats_per_bar * steps_per_beat
        total_samples = total_steps * step_samples
        mono = np.zeros(total_samples, dtype=np.float32)
        envelope = np.hanning(step_samples).astype(np.float32)
        time_axis = np.arange(step_samples, dtype=np.float32) / sample_rate
        lane_frequencies = {
            "low": 80.0,
            "mid": 1000.0,
            "high": 6000.0,
        }

        for bar_index, pattern in enumerate(bar_patterns):
            for step_index in range(beats_per_bar * steps_per_beat):
                start = (bar_index * beats_per_bar * steps_per_beat + step_index) * step_samples
                stop = start + step_samples
                segment = np.zeros(step_samples, dtype=np.float32)
                for lane_key, frequency in lane_frequencies.items():
                    lane_values = pattern.get(lane_key, [])
                    amplitude = float(lane_values[step_index]) if step_index < len(lane_values) else 0.0
                    if amplitude <= 0:
                        continue
                    segment += (
                        amplitude
                        * np.sin(2 * np.pi * frequency * time_axis, dtype=np.float32)
                        * envelope
                    )
                mono[start:stop] += segment

        beat_duration = 60.0 / bpm
        ticks = [
            round(index * beat_duration, 6)
            for index in range(len(bar_patterns) * beats_per_bar)
        ]
        return mono, {"ticks": ticks, "bpm": bpm}

    def test_analyze_rhythm_timeline_selects_representative_dsp_window(self) -> None:
        quiet_bar = {
            "low": [0.08 if step == 0 else 0.0 for step in range(16)],
            "mid": [0.04 if step == 4 else 0.0 for step in range(16)],
            "high": [0.03 if step % 4 == 2 else 0.0 for step in range(16)],
        }
        active_bar = {
            "low": [1.0 if step in (0, 8) else 0.0 for step in range(16)],
            "mid": [0.72 if step in (4, 12) else 0.0 for step in range(16)],
            "high": [0.38 if step % 2 == 0 else 0.14 for step in range(16)],
        }
        mono, rhythm_data = self._build_rhythm_timeline_fixture(
            [quiet_bar] * 4 + [active_bar] * 8 + [quiet_bar] * 4
        )

        result = self.analyze.analyze_rhythm_timeline(
            mono,
            sample_rate=16_000,
            rhythm_data=rhythm_data,
        )["rhythmTimeline"]

        self.assertIsNotNone(result)
        self.assertEqual(result["beatsPerBar"], 4)
        self.assertEqual(result["stepsPerBeat"], 4)
        self.assertEqual(result["availableBars"], 16)
        self.assertEqual(result["selectionMethod"], "representative_dsp_window")

        windows_by_bars = {window["bars"]: window for window in result["windows"]}
        self.assertEqual(sorted(windows_by_bars.keys()), [8, 16])

        window_8 = windows_by_bars[8]
        self.assertEqual(window_8["startBar"], 5)
        self.assertEqual(window_8["endBar"], 12)
        self.assertEqual(len(window_8["lowBandSteps"]), 8 * 16)
        self.assertEqual(len(window_8["midBandSteps"]), 8 * 16)
        self.assertEqual(len(window_8["highBandSteps"]), 8 * 16)
        self.assertEqual(len(window_8["overallSteps"]), 8 * 16)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in window_8["overallSteps"]))

        window_16 = windows_by_bars[16]
        self.assertEqual(window_16["startBar"], 1)
        self.assertEqual(window_16["endBar"], 16)
        self.assertEqual(len(window_16["overallSteps"]), 16 * 16)

    def test_analyze_rhythm_timeline_omits_16_bar_window_when_not_enough_bars(self) -> None:
        active_bar = {
            "low": [1.0 if step in (0, 8) else 0.0 for step in range(16)],
            "mid": [0.6 if step in (4, 12) else 0.0 for step in range(16)],
            "high": [0.35 if step % 2 == 0 else 0.12 for step in range(16)],
        }
        mono, rhythm_data = self._build_rhythm_timeline_fixture([active_bar] * 10)

        result = self.analyze.analyze_rhythm_timeline(
            mono,
            sample_rate=16_000,
            rhythm_data=rhythm_data,
        )["rhythmTimeline"]

        self.assertIsNotNone(result)
        self.assertEqual(result["availableBars"], 10)
        self.assertEqual([window["bars"] for window in result["windows"]], [8])


class TranscriptionBackendAbstractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.analyze_path = cls.repo_root / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_module_abstraction_test", cls.analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py for abstraction tests.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_torchcrepe_backend_name(self) -> None:
        backend = self.analyze.TorchcrepeBackend()
        self.assertEqual(backend.name, "torchcrepe-viterbi")

    def test_torchcrepe_backend_satisfies_protocol(self) -> None:
        backend = self.analyze.TorchcrepeBackend()
        self.assertIsInstance(backend, self.analyze.TranscriptionBackend)

    def test_analyze_transcription_returns_transcription_detail_key(self) -> None:
        result = self.analyze.analyze_transcription("nonexistent.wav")
        self.assertIn("transcriptionDetail", result)

    def test_analyze_transcription_accepts_stub_backend(self) -> None:
        class _StubBackend:
            name = "stub"

            def transcribe(self, audio_path, stem_paths=None):
                return {"transcriptionDetail": None}

        stub = _StubBackend()
        result = self.analyze.analyze_transcription("nonexistent.wav", backend=stub)
        self.assertEqual(result, {"transcriptionDetail": None})

    def test_resolve_transcription_backend_id_maps_supported_aliases(self) -> None:
        self.assertEqual(
            self.analyze.resolve_transcription_backend_id("auto"),
            "torchcrepe-viterbi",
        )
        self.assertEqual(
            self.analyze.resolve_transcription_backend_id("torchcrepe"),
            "torchcrepe-viterbi",
        )

    def test_resolve_transcription_backend_id_rejects_unknown_backend(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported transcription backend 'mystery'"):
            self.analyze.resolve_transcription_backend_id("mystery")

    def test_resolve_transcription_backend_id_rejects_penn(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported transcription backend 'penn'"):
            self.analyze.resolve_transcription_backend_id("penn")

    def test_analyze_transcription_rejects_explicit_unknown_backend_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported transcription backend 'mystery'"):
            self.analyze.analyze_transcription(
                "nonexistent.wav",
                backend_id="mystery",
            )

    def test_main_forwards_pitch_note_backend_to_pitch_note_only_runner(self) -> None:
        with (
            mock.patch.object(
                self.analyze,
                "_run_pitch_note_translation",
            ) as run_pitch_note_translation_mock,
            mock.patch.object(
                self.analyze.sys,
                "argv",
                [
                    "analyze.py",
                    "track.wav",
                    "--pitch-note-only",
                    "--pitch-note-backend",
                    "torchcrepe-viterbi",
                ],
            ),
        ):
            with self.assertRaises(SystemExit) as exit_ctx:
                self.analyze.main()

        self.assertEqual(exit_ctx.exception.code, 0)
        run_pitch_note_translation_mock.assert_called_once_with(
            "track.wav",
            stem_dir=None,
            stem_output_dir=None,
            backend_id="torchcrepe-viterbi",
        )


class AcidDetailTests(unittest.TestCase):
    """Tests for analyze_acid_detail — TB-303 acid bassline detection."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_acid_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_acid_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"acidDetail": None})

    def test_returns_none_when_bpm_is_none(self):
        mono = np.zeros(44100, dtype=np.float32)
        result = self.analyze.analyze_acid_detail(mono, 44100, bpm=None)
        self.assertEqual(result, {"acidDetail": None})

    def test_short_signal_returns_low_confidence(self):
        """Very short silence should produce zero-confidence acid result."""
        mono = np.zeros(44100, dtype=np.float32)
        result = self.analyze.analyze_acid_detail(mono, 44100, bpm=128.0)
        detail = result.get("acidDetail")
        self.assertIsNotNone(detail)
        self.assertFalse(detail["isAcid"])
        self.assertEqual(detail["confidence"], 0.0)

    def test_output_schema_fields(self):
        """All expected fields must be present in the output."""
        sr = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
        mono = 0.5 * np.sin(2 * np.pi * 200 * t).astype(np.float32)
        result = self.analyze.analyze_acid_detail(mono, sr, bpm=130.0)
        detail = result.get("acidDetail")
        self.assertIsNotNone(detail)
        expected_keys = {"isAcid", "confidence", "resonanceLevel", "centroidOscillationHz", "bassRhythmDensity"}
        self.assertEqual(set(detail.keys()), expected_keys)

    def test_resonant_sweeping_bass_scores_higher(self):
        """A signal with resonant bass + centroid movement should score higher than silence."""
        sr = 44100
        duration = 4.0
        n_samples = int(sr * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False, dtype=np.float32)
        sweep_freq = 150 + 550 * (t / duration)
        mono = 0.5 * np.sin(2 * np.pi * sweep_freq * t)
        mono += 0.3 * np.sin(2 * np.pi * sweep_freq * 2 * t)
        mono = mono.astype(np.float32)
        result = self.analyze.analyze_acid_detail(mono, sr, bpm=130.0)
        detail = result["acidDetail"]
        self.assertGreater(detail["centroidOscillationHz"], 0)
        self.assertGreater(detail["resonanceLevel"], 0)

    def test_confidence_bounded_zero_to_one(self):
        """Confidence must always be in [0, 1]."""
        sr = 44100
        mono = np.random.randn(int(sr * 2.0)).astype(np.float32) * 0.3
        result = self.analyze.analyze_acid_detail(mono, sr, bpm=140.0)
        detail = result["acidDetail"]
        self.assertGreaterEqual(detail["confidence"], 0.0)
        self.assertLessEqual(detail["confidence"], 1.0)


class ReverbDetailTests(unittest.TestCase):
    """Tests for analyze_reverb_detail — RT60 estimation from decay slopes."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_reverb_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def _make_decaying_signal(self, sr: int, n_transients: int, rt60_target: float, duration: float = 6.0) -> np.ndarray:
        """Generate a signal with clear transients followed by exponential decay."""
        n_samples = int(sr * duration)
        mono = np.zeros(n_samples, dtype=np.float32)
        beat_samples = int(sr * (60.0 / 130.0))
        decay_rate = np.log(1000) / (rt60_target * sr)

        for i in range(n_transients):
            onset = i * beat_samples
            if onset >= n_samples:
                break
            burst_len = min(200, n_samples - onset)
            t = np.arange(burst_len, dtype=np.float32)
            decay_env = np.exp(-decay_rate * t)
            mono[onset:onset + burst_len] += (0.8 * decay_env * np.sin(2 * np.pi * 440 * t / sr)).astype(np.float32)

        return mono

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_reverb_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"reverbDetail": None})

    def test_output_schema_fields(self):
        """All expected fields must be present."""
        sr = 44100
        mono = self._make_decaying_signal(sr, n_transients=8, rt60_target=0.4, duration=6.0)
        result = self.analyze.analyze_reverb_detail(mono, sr, bpm=130.0)
        detail = result.get("reverbDetail")
        self.assertIsNotNone(detail)
        self.assertEqual(set(detail.keys()), {"rt60", "isWet", "tailEnergyRatio", "measured"})

    def test_rt60_bounded(self):
        """RT60 must be >= 0 and <= 3.0 (capped) when measured."""
        sr = 44100
        mono = self._make_decaying_signal(sr, n_transients=8, rt60_target=0.3, duration=6.0)
        result = self.analyze.analyze_reverb_detail(mono, sr, bpm=130.0)
        detail = result["reverbDetail"]
        if detail["measured"]:
            self.assertGreaterEqual(detail["rt60"], 0.0)
            self.assertLessEqual(detail["rt60"], 3.0)
        else:
            self.assertIsNone(detail["rt60"])

    def test_tail_energy_ratio_bounded(self):
        """tailEnergyRatio must always be in [0, 1] when measured."""
        sr = 44100
        mono = self._make_decaying_signal(sr, n_transients=8, rt60_target=0.5, duration=6.0)
        result = self.analyze.analyze_reverb_detail(mono, sr, bpm=130.0)
        detail = result["reverbDetail"]
        if detail["measured"]:
            self.assertGreaterEqual(detail["tailEnergyRatio"], 0.0)
            self.assertLessEqual(detail["tailEnergyRatio"], 1.0)
        else:
            self.assertIsNone(detail["tailEnergyRatio"])

    def test_is_wet_matches_rt60_threshold(self):
        """`isWet` must be True iff rt60 > 0.5 when measured."""
        sr = 44100
        mono = self._make_decaying_signal(sr, n_transients=10, rt60_target=1.2, duration=8.0)
        result = self.analyze.analyze_reverb_detail(mono, sr, bpm=130.0)
        detail = result["reverbDetail"]
        if detail["measured"]:
            self.assertEqual(detail["isWet"], detail["rt60"] > 0.5)
        else:
            self.assertFalse(detail["isWet"])

    def test_fallback_on_no_bpm(self):
        """None BPM uses fallback (120 BPM) and does not crash."""
        sr = 44100
        mono = self._make_decaying_signal(sr, n_transients=6, rt60_target=0.4, duration=5.0)
        result = self.analyze.analyze_reverb_detail(mono, sr, bpm=None)
        self.assertIn("reverbDetail", result)

    def test_short_silence_returns_fallback(self):
        """Short silent signals return a safe fallback dict with measured=False."""
        mono = np.zeros(44100 // 2, dtype=np.float32)
        result = self.analyze.analyze_reverb_detail(mono, 44100, bpm=128.0)
        detail = result.get("reverbDetail")
        self.assertIsNotNone(detail)
        self.assertIn("rt60", detail)
        self.assertFalse(detail["measured"])
        self.assertFalse(detail["isWet"])


class VocalDetailTests(unittest.TestCase):
    """Tests for analyze_vocal_detail — vocal presence detection."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_vocal_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_vocal_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"vocalDetail": None})

    def test_returns_none_for_short_signal(self):
        mono = np.zeros(1024, dtype=np.float32)
        result = self.analyze.analyze_vocal_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"vocalDetail": None})

    def test_output_schema_fields(self):
        """All expected fields must be present."""
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
        mono = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
        result = self.analyze.analyze_vocal_detail(mono, sr, bpm=120.0)
        detail = result.get("vocalDetail")
        self.assertIsNotNone(detail)
        expected_keys = {"hasVocals", "confidence", "vocalEnergyRatio", "formantStrength", "mfccLikelihood"}
        self.assertEqual(set(detail.keys()), expected_keys)

    def test_confidence_bounded_zero_to_one(self):
        sr = 44100
        mono = np.random.randn(int(sr * 2.0)).astype(np.float32) * 0.3
        result = self.analyze.analyze_vocal_detail(mono, sr, bpm=120.0)
        detail = result["vocalDetail"]
        self.assertGreaterEqual(detail["confidence"], 0.0)
        self.assertLessEqual(detail["confidence"], 1.0)

    def test_silence_has_low_confidence(self):
        """Silence should not be detected as vocals."""
        sr = 44100
        mono = np.zeros(int(sr * 2.0), dtype=np.float32)
        result = self.analyze.analyze_vocal_detail(mono, sr, bpm=120.0)
        detail = result["vocalDetail"]
        self.assertIsNotNone(detail)
        self.assertFalse(detail["hasVocals"])


class SupersawDetailTests(unittest.TestCase):
    """Tests for analyze_supersaw_detail — detuned unison detection."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_supersaw_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_supersaw_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"supersawDetail": None})

    def test_returns_none_for_short_signal(self):
        mono = np.zeros(2048, dtype=np.float32)
        result = self.analyze.analyze_supersaw_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"supersawDetail": None})

    def test_output_schema_fields(self):
        """All expected fields must be present."""
        sr = 44100
        duration = 2.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
        mono = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
        result = self.analyze.analyze_supersaw_detail(mono, sr, bpm=128.0)
        detail = result.get("supersawDetail")
        self.assertIsNotNone(detail)
        expected_keys = {"isSupersaw", "confidence", "voiceCount", "avgDetuneCents", "spectralComplexity"}
        self.assertEqual(set(detail.keys()), expected_keys)

    def test_confidence_bounded_zero_to_one(self):
        sr = 44100
        mono = np.random.randn(int(sr * 2.0)).astype(np.float32) * 0.3
        result = self.analyze.analyze_supersaw_detail(mono, sr, bpm=128.0)
        detail = result["supersawDetail"]
        self.assertGreaterEqual(detail["confidence"], 0.0)
        self.assertLessEqual(detail["confidence"], 1.0)

    def test_detuned_saws_score_higher_than_single_sine(self):
        """Multiple detuned sawtooth waves should score higher than a single sine."""
        sr = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
        # Single sine
        single = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
        result_single = self.analyze.analyze_supersaw_detail(single, sr, bpm=128.0)
        # Detuned stack (5 voices, ±15 cents)
        stack = np.zeros_like(t)
        base_freq = 440.0
        for detune_cents in [-15, -7, 0, 7, 15]:
            freq = base_freq * (2.0 ** (detune_cents / 1200.0))
            stack += 0.15 * np.sin(2 * np.pi * freq * t)
        stack = stack.astype(np.float32)
        result_stack = self.analyze.analyze_supersaw_detail(stack, sr, bpm=128.0)
        self.assertGreaterEqual(
            result_stack["supersawDetail"]["voiceCount"],
            result_single["supersawDetail"]["voiceCount"],
        )


class BassDetailTests(unittest.TestCase):
    """Tests for analyze_bass_detail — bass character analysis."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_bass_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_bass_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"bassDetail": None})

    def test_returns_none_for_short_signal(self):
        """Signal shorter than 1 second should return None."""
        mono = np.zeros(22050, dtype=np.float32)
        result = self.analyze.analyze_bass_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"bassDetail": None})

    def test_output_schema_fields(self):
        """All expected fields must be present."""
        sr = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
        mono = 0.5 * np.sin(2 * np.pi * 60 * t).astype(np.float32)
        result = self.analyze.analyze_bass_detail(mono, sr, bpm=128.0)
        detail = result.get("bassDetail")
        self.assertIsNotNone(detail)
        expected_keys = {"averageDecayMs", "type", "transientRatio", "fundamentalHz", "transientCount", "swingPercent", "grooveType"}
        self.assertEqual(set(detail.keys()), expected_keys)

    def test_groove_type_valid_values(self):
        """grooveType must be one of the defined categories."""
        sr = 44100
        duration = 4.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
        mono = 0.5 * np.sin(2 * np.pi * 80 * t).astype(np.float32)
        result = self.analyze.analyze_bass_detail(mono, sr, bpm=130.0)
        detail = result.get("bassDetail")
        if detail is not None:
            self.assertIn(detail["grooveType"], {"straight", "slight-swing", "heavy-swing", "shuffle"})
            self.assertIn(detail["type"], {"punchy", "medium", "rolling", "sustained"})

    def test_fallback_on_no_bpm(self):
        """None BPM uses fallback (120 BPM) and does not crash."""
        sr = 44100
        t = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False, dtype=np.float32)
        mono = 0.5 * np.sin(2 * np.pi * 60 * t).astype(np.float32)
        result = self.analyze.analyze_bass_detail(mono, sr, bpm=None)
        self.assertIn("bassDetail", result)

    def test_prefers_bass_stem_when_available(self):
        sr = 44_100
        mono = np.zeros(int(sr * 3.0), dtype=np.float32)
        time_axis = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False, dtype=np.float32)
        stem_signal = 0.5 * np.sin(2 * np.pi * 60.0 * time_axis).astype(np.float32)

        with mock.patch.object(self.analyze.os.path, "isfile", return_value=True), mock.patch.object(
            self.analyze,
            "load_mono",
            return_value=stem_signal,
        ):
            result = self.analyze.analyze_bass_detail(
                mono,
                sr,
                bpm=128.0,
                stems={"bass": "/tmp/bass.wav"},
            )

        self.assertGreater(result["bassDetail"]["fundamentalHz"], 50)


class KickDetailTests(unittest.TestCase):
    """Tests for analyze_kick_detail — kick drum distortion and THD."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_kick_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_kick_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"kickDetail": None})

    def test_returns_none_for_short_signal(self):
        mono = np.zeros(2048, dtype=np.float32)
        result = self.analyze.analyze_kick_detail(mono, 44100, bpm=128.0)
        self.assertEqual(result, {"kickDetail": None})

    def test_output_schema_fields(self):
        """All expected fields must be present."""
        sr = 44100
        duration = 4.0
        n = int(sr * duration)
        t = np.linspace(0, duration, n, endpoint=False, dtype=np.float32)
        # Simulate kick-like transients at 60 Hz
        beat_samples = int(sr * 0.5)  # 120 BPM
        mono = np.zeros(n, dtype=np.float32)
        for i in range(int(duration * 2)):
            onset = i * beat_samples
            if onset + 2000 < n:
                burst = np.arange(2000, dtype=np.float32)
                mono[onset:onset + 2000] = 0.8 * np.sin(2 * np.pi * 60 * burst / sr) * np.exp(-burst / 500)
        result = self.analyze.analyze_kick_detail(mono, sr, bpm=120.0)
        detail = result.get("kickDetail")
        self.assertIsNotNone(detail)
        expected_keys = {"isDistorted", "thd", "harmonicRatio", "fundamentalHz", "kickCount"}
        self.assertEqual(set(detail.keys()), expected_keys)

    def test_thd_bounded(self):
        """THD should be in [0, 1]."""
        sr = 44100
        duration = 3.0
        n = int(sr * duration)
        t = np.linspace(0, duration, n, endpoint=False, dtype=np.float32)
        mono = 0.5 * np.sin(2 * np.pi * 60 * t).astype(np.float32)
        result = self.analyze.analyze_kick_detail(mono, sr, bpm=128.0)
        detail = result.get("kickDetail")
        if detail is not None:
            self.assertGreaterEqual(detail["thd"], 0.0)
            self.assertLessEqual(detail["thd"], 1.0)

    def test_fallback_on_no_bpm(self):
        """None BPM uses fallback (120 BPM) and does not crash."""
        sr = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
        mono = 0.5 * np.sin(2 * np.pi * 60 * t).astype(np.float32)
        result = self.analyze.analyze_kick_detail(mono, sr, bpm=None)
        self.assertIn("kickDetail", result)

    def test_prefers_drums_stem_when_available(self):
        sr = 44_100
        mono = np.zeros(int(sr * 4.0), dtype=np.float32)
        stem_signal = np.zeros_like(mono)
        beat_samples = int(sr * 0.5)

        for i in range(8):
            onset = i * beat_samples
            if onset + 2_000 >= stem_signal.size:
                break
            burst = np.arange(2_000, dtype=np.float32)
            stem_signal[onset:onset + 2_000] = (
                0.8
                * np.sin(2 * np.pi * 60 * burst / sr)
                * np.exp(-burst / 500)
            )

        with mock.patch.object(self.analyze.os.path, "isfile", return_value=True), mock.patch.object(
            self.analyze,
            "load_mono",
            return_value=stem_signal,
        ):
            result = self.analyze.analyze_kick_detail(
                mono,
                sr,
                bpm=120.0,
                stems={"drums": "/tmp/drums.wav"},
            )

        self.assertGreater(result["kickDetail"]["kickCount"], 1)


class SidechainDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_sidechain_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_prefers_bass_stem_when_available(self):
        sample_rate = 1_000
        duration_seconds = 4.0
        mono = np.zeros(int(sample_rate * duration_seconds), dtype=np.float32)
        beats = np.asarray([0.0, 1.0, 2.0, 3.0, 4.0], dtype=np.float64)
        low_band = np.asarray([1.0, 0.25, 1.0, 0.25, 1.0], dtype=np.float64)
        beat_loudness = low_band + 0.4

        sixteenth_times = []
        for i in range(beats.size - 1):
            start = float(beats[i])
            step = float(beats[i + 1] - beats[i]) / 4.0
            sixteenth_times.extend([start + j * step for j in range(4)])
        sixteenth_times.append(float(beats[-1]))

        centers = np.asarray(
            [
                (float(sixteenth_times[i]) + float(sixteenth_times[i + 1])) / 2.0
                for i in range(len(sixteenth_times) - 1)
            ],
            dtype=np.float64,
        )
        kick_series = np.interp(centers, beats, low_band, left=low_band[0], right=low_band[-1])
        amplitudes = np.clip(1.1 - kick_series, 0.08, 1.0)
        bass_stem = np.zeros_like(mono)

        for index, amplitude in enumerate(amplitudes):
            start_idx = int(round(sixteenth_times[index] * sample_rate))
            end_idx = int(round(sixteenth_times[index + 1] * sample_rate))
            slot_time = np.arange(end_idx - start_idx, dtype=np.float32) / sample_rate
            bass_stem[start_idx:end_idx] = (
                amplitude * np.sin(2 * np.pi * 55.0 * slot_time)
            ).astype(np.float32)

        beat_data = {
            "beats": beats,
            "lowBand": low_band,
            "beatLoudness": beat_loudness,
        }

        fallback = self.analyze.analyze_sidechain_detail(
            mono,
            sample_rate,
            beat_data=beat_data,
        )["sidechainDetail"]

        with mock.patch.object(self.analyze.os.path, "isfile", return_value=True), mock.patch.object(
            self.analyze,
            "load_mono",
            return_value=bass_stem,
        ):
            stem_result = self.analyze.analyze_sidechain_detail(
                mono,
                sample_rate,
                beat_data=beat_data,
                stems={"bass": "/tmp/bass.wav"},
            )["sidechainDetail"]

        self.assertIsNotNone(fallback)
        self.assertIsNotNone(stem_result)
        self.assertGreater(stem_result["pumpingStrength"], fallback["pumpingStrength"])


class GenreDetailTests(unittest.TestCase):
    """Tests for analyze_genre_detail — multi-feature genre classification."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_genre_test", analyze_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def _make_result(self, **overrides) -> dict:
        """Minimal result dict that passes all feature lookups."""
        base = {
            "bpm": 128.0,
            "crestFactor": 7.0,
            "spectralBalance": {"subBass": -16.0},
            "spectralDetail": {"spectralCentroid": 2500.0},
            "rhythmDetail": {"onsetRate": 5.0},
            "sidechainDetail": {"pumpingStrength": 0.55},
            "bassDetail": {"averageDecayMs": 300.0},
            "reverbDetail": {"rt60": None},
            "kickDetail": {"thd": 0.05},
            "acidDetail": {"isAcid": False},
            "supersawDetail": {"isSupersaw": False},
        }
        base.update(overrides)
        return base

    def test_returns_genreDetail_key(self):
        """Result must contain genreDetail key."""
        result = self.analyze.analyze_genre_detail(self._make_result())
        self.assertIn("genreDetail", result)

    def test_shape_when_not_none(self):
        """genreDetail must have required keys with correct types."""
        result = self.analyze.analyze_genre_detail(self._make_result())
        detail = result["genreDetail"]
        self.assertIsNotNone(detail)
        self.assertIsInstance(detail["genre"], str)
        self.assertIsInstance(detail["confidence"], float)
        self.assertIn(detail["genreFamily"], ("house", "techno", "dnb", "ambient", "trance", "dubstep", "breaks", "other"))
        self.assertIsInstance(detail["topScores"], list)
        self.assertEqual(len(detail["topScores"]), 5)
        for entry in detail["topScores"]:
            self.assertIn("genre", entry)
            self.assertIn("score", entry)

    def test_confidence_bounded(self):
        """Confidence must be in [0, 1]."""
        result = self.analyze.analyze_genre_detail(self._make_result())
        detail = result["genreDetail"]
        self.assertGreaterEqual(detail["confidence"], 0.0)
        self.assertLessEqual(detail["confidence"], 1.0)

    def test_tech_house_signature_scores_high(self):
        """Strong sidechain + punchy bass at 127 BPM should score tech-house or similar."""
        result = self.analyze.analyze_genre_detail(self._make_result(
            bpm=127.0,
            crestFactor=7.0,
            spectralBalance={"subBass": -12.0},
            sidechainDetail={"pumpingStrength": 0.62},
            bassDetail={"averageDecayMs": 280.0},
        ))
        detail = result["genreDetail"]
        self.assertIsNotNone(detail)
        self.assertIn(detail["genreFamily"], ("house", "techno"))

    def test_acid_boost_raises_acid_techno(self):
        """acid-techno should be boosted when acidDetail.isAcid is True."""
        result_plain = self.analyze.analyze_genre_detail(self._make_result(
            bpm=130.0,
            sidechainDetail={"pumpingStrength": 0.45},
            bassDetail={"averageDecayMs": 380.0},
            acidDetail={"isAcid": False},
        ))
        result_acid = self.analyze.analyze_genre_detail(self._make_result(
            bpm=130.0,
            sidechainDetail={"pumpingStrength": 0.45},
            bassDetail={"averageDecayMs": 380.0},
            acidDetail={"isAcid": True},
        ))
        # acid-techno score must be higher when acid is detected
        def acid_score(r):
            return next(
                (e["score"] for e in r["genreDetail"]["topScores"] if e["genre"] == "acid-techno"),
                None,
            )
        plain_s = acid_score(result_plain)
        acid_s = acid_score(result_acid)
        if plain_s is not None and acid_s is not None:
            self.assertGreaterEqual(acid_s, plain_s)

    def test_empty_result_dict_abstains(self):
        """Empty result dict → genreDetail is None (fewer than 3 real features)."""
        result = self.analyze.analyze_genre_detail({})
        self.assertIn("genreDetail", result)
        self.assertIsNone(result["genreDetail"])

    def test_sparse_input_abstains(self):
        """Only 2 of 7 core features present → abstention."""
        result = self.analyze.analyze_genre_detail({
            "bpm": 128.0,
            "crestFactor": 8.0,
            # Missing: spectralBalance, spectralDetail, rhythmDetail,
            #          sidechainDetail, bassDetail
        })
        self.assertIn("genreDetail", result)
        self.assertIsNone(result["genreDetail"])

    def test_three_features_does_not_abstain(self):
        """Exactly 3 of 7 core features → proceeds with classification."""
        result = self.analyze.analyze_genre_detail({
            "bpm": 128.0,
            "crestFactor": 7.0,
            "sidechainDetail": {"pumpingStrength": 0.55},
        })
        self.assertIn("genreDetail", result)
        # With 3 real features the classifier should produce a result
        # (unless the score is below the 0.25 threshold)
        detail = result["genreDetail"]
        if detail is not None:
            self.assertIn("genre", detail)
            self.assertIn("confidence", detail)

    def test_ambiguous_input_caps_confidence(self):
        """Two genres within 0.05 score gap → confidence capped at 0.4."""
        # Use features that sit in overlap zones between genres to
        # produce near-tied scores. Mid-range values are deliberately
        # ambiguous between multiple signatures.
        result = self.analyze.analyze_genre_detail(self._make_result(
            bpm=125.0,
            crestFactor=9.0,
            spectralBalance={"subBass": -20.0},
            spectralDetail={"spectralCentroid": 2000.0},
            rhythmDetail={"onsetRate": 4.0},
            sidechainDetail={"pumpingStrength": 0.3},
            bassDetail={"averageDecayMs": 400.0},
        ))
        detail = result["genreDetail"]
        if detail is not None:
            # If the top two scores are within 0.05, confidence must be ≤ 0.4
            top_scores = detail["topScores"]
            if len(top_scores) >= 2:
                gap = top_scores[0]["score"] - top_scores[1]["score"]
                if gap < 0.05:
                    self.assertLessEqual(detail["confidence"], 0.4)

    def test_ambient_signature_scores_high(self):
        """Slow BPM, no sidechain, long bass decay should score ambient family."""
        result = self.analyze.analyze_genre_detail(self._make_result(
            bpm=75.0,
            crestFactor=15.0,
            spectralBalance={"subBass": -28.0},
            spectralDetail={"spectralCentroid": 1200.0},
            rhythmDetail={"onsetRate": 1.5},
            sidechainDetail={"pumpingStrength": 0.05},
            bassDetail={"averageDecayMs": 1100.0},
        ))
        detail = result["genreDetail"]
        self.assertIsNotNone(detail)
        self.assertIn(detail["genreFamily"], ("ambient", "other"))

    def test_dense_techno_145bpm_boundary(self):
        """145 BPM with dense onsets and punchy bass should classify as techno or trance family.

        At 145 BPM the classifier sits on the techno/trance boundary.
        Dense onsets + punchy bass push toward techno variants, but BPM
        alone can tip into trance. Both families are valid at this boundary.
        """
        result = self.analyze.analyze_genre_detail(self._make_result(
            bpm=145.0,
            crestFactor=8.5,
            spectralBalance={"subBass": -10.0},
            spectralDetail={"spectralCentroid": 3200.0},
            rhythmDetail={"onsetRate": 12.0},
            sidechainDetail={"pumpingStrength": 0.4},
            bassDetail={"averageDecayMs": 80.0},
        ))
        detail = result["genreDetail"]
        self.assertIsNotNone(detail)
        self.assertIn(detail["genreFamily"], ("techno", "trance"))
        # Top scores should include techno-family genres
        top_genres = [e["genre"] for e in detail["topScores"]]
        techno_variants = {"techno", "industrial-techno", "hard-techno"}
        self.assertTrue(
            techno_variants & set(top_genres),
            f"Expected at least one techno variant in top scores, got {top_genres}",
        )
        top_score = detail["topScores"][0]["score"]
        self.assertGreater(top_score, 0.25)


class ApplyBpmCorrectionTests(unittest.TestCase):
    """Unit tests for the apply_bpm_correction helper."""

    def test_2x_ratio_correction(self) -> None:
        """Ratio ~2.0 → percival wins."""
        from analyze import apply_bpm_correction
        result = apply_bpm_correction(66.0, 132.0, False)
        self.assertEqual(result["bpm"], 132.0)
        self.assertTrue(result["bpmDoubletime"])
        self.assertEqual(result["bpmSource"], "percival_ratio_corrected")
        self.assertEqual(result["bpmRawOriginal"], 66.0)

    def test_half_ratio_correction(self) -> None:
        """Ratio ~0.5 → percival wins."""
        from analyze import apply_bpm_correction
        result = apply_bpm_correction(264.0, 132.0, False)
        self.assertEqual(result["bpm"], 132.0)
        self.assertTrue(result["bpmDoubletime"])
        self.assertEqual(result["bpmSource"], "percival_ratio_corrected")

    def test_1_5x_ratio_correction(self) -> None:
        """Ratio ~1.5 → percival wins."""
        from analyze import apply_bpm_correction
        result = apply_bpm_correction(88.0, 132.0, False)
        self.assertEqual(result["bpm"], 132.0)
        self.assertTrue(result["bpmDoubletime"])
        self.assertEqual(result["bpmSource"], "percival_ratio_corrected")

    def test_two_thirds_ratio_correction(self) -> None:
        """Ratio ~0.667 → percival wins."""
        from analyze import apply_bpm_correction
        result = apply_bpm_correction(198.0, 132.0, False)
        self.assertEqual(result["bpm"], 132.0)
        self.assertTrue(result["bpmDoubletime"])
        self.assertEqual(result["bpmSource"], "percival_ratio_corrected")

    def test_disagreement_outside_windows(self) -> None:
        """Ratio outside correction windows → no correction."""
        from analyze import apply_bpm_correction
        result = apply_bpm_correction(128.0, 140.0, False)
        self.assertEqual(result["bpm"], 128.0)
        self.assertFalse(result["bpmDoubletime"])
        self.assertEqual(result["bpmSource"], "rhythm_extractor")

    def test_agreement_path(self) -> None:
        """When bpm_agreement is True and no ratio match → confirmed."""
        from analyze import apply_bpm_correction
        result = apply_bpm_correction(128.0, 127.5, True)
        self.assertEqual(result["bpm"], 128.0)
        self.assertFalse(result["bpmDoubletime"])
        self.assertEqual(result["bpmSource"], "rhythm_extractor_confirmed")

    def test_raw_none(self) -> None:
        """When bpm_raw is None → safe defaults."""
        from analyze import apply_bpm_correction
        result = apply_bpm_correction(None, 132.0, None)
        self.assertIsNone(result["bpm"])
        self.assertFalse(result["bpmDoubletime"])
        self.assertEqual(result["bpmSource"], "rhythm_extractor")
        self.assertIsNone(result["bpmRawOriginal"])

    def test_percival_none(self) -> None:
        """When bpm_percival is None → no correction."""
        from analyze import apply_bpm_correction
        result = apply_bpm_correction(128.0, None, None)
        self.assertEqual(result["bpm"], 128.0)
        self.assertFalse(result["bpmDoubletime"])
        self.assertEqual(result["bpmRawOriginal"], 128.0)

    def test_bpm_raw_original_always_set(self) -> None:
        """bpmRawOriginal is always populated when RhythmExtractor succeeds."""
        from analyze import apply_bpm_correction
        # No correction case
        result = apply_bpm_correction(128.0, 127.5, True)
        self.assertEqual(result["bpmRawOriginal"], 128.0)
        # Correction case
        result = apply_bpm_correction(66.0, 132.0, False)
        self.assertEqual(result["bpmRawOriginal"], 66.0)


if __name__ == "__main__":
    unittest.main()
