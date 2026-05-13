"""Unit tests for url_ingest — URL validation, SSRF guard, fetch error mapping.

The route-level tests in test_server.py exercise the HTTP shell;
these tests focus on the pure-logic surface of url_ingest.py: given
specific URL shapes and mock HTTP responses, does the right error
class come back, does the size limit get enforced, does the SSRF
guard block private addresses?
"""

import sys
import unittest
from pathlib import Path
from unittest import mock


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


import url_ingest  # noqa: E402 — load after sys.path is set


def _make_addrinfo_for(ip: str):
    """Build a getaddrinfo-style result for one IPv4 address."""
    import socket as _socket

    family = _socket.AF_INET6 if ":" in ip else _socket.AF_INET
    sockaddr = (ip, 0, 0, 0) if family == _socket.AF_INET6 else (ip, 0)
    return [(family, _socket.SOCK_STREAM, 0, "", sockaddr)]


def _make_mock_response(
    *,
    status: int = 200,
    body: bytes = b"audio-bytes",
    content_type: str = "audio/mpeg",
    content_length: str | None = None,
    chunk_size: int = 4096,
) -> mock.MagicMock:
    """A stand-in for the requests.Response that ``requests.get`` returns
    as a context manager. Streams ``body`` in chunks of ``chunk_size``."""
    headers = {"Content-Type": content_type}
    if content_length is not None:
        headers["Content-Length"] = content_length

    def iter_content(chunk_size=4096):  # noqa: ARG001 — match requests API
        # Yield body in fixed-size pieces.
        for i in range(0, len(body), chunk_size):
            yield body[i : i + chunk_size]

    response = mock.MagicMock(
        name="response",
        status_code=status,
        headers=headers,
    )
    response.iter_content.side_effect = iter_content
    # Make the response a usable context manager: __enter__ returns the
    # response itself, __exit__ does nothing.
    response.__enter__ = mock.MagicMock(return_value=response)
    response.__exit__ = mock.MagicMock(return_value=False)
    return response


class UrlShapeValidationTests(unittest.TestCase):
    """The cheap, deterministic URL-string checks."""

    def test_empty_string_rejected(self):
        with self.assertRaises(url_ingest.UrlInvalidError):
            url_ingest._validate_url_shape("")

    def test_too_long_rejected(self):
        too_long = "https://example.com/" + ("a" * (url_ingest.MAX_URL_LENGTH + 1))
        with self.assertRaises(url_ingest.UrlInvalidError):
            url_ingest._validate_url_shape(too_long)

    def test_file_scheme_rejected(self):
        with self.assertRaises(url_ingest.UrlInvalidError) as ctx:
            url_ingest._validate_url_shape("file:///etc/passwd")
        self.assertIn("scheme", str(ctx.exception).lower())

    def test_ftp_scheme_rejected(self):
        with self.assertRaises(url_ingest.UrlInvalidError):
            url_ingest._validate_url_shape("ftp://example.com/audio.mp3")

    def test_no_hostname_rejected(self):
        with self.assertRaises(url_ingest.UrlInvalidError):
            url_ingest._validate_url_shape("https:///audio.mp3")

    def test_http_accepted(self):
        # No exception
        url_ingest._validate_url_shape("http://example.com/audio.mp3")

    def test_https_accepted(self):
        url_ingest._validate_url_shape("https://example.com/audio.mp3")


class SsrfGuardTests(unittest.TestCase):
    """Hostnames that resolve to private/loopback/etc. must be rejected
    before any HTTP request is dispatched."""

    def _assert_blocks(self, ip: str) -> None:
        with mock.patch(
            "socket.getaddrinfo", return_value=_make_addrinfo_for(ip)
        ):
            with self.assertRaises(url_ingest.UrlBlockedPrivateHostError):
                url_ingest._assert_host_is_public("blocked.example.com")

    def _assert_allows(self, ip: str) -> None:
        with mock.patch(
            "socket.getaddrinfo", return_value=_make_addrinfo_for(ip)
        ):
            # Should not raise.
            url_ingest._assert_host_is_public("public.example.com")

    def test_blocks_ipv4_loopback(self):
        self._assert_blocks("127.0.0.1")

    def test_blocks_ipv4_rfc1918_10(self):
        self._assert_blocks("10.0.0.5")

    def test_blocks_ipv4_rfc1918_192(self):
        self._assert_blocks("192.168.1.50")

    def test_blocks_ipv4_rfc1918_172(self):
        self._assert_blocks("172.20.0.1")

    def test_blocks_ipv4_link_local(self):
        self._assert_blocks("169.254.169.254")  # AWS metadata endpoint

    def test_blocks_ipv6_loopback(self):
        self._assert_blocks("::1")

    def test_allows_public_ipv4(self):
        self._assert_allows("8.8.8.8")  # Google DNS

    def test_allows_public_ipv6(self):
        self._assert_allows("2001:4860:4860::8888")  # Google DNS v6

    def test_dns_failure_surfaces_as_fetch_failed(self):
        import socket as _socket

        with mock.patch(
            "socket.getaddrinfo", side_effect=_socket.gaierror("no such host")
        ):
            with self.assertRaises(url_ingest.UrlFetchFailedError):
                url_ingest._assert_host_is_public("nx.example.com")


