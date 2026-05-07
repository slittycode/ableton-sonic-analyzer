import unittest

from runtime_profile import should_recover_incomplete_attempts


class RuntimeProfileTests(unittest.TestCase):
    def test_local_all_process_recovers_incomplete_attempts(self) -> None:
        self.assertTrue(
            should_recover_incomplete_attempts("local", "all")
        )

    def test_hosted_api_process_skips_recovery_sweep(self) -> None:
        self.assertFalse(
            should_recover_incomplete_attempts("hosted", "api")
        )

    def test_hosted_worker_process_recovers_incomplete_attempts(self) -> None:
        self.assertTrue(
            should_recover_incomplete_attempts("hosted", "worker")
        )


if __name__ == "__main__":
    unittest.main()
