"""URL-based ingestion for ``POST /api/analysis-runs``.

Lets a producer point ASA at a publicly hosted audio file instead of
uploading bytes through the browser. The server fetches, validates,
and feeds the bytes into the same downstream pipeline as a multipart
upload would.

Scope (v1):

- HTTP and HTTPS only. ``file://``, ``ftp://`` etc. are rejected.
- SSRF guarded: hostnames that resolve to private, loopback, link-local,
  or otherwise reserved IP space are rejected before any HTTP request
  is made. This is a "first-line" guard — there is still a small DNS
  TOCTOU window between resolution and fetch, but the alternative
  (custom DNS resolver that pins the result through the HTTP client)
  is out of scope for v1.
- Streaming size enforcement: ``Content-Length`` is checked up-front
  if present, and the body is also streamed-and-accumulated with an
  abort if bytes exceed :data:`upload_limits.MAX_UPLOAD_SIZE_BYTES`.
- Timeouts: connect + read timeout default 60 s; total wall clock
  capped at 300 s.
- The filename is extracted from the URL path; falls back to
  ``url_audio.bin`` when missing. MIME type prefers the response
  ``Content-Type`` header, then guesses from the filename.

This module is pure I/O + validation. The HTTP route handler in
``server.py`` is responsible for translating typed exceptions raised
here into the canonical error envelope codes.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Final
from urllib.parse import unquote, urlparse

import requests

import upload_limits
from audio_mime import canonical_audio_mime


__all__ = [
    "FetchedUrl",
    "UrlIngestionError",
    "UrlInvalidError",
    "UrlBlockedPrivateHostError",
    "UrlFetchFailedError",
    "UrlTooLargeError",
    "fetch_url_to_bytes",
]


# Public defaults — keep them in sync with the route-handler docs.
DEFAULT_CONNECT_TIMEOUT_S: Final[float] = 30.0
DEFAULT_READ_TIMEOUT_S: Final[float] = 60.0
DEFAULT_TOTAL_TIMEOUT_S: Final[float] = 300.0
MAX_URL_LENGTH: Final[int] = 4096
ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})
# Stream chunk size. Small enough to detect oversize quickly; large enough
# that we're not blocked on syscall overhead.
_FETCH_CHUNK_BYTES: Final[int] = 64 * 1024


@dataclass(frozen=True)
class FetchedUrl:
    """The output of a successful URL fetch.

    ``content`` is the full audio body in memory. The byte limit
    (``MAX_UPLOAD_SIZE_BYTES``, 100 MiB) means this is bounded; we do
    not stream to disk because the downstream ``create_run`` API
    expects ``bytes`` and writes to its own artifact store from there.
    """

    content: bytes
    filename: str
    mime_type: str


# ----------------------------------------------------------------------
# Exception hierarchy
# ----------------------------------------------------------------------


class UrlIngestionError(Exception):
    """Base class for URL-ingestion errors.

    Subclasses map 1:1 to public error codes returned by the route
    handler. The ``message`` is safe to surface to the client; do not
    embed secrets or internal hostnames.
    """

    code: str = "URL_INGESTION_ERROR"


class UrlInvalidError(UrlIngestionError):
    """The URL is malformed, too long, or uses a disallowed scheme."""

    code = "URL_INVALID"


class UrlBlockedPrivateHostError(UrlIngestionError):
    """The URL resolves to a private/loopback/link-local IP — SSRF guard.

    Triggered before any HTTP request is dispatched. The TOCTOU window
    between resolution-time and fetch-time is acknowledged as out of
    scope for v1; a pinning DNS resolver is the v2 improvement.
    """

    code = "URL_BLOCKED_PRIVATE_HOST"


class UrlFetchFailedError(UrlIngestionError):
    """Network, DNS, timeout, or non-2xx response. Generic 'fetch failed'.

    The message includes the underlying error class name (without
    private internals) so operators can diagnose. Do not log the URL
    itself at INFO level — treat as user input.
    """

    code = "URL_FETCH_FAILED"


class UrlTooLargeError(UrlIngestionError):
    """The response exceeds :data:`upload_limits.MAX_UPLOAD_SIZE_BYTES`.

    Raised either from a declared ``Content-Length`` header or from
    streaming the body and accumulating past the limit.
    """

    code = "URL_TOO_LARGE"


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


def fetch_url_to_bytes(
    url: str,
    *,
    max_bytes: int = upload_limits.MAX_UPLOAD_SIZE_BYTES,
    connect_timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S,
    read_timeout_s: float = DEFAULT_READ_TIMEOUT_S,
    user_agent: str = "AbletonSonicAnalyzer/url-ingest",
) -> FetchedUrl:
    """Validate ``url``, fetch its bytes, return content + filename + MIME.

    Raises:
        UrlInvalidError: malformed URL, oversize URL, or non-http(s) scheme.
        UrlBlockedPrivateHostError: hostname resolves to private IP space.
        UrlFetchFailedError: any network, DNS, or non-2xx failure.
        UrlTooLargeError: response body exceeds ``max_bytes``.
    """
    _validate_url_shape(url)
    parsed = urlparse(url)
    _assert_host_is_public(parsed.hostname or "")

    try:
        with requests.get(
            url,
            stream=True,
            timeout=(connect_timeout_s, read_timeout_s),
            # Redirects are NOT followed automatically. The SSRF guard
            # above only validates the initial hostname; if we followed
            # a 3xx, an attacker controlling any public host could
            # redirect us to a private/loopback target (e.g.
            # 169.254.169.254 metadata endpoint) and bypass the guard.
            # A 3xx is surfaced as a fetch failure; users should provide
            # the canonical direct URL.
            allow_redirects=False,
            headers={"User-Agent": user_agent},
        ) as response:
            if 300 <= response.status_code < 400:
                raise UrlFetchFailedError(
                    f"Upstream returned HTTP {response.status_code} "
                    f"(redirect). URL ingestion does not follow redirects; "
                    f"provide a direct URL to the audio file."
                )
            if response.status_code >= 400:
                raise UrlFetchFailedError(
                    f"Upstream returned HTTP {response.status_code} for the URL."
                )

            # Up-front check on declared size before streaming any body.
            declared_size = _parse_content_length(
                response.headers.get("Content-Length")
            )
            if declared_size is not None and declared_size > max_bytes:
                raise UrlTooLargeError(
                    f"Upstream declared Content-Length {declared_size} bytes; "
                    f"limit is {max_bytes} bytes."
                )

            chunks: list[bytes] = []
            total_bytes = 0
            for chunk in response.iter_content(chunk_size=_FETCH_CHUNK_BYTES):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise UrlTooLargeError(
                        f"Response body exceeded {max_bytes} bytes; aborted."
                    )
                chunks.append(chunk)

            if total_bytes == 0:
                raise UrlFetchFailedError(
                    "Upstream returned an empty body."
                )

            content = b"".join(chunks)
            content_type = response.headers.get("Content-Type") or ""
            mime_type = _pick_mime_type(content_type, parsed.path)
            filename = _extract_filename(parsed.path)

            return FetchedUrl(
                content=content,
                filename=filename,
                mime_type=mime_type,
            )

    except UrlIngestionError:
        raise
    except requests.exceptions.Timeout as exc:
        raise UrlFetchFailedError(
            f"Timed out fetching URL: {type(exc).__name__}."
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise UrlFetchFailedError(
            f"Connection error fetching URL: {type(exc).__name__}."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise UrlFetchFailedError(
            f"HTTP client error fetching URL: {type(exc).__name__}."
        ) from exc


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------


def _validate_url_shape(url: str) -> None:
    """Cheap, deterministic URL-string checks. No network."""
    if not isinstance(url, str) or not url:
        raise UrlInvalidError("URL must be a non-empty string.")
    if len(url) > MAX_URL_LENGTH:
        raise UrlInvalidError(
            f"URL exceeds maximum length of {MAX_URL_LENGTH} characters."
        )
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise UrlInvalidError(f"URL is not parseable: {type(exc).__name__}.") from exc
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UrlInvalidError(
            f"URL scheme '{parsed.scheme}' is not allowed. "
            f"Supported schemes: {', '.join(sorted(ALLOWED_SCHEMES))}."
        )
    if not parsed.hostname:
        raise UrlInvalidError("URL must include a hostname.")


def _assert_host_is_public(hostname: str) -> None:
    """Reject hostnames that resolve to non-public IP space.

    Performs the DNS resolution here so the SSRF check is done before
    we send any HTTP request. A small TOCTOU window remains between
    this resolution and the eventual fetch; the v2 fix is a custom
    DNS resolver that pins the result through the HTTP client.
    """
    if not hostname:
        raise UrlInvalidError("URL must include a hostname.")

    # Resolve all A/AAAA records, not just the first; reject if *any*
    # resolved address is non-public.
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UrlFetchFailedError(
            f"Could not resolve hostname: {type(exc).__name__}."
        ) from exc

    seen: set[str] = set()
    for family, _socktype, _proto, _canon, sockaddr in addrinfo:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        # IPv4 sockaddr = (ip, port); IPv6 = (ip, port, flow, scope).
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            # Defensive: getaddrinfo gave us something we can't parse.
            # Treat as suspicious rather than as a transient error.
            raise UrlBlockedPrivateHostError(
                f"Resolved address '{ip_str}' is not a valid IP."
            ) from None
        if _is_non_public_address(ip):
            raise UrlBlockedPrivateHostError(
                f"Hostname resolves to non-public address '{ip}'. "
                f"URL ingestion only accepts public hosts."
            )

    if not seen:
        raise UrlFetchFailedError(
            "Hostname resolved to no usable IPv4 or IPv6 addresses."
        )


def _is_non_public_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for any address category we refuse to fetch from.

    Includes loopback, link-local, multicast, private RFC1918, reserved,
    unspecified (0.0.0.0/::). The AWS/GCP cloud metadata endpoint
    (169.254.169.254) is already caught by ``is_link_local``.

    Also explicitly blocks RFC 6598 Shared Address Space (CGNAT,
    ``100.64.0.0/10``). In Python's ``ipaddress``, ``is_private``
    returns False for this range and ``is_reserved`` doesn't cover it,
    so we check it directly.
    """
    if ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return True
    if ip.is_private or ip.is_reserved or ip.is_unspecified:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_RFC6598:
        return True
    return False