class FilenameExtractionTests(unittest.TestCase):
    """Filename comes from the last URL path segment with a safe fallback."""

    def test_simple_path(self):
        self.assertEqual(url_ingest._extract_filename("/audio.mp3"), "audio.mp3")

    def test_nested_path(self):
        self.assertEqual(
            url_ingest._extract_filename("/uploads/tracks/song.flac"),
            "song.flac",
        )

    def test_trailing_slash(self):
        self.assertEqual(url_ingest._extract_filename("/audio.mp3/"), "audio.mp3")

    def test_empty_path_falls_back(self):
        self.assertEqual(url_ingest._extract_filename(""), "url_audio.bin")

    def test_root_falls_back(self):
        self.assertEqual(url_ingest._extract_filename("/"), "url_audio.bin")

    def test_dotdot_falls_back(self):
        # Defense in depth — we never use this as a filesystem path,
        # but the helper shouldn't return "..".
        self.assertEqual(url_ingest._extract_filename("/../audio.mp3"), "audio.mp3")
        self.assertEqual(url_ingest._extract_filename("/.."), "url_audio.bin")

    def test_url_encoded_filename_is_decoded(self):
        self.assertEqual(
            url_ingest._extract_filename("/track%20one.mp3"),
            "track one.mp3",
        )


class MimeTypePickerTests(unittest.TestCase):
    """Content-Type wins; filename guess is the fallback."""

    def test_content_type_header_wins(self):
        self.assertEqual(
            url_ingest._pick_mime_type("audio/mpeg", "/anything.bin"),
            "audio/mpeg",
        )

    def test_content_type_with_charset_is_stripped(self):
        self.assertEqual(
            url_ingest._pick_mime_type(
                "audio/mpeg; charset=binary", "/x.bin"
            ),
            "audio/mpeg",
        )

    def test_octet_stream_triggers_filename_fallback(self):
        # application/octet-stream is too generic — fall through.
        self.assertEqual(
            url_ingest._pick_mime_type(
                "application/octet-stream", "/audio.flac"
            ),
            "audio/flac",
        )

    def test_no_content_type_falls_back_to_filename(self):
        self.assertEqual(
            url_ingest._pick_mime_type("", "/audio.wav"), "audio/x-wav"
        )

    def test_unknown_extension_falls_back_to_octet_stream(self):
        # ``.qqqzz`` is not in any standard mimetypes database, so the
        # fallback path runs.
        self.assertEqual(
            url_ingest._pick_mime_type("", "/audio.qqqzz"),
            "application/octet-stream",
        )


