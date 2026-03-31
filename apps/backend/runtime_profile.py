from __future__ import annotations

import os
from typing import Literal

RuntimeProfile = Literal["local", "hosted"]
ProcessRole = Literal["all", "api", "worker"]

DEFAULT_RUNTIME_PROFILE: RuntimeProfile = "local"
DEFAULT_LOCAL_PROCESS_ROLE: ProcessRole = "all"
DEFAULT_HOSTED_PROCESS_ROLE: ProcessRole = "api"


def resolve_runtime_profile(raw_value: str | None = None) -> RuntimeProfile:
    value = (raw_value or os.getenv("SONIC_ANALYZER_RUNTIME_PROFILE", "")).strip().lower()
    if value in {"", "local"}:
        return "local"
    if value == "hosted":
        return "hosted"
    return DEFAULT_RUNTIME_PROFILE


def resolve_process_role(
    raw_value: str | None = None,
    *,
    runtime_profile: RuntimeProfile | None = None,
) -> ProcessRole:
    profile = runtime_profile or resolve_runtime_profile()
    default_role = (
        DEFAULT_LOCAL_PROCESS_ROLE if profile == "local" else DEFAULT_HOSTED_PROCESS_ROLE
    )
    value = (raw_value or os.getenv("SONIC_ANALYZER_PROCESS_ROLE", "")).strip().lower()
    if value in {"all", "api", "worker"}:
        return value  # type: ignore[return-value]
    return default_role


def should_require_authenticated_user(runtime_profile: RuntimeProfile | None = None) -> bool:
    return (runtime_profile or resolve_runtime_profile()) == "hosted"


def should_start_in_process_workers(
    runtime_profile: RuntimeProfile | None = None,
    process_role: ProcessRole | None = None,
) -> bool:
    profile = runtime_profile or resolve_runtime_profile()
    role = process_role or resolve_process_role(runtime_profile=profile)
    if profile == "local":
        return role == "all"
    return role == "worker"


def should_recover_incomplete_attempts(
    runtime_profile: RuntimeProfile | None = None,
    process_role: ProcessRole | None = None,
) -> bool:
    profile = runtime_profile or resolve_runtime_profile()
    role = process_role or resolve_process_role(runtime_profile=profile)
    if profile == "local":
        return role == "all"
    return role == "worker"
