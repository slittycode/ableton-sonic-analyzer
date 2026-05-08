from __future__ import annotations

from dataclasses import dataclass

from runtime_profile import resolve_runtime_profile, should_require_authenticated_user

LOCAL_DEV_USER_ID = "local-dev"


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