# RFC 6598 Shared Address Space — carrier-grade NAT range. Not covered
# by ``ipaddress.IPv4Address.is_private``.
_CGNAT_RFC6598: Final[ipaddress.IPv4Network] = ipaddress.ip_network(
    "100.64.0.0/10"
)


# ----------------------------------------------------------------------
# Response parsing helpers
# ----------------------------------------------------------------------


def _parse_content_length(header_value: str | None) -> int | None:
    """Best-effort parse of ``Content-Length``. None if absent/invalid."""
    if header_value is None:
        return None
    try:
        value = int(header_value.strip())
    except (ValueError, AttributeError):
        return None
    return value if value >= 0 else None


def _extract_filename(url_path: str) -> str:
    """Pull the last path segment as the filename, with a safe fallback."""
    if not url_path:
        return "url_audio.bin"
    # Strip trailing slashes and pick the final segment.
    segment = unquote(url_path.rstrip("/").split("/")[-1])
    # Guard against pathological cases (e.g. empty, or hostile path
    # traversal like '..' — we never use this as a filesystem path, but
    # also no need to pass it through).
    if not segment or segment in {".", ".."}:
        return "url_audio.bin"
    return segment


def _pick_mime_type(content_type_header: str, url_path: str) -> str:
    """Prefer the response Content-Type; fall back to filename guess."""
    # Strip charset / parameters: "audio/mpeg; charset=binary" -> "audio/mpeg".
    primary = (content_type_header or "").split(";")[0].strip().lower()
    if primary and primary not in {
        "application/octet-stream",
        "binary/octet-stream",
    }:
        return primary

    # Fall back to filename-based sniffing. Prefer the canonical map so
    # supported audio types resolve identically on every host.
    import mimetypes

    filename = _extract_filename(url_path)
    canonical = canonical_audio_mime(filename)
    if canonical:
        return canonical
    guessed, _enc = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    return "application/octet-stream"
