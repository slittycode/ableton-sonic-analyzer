import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from polyphonic_evaluation import (
    build_manual_scorecard,
    run_polyphonic_evaluation,
    summarize_candidate_gate,
    summarize_midi_file,
)


def _write_wav(path: Path, duration_seconds: float = 1.0, sample_rate: int = 22050) -> None:
    sample_count = int(duration_seconds * sample_rate)
    timeline = np.linspace(0.0, duration_seconds, sample_count, endpoint=False, dtype=np.float32)
    waveform = 0.2 * np.sin(2.0 * np.pi * 220.0 * timeline)
    sf.write(str(path), waveform, sample_rate)


def _write_midi(path: Path, note_specs: list[tuple[int, float, float]]) -> None:
    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)
    for pitch, start, end in note_specs:
        instrument.notes.append(
            pretty_midi.Note(
                velocity=90,
                pitch=pitch,
                start=start,
                end=end,
            )
        )
    midi.instruments.append(instrument)
    midi.write(str(path))


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


if __name__ == "__main__":
    unittest.main()

