import json
import tempfile
import unittest
from pathlib import Path

from phase1_evaluation import DEFAULT_MANIFEST_PATH, run_phase1_evaluation


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


if __name__ == "__main__":
    unittest.main()
