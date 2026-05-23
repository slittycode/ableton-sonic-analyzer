"""Unit tests for audio_mime — host-independent canonical MIME resolution.

Regression guard: Python's stdlib ``mimetypes`` resolves ``.flac`` to
``audio/x-flac`` on macOS but ``audio/flac`` on Linux. ``canonical_audio_mime``
must return the same value regardless of host so the backend test gate is stable
and a FLAC handed to Gemini is labeled ``audio/flac`` everywhere.
"""

import sys
import unittest
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


import audio_mime  # noqa: E402 — load after sys.path is set
import url_ingest  # noqa: E402


class CanonicalAudioMimeTests(unittest.TestCase):
    def test_known_extensions_map_to_canonical_types(self):
        cases = {
            "track.mp3": "audio/mpeg",
            "track.wav": "audio/wav",
            "track.flac": "audio/flac",
            "track.aiff": "audio/aiff",
            "track.aif": "audio/aiff",
        }
        for name, expected in cases.items():
            self.assertEqual(audio_mime.canonical_audio_mime(name), expected)

    def test_is_case_insensitive_and_path_aware(self):
        self.assertEqual(audio_mime.canonical_audio_mime("/a/b/SONG.FLAC"), "audio/flac")
        self.assertEqual(audio_mime.canonical_audio_mime("My Track.Wav"), "audio/wav")

    def test_flac_is_host_independent(self):
        # The whole point: never the host-specific ``audio/x-flac``.
        self.assertEqual(audio_mime.canonical_audio_mime("x.flac"), "audio/flac")

    def test_unknown_or_missing_extension_returns_none(self):
        self.assertIsNone(audio_mime.canonical_audio_mime("blob.bin"))
        self.assertIsNone(audio_mime.canonical_audio_mime("noext"))
        self.assertIsNone(audio_mime.canonical_audio_mime(""))

    def test_backend_matches_frontend_contract(self):
        # Mirror of AUDIO_EXTENSION_MIME_TYPES in
        # apps/ui/src/services/audioFile.ts — keep these in sync.
        self.assertEqual(
            audio_mime.CANONICAL_AUDIO_MIME_BY_EXT,
            {
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".flac": "audio/flac",
                ".aiff": "audio/aiff",
                ".aif": "audio/aiff",
            },
        )

    def test_url_ingest_picker_uses_canonical_map_on_octet_stream(self):
        # The macOS regression that started this: octet-stream + .flac filename.
        self.assertEqual(
            url_ingest._pick_mime_type("application/octet-stream", "/audio.flac"),
            "audio/flac",
        )


if __name__ == "__main__":
    unittest.main()
