import json
import tempfile
import unittest
from pathlib import Path

from fundamentals_evaluation import (
    DEFAULT_MANIFEST_PATH,
    run_fundamentals_evaluation,
)


class FundamentalsEvaluationTests(unittest.TestCase):
    def test_default_manifest_skips_missing_local_audio(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_fundamentals_eval_") as temp_dir:
            report_path = Path(temp_dir) / "fundamentals_report.json"
            tracks_dir = Path(temp_dir) / "empty_tracks"
            tracks_dir.mkdir()

            report = run_fundamentals_evaluation(
                manifest_path=DEFAULT_MANIFEST_PATH,
                tracks_dir=tracks_dir,
                report_path=report_path,
            )

            self.assertTrue(report["summary"]["allPassed"])
            self.assertEqual(report["summary"]["tracksEvaluated"], 0)
            self.assertGreaterEqual(report["summary"]["tracksSkipped"], 1)
            self.assertTrue(report_path.exists())


    def test_fail_on_skip_marks_missing_audio_report_failed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_fundamentals_eval_fail_skip_") as temp_dir:
            report_path = Path(temp_dir) / "fundamentals_report.json"
            tracks_dir = Path(temp_dir) / "empty_tracks"
            tracks_dir.mkdir()

            report = run_fundamentals_evaluation(
                manifest_path=DEFAULT_MANIFEST_PATH,
                tracks_dir=tracks_dir,
                report_path=report_path,
                fail_on_skip=True,
            )

            self.assertFalse(report["summary"]["allPassed"])
            self.assertTrue(report["summary"]["failOnSkip"])
            self.assertGreaterEqual(report["summary"]["tracksSkipped"], 1)

    def test_known_gaps_report_scores_without_gating(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_fundamentals_eval_gaps_") as temp_dir:
            temp_root = Path(temp_dir)
            tracks_dir = temp_root / "tracks"
            tracks_dir.mkdir()
            (tracks_dir / "loop.wav").write_bytes(b"placeholder")
            manifest_path = temp_root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "fundamentals-eval.v1",
                        "tracks": [
                            {
                                "id": "loop",
                                "audioPath": "loop.wav",
                                "category": "unit",
                                "expected": {"bpm": 128, "timeSignature": "3/4"},
                                "thresholds": {"bpmTolerance": 1.0},
                                "knownGaps": ["meter:timeSignature"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            def runner(path: Path, flags: list[str] | None) -> dict:
                # Meter is wrong (a known baseline gap); bpm is right.
                return {"bpm": 128.0, "timeSignature": "4/4"}

            report = run_fundamentals_evaluation(
                manifest_path=manifest_path,
                tracks_dir=tracks_dir,
                report_path=temp_root / "report.json",
                runner=runner,
                fail_on_skip=True,
            )

            self.assertTrue(report["summary"]["allPassed"])
            self.assertEqual(report["summary"]["checksFailed"], 0)
            self.assertEqual(report["summary"]["checksInformational"], 1)
            track = report["tracks"][0]
            self.assertTrue(track["allPassed"])
            meter_check = next(c for c in track["checks"] if c["name"] == "meter:timeSignature")
            self.assertTrue(meter_check["informational"])
            self.assertFalse(meter_check["passed"])  # score still visible

    def test_present_track_enforces_declared_fundamental_gates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_fundamentals_eval_present_") as temp_dir:
            temp_root = Path(temp_dir)
            tracks_dir = temp_root / "tracks"
            tracks_dir.mkdir()
            audio_path = tracks_dir / "loop.wav"
            audio_path.write_bytes(b"placeholder")
            manifest_path = temp_root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "fundamentals-eval.v1",
                        "targetProfile": "electronic_ableton_v1",
                        "tracks": [
                            {
                                "id": "loop",
                                "audioPath": "loop.wav",
                                "category": "unit",
                                "description": "unit test",
                                "expected": {
                                    "bpm": 128,
                                    "key": "A minor",
                                    "timeSignature": "4/4",
                                    "beatGrid": [0.0, 0.46875, 0.9375],
                                    "downbeats": [0.0],
                                    "percussion": {"kickCount": 3},
                                    "transcriptionNotes": [
                                        {"pitchMidi": 48, "onsetSeconds": 0.0},
                                    ],
                                },
                                "thresholds": {
                                    "bpmTolerance": 1.0,
                                    "beatF1": 0.9,
                                    "downbeatF1": 0.75,
                                    "percussionCountTolerance": 0,
                                    "transcriptionNoteF1": 0.75,
                                    "requiredQuality": {
                                        "tempo": "authoritative",
                                        "key": "authoritative",
                                    },
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            def runner(path: Path, flags: list[str] | None) -> dict:
                self.assertEqual(path, audio_path.resolve())
                self.assertIsNone(flags)
                return {
                    "bpm": 128.2,
                    "key": "A minor",
                    "timeSignature": "4/4",
                    "rhythmDetail": {
                        "beatGrid": [0.0, 0.469, 0.938],
                        "downbeats": [0.02],
                    },
                    "kickDetail": {"kickCount": 3},
                    "transcriptionDetail": {
                        "notes": [{"pitchMidi": 48, "onsetSeconds": 0.01}],
                    },
                    "fundamentalsQuality": {
                        "domains": {
                            "tempo": {"status": "authoritative"},
                            "key": {"status": "authoritative"},
                        }
                    },
                }

            report = run_fundamentals_evaluation(
                manifest_path=manifest_path,
                tracks_dir=tracks_dir,
                report_path=temp_root / "report.json",
                runner=runner,
            )

            self.assertTrue(report["summary"]["allPassed"])
            self.assertEqual(report["summary"]["tracksEvaluated"], 1)
            checks = report["tracks"][0]["checks"]
            self.assertTrue(all(check["passed"] for check in checks))
            self.assertIn("tempo:bpm", {check["name"] for check in checks})
            self.assertIn("transcription:noteF1", {check["name"] for check in checks})

    def test_present_track_failure_fails_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_fundamentals_eval_fail_") as temp_dir:
            temp_root = Path(temp_dir)
            tracks_dir = temp_root / "tracks"
            tracks_dir.mkdir()
            (tracks_dir / "loop.wav").write_bytes(b"placeholder")
            manifest_path = temp_root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "tracks": [
                            {
                                "id": "loop",
                                "audioPath": "loop.wav",
                                "expected": {"bpm": 128},
                                "thresholds": {"bpmTolerance": 1.0},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = run_fundamentals_evaluation(
                manifest_path=manifest_path,
                tracks_dir=tracks_dir,
                report_path=temp_root / "report.json",
                runner=lambda _path, _flags: {"bpm": 132},
            )

            self.assertFalse(report["summary"]["allPassed"])
            self.assertEqual(report["summary"]["checksFailed"], 1)

    def test_honesty_checks_assert_abstention_on_beatless_material(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_fundamentals_eval_honesty_") as temp_dir:
            temp_root = Path(temp_dir)
            tracks_dir = temp_root / "tracks"
            tracks_dir.mkdir()
            (tracks_dir / "pad.wav").write_bytes(b"placeholder")
            manifest_path = temp_root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "tracks": [
                            {
                                "id": "pad",
                                "audioPath": "pad.wav",
                                "category": "ambient",
                                "expected": {
                                    "key": "A minor",
                                    "honesty": {
                                        "maxBpmConfidence": 0.4,
                                        "swingDetailAbsent": True,
                                        "meterSources": ["assumed_four_four"],
                                    },
                                },
                                "thresholds": {},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            def honest_runner(_path: Path, _flags: list[str] | None) -> dict:
                return {
                    "key": "A Minor",
                    "bpmConfidence": 0.12,
                    "timeSignatureSource": "assumed_four_four",
                    "rhythmDetail": {"swingDetail": None},
                }

            report = run_fundamentals_evaluation(
                manifest_path=manifest_path,
                tracks_dir=tracks_dir,
                report_path=temp_root / "report.json",
                runner=honest_runner,
            )
            self.assertTrue(report["summary"]["allPassed"])
            names = {check["name"] for check in report["tracks"][0]["checks"]}
            self.assertEqual(
                names,
                {"key:label", "honesty:bpmConfidence", "honesty:swingAbsent", "honesty:meterSource"},
            )

            def overconfident_runner(_path: Path, _flags: list[str] | None) -> dict:
                return {
                    "key": "A Minor",
                    "bpmConfidence": 0.93,
                    "timeSignatureSource": "onset_autocorrelation",
                    "rhythmDetail": {"swingDetail": {"swingPercent": 58.0}},
                }

            report = run_fundamentals_evaluation(
                manifest_path=manifest_path,
                tracks_dir=tracks_dir,
                report_path=temp_root / "report.json",
                runner=overconfident_runner,
            )
            self.assertFalse(report["summary"]["allPassed"])
            failed = {c["name"] for c in report["tracks"][0]["checks"] if not c["passed"]}
            self.assertEqual(
                failed,
                {"honesty:bpmConfidence", "honesty:swingAbsent", "honesty:meterSource"},
            )

    def test_swing_grid_check_gates_detection_separately_from_ratio(self) -> None:
        from fundamentals_evaluation import _evaluate_expected

        payload = {
            "rhythmDetail": {
                "swingDetail": {"swingPercent": 55.0, "gridResolution": "16th"},
            },
        }
        checks = _evaluate_expected(
            payload,
            {"swingPercent": 62.0, "swingGrid": "16th"},
            {"swingTolerance": 3.0},
        )
        by_name = {check.name: check for check in checks}
        self.assertFalse(by_name["swing:swingPercent"].passed)  # value compressed
        self.assertTrue(by_name["swing:gridResolution"].passed)  # detection gates

    def test_honesty_bpm_confidence_passes_when_field_is_absent(self) -> None:
        # A pipeline that cannot say anything (bpmConfidence None/missing) is
        # abstaining, which is exactly what the honesty gate wants.
        from fundamentals_evaluation import _evaluate_honesty

        checks = _evaluate_honesty({}, {"maxBpmConfidence": 0.4})
        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0].passed)


if __name__ == "__main__":
    unittest.main()
