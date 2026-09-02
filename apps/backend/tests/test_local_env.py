"""Unit tests for server._load_local_env (~/.asa/env loader).

Covers: parsing KEY=VALUE, comments/blanks, export prefix, quoted values,
no-override of already-exported vars, missing file no-op, OSError no-op.

Run:
  ./venv/bin/python -m unittest tests.test_local_env
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server


class LoadLocalEnvTests(unittest.TestCase):
    def test_missing_file_is_noop(self) -> None:
        missing = Path(tempfile.gettempdir()) / "asa-env-does-not-exist-xyz.env"
        with mock.patch.dict(os.environ, {}, clear=True):
            applied = server._load_local_env(missing)
        self.assertEqual(applied, {})

    def test_parses_key_value_and_skips_comments_blanks(self) -> None:
        content = "\n".join(
            [
                "# comment",
                "",
                "ASA_GEMINI_BACKEND=vertex",
                "export GOOGLE_CLOUD_PROJECT=sonic-analysis",
                "GOOGLE_CLOUD_LOCATION='us-central1'",
                "QUOTED=\"double-quoted\"",
                "NOT_A_PAIR",
                "  SPACED_KEY = spaced-value  ",
            ]
        )
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write(content)
            env_path = Path(handle.name)
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                applied = server._load_local_env(env_path)
                self.assertEqual(applied["ASA_GEMINI_BACKEND"], "vertex")
                self.assertEqual(applied["GOOGLE_CLOUD_PROJECT"], "sonic-analysis")
                self.assertEqual(applied["GOOGLE_CLOUD_LOCATION"], "us-central1")
                self.assertEqual(applied["QUOTED"], "double-quoted")
                self.assertEqual(applied["SPACED_KEY"], "spaced-value")
                self.assertNotIn("NOT_A_PAIR", applied)
                self.assertEqual(os.environ["ASA_GEMINI_BACKEND"], "vertex")
                self.assertEqual(os.environ["GOOGLE_CLOUD_PROJECT"], "sonic-analysis")
        finally:
            env_path.unlink(missing_ok=True)

    def test_never_overrides_already_exported_vars(self) -> None:
        content = "ASA_GEMINI_BACKEND=vertex\nGEMINI_API_KEY=from-file\n"
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write(content)
            env_path = Path(handle.name)
        try:
            with mock.patch.dict(
                os.environ,
                {"ASA_GEMINI_BACKEND": "apistudio", "OTHER": "keep"},
                clear=True,
            ):
                applied = server._load_local_env(env_path)
                self.assertNotIn("ASA_GEMINI_BACKEND", applied)
                self.assertEqual(os.environ["ASA_GEMINI_BACKEND"], "apistudio")
                self.assertEqual(applied["GEMINI_API_KEY"], "from-file")
                self.assertEqual(os.environ["GEMINI_API_KEY"], "from-file")
                self.assertEqual(os.environ["OTHER"], "keep")
        finally:
            env_path.unlink(missing_ok=True)

    def test_oserror_is_noop(self) -> None:
        # Point at a directory so read_text raises IsADirectoryError (OSError).
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {}, clear=True):
                applied = server._load_local_env(Path(tmpdir))
        self.assertEqual(applied, {})


if __name__ == "__main__":
    unittest.main()
