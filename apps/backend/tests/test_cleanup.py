import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import server


class CleanupArtifactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="asa_cleanup_test_")
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"
        self.artifacts_dir = self.runtime_dir / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _cleanup_module(self):
        from utils import cleanup as cleanup_module

        return cleanup_module

    def _write_artifact(self, relative_path: str, *, age_hours: float, now: datetime) -> Path:
        path = self.artifacts_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"artifact")
        timestamp = (now - timedelta(hours=age_hours)).timestamp()
        os.utime(path, (timestamp, timestamp))
        return path

    def test_cleanup_artifacts_deletes_only_expired_non_preserved_files(self) -> None:
        cleanup_module = self._cleanup_module()
        now = datetime(2026, 3, 26, 12, 0, 0)

        expired_root = self._write_artifact("expired.wav", age_hours=30, now=now)
        expired_nested = self._write_artifact("nested/expired.json", age_hours=30, now=now)
        fresh = self._write_artifact("fresh.wav", age_hours=2, now=now)
        keep_marker = self._write_artifact("nested/sentinel.keep", age_hours=30, now=now)
        preserved_root = self._write_artifact("preserved/old.mid", age_hours=30, now=now)
        preserved_nested = self._write_artifact(
            "nested/preserved/old.png",
            age_hours=30,
            now=now,
        )

        with patch.object(cleanup_module, "_current_time", return_value=now):
            with self.assertLogs(cleanup_module.logger.name, level="INFO") as logs:
                cleanup_module.cleanup_artifacts(self.runtime_dir)

        self.assertFalse(expired_root.exists())
        self.assertFalse(expired_nested.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue(keep_marker.exists())
        self.assertTrue(preserved_root.exists())
        self.assertTrue(preserved_nested.exists())

        joined_logs = "\n".join(logs.output)
        self.assertIn(str(expired_root), joined_logs)
        self.assertIn(str(expired_nested), joined_logs)
        self.assertNotIn(str(fresh), joined_logs)
        self.assertNotIn(str(keep_marker), joined_logs)
        self.assertNotIn(str(preserved_root), joined_logs)

    def test_cleanup_artifacts_aborts_when_candidate_count_exceeds_safety_cap(self) -> None:
        cleanup_module = self._cleanup_module()
        now = datetime(2026, 3, 26, 12, 0, 0)
        expired_paths = [
            self._write_artifact(f"expired-{index}.wav", age_hours=30, now=now)
            for index in range(101)
        ]

        with patch.object(cleanup_module, "_current_time", return_value=now):
            with self.assertLogs(cleanup_module.logger.name, level="INFO") as logs:
                cleanup_module.cleanup_artifacts(self.runtime_dir)

        self.assertTrue(all(path.exists() for path in expired_paths))
        joined_logs = "\n".join(logs.output)
        self.assertIn("ARTIFACT_CLEANUP_MAX", joined_logs)
        self.assertIn("aborting", joined_logs.lower())


class CleanupStartupHookTests(unittest.TestCase):
    def _close_coro_and_return_task(self, coro):
        coro.close()
        return Mock(name="task")

    def test_startup_schedules_artifact_cleanup_in_daemon_thread(self) -> None:
        runtime = Mock()
        runtime.runtime_dir = Path("/tmp/asa-runtime")
        thread = Mock()
        captured_target = {}

        def build_thread(*args, **kwargs):
            captured_target["target"] = kwargs["target"]
            return thread

        with patch.object(server, "_BACKGROUND_TASKS", []):
            with patch.object(server, "get_analysis_runtime", return_value=runtime):
                with patch.object(server.threading, "Thread", side_effect=build_thread) as thread_cls:
                    with patch.object(server.asyncio, "create_task", side_effect=self._close_coro_and_return_task):
                        with patch.object(server, "cleanup_artifacts", create=True) as cleanup_mock:
                            asyncio.run(server._start_cache_eviction())
                            captured_target["target"]()

        runtime.recover_incomplete_attempts.assert_called_once_with()
        thread_cls.assert_called_once()
        self.assertTrue(thread_cls.call_args.kwargs["daemon"])
        self.assertEqual(thread_cls.call_args.kwargs["name"], "artifact-cleanup")
        thread.start.assert_called_once_with()
        cleanup_mock.assert_called_once_with(runtime.runtime_dir)

    def test_startup_cleanup_target_swallows_exceptions_with_warning_log(self) -> None:
        runtime = Mock()
        runtime.runtime_dir = Path("/tmp/asa-runtime")
        thread = Mock()
        captured_target = {}

        def build_thread(*args, **kwargs):
            captured_target["target"] = kwargs["target"]
            return thread

        with patch.object(server, "_BACKGROUND_TASKS", []):
            with patch.object(server, "get_analysis_runtime", return_value=runtime):
                with patch.object(server.threading, "Thread", side_effect=build_thread):
                    with patch.object(server.asyncio, "create_task", side_effect=self._close_coro_and_return_task):
                        with patch.object(
                            server,
                            "cleanup_artifacts",
                            side_effect=RuntimeError("boom"),
                            create=True,
                        ):
                            with patch.object(server.logger, "warning") as warning_mock:
                                asyncio.run(server._start_cache_eviction())
                                captured_target["target"]()

        warning_mock.assert_called_once()
        self.assertIn("artifact cleanup failed", warning_mock.call_args.args[0].lower())


if __name__ == "__main__":
    unittest.main()
