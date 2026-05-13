from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from runtime_profile import resolve_runtime_profile, should_require_authenticated_user

LOCAL_DEV_USER_ID = "local-dev"

# Operator-level privilege gate. When this env var is set and non-empty,
# requests carrying a matching ``X-Admin-Key`` header may perform privileged
# operations (e.g. delete runs they do not own). When unset, no admin path
# exists and routes fall back to per-user-ownership enforcement. Default for
# local development is unset.
ADMIN_KEY_ENV_VAR = "SONIC_ANALYZER_ADMIN_KEY"


class AuthenticationRequiredError(PermissionError):
    pass


@dataclass(frozen=True)
class UserContext:
    user_id: str
    email: str | None
    runtime_profile: str


def resolve_api_user_context(
    header_user_id: str | None,
    header_user_email: str | None,
) -> UserContext:
    runtime_profile = resolve_runtime_profile()
    if not should_require_authenticated_user(runtime_profile):
        return UserContext(
            user_id=LOCAL_DEV_USER_ID,
            email=header_user_email.strip() if isinstance(header_user_email, str) and header_user_email.strip() else None,
            runtime_profile=runtime_profile,
        )

    user_id = header_user_id.strip() if isinstance(header_user_id, str) else ""
    if not user_id:
        raise AuthenticationRequiredError(
            "Hosted runtime requests must include the X-ASA-User-Id header."
        )

    email = header_user_email.strip() if isinstance(header_user_email, str) else ""
    return UserContext(
        user_id=user_id,
        email=email or None,
        runtime_profile=runtime_profile,
    )


def _read_configured_admin_key() -> str:
    """Return the configured admin key, or empty string if unset."""
    return (os.getenv(ADMIN_KEY_ENV_VAR) or "").strip()


def admin_key_is_configured() -> bool:
    """True iff :data:`ADMIN_KEY_ENV_VAR` is set to a non-empty value.

    Use this to decide *whether* to expose admin-gated routes, not to
    *authorize* a specific request. For authorization, call
    :func:`admin_key_matches`.
    """
    return bool(_read_configured_admin_key())


def admin_key_matches(provided: str | None) -> bool:
    """Constant-time check: does ``provided`` match the configured admin key?

    Returns ``False`` when:
    - the admin key is not configured (the env var is unset/empty), or
    - the caller did not supply a header value, or
    - the supplied value does not match the configured key.

    Uses :func:`hmac.compare_digest` to resist timing-based probing of
    the configured key. Strips whitespace from both sides — both the
    header value and the env var — to avoid trailing-newline surprises
    when keys are sourced from secret managers.
    """
    if provided is None:
        return False
    configured = _read_configured_admin_key()
    if not configured:
        return False
    stripped = provided.strip()
    if not stripped:
        return False
    return hmac.compare_digest(configured, stripped)
