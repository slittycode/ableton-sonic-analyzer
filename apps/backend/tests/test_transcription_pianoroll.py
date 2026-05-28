"""Unit tests for transcription_pianoroll.

Stdlib unittest to match the rest of apps/backend/tests/. Pure-Python — no
audio fixtures, no network, no Phase 1 run. All inputs are minimal dicts
shaped like a real transcriptionDetail.
"""

from __future__ import annotations

import unittest

import numpy as np

from transcription_pianoroll import (
    DEFAULT_PITCH_LOW,
    VELOCITY_FLOOR,
    _parse_time_signature,
    _velocity_from_confidence,
    build_score,
    payload_to_json_dict,
    render_pianoroll,
)


def _mock_transcription(notes: list[dict]) -> dict:
    return {
        "transcriptionMethod": "torchcrepe-viterbi",
        "noteCount": len(notes),
        "averageConfidence": 0.9,
        "notes": notes,
    }


def _make_note(
    pitch: int,
    onset: float,
    duration: float,
    *,
    confidence: float = 0.9,
    stem: str = "full_mix",
) -> dict:
    return {
        "pitchMidi": pitch,
        "pitchName": "C4",  # irrelevant for the matrix
        "onsetSeconds": onset,
        "durationSeconds": duration,
        "confidence": confidence,
        "stemSource": stem,
    }


class VelocityMappingTests(unittest.TestCase):
    def test_zero_confidence_maps_to_floor(self):
        self.assertEqual(_velocity_from_confidence(0.0), VELOCITY_FLOOR)

    def test_full_confidence_maps_to_127(self):
        self.assertEqual(_velocity_from_confidence(1.0), 127)

    def test_half_confidence_midrange(self):
        # 64 + 63 * 0.5 = 95.5; Python's banker's rounding takes 95.5 -> 96.
        self.assertEqual(_velocity_from_confidence(0.5), 96)

    def test_below_zero_clipped_to_floor(self):
        self.assertEqual(_velocity_from_confidence(-2.0), VELOCITY_FLOOR)

    def test_above_one_clipped_to_max(self):
        self.assertEqual(_velocity_from_confidence(5.0), 127)

    def test_non_numeric_input_clamps_to_floor(self):
        self.assertEqual(_velocity_from_confidence("not-a-number"), VELOCITY_FLOOR)
        self.assertEqual(_velocity_from_confidence(None), VELOCITY_FLOOR)


class TimeSignatureParseTests(unittest.TestCase):
    def test_valid_4_4(self):
        self.assertEqual(_parse_time_signature("4/4"), (4, 4))

    def test_valid_3_4(self):
        self.assertEqual(_parse_time_signature("3/4"), (3, 4))

    def test_valid_7_8(self):
        self.assertEqual(_parse_time_signature("7/8"), (7, 8))

    def test_none_input(self):
        self.assertIsNone(_parse_time_signature(None))

    def test_malformed_returns_none(self):
        self.assertIsNone(_parse_time_signature("not-a-sig"))

    def test_non_integer_returns_none(self):
        self.assertIsNone(_parse_time_signature("4/four"))

    def test_too_many_parts(self):
        self.assertIsNone(_parse_time_signature("4/4/4"))


