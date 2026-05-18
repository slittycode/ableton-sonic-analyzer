"""Pure-function tests for the Layer 2 (transcription) evaluation harness.

These tests deliberately avoid loading torchcrepe by injecting a fake
transcribe_runner into the harness — they validate the matcher, metrics,
threshold-direction extension, and the MIDI import script without paying the
model-load cost.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pretty_midi

from phase1_evaluation import (
    DEFAULT_MANIFEST_PATH,
    _compute_note_metrics,
    _evaluate_threshold,
    _evaluate_transcription_track,
    _match_notes,
    run_phase1_evaluation,
)

REPO_DIR = Path(__file__).resolve().parent.parent
IMPORT_SCRIPT = REPO_DIR / "scripts" / "import_midi_to_ground_truth.py"


def _note(pitch_midi: int, onset_seconds: float, duration_seconds: float = 0.25) -> dict:
    return {
        "pitchMidi": pitch_midi,
        "onsetSeconds": round(onset_seconds, 4),
        "durationSeconds": round(duration_seconds, 4),
    }


class MatchNotesTests(unittest.TestCase):
    def test_perfect_match_pairs_all_notes(self) -> None:
        gt = [_note(60, 0.0), _note(62, 0.5), _note(64, 1.0)]
        detected = [_note(60, 0.01), _note(62, 0.51), _note(64, 1.02)]
        matches = _match_notes(detected, gt)
        self.assertEqual(len(matches), 3)
        self.assertEqual(sorted(matches), [(0, 0), (1, 1), (2, 2)])

    def test_missed_note_leaves_gt_unmatched(self) -> None:
        gt = [_note(60, 0.0), _note(62, 0.5), _note(64, 1.0)]
        detected = [_note(60, 0.0), _note(64, 1.0)]
        matches = _match_notes(detected, gt)
        gt_matched = {g for g, _d in matches}
        self.assertEqual(len(matches), 2)
        self.assertNotIn(1, gt_matched)

    def test_spurious_detected_note_is_unmatched(self) -> None:
        gt = [_note(60, 0.0)]
        detected = [_note(60, 0.0), _note(70, 2.0)]
        matches = _match_notes(detected, gt)
        self.assertEqual(matches, [(0, 0)])

    def test_pitch_off_by_two_semitones_does_not_match(self) -> None:
        gt = [_note(60, 0.0)]
        detected = [_note(62, 0.0)]
        matches = _match_notes(detected, gt)
        self.assertEqual(matches, [])

    def test_onset_off_by_100ms_does_not_match(self) -> None:
        gt = [_note(60, 0.0)]
        detected = [_note(60, 0.1)]
        matches = _match_notes(detected, gt)
        self.assertEqual(matches, [])

    def test_two_detected_within_window_first_wins(self) -> None:
        gt = [_note(60, 0.5)]
        detected = [_note(60, 0.46), _note(60, 0.52)]
        matches = _match_notes(detected, gt)
        self.assertEqual(matches, [(0, 0)])


class ComputeNoteMetricsTests(unittest.TestCase):
    def test_empty_detected_returns_precision_one(self) -> None:
        metrics = _compute_note_metrics([], [_note(60, 0.0)], [])
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 0.0)
        self.assertEqual(metrics["f1"], 0.0)
        self.assertEqual(metrics["matchedCount"], 0)
        self.assertEqual(metrics["missedCount"], 1)
        self.assertEqual(metrics["falsePositiveCount"], 0)

    def test_empty_ground_truth_returns_recall_one(self) -> None:
        metrics = _compute_note_metrics([_note(60, 0.0)], [], [])
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["precision"], 0.0)
        self.assertEqual(metrics["falsePositiveCount"], 1)

    def test_both_empty_returns_f1_one(self) -> None:
        metrics = _compute_note_metrics([], [], [])
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["f1"], 1.0)

    def test_perfect_match_metrics(self) -> None:
        gt = [_note(60, 0.0), _note(62, 0.5)]
        detected = [_note(60, 0.0), _note(62, 0.5)]
        matches = _match_notes(detected, gt)
        metrics = _compute_note_metrics(detected, gt, matches)
        self.assertEqual(metrics["f1"], 1.0)
        self.assertEqual(metrics["meanPitchCentsError"], 0.0)

    def test_signed_cents_error_uses_detected_minus_ground_truth(self) -> None:
        gt = [_note(60, 0.0)]
        detected = [_note(61, 0.0)]
        matches = _match_notes(detected, gt)
        metrics = _compute_note_metrics(detected, gt, matches)
        self.assertEqual(metrics["meanPitchCentsError"], 100.0)


class EvaluateThresholdDirectionTests(unittest.TestCase):
    def test_min_direction_passes_at_target(self) -> None:
        check = _evaluate_threshold(
            {"v": 0.75}, "v", {"target": 0.75, "tolerance": 0.0, "direction": "min"}
        )
        self.assertTrue(check.passed)

    def test_min_direction_passes_above_target(self) -> None:
        check = _evaluate_threshold(
            {"v": 0.9}, "v", {"target": 0.75, "tolerance": 0.0, "direction": "min"}
        )
        self.assertTrue(check.passed)

    def test_min_direction_fails_below_bound(self) -> None:
        check = _evaluate_threshold(
            {"v": 0.7}, "v", {"target": 0.75, "tolerance": 0.0, "direction": "min"}
        )
        self.assertFalse(check.passed)

    def test_min_direction_tolerance_relaxes_bound(self) -> None:
        check = _evaluate_threshold(
            {"v": 0.7}, "v", {"target": 0.75, "tolerance": 0.1, "direction": "min"}
        )
        self.assertTrue(check.passed)

    def test_max_direction_passes_at_target(self) -> None:
        check = _evaluate_threshold(
            {"v": 50.0}, "v", {"target": 50.0, "tolerance": 0.0, "direction": "max"}
        )
        self.assertTrue(check.passed)

    def test_max_direction_fails_above_bound(self) -> None:
        check = _evaluate_threshold(
            {"v": 60.0}, "v", {"target": 50.0, "tolerance": 5.0, "direction": "max"}
        )
        self.assertFalse(check.passed)

    def test_symmetric_default_still_applies(self) -> None:
        check = _evaluate_threshold(
            {"v": 1.1}, "v", {"target": 1.0, "tolerance": 0.2}
        )
        self.assertTrue(check.passed)
        check = _evaluate_threshold(
            {"v": 1.5}, "v", {"target": 1.0, "tolerance": 0.2}
        )
        self.assertFalse(check.passed)


class TranscriptionTrackHarnessTests(unittest.TestCase):
    def test_evaluate_transcription_track_with_injected_runner(self) -> None:
        """Cover the end-to-end harness path without paying torchcrepe cost.

        The injected runner returns a known transcriptionDetail payload so that
        threshold-on-noteMetrics splicing and the all_passed roll-up are
        exercised against deterministic inputs.
        """
        ground_truth = [_note(60, 0.0), _note(62, 0.5), _note(64, 1.0)]
        with tempfile.TemporaryDirectory(prefix="asa_transcription_track_") as temp_dir:
            tracks_dir = Path(temp_dir)
            audio_path = tracks_dir / "fake_track.wav"
            audio_path.write_bytes(b"placeholder")

            def fake_runner(_path: Path, _flags: list[str]) -> dict:
                return {
                    "transcriptionDetail": {
                        "averageConfidence": 0.8,
                        "notes": [
                            _note(60, 0.0),
                            _note(62, 0.5),
                            _note(64, 1.0),
                        ],
                    }
                }

            entry = {
                "id": "perfect_match_synthetic",
                "audioPath": "fake_track.wav",
                "category": "monophonic_lead",
                "description": "Perfect-match fake runner",
                "analyzeFlags": ["--transcribe"],
                "groundTruthNotes": ground_truth,
                "thresholds": {
                    "noteMetrics.f1": {"target": 0.75, "tolerance": 0.0, "direction": "min"},
                    "noteMetrics.meanPitchCentsError": {"target": 0.0, "tolerance": 50.0},
                    "transcriptionDetail.averageConfidence": {
                        "target": 0.65,
                        "tolerance": 0.0,
                        "direction": "min",
                    },
                },
            }

            result = _evaluate_transcription_track(entry, tracks_dir, transcribe_runner=fake_runner)
            self.assertEqual(result.status, "evaluated")
            self.assertTrue(result.all_passed)
            self.assertEqual(result.note_metrics["matchedCount"], 3)
            self.assertEqual(result.note_metrics["f1"], 1.0)

    def test_missing_audio_is_skipped_not_failed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_transcription_missing_") as temp_dir:
            tracks_dir = Path(temp_dir)
            entry = {
                "id": "absent_audio",
                "audioPath": "nope.wav",
                "category": "monophonic_lead",
                "description": "Audio absent on disk",
                "groundTruthNotes": [],
                "thresholds": {},
            }
            result = _evaluate_transcription_track(entry, tracks_dir)
            self.assertEqual(result.status, "skipped_audio_missing")
            self.assertTrue(result.all_passed)
            self.assertIn("audio not present at", result.skip_reason)

    def test_run_phase1_with_transcription_skips_when_self_test_runner_fakes_success(
        self,
    ) -> None:
        """run_phase1_evaluation with include_transcription should add summary
        counters and a transcriptionTracks block — exercised here with an
        injected runner so we do not boot the real model.
        """
        with tempfile.TemporaryDirectory(prefix="asa_phase1_with_transcription_") as temp_dir:
            report_path = Path(temp_dir) / "phase1_eval_report.json"

            def fake_runner(_path: Path, _flags: list[str]) -> dict:
                return {
                    "transcriptionDetail": {
                        "averageConfidence": 0.9,
                        "notes": [
                            _note(60, 0.0, 0.6),
                            _note(64, 0.8, 0.6),
                            _note(67, 1.6, 0.6),
                            _note(72, 2.4, 0.6),
                        ],
                    }
                }

            report = run_phase1_evaluation(
                manifest_path=DEFAULT_MANIFEST_PATH,
                report_path=report_path,
                runs_per_fixture=1,
                include_transcription=True,
                transcription_tracks_dir=Path(temp_dir),
                transcribe_runner=fake_runner,
            )

            self.assertTrue(report["includeTranscription"])
            self.assertIn("transcriptionTracks", report)
            self.assertGreaterEqual(report["summary"]["transcriptionTracksEvaluated"], 1)
            self.assertEqual(report["summary"]["transcriptionTracksAnalyzeFailed"], 0)
            self_test_row = report["transcriptionTracks"][0]
            self.assertEqual(self_test_row["id"], "stepped_sine_synthetic")
            self.assertEqual(self_test_row["status"], "evaluated")


class ImportMidiScriptTests(unittest.TestCase):
    def _write_midi(self, path: Path, notes: list[tuple[int, float, float]]) -> None:
        midi = pretty_midi.PrettyMIDI()
        instrument = pretty_midi.Instrument(program=0)
        for pitch, start, end in notes:
            instrument.notes.append(
                pretty_midi.Note(velocity=90, pitch=pitch, start=start, end=end)
            )
        midi.instruments.append(instrument)
        midi.write(str(path))

    def _invoke(self, midi_path: Path, *extra_args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(IMPORT_SCRIPT), str(midi_path), *extra_args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_round_trip_emits_expected_notes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_import_midi_") as temp_dir:
            midi_path = Path(temp_dir) / "ref.mid"
            self._write_midi(midi_path, [(60, 0.0, 0.5), (62, 0.5, 1.0), (64, 1.0, 1.5)])
            result = self._invoke(midi_path)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            notes = json.loads(result.stdout)
            self.assertEqual(len(notes), 3)
            self.assertEqual(notes[0]["pitchMidi"], 60)
            self.assertEqual(notes[0]["onsetSeconds"], 0.0)
            self.assertAlmostEqual(notes[0]["durationSeconds"], 0.5, places=2)

    def test_overlapping_notes_with_default_rejects(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_import_midi_reject_") as temp_dir:
            midi_path = Path(temp_dir) / "chord.mid"
            self._write_midi(midi_path, [(60, 0.0, 0.5), (64, 0.1, 0.5)])
            result = self._invoke(midi_path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("overlapping note pair", result.stderr)

    def test_monophonic_collapse_highest_keeps_top_pitch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_import_midi_collapse_") as temp_dir:
            midi_path = Path(temp_dir) / "chord.mid"
            self._write_midi(midi_path, [(60, 0.0, 0.5), (64, 0.1, 0.5), (67, 0.2, 0.5)])
            result = self._invoke(midi_path, "--monophonic-collapse", "highest")
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            notes = json.loads(result.stdout)
            pitches = sorted(note["pitchMidi"] for note in notes)
            self.assertEqual(pitches, [67])

    def test_offset_seconds_shifts_onsets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_import_midi_offset_") as temp_dir:
            midi_path = Path(temp_dir) / "ref.mid"
            self._write_midi(midi_path, [(60, 0.0, 0.5)])
            result = self._invoke(midi_path, "--offset-seconds", "0.25")
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            notes = json.loads(result.stdout)
            self.assertAlmostEqual(notes[0]["onsetSeconds"], 0.25, places=2)


if __name__ == "__main__":
    unittest.main()
