import json
import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import audio_source_providers as providers
from url_ingest import UrlBlockedPrivateHostError, UrlInvalidError


class _Response:
    def __init__(self, status=200, *, headers=None, chunks=None, payload=None):
        self.status = status
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks or []
        self._payload = payload or {}

    def stream(self, _size):
        return iter(self._chunks)

    def release_conn(self):
        return None

    def json(self):
        return self._payload


class AudioSourceProviderTests(unittest.TestCase):
    def test_exact_provider_classification_rejects_deceptive_domains(self):
        self.assertEqual(providers.classify_audio_source("https://www.youtube.com/watch?v=1"), "youtube")
        self.assertEqual(providers.classify_audio_source("https://youtu.be/abc"), "youtube")
        self.assertEqual(providers.classify_audio_source("https://artist.bandcamp.com/track/test"), "bandcamp")
        self.assertEqual(providers.classify_audio_source("https://youtube.com.example.org/audio.mp3"), "direct")
        self.assertEqual(providers.classify_audio_source("https://notspotify.com/audio.mp3"), "direct")

    def test_url_credentials_are_rejected(self):
        with self.assertRaises(UrlInvalidError):
            providers.classify_audio_source("https://user:secret@example.com/audio.mp3")

    @patch("audio_source_providers.socket.getaddrinfo")
    def test_dns_resolution_rejects_any_private_address(self, getaddrinfo):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
        ]
        with self.assertRaises(UrlBlockedPrivateHostError):
            providers._resolve_public_ip("example.com")

    def test_direct_download_checks_each_redirect_and_streams_to_disk(self):
        responses = [
            (_Response(302, headers={"Location": "https://cdn.example.net/song.wav"}), SimpleNamespace(close=lambda: None)),
            (_Response(200, headers={"Content-Type": "audio/wav"}, chunks=[b"RIFF", b"audio"]), SimpleNamespace(close=lambda: None)),
        ]
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "audio_source_providers._request_to_validated_ip", side_effect=responses
        ) as request:
            path, filename, mime = providers.download_direct_audio(
                "https://example.com/start", Path(temp_dir), should_cancel=lambda: False
            )
            self.assertEqual(path.read_bytes(), b"RIFFaudio")
        self.assertEqual(request.call_args_list[0].args[0], "https://example.com/start")
        self.assertEqual(request.call_args_list[1].args[0], "https://cdn.example.net/song.wav")
        self.assertEqual(filename, "song.wav")
        self.assertEqual(mime, "audio/wav")

    def test_direct_provider_requires_decodable_audio(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "audio_source_providers.download_direct_audio",
            return_value=(Path(temp_dir) / "bad.mp3", "bad.mp3", "audio/mpeg"),
        ), patch("audio_source_providers.get_audio_duration_seconds", return_value=None):
            (Path(temp_dir) / "bad.mp3").write_bytes(b"not audio")
            with self.assertRaises(providers.AudioSourceInvalidAudioError):
                providers.DirectAudioProvider().prepare(
                    "https://example.com/bad.mp3",
                    Path(temp_dir),
                    should_cancel=lambda: False,
                    update_status=lambda _status: None,
                )

    @patch.dict(
        "os.environ",
        {
            "ASA_ENABLE_SOUNDCLOUD_LINKS": "1",
            "SOUNDCLOUD_CLIENT_ID": "client",
            "SOUNDCLOUD_CLIENT_SECRET": "secret",
        },
        clear=False,
    )
    @patch("audio_source_providers.requests.post")
    def test_soundcloud_token_is_cached(self, post):
        providers._SOUNDCLOUD_TOKEN = None
        post.return_value = _Response(payload={"access_token": "token", "expires_in": 3600})
        self.assertEqual(providers._soundcloud_access_token(), "token")
        self.assertEqual(providers._soundcloud_access_token(), "token")
        post.assert_called_once()

    @patch("audio_source_providers._validate_prepared_audio", return_value=60.0)
    @patch("audio_source_providers.download_direct_audio")
    @patch("audio_source_providers.requests.get")
    @patch("audio_source_providers._soundcloud_access_token", side_effect=["old", "new"])
    @patch("audio_source_providers._invalidate_soundcloud_token")
    def test_soundcloud_refreshes_rejected_cached_token(
        self, invalidate, token, get, download, _validate
    ):
        track = {
            "kind": "track",
            "access": "playable",
            "duration": 60_000,
            "id": 123,
            "title": "Track",
            "permalink_url": "https://soundcloud.com/artist/track",
            "user": {"username": "Artist"},
        }
        get.side_effect = [
            _Response(401),
            _Response(payload=track),
            _Response(302, headers={"Location": "https://cdn.example.com/track.mp3"}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "track.mp3"
            audio_path.write_bytes(b"audio")
            download.return_value = (audio_path, "track.mp3", "audio/mpeg")
            prepared = providers.SoundCloudProvider().prepare(
                "https://soundcloud.com/artist/track",
                Path(temp_dir),
                should_cancel=lambda: False,
                update_status=lambda _status: None,
            )
        invalidate.assert_called_once_with("old")
        self.assertEqual(token.call_count, 2)
        self.assertEqual(get.call_args_list[1].kwargs["headers"]["Authorization"], "OAuth new")
        self.assertEqual(prepared.creator, "Artist")

    @patch.dict("os.environ", {"ASA_ENABLE_YOUTUBE_LINKS": "1", "ASA_RUNTIME_PROFILE": "local"}, clear=False)
    @patch("audio_source_providers.shutil.which", side_effect=lambda name: f"/usr/bin/{name}")
    @patch("audio_source_providers._validate_prepared_audio", return_value=120.0)
    @patch("audio_source_providers._run_cancellable_command")
    def test_youtube_uses_safe_non_shell_commands(self, run_command, _validate, _which):
        def command_result(command, **_kwargs):
            if "--skip-download" in command:
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps({"id": "abc", "title": "Track", "duration": 120}),
                )
            output_template = Path(command[command.index("--output") + 1])
            output_template.with_name("source.mp3").write_bytes(b"mp3")
            return SimpleNamespace(returncode=0, stdout="")

        run_command.side_effect = command_result
        with tempfile.TemporaryDirectory() as temp_dir:
            prepared = providers.YouTubeExperimentalProvider().prepare(
                "https://www.youtube.com/watch?v=abc",
                Path(temp_dir),
                should_cancel=lambda: False,
                update_status=lambda _status: None,
            )
        commands = [call.args[0] for call in run_command.call_args_list]
        self.assertTrue(all(isinstance(command, list) for command in commands))
        self.assertTrue(all("--ignore-config" in command for command in commands))
        self.assertTrue(all("--no-playlist" in command for command in commands))
        self.assertEqual(prepared.mime_type, "audio/mpeg")
        self.assertTrue(prepared.experimental)


if __name__ == "__main__":
    unittest.main()