class BuildScoreTests(unittest.TestCase):
    def test_empty_notes_produces_empty_track(self):
        score = build_score(
            _mock_transcription([]), bpm=120.0, time_signature="4/4"
        )
        self.assertEqual(len(score.tracks), 1)
        self.assertEqual(len(score.tracks[0].notes), 0)

    def test_tempo_emitted_when_bpm_positive(self):
        score = build_score(
            _mock_transcription([]), bpm=128.0, time_signature="4/4"
        )
        self.assertEqual(len(score.tempos), 1)
        self.assertAlmostEqual(score.tempos[0].qpm, 128.0)

    def test_no_tempo_when_bpm_missing(self):
        score = build_score(
            _mock_transcription([]), bpm=None, time_signature="4/4"
        )
        self.assertEqual(len(score.tempos), 0)

    def test_no_tempo_when_bpm_zero(self):
        score = build_score(
            _mock_transcription([]), bpm=0.0, time_signature="4/4"
        )
        self.assertEqual(len(score.tempos), 0)

    def test_time_signature_emitted_when_present(self):
        score = build_score(
            _mock_transcription([]), bpm=120.0, time_signature="3/4"
        )
        self.assertEqual(len(score.time_signatures), 1)
        self.assertEqual(score.time_signatures[0].numerator, 3)
        self.assertEqual(score.time_signatures[0].denominator, 4)

    def test_no_time_signature_when_malformed(self):
        score = build_score(
            _mock_transcription([]), bpm=120.0, time_signature="garbage"
        )
        self.assertEqual(len(score.time_signatures), 0)

    def test_notes_carried_through(self):
        notes_in = [
            _make_note(60, 0.0, 0.5),
            _make_note(64, 0.5, 0.5, confidence=1.0),
        ]
        score = build_score(
            _mock_transcription(notes_in), bpm=120.0, time_signature="4/4"
        )
        track_notes = sorted(score.tracks[0].notes, key=lambda n: n.time)
        self.assertEqual(len(track_notes), 2)
        self.assertEqual(track_notes[0].pitch, 60)
        self.assertEqual(track_notes[1].pitch, 64)
        self.assertEqual(track_notes[1].velocity, 127)

    def test_malformed_note_skipped(self):
        notes_in = [
            _make_note(60, 0.0, 0.5),
            {
                "pitchMidi": "bad",
                "onsetSeconds": 1.0,
                "durationSeconds": 0.5,
            },
            _make_note(64, 1.5, 0.5),
        ]
        score = build_score(
            _mock_transcription(notes_in), bpm=120.0, time_signature="4/4"
        )
        self.assertEqual(len(score.tracks[0].notes), 2)

    def test_zero_or_negative_duration_skipped(self):
        notes_in = [
            _make_note(60, 0.0, 0.0),
            _make_note(62, 0.5, -0.1),
            _make_note(64, 1.0, 0.5),
        ]
        score = build_score(
            _mock_transcription(notes_in), bpm=120.0, time_signature="4/4"
        )
        self.assertEqual(len(score.tracks[0].notes), 1)
        self.assertEqual(score.tracks[0].notes[0].pitch, 64)

    def test_out_of_range_pitch_skipped(self):
        notes_in = [
            _make_note(60, 0.0, 0.5),
            _make_note(128, 1.0, 0.5),  # 128 is invalid
            _make_note(-1, 2.0, 0.5),
        ]
        score = build_score(
            _mock_transcription(notes_in), bpm=120.0, time_signature="4/4"
        )
        self.assertEqual(len(score.tracks[0].notes), 1)

    def test_non_dict_transcription_is_safe(self):
        score = build_score(None, bpm=120.0, time_signature="4/4")  # type: ignore[arg-type]
        self.assertEqual(len(score.tracks), 1)
        self.assertEqual(len(score.tracks[0].notes), 0)


