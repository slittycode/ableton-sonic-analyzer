"""Tests for the Phase 1 separation backend seam (Demucs).

The former MSST branch was removed in the 2026-07 trust diet; these tests lock
the demucs-only thin seam that ``analyze.py`` calls.
"""

import os
import unittest
from unittest import mock

import separation_backend as sb


_SENTINEL_STEMS = {"vocals": "/tmp/v.wav", "bass": "/tmp/b.wav", "drums": "/tmp/d.wav", "other": "/tmp/o.wav"}


class SeparationBackendNameTests(unittest.TestCase):
    def test_default_is_demucs(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASA_SEPARATION_BACKEND", None)
            self.assertEqual(sb.separation_backend_name(), "demucs")

    def test_unknown_value_falls_back_to_demucs(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_SEPARATION_BACKEND": "bogus"}):
            self.assertEqual(sb.separation_backend_name(), "demucs")

    def test_former_msst_value_falls_back_to_demucs(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_SEPARATION_BACKEND": "msst"}):
            self.assertEqual(sb.separation_backend_name(), "demucs")


class DispatchTests(unittest.TestCase):
    def test_demucs_default_delegates_to_separate_stems(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASA_SEPARATION_BACKEND", None)
            with mock.patch.object(
                sb, "separate_stems", return_value=_SENTINEL_STEMS
            ) as demucs:
                out = sb.separate_stems_backend("/tmp/track.flac", output_dir="/tmp/out")
        demucs.assert_called_once_with("/tmp/track.flac", output_dir="/tmp/out")
        self.assertEqual(out, _SENTINEL_STEMS)

    def test_msst_env_still_delegates_to_demucs(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_SEPARATION_BACKEND": "msst"}, clear=False):
            with mock.patch.object(
                sb, "separate_stems", return_value=_SENTINEL_STEMS
            ) as demucs:
                out = sb.separate_stems_backend("/tmp/track.flac")
        demucs.assert_called_once()
        self.assertEqual(out, _SENTINEL_STEMS)


if __name__ == "__main__":
    unittest.main()
