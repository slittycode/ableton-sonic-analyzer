import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf
from symusic import Note, Score, Tempo, Track

from polyphonic_evaluation import (
    build_manual_scorecard,
    run_polyphonic_evaluation,
    summarize_candidate_gate,
    summarize_midi_file,
)

REPO_DIR = Path(__file__).resolve().parent.parent
SCORECARD_SCRIPT = REPO_DIR / "scripts" / "score_polyphonic_clip.py"


def _write_wav(path: Path, duration_seconds: float = 1.0, sample_rate: int = 22050) -> None:
    sample_count = int(duration_seconds * sample_rate)
    timeline = np.linspace(0.0, duration_seconds, sample_count, endpoint=False, dtype=np.float32)
    waveform = 0.2 * np.sin(2.0 * np.pi * 220.0 * timeline)
    sf.write(str(path), waveform, sample_rate)


def _write_midi(path: Path, note_specs: list[tuple[int, float, float]]) -> None:
    """Build a tiny seconds-unit Score and dump as MIDI.

    Mirrors the polyphonic-eval candidate output shape: one track, one
    program, notes at `(start, end)` in seconds with constant velocity 90.
    """
    score = Score(480, ttype="Second")
    score.tempos.append(Tempo(time=0.0, qpm=120.0, ttype="Second"))
    track = Track(name="candidate", program=0, ttype="Second")
    for pitch, start, end in note_specs:
        duration = max(0.0, end - start)
        track.notes.append(
            Note(
                time=float(start),
                duration=float(duration),
                pitch=int(pitch),
                velocity=90,
                ttype="Second",
            )
        )
    score.tracks.append(track)
    score.dump_midi(str(path))


