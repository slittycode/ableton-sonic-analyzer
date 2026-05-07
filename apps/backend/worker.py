#!/usr/bin/env python3
from __future__ import annotations

import asyncio

import server
from runtime_profile import resolve_process_role, resolve_runtime_profile, should_recover_incomplete_attempts


async def _run_worker_service() -> None:
    runtime = server.get_analysis_runtime()
    runtime_profile = resolve_runtime_profile()
    process_role = resolve_process_role(runtime_profile=runtime_profile)
    if should_recover_incomplete_attempts(runtime_profile, process_role):
        runtime.recover_incomplete_attempts()
    tasks = server._create_background_tasks(
        include_cache_eviction=False,
        include_workers=True,
    )
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(_run_worker_service())