class FetchUrlToBytesTests(unittest.TestCase):
    """End-to-end fetch path with mocked requests.get."""

    PUBLIC_URL = "https://example.com/track.mp3"

    def _patch_dns_and_get(self, response, public_ip="93.184.216.34"):
        """Stack the patches needed for a happy-path fetch."""
        return mock.patch.multiple(
            "url_ingest",
            requests=mock.DEFAULT,
        ), mock.patch(
            "socket.getaddrinfo",
            return_value=_make_addrinfo_for(public_ip),
        )

    def test_happy_path_returns_content_filename_mime(self):
        response = _make_mock_response(
            status=200,
            body=b"abc" * 1000,  # 3000 bytes
            content_type="audio/mpeg",
        )
        with mock.patch(
            "socket.getaddrinfo",
            return_value=_make_addrinfo_for("93.184.216.34"),
        ), mock.patch.object(url_ingest.requests, "get", return_value=response):
            fetched = url_ingest.fetch_url_to_bytes(self.PUBLIC_URL)

        self.assertEqual(fetched.content, b"abc" * 1000)
        self.assertEqual(fetched.filename, "track.mp3")
        self.assertEqual(fetched.mime_type, "audio/mpeg")

    def test_http_error_status_raises_fetch_failed(self):
        response = _make_mock_response(status=404, body=b"not found")
        with mock.patch(
            "socket.getaddrinfo",
            return_value=_make_addrinfo_for("93.184.216.34"),
        ), mock.patch.object(url_ingest.requests, "get", return_value=response):
            with self.assertRaises(url_ingest.UrlFetchFailedError) as ctx:
                url_ingest.fetch_url_to_bytes(self.PUBLIC_URL)
            self.assertIn("404", str(ctx.exception))

    def test_content_length_too_large_raises(self):
        response = _make_mock_response(
            status=200,
            body=b"x",
            # Declare a 1 GiB body — exceeds default 100 MiB limit.
            content_length=str(1024 * 1024 * 1024),
        )
        with mock.patch(
            "socket.getaddrinfo",
            return_value=_make_addrinfo_for("93.184.216.34"),
        ), mock.patch.object(url_ingest.requests, "get", return_value=response):
            with self.assertRaises(url_ingest.UrlTooLargeError):
                url_ingest.fetch_url_to_bytes(self.PUBLIC_URL)

    def test_streaming_overrun_raises(self):
        # No Content-Length set; body is larger than max_bytes override.
        response = _make_mock_response(
            status=200,
            body=b"x" * 5_000,
            content_type="audio/mpeg",
        )
        with mock.patch(
            "socket.getaddrinfo",
            return_value=_make_addrinfo_for("93.184.216.34"),
        ), mock.patch.object(url_ingest.requests, "get", return_value=response):
            with self.assertRaises(url_ingest.UrlTooLargeError):
                url_ingest.fetch_url_to_bytes(self.PUBLIC_URL, max_bytes=1_000)

    def test_empty_body_raises_fetch_failed(self):
        response = _make_mock_response(status=200, body=b"")
        with mock.patch(
            "socket.getaddrinfo",
            return_value=_make_addrinfo_for("93.184.216.34"),
        ), mock.patch.object(url_ingest.requests, "get", return_value=response):
            with self.assertRaises(url_ingest.UrlFetchFailedError) as ctx:
                url_ingest.fetch_url_to_bytes(self.PUBLIC_URL)
            self.assertIn("empty", str(ctx.exception).lower())

    def test_private_host_blocks_before_http(self):
        # If SSRF guard fires, we never reach requests.get.
        mock_get = mock.MagicMock()
        with mock.patch(
            "socket.getaddrinfo",
            return_value=_make_addrinfo_for("10.0.0.5"),
        ), mock.patch.object(url_ingest.requests, "get", mock_get):
            with self.assertRaises(url_ingest.UrlBlockedPrivateHostError):
                url_ingest.fetch_url_to_bytes(self.PUBLIC_URL)
            mock_get.assert_not_called()

    def test_timeout_raises_fetch_failed(self):
        import requests as _requests

        with mock.patch(
            "socket.getaddrinfo",
            return_value=_make_addrinfo_for("93.184.216.34"),
        ), mock.patch.object(
            url_ingest.requests,
            "get",
            side_effect=_requests.exceptions.Timeout("read timeout"),
        ):
            with self.assertRaises(url_ingest.UrlFetchFailedError) as ctx:
                url_ingest.fetch_url_to_bytes(self.PUBLIC_URL)
            self.assertIn("timed out", str(ctx.exception).lower())

    def test_connection_error_raises_fetch_failed(self):
        import requests as _requests

        with mock.patch(
            "socket.getaddrinfo",
            return_value=_make_addrinfo_for("93.184.216.34"),
        ), mock.patch.object(
            url_ingest.requests,
            "get",
            side_effect=_requests.exceptions.ConnectionError("refused"),
        ):
            with self.assertRaises(url_ingest.UrlFetchFailedError):
                url_ingest.fetch_url_to_bytes(self.PUBLIC_URL)


if __name__ == "__main__":
    unittest.main()
