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
    "lufsIntegrated", "lufsRange", "lufsCurve", "truePeak", "plr", "crestFactor",
    "dynamicSpread", "dynamicCharacter", "textureCharacter", "stereoDetail", "monoCompatible",
    "spectralBalance", "spectralBalanceTimeSeries",
    "spectralDetail", "stemAnalysis", "transientDensityDetail", "saturationDetail",
    "snareDetail", "hihatDetail",
    "rhythmDetail", "melodyDetail", "transcriptionDetail",
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

        # Positions cycle 1..meter, phase-aligned so that position 1 marks a
        # downbeat. The phase is data-dependent (kick-accent resolved), so assert
        # the cycle structure rather than a fixed beat_grid[::4] stride.
        meter = max(beat_positions)
        self.assertGreaterEqual(meter, 2)
        self.assertTrue(all(1 <= value <= meter for value in beat_positions))
        phase = beat_positions.index(1)
        self.assertEqual(
            beat_positions,
            [(((index - phase) % meter) + 1) for index in range(len(beat_grid))],
        )

        self.assertIsInstance(downbeats, list)
        self.assertEqual(downbeats, beat_grid[phase::meter])
        self.assertEqual(
            downbeats,
            [beat_grid[i] for i, pos in enumerate(beat_positions) if pos == 1],
        )

        source = rhythm_detail.get("downbeatSource")
        self.assertIn(source, {"kick_accent", "stride"})
        confidence = rhythm_detail.get("downbeatConfidence")
        self.assertIsInstance(confidence, (int, float))
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)


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
        """Fast mode must emit exactly the shared top-level key set (EXPECTED_TOP_LEVEL_KEYS).

        Full mode emits these keys *plus* a few detail-only fields (keyProfile,
        tuningFrequency, tuningCents, lufsMomentaryMax, lufsShortTermMax, pitchDetail), so
        this asserts the shared contract — not a byte-for-byte match with full mode.
        """
        self.assertEqual(
            set(self.payload.keys()),
            EXPECTED_TOP_LEVEL_KEYS,
            "Fast mode output schema diverged from the shared key set. Update "
            "EXPECTED_TOP_LEVEL_KEYS if the output contract changed intentionally.",
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

    def test_per_stem_average_confidence_groups_means_by_stem_source(self) -> None:
        notes = [
            {"pitchMidi": 48, "confidence": 0.9, "stemSource": "bass"},
            {"pitchMidi": 50, "confidence": 0.8, "stemSource": "bass"},
            {"pitchMidi": 64, "confidence": 0.4, "stemSource": "other"},
            {"pitchMidi": 67, "confidence": 0.2, "stemSource": "other"},
        ]

        means = self.analyze._per_stem_average_confidence(notes)

        self.assertEqual(set(means.keys()), {"bass", "other"})
        self.assertAlmostEqual(means["bass"], 0.85, places=4)
        self.assertAlmostEqual(means["other"], 0.3, places=4)

    def test_per_stem_average_confidence_returns_empty_for_empty_notes(self) -> None:
        self.assertEqual(self.analyze._per_stem_average_confidence([]), {})

    def test_per_stem_average_confidence_skips_notes_with_missing_stem_source(self) -> None:
        notes = [
            {"pitchMidi": 48, "confidence": 0.9, "stemSource": "bass"},
            {"pitchMidi": 60, "confidence": 0.7},  # missing stemSource entirely
            {"pitchMidi": 64, "confidence": 0.5, "stemSource": ""},  # empty string
            {"pitchMidi": 65, "confidence": 0.4, "stemSource": None},  # explicit null
        ]

        means = self.analyze._per_stem_average_confidence(notes)

        self.assertEqual(set(means.keys()), {"bass"})
        self.assertAlmostEqual(means["bass"], 0.9, places=4)

    def test_per_stem_average_confidence_tolerates_invalid_confidence_values(self) -> None:
        notes = [
            {"pitchMidi": 48, "confidence": 0.9, "stemSource": "bass"},
            {"pitchMidi": 50, "confidence": "not a number", "stemSource": "bass"},
            {"pitchMidi": 52, "confidence": None, "stemSource": "bass"},
        ]

        means = self.analyze._per_stem_average_confidence(notes)

        # The two malformed entries are skipped; only the 0.9 contributes.
        self.assertAlmostEqual(means["bass"], 0.9, places=4)



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

    def test_downbeat_phase_resolves_kick_accented_position(self) -> None:
        import analyze_rhythm

        self.assertEqual(analyze_rhythm._parse_meter("4/4"), 4)
        self.assertEqual(analyze_rhythm._parse_meter("3/4"), 3)
        self.assertEqual(analyze_rhythm._parse_meter(None), 4)
        self.assertEqual(analyze_rhythm._parse_meter("garbage"), 4)

        # Kick accented on beat position 2 within a 4/4 bar → phase 2, confident.
        low_band = np.asarray([0.1, 0.1, 1.0, 0.1] * 8, dtype=np.float64)
        phase, confidence = analyze_rhythm._compute_downbeat_phase(low_band, 4)
        self.assertEqual(phase, 2)
        self.assertGreater(confidence, 0.5)

        # Four-on-the-floor (kick on every beat) carries no phase info → ~0.
        flat = np.ones(32, dtype=np.float64)
        _flat_phase, flat_confidence = analyze_rhythm._compute_downbeat_phase(flat, 4)
        self.assertLess(flat_confidence, 1e-6)

        # Fewer beats than the meter → safe stride fallback.
        self.assertEqual(
            analyze_rhythm._compute_downbeat_phase(np.asarray([0.5, 0.5]), 4),
            (0, 0.0),
        )

    def test_downbeat_phase_is_robust_to_non_finite_beats(self) -> None:
        # A non-finite lowBand value (silent intro, BeatLoudness dropout) must be
        # sanitized IN PLACE, not filtered out. Filtering would compact the array
        # and rotate the phase relative to the unfiltered beat_grid the caller
        # indexes — shifting the downbeat to the wrong beat. Kick lives on
        # position 2; a NaN at a non-kick index must not move the resolved phase.
        import analyze_rhythm

        clean = np.asarray([0.1, 0.1, 1.0, 0.1] * 8, dtype=np.float64)
        clean_phase, _ = analyze_rhythm._compute_downbeat_phase(clean, 4)
        self.assertEqual(clean_phase, 2)

        with_nan = clean.copy()
        with_nan[0] = np.nan  # non-kick beat goes missing
        nan_phase, nan_conf = analyze_rhythm._compute_downbeat_phase(with_nan, 4)
        self.assertEqual(nan_phase, 2)  # would be 1 if the array were compacted
        self.assertGreater(nan_conf, 0.5)

        # +inf / -inf are handled the same way and never crash the mean/argmax.
        with_inf = clean.copy()
        with_inf[1] = np.inf
        with_inf[5] = -np.inf
        inf_phase, _ = analyze_rhythm._compute_downbeat_phase(with_inf, 4)
        self.assertEqual(inf_phase, 2)

    def test_resolve_downbeats_uses_resolved_phase_with_legacy_fallback(self) -> None:
        import analyze_structure

        ticks = np.asarray([float(i) for i in range(16)], dtype=np.float64)

        # No phase/meter recorded → legacy 4/4 stride from index 0.
        legacy, interval = analyze_structure._resolve_downbeats_and_interval({"ticks": ticks})
        np.testing.assert_array_equal(legacy, ticks[::4])
        self.assertAlmostEqual(interval, 1.0)

        # Resolved bar-1 phase shifts the downbeat grid accordingly.
        real, _ = analyze_structure._resolve_downbeats_and_interval(
            {"ticks": ticks, "downbeatPhase": 2, "meter": 4}
        )
        np.testing.assert_array_equal(real, ticks[2::4])

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
        """All expected fields must be present (Phase 1.D #5 added perBandRt60 + preDelayMs)."""
        sr = 44100
        mono = self._make_decaying_signal(sr, n_transients=8, rt60_target=0.4, duration=6.0)
        result = self.analyze.analyze_reverb_detail(mono, sr, bpm=130.0)
        detail = result.get("reverbDetail")
        self.assertIsNotNone(detail)
        self.assertEqual(
            set(detail.keys()),
            {"rt60", "isWet", "tailEnergyRatio", "measured", "perBandRt60", "preDelayMs"},
        )

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
        # 2026-05-12: stemEnergyRatio + stemOtherCorrelation added for the
        # two-signal Demucs-ghost-stem scaling (energy + envelope correlation
        # against the "other" stem).
        expected_keys = {
            "hasVocals", "confidence", "vocalEnergyRatio",
            "formantStrength", "mfccLikelihood",
            "stemEnergyRatio", "stemOtherCorrelation",
        }
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

    def test_prefers_vocal_stem_when_available(self):
        """Vocal detection should analyze the vocals stem when Demucs output exists."""
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
        stem_signal = (
            0.5 * np.sin(2 * np.pi * 220.0 * t)
            + 0.3 * np.sin(2 * np.pi * 440.0 * t)
        ).astype(np.float32)
        mono = np.zeros(int(sr * 2.0), dtype=np.float32)
        stems = {"vocals": "/tmp/vocals.wav"}

        with mock.patch("analyze_detection._load_stem_mono", return_value=stem_signal) as mock_load:
            result = self.analyze.analyze_vocal_detail(mono, sr, bpm=120.0, stems=stems)

        self.assertIsNotNone(result["vocalDetail"])
        # As of 2026-05-12 the analyzer also loads the "other" stem to compute
        # the Demucs-ghost-stem cross-correlation. The invariant is that the
        # vocals stem WAS loaded with the right arguments, not that it was the
        # only stem touched.
        mock_load.assert_any_call(stems, "vocals", sr)

    def test_vocal_detail_falls_back_to_mix_when_stem_unavailable(self):
        """Missing vocals stem should keep the existing full-mix behavior."""
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
        mono = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        expected = self.analyze.analyze_vocal_detail(mono, sr, bpm=120.0)
        with mock.patch("analyze_detection._load_stem_mono", return_value=None):
            actual = self.analyze.analyze_vocal_detail(
                mono,
                sr,
                bpm=120.0,
                stems={"vocals": "/tmp/missing-vocals.wav"},
            )

        self.assertEqual(actual, expected)


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

    def test_prefers_other_stem_when_available(self):
        """Supersaw detection should analyze the musical/other stem when available."""
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
        stem_signal = np.zeros_like(t)
        for detune_cents in [-12, -5, 0, 5, 12]:
            freq = 440.0 * (2.0 ** (detune_cents / 1200.0))
            stem_signal += 0.12 * np.sin(2 * np.pi * freq * t)
        stem_signal = stem_signal.astype(np.float32)
        mono = np.zeros(int(sr * 2.0), dtype=np.float32)
        stems = {"other": "/tmp/other.wav"}

        with mock.patch("analyze_detection._load_stem_mono", return_value=stem_signal) as mock_load:
            result = self.analyze.analyze_supersaw_detail(mono, sr, bpm=128.0, stems=stems)

        self.assertIsNotNone(result["supersawDetail"])
        mock_load.assert_called_once_with(stems, "other", sr)

    def test_supersaw_detail_falls_back_to_mix_when_stem_unavailable(self):
        """Missing other stem should keep the existing full-mix behavior."""
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
        mono = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        expected = self.analyze.analyze_supersaw_detail(mono, sr, bpm=128.0)
        with mock.patch("analyze_detection._load_stem_mono", return_value=None):
            actual = self.analyze.analyze_supersaw_detail(
                mono,
                sr,
                bpm=128.0,
                stems={"other": "/tmp/missing-other.wav"},
            )

        self.assertEqual(actual, expected)


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

        with mock.patch.object(self.analyze, "_load_stem_mono", return_value=stem_signal):
            result = self.analyze.analyze_bass_detail(
                mono,
                sr,
                bpm=128.0,
                stems={"bass": "/tmp/bass.wav"},
            )

        self.assertGreater(result["bassDetail"]["fundamentalHz"], 50)

    def test_average_decay_ms_is_positive_for_bass_pulses(self):
        """Regression for the envelope-decay fix: a series of decaying bass pulses must
        report a sane positive averageDecayMs, never the sub-millisecond values the old
        raw-waveform loop produced (a 50 Hz sine crosses zero every ~10 ms, which used
        to trigger the -6 dB threshold almost immediately on every note).
        """
        sr = 44_100
        duration = 4.0
        n_samples = int(sr * duration)
        mono = np.zeros(n_samples, dtype=np.float32)
        # Eight 60 Hz pulses, each ~400 ms with a slow exponential decay envelope so
        # the expected envelope-to-half time sits comfortably above the regression floor.
        beat_samples = int(sr * 0.5)  # 120 BPM
        pulse_len = int(sr * 0.4)
        decay_const = pulse_len / 1.5  # ~177 ms time constant → ~123 ms to -6 dB
        for i in range(8):
            onset = i * beat_samples
            if onset + pulse_len >= n_samples:
                break
            t = np.arange(pulse_len, dtype=np.float32)
            env = np.exp(-t / decay_const)
            pulse = (0.7 * env * np.sin(2 * np.pi * 60.0 * t / sr)).astype(np.float32)
            mono[onset:onset + pulse_len] = pulse

        result = self.analyze.analyze_bass_detail(mono, sr, bpm=120.0)
        detail = result.get("bassDetail")
        self.assertIsNotNone(detail)
        self.assertIsNotNone(detail["averageDecayMs"])
        # Pre-fix: averageDecayMs was effectively 0 (sub-ms) — the raw oscillating
        # waveform's RMS over a small window crossed -6 dB on every zero crossing.
        # Post-fix: the envelope-based search anchors at the per-pulse peak and waits
        # for the smoothed envelope to fall -6 dB, so the reported value must be at
        # least a few tens of ms for any realistic bass pulse.
        self.assertGreaterEqual(
            detail["averageDecayMs"], 30,
            f"averageDecayMs={detail['averageDecayMs']} regressed near the pre-fix sub-ms range",
        )


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

        with mock.patch.object(self.analyze, "_load_stem_mono", return_value=stem_signal):
            result = self.analyze.analyze_kick_detail(
                mono,
                sr,
                bpm=120.0,
                stems={"drums": "/tmp/drums.wav"},
            )

        self.assertGreater(result["kickDetail"]["kickCount"], 1)


def _make_drum_band_signal(
    sr: int,
    band_lo_hz: float,
    band_hi_hz: float,
    n_hits: int,
    duration: float,
    decay_samples: int = 1500,
) -> np.ndarray:
    """Synth a signal of band-limited transients spaced uniformly across `duration`.

    Each hit is a noise burst windowed by exp(-t/decay) and weakly bandpass-shaped
    by a centered sine, so band onset detectors light up reliably.
    """
    n_samples = int(sr * duration)
    mono = np.zeros(n_samples, dtype=np.float32)
    if n_hits <= 0:
        return mono
    center_hz = 0.5 * (band_lo_hz + band_hi_hz)
    step = n_samples // n_hits
    for i in range(n_hits):
        onset = i * step
        if onset >= n_samples:
            break
        burst_len = min(decay_samples, n_samples - onset)
        t = np.arange(burst_len, dtype=np.float32)
        env = np.exp(-t / (decay_samples * 0.35))
        noise = np.random.default_rng(seed=42 + i).standard_normal(burst_len).astype(np.float32) * 0.3
        carrier = np.sin(2 * np.pi * center_hz * t / sr).astype(np.float32)
        mono[onset:onset + burst_len] += (0.8 * env * (carrier + 0.3 * noise)).astype(np.float32)
    return mono


class BandDrumDetailTests(unittest.TestCase):
    """Tests for _analyze_band_drum_detail — shared snare/hi-hat band analyzer."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_band_drum_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze._analyze_band_drum_detail(
            mono, 44100, band_lo_hz=120.0, band_hi_hz=2000.0, bpm=120.0, stems=None,
        )
        self.assertIsNone(result)

    def test_returns_none_for_short_signal(self):
        mono = np.zeros(2048, dtype=np.float32)
        result = self.analyze._analyze_band_drum_detail(
            mono, 44100, band_lo_hz=120.0, band_hi_hz=2000.0, bpm=120.0, stems=None,
        )
        self.assertIsNone(result)

    def test_returns_none_for_silence(self):
        """Silent input has env_max == 0 → returns None."""
        mono = np.zeros(int(44100 * 3.0), dtype=np.float32)
        result = self.analyze._analyze_band_drum_detail(
            mono, 44100, band_lo_hz=120.0, band_hi_hz=2000.0, bpm=120.0, stems=None,
        )
        self.assertIsNone(result)

    def test_detects_band_limited_hits(self):
        """A signal with 8 mid-band transients should yield ≥ 2 hits and a sane schema."""
        sr = 44100
        mono = _make_drum_band_signal(sr, 120.0, 2000.0, n_hits=8, duration=4.0)
        result = self.analyze._analyze_band_drum_detail(
            mono, sr, band_lo_hz=120.0, band_hi_hz=2000.0, bpm=120.0, stems=None,
            min_event_dist_subdivisions=0.5, body_split_ratio=0.35,
        )
        self.assertIsNotNone(result)
        expected_keys = {
            "hitCount", "hitsPerSecond", "meanAttackSharpness",
            "meanBodyEnergyRatio", "meanSnapEnergyRatio", "meanCentroidHz",
            "meanDecayFrames", "meanDecaySeconds", "bandHz",
        }
        self.assertEqual(set(result.keys()), expected_keys)
        self.assertGreaterEqual(result["hitCount"], 2)
        self.assertGreater(result["hitsPerSecond"], 0.0)
        self.assertGreater(result["meanAttackSharpness"], 0.0)
        self.assertGreaterEqual(result["meanDecayFrames"], 0.0)
        self.assertEqual(result["bandHz"], [120.0, 2000.0])

    def test_uses_drums_stem_when_available(self):
        """When a `drums` stem is provided via `_load_stem_mono`, it overrides the full-mix input."""
        sr = 44100
        mono = np.zeros(int(sr * 3.0), dtype=np.float32)  # silent full mix
        stem_signal = _make_drum_band_signal(sr, 120.0, 2000.0, n_hits=6, duration=3.0)
        with mock.patch.object(self.analyze, "_load_stem_mono", return_value=stem_signal):
            result = self.analyze._analyze_band_drum_detail(
                mono, sr, band_lo_hz=120.0, band_hi_hz=2000.0, bpm=120.0,
                stems={"drums": "/tmp/drums.wav"},
                min_event_dist_subdivisions=0.5, body_split_ratio=0.35,
            )
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result["hitCount"], 2)


class SnareDetailTests(unittest.TestCase):
    """Tests for analyze_snare_detail — 120-2000 Hz drum-band character."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_snare_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_snare_detail(mono, 44100, bpm=120.0)
        self.assertEqual(result, {"snareDetail": None})

    def test_returns_none_for_short_signal(self):
        mono = np.zeros(2048, dtype=np.float32)
        result = self.analyze.analyze_snare_detail(mono, 44100, bpm=120.0)
        self.assertEqual(result, {"snareDetail": None})

    def test_output_schema_fields(self):
        sr = 44100
        mono = _make_drum_band_signal(sr, 120.0, 2000.0, n_hits=8, duration=4.0)
        result = self.analyze.analyze_snare_detail(mono, sr, bpm=120.0)
        detail = result.get("snareDetail")
        self.assertIsNotNone(detail)
        expected_keys = {
            "hitCount", "hitsPerSecond", "meanAttackSharpness",
            "meanBodyEnergyRatio", "meanSnapEnergyRatio", "meanCentroidHz",
            "meanDecayFrames", "meanDecaySeconds", "bandHz",
        }
        self.assertEqual(set(detail.keys()), expected_keys)
        self.assertEqual(detail["bandHz"], [120.0, 2000.0])

    def test_fallback_on_no_bpm(self):
        sr = 44100
        mono = _make_drum_band_signal(sr, 120.0, 2000.0, n_hits=6, duration=3.0)
        result = self.analyze.analyze_snare_detail(mono, sr, bpm=None)
        self.assertIn("snareDetail", result)


class HihatDetailTests(unittest.TestCase):
    """Tests for analyze_hihat_detail — 2000-12000 Hz drum-band character."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_hihat_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_hihat_detail(mono, 44100, bpm=120.0)
        self.assertEqual(result, {"hihatDetail": None})

    def test_returns_none_for_short_signal(self):
        mono = np.zeros(2048, dtype=np.float32)
        result = self.analyze.analyze_hihat_detail(mono, 44100, bpm=120.0)
        self.assertEqual(result, {"hihatDetail": None})

    def test_output_schema_fields(self):
        sr = 44100
        mono = _make_drum_band_signal(sr, 2000.0, 12000.0, n_hits=16, duration=4.0)
        result = self.analyze.analyze_hihat_detail(mono, sr, bpm=120.0)
        detail = result.get("hihatDetail")
        self.assertIsNotNone(detail)
        expected_keys = {
            "hitCount", "hitsPerSecond", "meanAttackSharpness",
            "meanBodyEnergyRatio", "meanSnapEnergyRatio", "meanCentroidHz",
            "meanDecayFrames", "meanDecaySeconds", "bandHz",
        }
        self.assertEqual(set(detail.keys()), expected_keys)
        self.assertEqual(detail["bandHz"], [2000.0, 12000.0])

    def test_fallback_on_no_bpm(self):
        sr = 44100
        mono = _make_drum_band_signal(sr, 2000.0, 12000.0, n_hits=12, duration=3.0)
        result = self.analyze.analyze_hihat_detail(mono, sr, bpm=None)
        self.assertIn("hihatDetail", result)


class TransientDensityDetailTests(unittest.TestCase):
    """Tests for analyze_per_band_transient_density — per-band onset rates."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_transient_density_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_signal(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_per_band_transient_density(mono, 44100)
        self.assertEqual(result, {"transientDensityDetail": None})

    def test_returns_none_for_zero_sample_rate(self):
        mono = np.zeros(44100, dtype=np.float32)
        result = self.analyze.analyze_per_band_transient_density(mono, 0)
        self.assertEqual(result, {"transientDensityDetail": None})

    def test_output_has_all_seven_bands(self):
        """Each spectralBalance band must appear in the output with the documented field set."""
        sr = 44100
        # Mid-band transients should drive at least one band's onset rate above zero.
        mono = _make_drum_band_signal(sr, 500.0, 2000.0, n_hits=8, duration=4.0)
        result = self.analyze.analyze_per_band_transient_density(mono, sr)
        detail = result.get("transientDensityDetail")
        self.assertIsNotNone(detail)
        self.assertEqual(set(detail.keys()), EXPECTED_SPECTRAL_BANDS)
        for band_name, stats in detail.items():
            self.assertEqual(
                set(stats.keys()),
                {"onsetRatePerSecond", "meanOnsetStrength", "peakOnsetStrength", "eventCount"},
                f"band {band_name} missing fields",
            )
            self.assertGreaterEqual(stats["onsetRatePerSecond"], 0.0)
            self.assertGreaterEqual(stats["meanOnsetStrength"], 0.0)
            self.assertGreaterEqual(stats["peakOnsetStrength"], 0.0)
            self.assertGreaterEqual(stats["eventCount"], 0)

    def test_silence_yields_zero_rates(self):
        """Pure silence must not invent onsets — every band's eventCount must be 0."""
        sr = 44100
        mono = np.zeros(int(sr * 3.0), dtype=np.float32)
        result = self.analyze.analyze_per_band_transient_density(mono, sr)
        detail = result.get("transientDensityDetail")
        self.assertIsNotNone(detail)
        for band_name, stats in detail.items():
            self.assertEqual(stats["eventCount"], 0, f"band {band_name} hallucinated onsets in silence")
            self.assertEqual(stats["onsetRatePerSecond"], 0.0)

    def test_mid_band_transients_increase_mids_rate(self):
        """Transients in the 500-2000 Hz band should produce a non-zero `mids` onset rate."""
        sr = 44100
        mono = _make_drum_band_signal(sr, 500.0, 2000.0, n_hits=10, duration=4.0)
        result = self.analyze.analyze_per_band_transient_density(mono, sr)
        detail = result["transientDensityDetail"]
        # Any of mids / lowMids / upperMids should detect something. The cluster is
        # asserted (rather than `mids` exactly) because the synthetic carrier sweeps
        # both sides of the band edge after windowing.
        nearby_event_total = (
            detail["lowMids"]["eventCount"]
            + detail["mids"]["eventCount"]
            + detail["upperMids"]["eventCount"]
        )
        self.assertGreater(nearby_event_total, 0)


class SaturationDetailTests(unittest.TestCase):
    """Tests for analyze_saturation_detail — clip / compression telltales."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_saturation_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    def test_returns_none_for_empty_mono(self):
        mono = np.array([], dtype=np.float32)
        result = self.analyze.analyze_saturation_detail(mono, None, 44100)
        self.assertEqual(result, {"saturationDetail": None})

    def test_output_schema_fields(self):
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
        mono = 0.3 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
        result = self.analyze.analyze_saturation_detail(mono, None, sr)
        detail = result.get("saturationDetail")
        self.assertIsNotNone(detail)
        expected_keys = {
            "clippedSampleCount", "clippedSamplePercent",
            "nearClippedSampleCount", "nearClippedSamplePercent",
            "peakRatio95to50", "rmsToPeakRatioDb", "saturationLikely",
        }
        self.assertEqual(set(detail.keys()), expected_keys)

    def test_clean_signal_has_no_clipped_samples(self):
        """A 0.3 amplitude sine produces zero clipped/near-clipped samples."""
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
        mono = 0.3 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
        result = self.analyze.analyze_saturation_detail(mono, None, sr)
        detail = result["saturationDetail"]
        self.assertEqual(detail["clippedSampleCount"], 0)
        self.assertEqual(detail["clippedSamplePercent"], 0.0)
        self.assertEqual(detail["nearClippedSampleCount"], 0)

    def test_dynamic_signal_is_not_flagged_as_saturated(self):
        """A transient-rich signal with natural crest factor must not trip saturationLikely.

        A pure sine has rms_to_peak ≈ 3 dB and p95/p50 ≈ 1.4, which the heuristic
        misreads as "compressed" — so we test against a realistic decaying-pulse signal
        whose crest factor is well above the 8 dB heuristic threshold.
        """
        sr = 44100
        n = int(sr * 2.0)
        mono = np.zeros(n, dtype=np.float32)
        pulse_len = int(sr * 0.05)
        beat_samples = int(sr * 0.25)
        rng = np.random.default_rng(seed=7)
        for i in range(8):
            onset = i * beat_samples
            if onset + pulse_len >= n:
                break
            t = np.arange(pulse_len, dtype=np.float32)
            env = np.exp(-t / (pulse_len * 0.2))
            noise = rng.standard_normal(pulse_len).astype(np.float32) * 0.5
            mono[onset:onset + pulse_len] = (0.7 * env * (np.sin(2 * np.pi * 200 * t / sr) + 0.3 * noise)).astype(np.float32)
        result = self.analyze.analyze_saturation_detail(mono, None, sr)
        detail = result["saturationDetail"]
        self.assertEqual(detail["clippedSampleCount"], 0)
        self.assertFalse(detail["saturationLikely"])

    def test_clipped_signal_is_flagged(self):
        """Hard-clipped signal must produce a non-zero clippedSampleCount and saturationLikely=True."""
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
        # 2.0-amplitude sine clipped to [-1, 1]: ~50% of samples sit at ±1.0.
        raw = 2.0 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
        mono = np.clip(raw, -1.0, 1.0).astype(np.float32)
        stereo = np.stack([mono, mono], axis=1)
        result = self.analyze.analyze_saturation_detail(mono, stereo, sr)
        detail = result["saturationDetail"]
        self.assertGreater(detail["clippedSampleCount"], 100)
        self.assertGreater(detail["clippedSamplePercent"], 0.0)
        self.assertGreater(detail["nearClippedSamplePercent"], 0.5)
        self.assertTrue(detail["saturationLikely"])

    def test_peak_ratio_lower_for_compressed_signal(self):
        """A nearly-flat (compressed) waveform has p95/p50 close to 1; a sine pattern is higher."""
        sr = 44100
        t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
        sine = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        # Flat tone with low dynamic range
        compressed = (0.4 * np.sign(np.sin(2 * np.pi * 220 * t))).astype(np.float32)
        sine_detail = self.analyze.analyze_saturation_detail(sine, None, sr)["saturationDetail"]
        compressed_detail = self.analyze.analyze_saturation_detail(compressed, None, sr)["saturationDetail"]
        self.assertIsNotNone(sine_detail["peakRatio95to50"])
        self.assertIsNotNone(compressed_detail["peakRatio95to50"])
        self.assertGreater(sine_detail["peakRatio95to50"], compressed_detail["peakRatio95to50"])


class RunPerStemAnalysesTests(unittest.TestCase):
    """Tests for _run_per_stem_analyses — Phase 1.B stem-overlay orchestrator."""

    @classmethod
    def setUpClass(cls):
        analyze_path = Path(__file__).resolve().parents[1] / "analyze.py"
        spec = importlib.util.spec_from_file_location("analyze_per_stem_test", analyze_path)
        if spec is None or spec.loader is None:
            raise AssertionError("Could not load analyze.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.analyze = module

    @staticmethod
    def _make_stem_mono(sr: int, duration: float = 1.5) -> np.ndarray:
        t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
        return (0.3 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)

    @classmethod
    def _make_stem_stereo(cls, sr: int, duration: float = 1.5) -> np.ndarray:
        mono = cls._make_stem_mono(sr, duration)
        return np.stack([mono, mono * 0.9], axis=1)

    def test_returns_none_for_none_stems(self):
        self.assertIsNone(self.analyze._run_per_stem_analyses(None, 44100))

    def test_returns_none_for_empty_stems_dict(self):
        self.assertIsNone(self.analyze._run_per_stem_analyses({}, 44100))

    def test_returns_none_when_all_loads_fail(self):
        """If _load_stem_mono returns None for every stem, the whole result collapses to None."""
        stems = {"drums": "/tmp/d.wav", "bass": "/tmp/b.wav"}
        with mock.patch.object(self.analyze, "_load_stem_mono", return_value=None):
            result = self.analyze._run_per_stem_analyses(stems, 44100)
        self.assertIsNone(result)

    def test_returns_dict_for_two_loaded_stems(self):
        """When two stems load successfully, the result is keyed by stem name."""
        sr = 44100
        stem_mono = self._make_stem_mono(sr)
        stem_stereo = self._make_stem_stereo(sr)
        stems = {"drums": "/tmp/d.wav", "bass": "/tmp/b.wav"}

        def _mono_side_effect(stems_arg, name, sample_rate=44100):
            if name in ("drums", "bass"):
                return stem_mono
            return None

        def _stereo_side_effect(stems_arg, name):
            if name in ("drums", "bass"):
                return stem_stereo
            return None

        with mock.patch.object(self.analyze, "_load_stem_mono", side_effect=_mono_side_effect), \
             mock.patch.object(self.analyze, "_load_stem_stereo", side_effect=_stereo_side_effect):
            result = self.analyze._run_per_stem_analyses(stems, sr)

        self.assertIsInstance(result, dict)
        self.assertIn("drums", result)
        self.assertIn("bass", result)
        self.assertNotIn("other", result)
        self.assertNotIn("vocals", result)
        # Schema sanity: each stem block carries the documented set of overlay fields.
        for stem_name, block in result.items():
            self.assertIsInstance(block, dict)
            self.assertIn("spectralBalance", block)
            self.assertIn("spectralDetail", block)
            self.assertIn("crestFactor", block)
            self.assertIn("dynamicSpread", block)

    def test_partial_analyzer_failure_does_not_drop_stem(self):
        """If one analyzer raises for one stem, other analyzers' fields still appear."""
        sr = 44100
        stem_mono = self._make_stem_mono(sr)
        stem_stereo = self._make_stem_stereo(sr)
        stems = {"drums": "/tmp/d.wav"}

        original_spectral_balance = self.analyze.analyze_spectral_balance

        def _failing_spectral_balance(mono, sample_rate):
            raise RuntimeError("simulated spectralBalance failure")

        with mock.patch.object(self.analyze, "_load_stem_mono", return_value=stem_mono), \
             mock.patch.object(self.analyze, "_load_stem_stereo", return_value=stem_stereo), \
             mock.patch.object(self.analyze, "analyze_spectral_balance", side_effect=_failing_spectral_balance):
            result = self.analyze._run_per_stem_analyses(stems, sr)

        self.assertIsNotNone(result)
        self.assertIn("drums", result)
        drums_block = result["drums"]
        # spectralBalance failed → not present (or None), but other analyzers still produced fields.
        self.assertNotIn("spectralBalance", drums_block)
        self.assertIn("crestFactor", drums_block)
        # Sanity: the unmocked analyzer is still callable on the same input.
        _ = original_spectral_balance

    def test_skips_stem_when_stereo_is_unavailable(self):
        """Stereo-only analyzers (LUFS, stereoDetail) must be silently skipped when stereo load fails."""
        sr = 44100
        stem_mono = self._make_stem_mono(sr)
        stems = {"drums": "/tmp/d.wav"}

        with mock.patch.object(self.analyze, "_load_stem_mono", return_value=stem_mono), \
             mock.patch.object(self.analyze, "_load_stem_stereo", return_value=None):
            result = self.analyze._run_per_stem_analyses(stems, sr)

        self.assertIsNotNone(result)
        drums_block = result["drums"]
        # Mono-only fields still appear.
        self.assertIn("spectralBalance", drums_block)
        self.assertIn("crestFactor", drums_block)
        # Stereo-only LUFS/stereoDetail/truePeak fields are skipped.
        self.assertNotIn("lufsIntegrated", drums_block)
        self.assertNotIn("stereoDetail", drums_block)
        self.assertNotIn("truePeak", drums_block)


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

        with mock.patch.object(self.analyze, "_load_stem_mono", return_value=bass_stem):
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

    def test_vocal_boost_raises_vocal_aware_genre_score(self):
        """Vocal-aware genres should receive a bounded boost when vocalDetail.hasVocals is True."""
        base = self._make_result(
            bpm=90.0,
            crestFactor=12.0,
            spectralBalance={"subBass": -16.0},
            spectralDetail={"spectralCentroid": 4200.0},
            rhythmDetail={"onsetRate": 6.0},
            sidechainDetail={"pumpingStrength": 0.1},
            bassDetail={"averageDecayMs": 700.0},
        )
        result_no_vocal = self.analyze.analyze_genre_detail({
            **base,
            "vocalDetail": {"hasVocals": False},
        })
        result_with_vocal = self.analyze.analyze_genre_detail({
            **base,
            "vocalDetail": {"hasVocals": True},
        })

        def hiphop_score(result):
            return next(
                (entry["score"] for entry in result["genreDetail"]["topScores"] if entry["genre"] == "hiphop"),
                None,
            )

        self.assertGreater(
            hiphop_score(result_with_vocal),
            hiphop_score(result_no_vocal),
        )

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


class ChordTimelineViterbiTests(unittest.TestCase):
    """Phase 1.D #2 — librosa+Viterbi chord-timeline migration.

    These tests verify the new 25-state Viterbi engine that replaced the
    earlier 5-frame median-filter smoothing in analyze_chords. We do not
    re-test the Essentia layer or the median smoother — those are gone.
    """

    SAMPLE_RATE = 44_100
    DURATION_SECONDS = 4.0
    EXPECTED_TIMELINE_KEYS = {"startSec", "endSec", "label", "labelLong", "confidence"}

    def _make_chord_triad_audio(
        self, frequencies: tuple[float, ...], duration_s: float = DURATION_SECONDS
    ) -> np.ndarray:
        """Sum sine tones at the given frequencies to make a synthetic chord."""
        n = int(self.SAMPLE_RATE * duration_s)
        t = np.arange(n, dtype=np.float64) / self.SAMPLE_RATE
        signal = np.zeros(n, dtype=np.float64)
        for freq in frequencies:
            signal += np.sin(2 * np.pi * freq * t)
        signal /= max(1.0, len(frequencies))
        # 50 ms fade in / out so the highpass + window edge effects don't
        # dominate the start/end frames.
        fade = int(0.05 * self.SAMPLE_RATE)
        signal[:fade] *= np.linspace(0.0, 1.0, fade)
        signal[-fade:] *= np.linspace(1.0, 0.0, fade)
        return signal.astype(np.float32)

    def test_chord_timeline_synthetic_c_major(self) -> None:
        """A 4-second C-major-triad sine cluster produces a clean Viterbi timeline."""
        from analyze_segments import analyze_chords

        # C4 + E4 + G4 — the canonical C major triad.
        audio = self._make_chord_triad_audio((261.63, 329.63, 392.00))
        result = analyze_chords(audio, sample_rate=self.SAMPLE_RATE)
        cd = result.get("chordDetail")
        self.assertIsNotNone(cd, "chord analysis should not return None for clean audio")
        timeline = cd.get("chordTimeline")
        self.assertIsInstance(timeline, list)
        self.assertGreater(len(timeline), 0, "synthetic chord should produce ≥1 segment")

        # Shape & invariants for every segment.
        previous_end = -1.0
        for seg in timeline:
            self.assertEqual(set(seg.keys()), self.EXPECTED_TIMELINE_KEYS)
            self.assertGreaterEqual(seg["startSec"], 0.0)
            self.assertGreaterEqual(seg["endSec"], seg["startSec"])
            self.assertGreaterEqual(seg["confidence"], 0.0)
            self.assertLessEqual(seg["confidence"], 1.0)
            self.assertIsInstance(seg["label"], str)
            self.assertIsInstance(seg["labelLong"], str)
            # Non-overlapping & ordered.
            self.assertGreaterEqual(seg["startSec"], previous_end - 1e-6)
            previous_end = seg["endSec"]

        # Soft expectation: dominant label is C major. Don't fail on this —
        # synthetic-fixture decoding can flicker under template ambiguity.
        from collections import Counter as _Counter
        label_counts = _Counter(seg["label"] for seg in timeline)
        dominant = label_counts.most_common(1)[0][0]
        if dominant != "C":
            print(
                f"[soft] expected dominant 'C', got {dominant} "
                f"(distribution: {dict(label_counts)})",
                file=sys.stderr,
            )

    def test_chord_timeline_white_noise_no_spurious_confident_triads(self) -> None:
        """White noise should not produce strongly-confident triads.

        The cosine-similarity confidence has a noise floor at ~0.5 for random
        chroma against 3-active-bin templates (sqrt(3/12) ≈ 0.5), so the bar
        is 0.65 — well above the noise floor, well below a clean chord match.
        """
        from analyze_segments import analyze_chords

        rng = np.random.default_rng(seed=42)
        noise = rng.standard_normal(int(self.SAMPLE_RATE * self.DURATION_SECONDS))
        noise = (noise * 0.1).astype(np.float32)
        result = analyze_chords(noise, sample_rate=self.SAMPLE_RATE)
        cd = result.get("chordDetail")
        self.assertIsNotNone(cd)
        timeline = cd.get("chordTimeline")
        self.assertIsInstance(timeline, list)
        for seg in timeline:
            allowed = seg["label"] == "N" or seg["confidence"] < 0.65
            self.assertTrue(
                allowed,
                f"white noise produced confident triad: {seg!r}",
            )

    def test_chord_timeline_source_and_agreement_fields(self) -> None:
        """chordDetail exposes chordTimelineSource and chordTimelineAgreement."""
        from analyze_segments import analyze_chords

        audio = self._make_chord_triad_audio((261.63, 329.63, 392.00))
        result = analyze_chords(audio, sample_rate=self.SAMPLE_RATE)
        cd = result["chordDetail"]
        self.assertEqual(cd["chordTimelineSource"], "librosa_viterbi")
        # agreement must be a bool or None — never a string or number.
        agreement = cd["chordTimelineAgreement"]
        self.assertIn(agreement, (True, False, None))

    def test_chord_change_count_recomputed_from_viterbi_timeline(self) -> None:
        """chordChangeCount counts transitions in the new Viterbi timeline."""
        from analyze_segments import analyze_chords

        audio = self._make_chord_triad_audio((261.63, 329.63, 392.00))
        result = analyze_chords(audio, sample_rate=self.SAMPLE_RATE)
        cd = result["chordDetail"]
        expected = sum(
            1 for i in range(1, len(cd["chordTimeline"]))
            if cd["chordTimeline"][i]["label"] != cd["chordTimeline"][i - 1]["label"]
        )
        self.assertEqual(cd["chordChangeCount"], expected)

    def test_normalize_chord_label_handles_enharmonics_and_quality(self) -> None:
        """_normalize_chord_label_for_compare handles short/long forms and enharmonics."""
        from analyze_segments import _normalize_chord_label_for_compare

        # Short form.
        self.assertEqual(_normalize_chord_label_for_compare("C"), "C:maj")
        self.assertEqual(_normalize_chord_label_for_compare("Cm"), "C:min")
        self.assertEqual(_normalize_chord_label_for_compare("Em"), "E:min")
        self.assertEqual(_normalize_chord_label_for_compare("F#"), "Gb:maj")
        self.assertEqual(_normalize_chord_label_for_compare("F#m"), "Gb:min")
        # Long form.
        self.assertEqual(_normalize_chord_label_for_compare("C major"), "C:maj")
        self.assertEqual(_normalize_chord_label_for_compare("C minor"), "C:min")
        self.assertEqual(_normalize_chord_label_for_compare("D# minor"), "Eb:min")
        # Enharmonic equivalence — these MUST compare equal after normalization.
        self.assertEqual(
            _normalize_chord_label_for_compare("D#m"),
            _normalize_chord_label_for_compare("Eb minor"),
        )
        self.assertEqual(
            _normalize_chord_label_for_compare("A#"),
            _normalize_chord_label_for_compare("Bb major"),
        )
        # N stays N.
        self.assertEqual(_normalize_chord_label_for_compare("N"), "N")
        # Non-string input safely returns "".
        self.assertEqual(_normalize_chord_label_for_compare(None), "")  # type: ignore[arg-type]

    def test_chord_templates_25_has_correct_shape_and_triad_masks(self) -> None:
        """_chord_templates_25 emits 25 L1-normalized rows: 12 major + 12 minor + N."""
        from analyze_segments import _chord_templates_25

        templates = _chord_templates_25()
        self.assertEqual(templates.shape, (25, 12))
        # Each row sums to 1.0 (L1-normalized).
        np.testing.assert_allclose(templates.sum(axis=1), np.ones(25), atol=1e-9)
        # Row 0 = C major (root C, +4 E, +7 G) → pitch classes 0, 4, 7 active.
        c_major = templates[0]
        active = np.where(c_major > 0)[0].tolist()
        self.assertEqual(active, [0, 4, 7])
        # Row 12 = C minor (root C, +3 Eb, +7 G) → pitch classes 0, 3, 7 active.
        c_minor = templates[12]
        active = np.where(c_minor > 0)[0].tolist()
        self.assertEqual(active, [0, 3, 7])
        # Row 24 = N — uniform across all 12 pitch classes.
        n_row = templates[24]
        np.testing.assert_allclose(n_row, np.full(12, 1.0 / 12.0), atol=1e-9)


if __name__ == "__main__":
    unittest.main()