class RenderPianorollTests(unittest.TestCase):
    def test_empty_transcription_returns_zero_matrix(self):
        payload = render_pianoroll(_mock_transcription([]), bpm=120.0)
        self.assertEqual(payload.note_count, 0)
        self.assertEqual(payload.frames.dtype, np.uint8)
        self.assertEqual(int(payload.frames.sum()), 0)

    def test_single_note_lands_in_correct_pitch_row(self):
        notes_in = [_make_note(60, 0.0, 0.5, confidence=1.0)]
        payload = render_pianoroll(_mock_transcription(notes_in), bpm=120.0)
        target_row_index = 60 - DEFAULT_PITCH_LOW
        target_row = payload.frames[target_row_index]
        self.assertGreater(int(target_row.sum()), 0)
        # No spill into adjacent pitch rows.
        non_target = np.delete(payload.frames, target_row_index, axis=0)
        self.assertEqual(int(non_target.sum()), 0)

    def test_pitch_range_validation_rejects_inverted(self):
        with self.assertRaises(ValueError):
            render_pianoroll(
                _mock_transcription([]),
                bpm=120.0,
                pitch_low=50,
                pitch_high=50,
            )

    def test_pitch_range_validation_rejects_negative(self):
        with self.assertRaises(ValueError):
            render_pianoroll(
                _mock_transcription([]),
                bpm=120.0,
                pitch_low=-1,
                pitch_high=10,
            )

    def test_pitch_range_validation_rejects_above_128(self):
        with self.assertRaises(ValueError):
            render_pianoroll(
                _mock_transcription([]),
                bpm=120.0,
                pitch_low=0,
                pitch_high=200,
            )

    def test_tpq_validation(self):
        with self.assertRaises(ValueError):
            render_pianoroll(_mock_transcription([]), bpm=120.0, tpq=0)

    def test_mode_validation(self):
        with self.assertRaises(ValueError):
            render_pianoroll(
                _mock_transcription([]),
                bpm=120.0,
                mode="bogus",  # type: ignore[arg-type]
            )

    def test_onset_mode_is_sparser_than_frame_mode(self):
        notes_in = [_make_note(60, 0.0, 1.0, confidence=1.0)]
        frame_payload = render_pianoroll(
            _mock_transcription(notes_in), bpm=120.0, mode="frame"
        )
        onset_payload = render_pianoroll(
            _mock_transcription(notes_in), bpm=120.0, mode="onset"
        )
        row = 60 - DEFAULT_PITCH_LOW
        # Frame mode paints the sustain; onset mode marks only the note start.
        self.assertGreater(
            int(frame_payload.frames[row].sum()),
            int(onset_payload.frames[row].sum()),
        )

    def test_velocity_floor_visible_for_zero_confidence(self):
        notes_in = [_make_note(60, 0.0, 0.5, confidence=0.0)]
        payload = render_pianoroll(_mock_transcription(notes_in), bpm=120.0)
        row = payload.frames[60 - DEFAULT_PITCH_LOW]
        non_zero = row[row > 0]
        self.assertGreater(len(non_zero), 0)
        self.assertEqual(int(non_zero.max()), VELOCITY_FLOOR)

    def test_metadata_passes_through(self):
        payload = render_pianoroll(
            _mock_transcription([]),
            bpm=128.0,
            time_signature="3/4",
        )
        self.assertEqual(payload.quarters_per_minute, 128.0)
        self.assertEqual(payload.time_signature, (3, 4))
        self.assertEqual(payload.mode, "frame")

    def test_works_without_bpm(self):
        notes_in = [_make_note(60, 0.0, 0.5)]
        payload = render_pianoroll(_mock_transcription(notes_in), bpm=None)
        self.assertIsNone(payload.quarters_per_minute)
        # Pianoroll still renders — symusic falls back to qpm=120 internally.
        self.assertGreater(int(payload.frames.sum()), 0)


class PayloadJsonDictTests(unittest.TestCase):
    def test_round_trip_has_expected_keys(self):
        notes_in = [_make_note(60, 0.0, 0.5)]
        payload = render_pianoroll(
            _mock_transcription(notes_in), bpm=128.0, time_signature="4/4"
        )
        out = payload_to_json_dict(payload)
        self.assertEqual(
            set(out.keys()),
            {
                "mode",
                "pitchLow",
                "pitchHigh",
                "ticksPerQuarter",
                "quartersPerMinute",
                "timeSignature",
                "noteCount",
                "frames",
            },
        )
        self.assertEqual(out["mode"], "frame")
        self.assertEqual(out["timeSignature"], "4/4")
        self.assertAlmostEqual(out["quartersPerMinute"], 128.0)
        self.assertEqual(out["noteCount"], 1)
        self.assertIsInstance(out["frames"], list)
        self.assertEqual(len(out["frames"]), payload.frames.shape[0])
        # Each row is a list of ints (uint8 -> Python int via tolist()).
        self.assertTrue(
            all(isinstance(cell, int) for cell in out["frames"][0])
        )

    def test_missing_bpm_serializes_none(self):
        payload = render_pianoroll(_mock_transcription([]), bpm=None)
        out = payload_to_json_dict(payload)
        self.assertIsNone(out["quartersPerMinute"])

    def test_missing_time_signature_serializes_none(self):
        payload = render_pianoroll(_mock_transcription([]), bpm=120.0)
        out = payload_to_json_dict(payload)
        self.assertIsNone(out["timeSignature"])


if __name__ == "__main__":
    unittest.main()