class PolyphonicEvaluationTests(unittest.TestCase):
    def test_summarize_midi_file_reports_polyphony_metrics(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_polyphonic_metrics_") as temp_dir:
            midi_path = Path(temp_dir) / "candidate.mid"
            _write_midi(
                midi_path,
                [
                    (60, 0.0, 0.5),
                    (64, 0.0, 0.5),
                    (67, 0.5, 1.0),
                ],
            )

            summary = summarize_midi_file(midi_path, audio_duration_seconds=1.0)

            self.assertEqual(summary["noteCount"], 3)
            self.assertEqual(summary["distinctPitchCount"], 3)
            self.assertEqual(summary["maxPolyphony"], 2)
            self.assertGreater(summary["meanTimelinePolyphony"], 0.0)
            self.assertNotIn("monophonic_output", summary["flags"])

    def test_candidate_gate_requires_manual_scores_and_runtime_budget(self) -> None:
        reports = [
            {
                "status": "completed",
                "runtimeMs": 4800,
                "scorecard": build_manual_scorecard(
                    {
                        "bassRecognizable": True,
                        "toplineRecognizable": True,
                        "chordsNotObviouslyWrong": True,
                        "cleanupMinutes30s": 4.5,
                    }
                ),
            },
            {
                "status": "completed",
                "runtimeMs": 4200,
                "scorecard": build_manual_scorecard(
                    {
                        "bassRecognizable": True,
                        "toplineRecognizable": True,
                        "chordsNotObviouslyWrong": True,
                        "cleanupMinutes30s": 3.5,
                    }
                ),
            },
        ]

        summary = summarize_candidate_gate(reports, baseline_runtime_ms=2500)

        self.assertEqual(summary["status"], "ready_to_reopen")
        self.assertTrue(summary["readyToReopenProductization"])
        self.assertLessEqual(summary["runtimeVsStemAwareBaseline"], 2.0)

    def test_run_polyphonic_evaluation_writes_report_with_manual_scorecards(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_polyphonic_eval_") as temp_dir:
            temp_root = Path(temp_dir)
            audio_path = temp_root / "dense_mix.wav"
            _write_wav(audio_path, duration_seconds=1.2)
            manifest_path = temp_root / "manifest.json"
            report_path = temp_root / "report.json"
            output_dir = temp_root / "outputs"

            manifest = {
                "currentStemAwareAverageRuntimeMs": 3000,
                "clips": [
                    {
                        "id": "dense_mix",
                        "audioPath": str(audio_path),
                        "tags": ["dense-chords", "electronic"],
                        "manualReviewByCandidate": {
                            "basic-pitch": {
                                "bassRecognizable": True,
                                "toplineRecognizable": True,
                                "chordsNotObviouslyWrong": True,
                                "cleanupMinutes30s": 4.0,
                                "notes": "Usable after light cleanup.",
                            }
                        },
                    }
                ],
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            def fake_basic_pitch_runner(clip_id: str, _audio_path: Path, candidate_output_dir: Path) -> dict:
                candidate_output_dir.mkdir(parents=True, exist_ok=True)
                midi_path = candidate_output_dir / f"{clip_id}.mid"
                note_events_path = candidate_output_dir / f"{clip_id}.csv"
                _write_midi(
                    midi_path,
                    [
                        (48, 0.0, 0.5),
                        (55, 0.5, 1.0),
                        (60, 0.0, 1.0),
                    ],
                )
                note_events_path.write_text("start,end,pitch\n0,0.5,48\n", encoding="utf-8")
                return {
                    "status": "completed",
                    "runtimeMs": 5200,
                    "midiPath": str(midi_path),
                    "noteEventsPath": str(note_events_path),
                }

            report = run_polyphonic_evaluation(
                manifest_path=manifest_path,
                report_path=report_path,
                output_dir=output_dir,
                candidate_runners={"basic-pitch": fake_basic_pitch_runner},
            )

            self.assertTrue(report_path.exists())
            self.assertEqual(report["summary"]["clipCount"], 1)
            self.assertEqual(report["candidateSummaries"]["basic-pitch"]["status"], "ready_to_reopen")
            candidate_report = report["clips"][0]["candidates"]["basic-pitch"]
            self.assertEqual(candidate_report["scorecard"]["notes"], "Usable after light cleanup.")
            self.assertEqual(candidate_report["metrics"]["maxPolyphony"], 2)


class PolyphonicFlagRuleTests(unittest.TestCase):
    def _summarize(self, note_specs: list[tuple[int, float, float]], duration_s: float) -> dict:
        with tempfile.TemporaryDirectory(prefix="asa_polyphonic_flags_") as temp_dir:
            midi_path = Path(temp_dir) / "candidate.mid"
            _write_midi(midi_path, note_specs)
            return summarize_midi_file(midi_path, audio_duration_seconds=duration_s)

    def test_note_clutter_flag_when_density_exceeds_fifteen(self) -> None:
        # 32 notes across 2.0s = 16 notes/sec — clears > 15 threshold but
        # uses spaced onsets so it does not also trigger dense_chords_unusable.
        note_specs = [(60 + (i % 4), i * 0.0625, i * 0.0625 + 0.05) for i in range(32)]
        summary = self._summarize(note_specs, duration_s=2.0)
        self.assertIn("note_clutter", summary["flags"])
        self.assertNotIn("dense_chords_unusable", summary["flags"])
        self.assertNotIn("octave_junk", summary["flags"])
        self.assertNotIn("sparse_likely_undertranscribed", summary["flags"])

    def test_octave_junk_flag_when_many_distinct_pitches_low_polyphony(self) -> None:
        # 32 distinct pitches strung end-to-end; max polyphony = 1 < 3.
        note_specs = [(40 + i, i * 0.1, i * 0.1 + 0.08) for i in range(32)]
        summary = self._summarize(note_specs, duration_s=10.0)
        self.assertIn("octave_junk", summary["flags"])
        self.assertNotIn("dense_chords_unusable", summary["flags"])
        self.assertNotIn("note_clutter", summary["flags"])
        self.assertNotIn("sparse_likely_undertranscribed", summary["flags"])

    def test_dense_chords_unusable_flag_when_max_polyphony_above_eight(self) -> None:
        # 10 simultaneous notes within first half-second; nothing else fires
        # the other new flags (density is 10 notes / 2.0s = 5).
        note_specs = [(48 + i, 0.0, 0.5) for i in range(10)]
        summary = self._summarize(note_specs, duration_s=2.0)
        self.assertIn("dense_chords_unusable", summary["flags"])
        self.assertNotIn("note_clutter", summary["flags"])
        self.assertNotIn("octave_junk", summary["flags"])
        self.assertNotIn("sparse_likely_undertranscribed", summary["flags"])

    def test_sparse_likely_undertranscribed_flag_when_density_low_over_long_clip(self) -> None:
        # 5 notes across 15.0s = 0.33 notes/sec, well below 1.0; clip long enough.
        note_specs = [(60, i * 3.0, i * 3.0 + 0.2) for i in range(5)]
        summary = self._summarize(note_specs, duration_s=15.0)
        self.assertIn("sparse_likely_undertranscribed", summary["flags"])
        self.assertNotIn("note_clutter", summary["flags"])
        self.assertNotIn("dense_chords_unusable", summary["flags"])

    def test_existing_monophonic_and_high_density_flags_still_emit(self) -> None:
        # Regression guard for the pre-existing flags untouched by the new rules.
        note_specs = [(60, i * 0.08, i * 0.08 + 0.05) for i in range(20)]
        summary = self._summarize(note_specs, duration_s=1.5)
        self.assertIn("monophonic_output", summary["flags"])
        self.assertIn("high_note_density", summary["flags"])


class ScorePolyphonicClipScriptTests(unittest.TestCase):
    def test_no_play_with_piped_input_writes_scorecard_back(self) -> None:
        """Drive score_polyphonic_clip.py via subprocess + stdin.

        Builds a tempdir report JSON with one unscored clip / one candidate,
        pipes the prompt answers in, asserts the scorecard fields land in the
        written report.
        """
        with tempfile.TemporaryDirectory(prefix="asa_scorecard_cli_") as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            audio_path = Path(temp_dir) / "missing.wav"  # ok — playback skipped
            report = {
                "clips": [
                    {
                        "id": "clip_one",
                        "audioPath": str(audio_path),
                        "candidates": {
                            "basic-pitch": {
                                "status": "completed",
                                "metrics": {
                                    "noteCount": 12,
                                    "maxPolyphony": 4,
                                    "noteDensityPerSecond": 6.0,
                                    "flags": ["high_note_density"],
                                },
                                "scorecard": build_manual_scorecard(None),
                            }
                        },
                    }
                ]
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")

            stdin_lines = [
                "y",       # bassRecognizable
                "y",       # toplineRecognizable
                "n",       # chordsNotObviouslyWrong
                "4.25",    # cleanupMinutes30s
                "review notes",  # notes
                "",
            ]
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCORECARD_SCRIPT),
                    "--report",
                    str(report_path),
                    "--no-play",
                ],
                input="\n".join(stdin_lines),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            updated = json.loads(report_path.read_text(encoding="utf-8"))
            scorecard = updated["clips"][0]["candidates"]["basic-pitch"]["scorecard"]
            self.assertTrue(scorecard["bassRecognizable"])
            self.assertTrue(scorecard["toplineRecognizable"])
            self.assertFalse(scorecard["chordsNotObviouslyWrong"])
            self.assertEqual(scorecard["cleanupMinutes30s"], 4.25)
            self.assertEqual(scorecard["notes"], "review notes")

    def test_already_scored_clip_is_skipped_without_rescore(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_scorecard_cli_skip_") as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            complete = build_manual_scorecard(
                {
                    "bassRecognizable": True,
                    "toplineRecognizable": True,
                    "chordsNotObviouslyWrong": True,
                    "cleanupMinutes30s": 2.0,
                    "notes": "preexisting",
                }
            )
            report = {
                "clips": [
                    {
                        "id": "clip_one",
                        "audioPath": str(Path(temp_dir) / "missing.wav"),
                        "candidates": {
                            "basic-pitch": {
                                "status": "completed",
                                "metrics": {
                                    "noteCount": 1,
                                    "maxPolyphony": 1,
                                    "noteDensityPerSecond": 0.1,
                                    "flags": [],
                                },
                                "scorecard": complete,
                            }
                        },
                    }
                ]
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCORECARD_SCRIPT),
                    "--report",
                    str(report_path),
                    "--no-play",
                ],
                input="",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["scored"], 0)
            self.assertEqual(summary["skippedAlreadyComplete"], 1)


if __name__ == "__main__":
    unittest.main()

