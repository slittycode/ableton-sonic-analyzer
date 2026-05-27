"""Unit tests for ``worker.py`` — the hosted-mode background task entry point.

``worker.py`` is 29 lines and exists specifically as the hosted-profile process
entry. Local mode ignores it. The risk surface is small but load-bearing:
if it fails to import (e.g. an analyze.py side-effect breaks the chain), the
hosted deployment can't run background stages at all.

These tests verify the contract without booting a real Gemini client or
running an actual stage. They rely on ``unittest.mock`` to stub
``server.get_analysis_runtime`` and ``server._create_background_tasks``.
"""

import asyncio
import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _import_worker():
    """Re-import worker.py fresh so each test sees the patched server module."""
    if "worker" in sys.modules:
        del sys.modules["worker"]
    return importlib.import_module("worker")


class WorkerImportTests(unittest.TestCase):
    """The simplest contract: ``worker.py`` must import in the hosted
    environment. A regression where ``runtime_profile`` resolution crashes at
    import time would fail this test."""

    def test_worker_module_imports_cleanly(self):
        # Patch server before import so worker's ``import server`` doesn't
        # trigger essentia/fastapi side effects.
        fake_server = MagicMock()
        fake_server.get_analysis_runtime = MagicMock()
        fake_server._create_background_tasks = MagicMock(return_value=[])
        with patch.dict(sys.modules, {"server": fake_server}):
            worker = _import_worker()
        self.assertTrue(hasattr(worker, "_run_worker_service"))


class WorkerRuntimeBehaviorTests(unittest.TestCase):
    """``_run_worker_service`` must:
    1. Resolve the runtime profile / process role.
    2. Recover incomplete attempts only when configured to.
    3. Create background tasks with ``include_workers=True`` and
       ``include_cache_eviction=False``.
    4. Cancel cleanly on cancellation.
    """

    def _build_fake_server(self):
        fake = MagicMock()
        fake.get_analysis_runtime = MagicMock()

        # worker.py expects ``_create_background_tasks`` to return real
        # ``asyncio.Task`` objects (it calls ``.cancel()`` on each in the
        # ``finally`` block). Since this side_effect runs inside the active
        # event loop (called from ``_run_worker_service``), ``create_task``
        # can wrap our no-op coroutines into tasks.
        async def _no_op():
            return None
        def _build_tasks(**_):
            return [asyncio.create_task(_no_op())]
        fake._create_background_tasks = MagicMock(side_effect=_build_tasks)
        return fake

    def test_create_background_tasks_called_with_worker_role_flags(self):
        fake_server = self._build_fake_server()
        with patch.dict(sys.modules, {"server": fake_server}):
            worker = _import_worker()

            async def _run():
                await worker._run_worker_service()

            asyncio.run(_run())

            fake_server._create_background_tasks.assert_called_once_with(
                include_cache_eviction=False,
                include_workers=True,
            )

    def test_runtime_get_called_before_tasks_created(self):
        """A regression that builds tasks before fetching the runtime would
        race against runtime initialisation."""
        fake_server = self._build_fake_server()
        runtime_mock = MagicMock()
        call_order: list[str] = []

        def _get_runtime():
            call_order.append("runtime")
            return runtime_mock
        fake_server.get_analysis_runtime.side_effect = _get_runtime

        async def _no_op():
            return None
        def _build_tasks(**_):
            call_order.append("tasks")
            return [asyncio.create_task(_no_op())]
        fake_server._create_background_tasks.side_effect = _build_tasks

        with patch.dict(sys.modules, {"server": fake_server}):
            worker = _import_worker()
            asyncio.run(worker._run_worker_service())

        # ``runtime`` must be observed before ``tasks`` regardless of any
        # incomplete-attempt recovery path that runs in between.
        self.assertIn("runtime", call_order)
        self.assertIn("tasks", call_order)
        self.assertLess(call_order.index("runtime"), call_order.index("tasks"))

    def test_recover_incomplete_attempts_invoked_when_role_requires_it(self):
        fake_server = self._build_fake_server()
        runtime_mock = MagicMock()
        fake_server.get_analysis_runtime.return_value = runtime_mock

        # ``worker.py`` imports ``should_recover_incomplete_attempts`` by name,
        # so the rebind must target ``worker.should_recover_incomplete_attempts``
        # not the source module. Import worker first to install the
        # patch target.
        with patch.dict(sys.modules, {"server": fake_server}):
            worker = _import_worker()
            with patch.object(worker, "should_recover_incomplete_attempts", return_value=True):
                asyncio.run(worker._run_worker_service())

        runtime_mock.recover_incomplete_attempts.assert_called_once()

    def test_recover_incomplete_attempts_skipped_when_role_does_not_require_it(self):
        fake_server = self._build_fake_server()
        runtime_mock = MagicMock()
        fake_server.get_analysis_runtime.return_value = runtime_mock

        with patch.dict(sys.modules, {"server": fake_server}):
            worker = _import_worker()
            with patch.object(worker, "should_recover_incomplete_attempts", return_value=False):
                asyncio.run(worker._run_worker_service())

        runtime_mock.recover_incomplete_attempts.assert_not_called()


if __name__ == "__main__":
    unittest.main()
