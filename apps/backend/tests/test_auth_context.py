"""Tests for ``auth_context.admin_key_matches`` and ``admin_key_is_configured``.

These guard a security-critical surface: the admin key gates privileged
operations like cross-user run deletion. Bugs here trade ownership for
access — or vice versa.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


import auth_context  # noqa: E402 — load after sys.path is set


class AdminKeyIsConfiguredTests(unittest.TestCase):
    """``admin_key_is_configured()`` reflects only the env-var state."""

    def test_unset_env_var(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(auth_context.ADMIN_KEY_ENV_VAR, None)
            self.assertFalse(auth_context.admin_key_is_configured())

    def test_empty_env_var(self):
        with mock.patch.dict(
            os.environ,
            {auth_context.ADMIN_KEY_ENV_VAR: ""},
            clear=False,
        ):
            self.assertFalse(auth_context.admin_key_is_configured())

    def test_whitespace_only_env_var(self):
        with mock.patch.dict(
            os.environ,
            {auth_context.ADMIN_KEY_ENV_VAR: "   \n\t  "},
            clear=False,
        ):
            self.assertFalse(auth_context.admin_key_is_configured())

    def test_real_value(self):
        with mock.patch.dict(
            os.environ,
            {auth_context.ADMIN_KEY_ENV_VAR: "s3cret"},
            clear=False,
        ):
            self.assertTrue(auth_context.admin_key_is_configured())


class AdminKeyMatchesTests(unittest.TestCase):
    """``admin_key_matches(provided)`` is the auth decision."""

    def test_returns_false_when_env_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(auth_context.ADMIN_KEY_ENV_VAR, None)
            self.assertFalse(auth_context.admin_key_matches("anything"))
            self.assertFalse(auth_context.admin_key_matches(None))

    def test_returns_false_for_none_provided(self):
        with mock.patch.dict(
            os.environ,
            {auth_context.ADMIN_KEY_ENV_VAR: "s3cret"},
            clear=False,
        ):
            self.assertFalse(auth_context.admin_key_matches(None))

    def test_returns_false_for_empty_provided(self):
        with mock.patch.dict(
            os.environ,
            {auth_context.ADMIN_KEY_ENV_VAR: "s3cret"},
            clear=False,
        ):
            self.assertFalse(auth_context.admin_key_matches(""))
            self.assertFalse(auth_context.admin_key_matches("   "))

    def test_returns_true_for_exact_match(self):
        with mock.patch.dict(
            os.environ,
            {auth_context.ADMIN_KEY_ENV_VAR: "s3cret"},
            clear=False,
        ):
            self.assertTrue(auth_context.admin_key_matches("s3cret"))

    def test_returns_false_for_wrong_value(self):
        with mock.patch.dict(
            os.environ,
            {auth_context.ADMIN_KEY_ENV_VAR: "s3cret"},
            clear=False,
        ):
            self.assertFalse(auth_context.admin_key_matches("wrong"))
            # Case-sensitive: rejected even with the right letters.
            self.assertFalse(auth_context.admin_key_matches("S3CRET"))
            # Partial / prefix matches don't satisfy.
            self.assertFalse(auth_context.admin_key_matches("s3cre"))
            self.assertFalse(auth_context.admin_key_matches("s3cretX"))

    def test_strips_whitespace_on_both_sides(self):
        """Both the configured env value and the supplied header are
        stripped — matters for secret managers that append a newline."""
        with mock.patch.dict(
            os.environ,
            {auth_context.ADMIN_KEY_ENV_VAR: "  s3cret\n"},
            clear=False,
        ):
            self.assertTrue(auth_context.admin_key_matches("s3cret"))
            self.assertTrue(auth_context.admin_key_matches("  s3cret  "))

    def test_constant_time_comparison_is_used(self):
        """We use hmac.compare_digest under the hood to resist timing
        oracle attacks. Verifying the symbol is wired in is a cheap
        regression gate against someone 'simplifying' it to ==.
        """
        import hmac

        with mock.patch.object(
            hmac, "compare_digest", wraps=hmac.compare_digest
        ) as wrapped:
            with mock.patch.dict(
                os.environ,
                {auth_context.ADMIN_KEY_ENV_VAR: "s3cret"},
                clear=False,
            ):
                auth_context.admin_key_matches("s3cret")
            wrapped.assert_called_once()


if __name__ == "__main__":
    unittest.main()
