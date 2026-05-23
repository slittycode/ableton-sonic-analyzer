"""Regression tests for host-independent audio MIME resolution."""

import sys
import unittest
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


import audio_mime  # noqa: E402
import url_ingest  # noqa: E402


class CanonicalAudioMimeTests(unittest.TestCase):
    def test_known_extensions_map_to_canonical_types(self) -> None:
        self.assertEqual(audio_mime.canonical_audio_mime("track.mp3"), "audio/mpeg")
        self.assertEqual(audio_mime.canonical_audio_mime("track.wav"), "audio/wav")
        self.assertEqual(audio_mime.canonical_audio_mime("track.flac"), "audio/flac")
        self.assertEqual(audio_mime.canonical_audio_mime("track.aiff"), "audio/aiff")
        self.assertEqual(audio_mime.canonical_audio_mime("track.aif"), "audio/aiff")

    def test_is_case_insensitive_and_path_aware(self) -> None:
        self.assertEqual(audio_mime.canonical_audio_mime("/a/b/SONG.FLAC"), "audio/flac")
        self.assertEqual(audio_mime.canonical_audio_mime("My Track.Wav"), "audio/wav")

    def test_unknown_or_missing_extension_returns_none(self) -> None:
        self.assertIsNone(audio_mime.canonical_audio_mime("blob.bin"))
        self.assertIsNone(audio_mime.canonical_audio_mime("noext"))
        self.assertIsNone(audio_mime.canonical_audio_mime(""))

    def test_url_ingest_picker_uses_canonical_map_on_octet_stream(self) -> None:
        self.assertEqual(
            url_ingest._pick_mime_type("application/octet-stream", "/audio.flac"),
            "audio/flac",
        )


if __name__ == "__main__":
    unittest.main()
