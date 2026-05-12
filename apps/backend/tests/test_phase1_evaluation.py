import json
import tempfile
import unittest
from pathlib import Path

from phase1_evaluation import DEFAULT_MANIFEST_PATH, run_phase1_evaluation
from phase1_report_html import default_html_report_path, render_html_report


class Phase1EvaluationHarnessTests(unittest.TestCase):
    def test_evaluation_harness_generates_report_and_meets_thresholds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_phase1_eval_test_") as temp_dir:
            report_path = Path(temp_dir) / "phase1_eval_report.json"
            report = run_phase1_evaluation(
                manifest_path=DEFAULT_MANIFEST_PATH,
                report_path=report_path,
                runs_per_fixture=2,
            )

            self.assertTrue(report["summary"]["allPassed"])
            self.assertEqual(report["summary"]["checksFailed"], 0)
            self.assertTrue(report_path.exists())

            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(persisted["summary"]["allPassed"])
            self.assertGreaterEqual(len(persisted["fixtures"]), 2)
            fixture_ids = {fixture["id"] for fixture in persisted["fixtures"]}
            self.assertIn("click_120", fixture_ids)
            self.assertIn("sine_220", fixture_ids)

    def test_default_run_does_not_include_real_tracks_section(self) -> None:
        """Without --include-real, real-track plumbing stays inert.

        The default report shape should be backward-compatible with anything
        that read it before the real-track tier was added.
        """
        with tempfile.TemporaryDirectory(prefix="asa_phase1_default_test_") as temp_dir:
            report_path = Path(temp_dir) / "phase1_eval_report.json"
            report = run_phase1_evaluation(
                manifest_path=DEFAULT_MANIFEST_PATH,
                report_path=report_path,
                runs_per_fixture=1,
            )

            self.assertFalse(report["includeReal"])
            self.assertIsNone(report["realTracksDir"])
            self.assertNotIn("realTracks", report)
            self.assertEqual(report["summary"]["realTracksEvaluated"], 0)
            self.assertEqual(report["summary"]["realTracksSkipped"], 0)

    def test_include_real_with_missing_audio_skips_gracefully(self) -> None:
        """include_real with a manifest entry whose audio is absent should skip,
        not fail, and the synthetic-fixture run should still pass overall.

        This is the day-1 behavior promised by the bench README — populating
        bench tracks is opt-in, and a missing track is reported with a clear
        skipReason instead of breaking the audit.
        """
        with tempfile.TemporaryDirectory(prefix="asa_phase1_real_skip_") as temp_dir:
            temp_root = Path(temp_dir)
            manifest_path = temp_root / "manifest.json"

            base_manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
            base_manifest["realTracks"] = [
                {
                    "id": "missing_track_for_test",
                    "audioPath": "definitely_not_here.wav",
                    "category": "four_on_floor",
                    "description": "Synthetic entry for unit test — audio absent on disk",
                    "thresholds": {
                        "bpm": {"target": 128.0, "tolerance": 2.0},
                    },
                }
            ]
            manifest_path.write_text(json.dumps(base_manifest, indent=2), encoding="utf-8")

            empty_real_tracks_dir = temp_root / "empty_bench_tracks"
            empty_real_tracks_dir.mkdir()

            report_path = temp_root / "phase1_eval_report.json"
            report = run_phase1_evaluation(
                manifest_path=manifest_path,
                report_path=report_path,
                runs_per_fixture=1,
                include_real=True,
                real_tracks_dir=empty_real_tracks_dir,
            )

            self.assertTrue(report["includeReal"])
            self.assertTrue(report["summary"]["allPassed"])
            self.assertEqual(report["summary"]["realTracksEvaluated"], 0)
            self.assertEqual(report["summary"]["realTracksSkipped"], 1)
            self.assertEqual(report["summary"]["realTracksAnalyzeFailed"], 0)

            real_tracks = report["realTracks"]
            self.assertEqual(len(real_tracks), 1)
            entry = real_tracks[0]
            self.assertEqual(entry["id"], "missing_track_for_test")
            self.assertEqual(entry["status"], "skipped_audio_missing")
            self.assertIn("audio not present at", entry["skipReason"])
            self.assertEqual(entry["checks"], [])
            self.assertTrue(entry["allPassed"])


class Phase1HtmlReportTests(unittest.TestCase):
    def test_html_renderer_emits_expected_markers(self) -> None:
        """Render a hand-built report dict and confirm the HTML body contains
        the verdict, fixture identifiers, skipped-track reason, and the
        confidence-calibration footer note.

        Synthetic input keeps this test fast — we don't need to run analyze.py
        just to exercise rendering.
        """
        sample_report = {
            "generatedAt": "2026-05-11T10:00:00+00:00",
            "manifestPath": "/tmp/manifest.json",
            "runsPerFixture": 1,
            "includeReal": True,
            "realTracksDir": "/tmp/bench_tracks",
            "fixtures": [
                {
                    "id": "click_120",
                    "audioPath": "/tmp/click_120.wav",
                    "checks": [
                        {"name": "threshold:bpm", "passed": True, "message": "target=120.1 actual=120.05"},
                    ],
                    "allPassed": True,
                }
            ],
            "realTracks": [
                {
                    "id": "missing_track_for_test",
                    "audioPath": "/tmp/bench_tracks/missing.wav",
                    "category": "four_on_floor",
                    "description": "Synthetic test entry",
                    "status": "skipped_audio_missing",
                    "skipReason": "audio not present at /tmp/bench_tracks/missing.wav",
                    "checks": [],
                    "allPassed": True,
                }
            ],
            "summary": {
                "fixtures": 1,
                "realTracksEvaluated": 0,
                "realTracksSkipped": 1,
                "realTracksAnalyzeFailed": 0,
                "checksPassed": 1,
                "checksFailed": 0,
                "allPassed": True,
            },
        }

        with tempfile.TemporaryDirectory(prefix="asa_phase1_html_") as temp_dir:
            output_path = Path(temp_dir) / "accuracy.html"
            written = render_html_report(sample_report, output_path)

            self.assertEqual(written, output_path)
            self.assertTrue(output_path.exists())
            html = output_path.read_text(encoding="utf-8")

            self.assertIn("ASA Phase 1 Accuracy Report", html)
            self.assertIn("ALL CHECKS PASSED", html)
            self.assertIn("click_120", html)
            self.assertIn("missing_track_for_test", html)
            self.assertIn("audio not present at /tmp/bench_tracks/missing.wav", html)
            self.assertIn("Confidence-calibration sub-report", html)

    def test_default_html_report_path_uses_dated_filename(self) -> None:
        with tempfile.TemporaryDirectory(prefix="asa_phase1_path_") as temp_dir:
            reports_dir = Path(temp_dir)
            path = default_html_report_path(reports_dir)

            self.assertEqual(path.parent, reports_dir)
            self.assertTrue(path.name.startswith("accuracy_"))
            self.assertTrue(path.name.endswith(".html"))
            # Filename shape: accuracy_YYYYMMDD-HHMMSSZ.html → 8 digits, dash, 6 digits + Z
            stamp = path.stem.removeprefix("accuracy_")
            self.assertRegex(stamp, r"^\d{8}-\d{6}Z$")


if __name__ == "__main__":
    unittest.main()
