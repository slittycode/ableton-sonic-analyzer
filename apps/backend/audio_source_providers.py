"""Provider adapters for asynchronous link-based audio preparation.

The adapters in this module do not create analysis runs.  They materialize one
bounded, validated audio file plus safe display metadata.  ``server.py`` hands
that result to :class:`analysis_runtime.AnalysisRuntime`, which owns persistence
and the canonical run contract.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final
from urllib.parse import urljoin, urlsplit

import requests
import urllib3

import upload_limits
from analyze_estimate import get_audio_duration_seconds
from audio_mime import canonical_audio_mime
from runtime_profile import resolve_runtime_profile
from url_ingest import (
    UrlBlockedPrivateHostError,
    UrlFetchFailedError,
    UrlInvalidError,
    UrlTooLargeError,
    _extract_filename,
    _is_non_public_address,
    _validate_url_shape,
)


MAX_TRACK_DURATION_SECONDS: Final[float] = 15 * 60
MAX_REDIRECTS: Final[int] = 5
CONNECT_TIMEOUT_SECONDS: Final[float] = 30.0
READ_TIMEOUT_SECONDS: Final[float] = 60.0
YOUTUBE_TIMEOUT_SECONDS: Final[float] = 10 * 60
SAFE_AUDIO_MIME_TYPES: Final[dict[str, str]] = {
    "audio/mpeg": "audio/mpeg",
    "audio/mp3": "audio/mpeg",
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "audio/flac": "audio/flac",
    "audio/x-flac": "audio/flac",
    "audio/aiff": "audio/aiff",
    "audio/x-aiff": "audio/aiff",
}


class AudioSourceError(Exception):
    code = "AUDIO_SOURCE_FAILED"
    retryable = False


class AudioSourceUnsupportedError(AudioSourceError):
    code = "AUDIO_SOURCE_UNSUPPORTED"


class AudioSourceDisabledError(AudioSourceError):
    code = "AUDIO_SOURCE_DISABLED"


class AudioSourcePlaylistError(AudioSourceError):
    code = "AUDIO_SOURCE_PLAYLIST_UNSUPPORTED"


class AudioSourceDurationError(AudioSourceError):
    code = "AUDIO_SOURCE_TOO_LONG"


class AudioSourceInvalidAudioError(AudioSourceError):
    code = "AUDIO_SOURCE_INVALID_AUDIO"


class AudioSourceInterruptedError(AudioSourceError):
    code = "AUDIO_SOURCE_INTERRUPTED"


class AudioSourceFetchError(AudioSourceError):
    code = "AUDIO_SOURCE_FETCH_FAILED"
    retryable = True


@dataclass(frozen=True)
class PreparedAudioSource:
    provider: str
    path: str
    filename: str
    mime_type: str
    duration_seconds: float
    title: str | None = None
    creator: str | None = None
    attribution_url: str | None = None
    experimental: bool = False

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "title": self.title,
            "creator": self.creator,
            "durationSeconds": round(self.duration_seconds, 3),
            "attributionUrl": _safe_public_url(self.attribution_url),
            "experimental": self.experimental,
            "filename": self.filename,
            "mimeType": self.mime_type,
        }


CancelCheck = Callable[[], bool]
StatusUpdate = Callable[[str], None]


def _safe_public_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        _normalized_hostname(value)
    except (UrlInvalidError, UnicodeError):
        return None
    return value


def _normalized_hostname(url: str) -> str:
    _validate_url_shape(url)
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise UrlInvalidError("The link is not a valid URL.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UrlInvalidError("Only public HTTP and HTTPS links are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise UrlInvalidError("Links containing a username or password are not supported.")
    return parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")


def _matches_domain(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith(f".{domain}")


def classify_audio_source(url: str) -> str:
    hostname = _normalized_hostname(url)
    if _matches_domain(hostname, "soundcloud.com"):
        return "soundcloud"
    if hostname in {"youtu.be", "youtube.com"} or _matches_domain(hostname, "youtube.com"):
        return "youtube"
    if _matches_domain(hostname, "bandcamp.com"):
        return "bandcamp"
    if _matches_domain(hostname, "spotify.com"):
        return "spotify"
    if _matches_domain(hostname, "music.apple.com"):
        return "apple_music"
    return "direct"


def _flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def audio_source_capabilities() -> dict[str, Any]:
    soundcloud_missing = [
        name
        for name in ("SOUNDCLOUD_CLIENT_ID", "SOUNDCLOUD_CLIENT_SECRET")
        if not os.getenv(name, "").strip()
    ]
    if not _flag_enabled("ASA_ENABLE_SOUNDCLOUD_LINKS"):
        soundcloud_missing.append("ASA_ENABLE_SOUNDCLOUD_LINKS")
    soundcloud_enabled = not soundcloud_missing
    youtube_missing = [name for name in ("yt-dlp", "ffmpeg") if shutil.which(name) is None]
    if not _flag_enabled("ASA_ENABLE_YOUTUBE_LINKS"):
        youtube_missing.append("ASA_ENABLE_YOUTUBE_LINKS")
    if resolve_runtime_profile() != "local":
        youtube_missing.append("Available only in local mode")
    youtube_enabled = (
        resolve_runtime_profile() == "local"
        and not youtube_missing
    )
    return {
        "limits": {
            "maxBytes": upload_limits.MAX_UPLOAD_SIZE_BYTES,
            "maxDurationSeconds": int(MAX_TRACK_DURATION_SECONDS),
            "maxActiveIntakes": 4,
        },
        "providers": [
            {
                "id": "direct",
                "enabled": True,
                "experimental": False,
                "environments": ["local", "hosted"],
                "missingSetup": [],
            },
            {
                "id": "soundcloud",
                "enabled": soundcloud_enabled,
                "experimental": False,
                "environments": ["local", "hosted"],
                "missingSetup": soundcloud_missing,
            },
            {
                "id": "youtube",
                "enabled": youtube_enabled,
                "experimental": True,
                "environments": ["local"],
                "missingSetup": youtube_missing,
            },
            *[
                {
                    "id": provider,
                    "enabled": False,
                    "experimental": False,
                    "environments": [],
                    "missingSetup": ["Provider is recognised but not supported."],
                }
                for provider in ("bandcamp", "spotify", "apple_music")
            ],
        ],
    }


def _validate_prepared_audio(path: Path) -> float:
    duration = get_audio_duration_seconds(str(path))
    if duration is None:
        raise AudioSourceInvalidAudioError(
            "The downloaded file could not be decoded as supported audio."
        )
    if duration > MAX_TRACK_DURATION_SECONDS:
        raise AudioSourceDurationError(
            f"The track is longer than the {int(MAX_TRACK_DURATION_SECONDS // 60)} minute limit."
        )
    return duration


def _resolve_public_ip(hostname: str) -> str:
    try:
        addrinfo = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlFetchFailedError(
            f"Could not resolve hostname: {type(exc).__name__}."
        ) from exc
    addresses: list[str] = []
    for family, _socktype, _proto, _canon, sockaddr in addrinfo:
        if family in {socket.AF_INET, socket.AF_INET6}:
            ip_text = str(sockaddr[0])
            try:
                ip = ipaddress.ip_address(ip_text)
            except ValueError as exc:
                raise UrlBlockedPrivateHostError("The hostname resolved to an invalid address.") from exc
            if _is_non_public_address(ip):
                raise UrlBlockedPrivateHostError(
                    "The hostname resolves to a private or otherwise non-public address."
                )
            if ip_text not in addresses:
                addresses.append(ip_text)
    if addresses:
        # The exact checked address is passed to urllib3.  No second DNS lookup
        # occurs between validation and connection, closing the usual rebinding gap.
        return addresses[0]
    raise UrlFetchFailedError("The hostname resolved to no usable address.")


def _request_to_validated_ip(url: str) -> tuple[urllib3.HTTPResponse, Any]:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    ip = _resolve_public_ip(hostname)
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UrlInvalidError("The link contains an invalid port.") from exc
    host_header = hostname
    if parsed.port and parsed.port not in {80, 443}:
        host_header = f"{hostname}:{parsed.port}"
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    timeout = urllib3.Timeout(connect=CONNECT_TIMEOUT_SECONDS, read=READ_TIMEOUT_SECONDS)
    if parsed.scheme == "https":
        pool: Any = urllib3.HTTPSConnectionPool(
            ip,
            port=port,
            assert_hostname=hostname,
            server_hostname=hostname,
            cert_reqs="CERT_REQUIRED",
            timeout=timeout,
            maxsize=1,
        )
    else:
        pool = urllib3.HTTPConnectionPool(ip, port=port, timeout=timeout, maxsize=1)
    response = pool.urlopen(
        "GET",
        path,
        headers={"Host": host_header, "User-Agent": "AbletonSonicAnalyzer/audio-intake"},
        redirect=False,
        preload_content=False,
        retries=False,
    )
    return response, pool


def download_direct_audio(
    url: str,
    destination_dir: Path,
    *,
    should_cancel: CancelCheck,
) -> tuple[Path, str, str]:
    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        if should_cancel():
            raise AudioSourceInterruptedError("Link preparation was stopped.")
        _normalized_hostname(current_url)
        response = None
        pool = None
        try:
            response, pool = _request_to_validated_ip(current_url)
            if 300 <= response.status < 400:
                location = response.headers.get("Location")
                if not location:
                    raise AudioSourceFetchError("The source returned an invalid redirect.")
                if redirect_count >= MAX_REDIRECTS:
                    raise AudioSourceFetchError("The source redirected too many times.")
                current_url = urljoin(current_url, location)
                continue
            if response.status >= 400:
                raise AudioSourceFetchError(
                    f"The source returned HTTP {response.status}."
                )
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > upload_limits.MAX_UPLOAD_SIZE_BYTES:
                raise UrlTooLargeError("The linked audio exceeds the 100 MiB limit.")
            parsed = urlsplit(current_url)
            filename = _extract_filename(parsed.path)
            suffix = Path(filename).suffix or ".bin"
            destination = destination_dir / f"source{suffix}"
            total = 0
            with destination.open("wb") as output:
                for chunk in response.stream(64 * 1024):
                    if should_cancel():
                        raise AudioSourceInterruptedError("Link preparation was stopped.")
                    total += len(chunk)
                    if total > upload_limits.MAX_UPLOAD_SIZE_BYTES:
                        raise UrlTooLargeError("The linked audio exceeds the 100 MiB limit.")
                    output.write(chunk)
            if total == 0:
                raise AudioSourceFetchError("The source returned an empty file.")
            content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip()
            mime_type = SAFE_AUDIO_MIME_TYPES.get(
                content_type.lower(),
                canonical_audio_mime(filename) or "application/octet-stream",
            )
            return destination, filename, mime_type
        except (UrlInvalidError, UrlBlockedPrivateHostError, UrlTooLargeError, AudioSourceError):
            raise
        except (urllib3.exceptions.HTTPError, OSError) as exc:
            raise AudioSourceFetchError(
                f"The audio source could not be downloaded ({type(exc).__name__})."
            ) from exc
        finally:
            if response is not None:
                response.release_conn()
            if pool is not None:
                pool.close()
    raise AudioSourceFetchError("The source redirected too many times.")


class DirectAudioProvider:
    id = "direct"

    def prepare(
        self,
        url: str,
        destination_dir: Path,
        *,
        should_cancel: CancelCheck,
        update_status: StatusUpdate,
    ) -> PreparedAudioSource:
        path, filename, mime_type = download_direct_audio(
            url,
            destination_dir,
            should_cancel=should_cancel,
        )
        update_status("normalizing")
        duration = _validate_prepared_audio(path)
        return PreparedAudioSource(
            provider=self.id,
            path=str(path),
            filename=filename,
            mime_type=mime_type,
            duration_seconds=duration,
            title=Path(filename).stem or filename,
        )


_SOUNDCLOUD_TOKEN_LOCK = threading.Lock()
_SOUNDCLOUD_TOKEN: tuple[str, float] | None = None


def _soundcloud_access_token() -> str:
    global _SOUNDCLOUD_TOKEN
    client_id = os.getenv("SOUNDCLOUD_CLIENT_ID", "").strip()
    client_secret = os.getenv("SOUNDCLOUD_CLIENT_SECRET", "").strip()
    if not _flag_enabled("ASA_ENABLE_SOUNDCLOUD_LINKS") or not client_id or not client_secret:
        raise AudioSourceDisabledError(
            "SoundCloud link analysis is not configured on this server."
        )
    with _SOUNDCLOUD_TOKEN_LOCK:
        if _SOUNDCLOUD_TOKEN and _SOUNDCLOUD_TOKEN[1] > time.monotonic() + 30:
            return _SOUNDCLOUD_TOKEN[0]
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        response = requests.post(
            "https://secure.soundcloud.com/oauth/token",
            headers={"Authorization": f"Basic {basic}"},
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise AudioSourceFetchError("SoundCloud authentication failed.")
        payload = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AudioSourceFetchError("SoundCloud returned an invalid access token.")
        expires_in = float(payload.get("expires_in") or 3600)
        _SOUNDCLOUD_TOKEN = (token, time.monotonic() + max(60, expires_in))
        return token


def _invalidate_soundcloud_token(token: str) -> None:
    global _SOUNDCLOUD_TOKEN
    with _SOUNDCLOUD_TOKEN_LOCK:
        if _SOUNDCLOUD_TOKEN and _SOUNDCLOUD_TOKEN[0] == token:
            _SOUNDCLOUD_TOKEN = None


class SoundCloudProvider:
    id = "soundcloud"

    def prepare(
        self,
        url: str,
        destination_dir: Path,
        *,
        should_cancel: CancelCheck,
        update_status: StatusUpdate,
    ) -> PreparedAudioSource:
        if classify_audio_source(url) != self.id:
            raise AudioSourceUnsupportedError("That link is not a SoundCloud track URL.")
        token = _soundcloud_access_token()
        headers = {"Authorization": f"OAuth {token}", "Accept": "application/json"}
        response = requests.get(
            "https://api.soundcloud.com/resolve",
            params={"url": url},
            headers=headers,
            timeout=30,
        )
        if response.status_code == 401:
            _invalidate_soundcloud_token(token)
            token = _soundcloud_access_token()
            headers = {"Authorization": f"OAuth {token}", "Accept": "application/json"}
            response = requests.get(
                "https://api.soundcloud.com/resolve",
                params={"url": url},
                headers=headers,
                timeout=30,
            )
        if response.status_code >= 400:
            raise AudioSourceFetchError("SoundCloud could not resolve that link.")
        track = response.json()
        if track.get("kind") != "track":
            raise AudioSourcePlaylistError("SoundCloud playlists and sets are not supported.")
        if track.get("access") != "playable":
            raise AudioSourceUnsupportedError(
                "This SoundCloud track is private, blocked, paywalled, or preview-only."
            )
        duration = float(track.get("duration") or 0) / 1000
        if duration <= 0 or duration > MAX_TRACK_DURATION_SECONDS:
            raise AudioSourceDurationError("The SoundCloud track exceeds the 15 minute limit.")
        track_id = track.get("id")
        if track_id is None:
            raise AudioSourceFetchError("SoundCloud returned an invalid track record.")
        stream_response = requests.get(
            f"https://api.soundcloud.com/tracks/{track_id}/stream",
            headers=headers,
            allow_redirects=False,
            timeout=30,
        )
        stream_url = stream_response.headers.get("Location")
        if not stream_url:
            try:
                stream_url = stream_response.json().get("url")
            except (ValueError, AttributeError):
                stream_url = None
        if not isinstance(stream_url, str) or not stream_url:
            raise AudioSourceFetchError("SoundCloud did not provide a playable stream.")
        path, filename, mime_type = download_direct_audio(
            stream_url,
            destination_dir,
            should_cancel=should_cancel,
        )
        update_status("normalizing")
        measured_duration = _validate_prepared_audio(path)
        user = track.get("user") if isinstance(track.get("user"), dict) else {}
        return PreparedAudioSource(
            provider=self.id,
            path=str(path),
            filename=filename,
            mime_type=mime_type,
            duration_seconds=measured_duration,
            title=str(track.get("title") or Path(filename).stem),
            creator=str(user.get("username") or "") or None,
            attribution_url=str(track.get("permalink_url") or "") or None,
        )


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()


def _run_cancellable_command(
    command: list[str],
    *,
    should_cancel: CancelCheck,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    started = time.monotonic()
    while process.poll() is None:
        if should_cancel():
            _terminate_process_group(process)
            raise AudioSourceInterruptedError("YouTube preparation was stopped.")
        if time.monotonic() - started > timeout_seconds:
            _terminate_process_group(process)
            raise AudioSourceFetchError("YouTube preparation timed out.")
        time.sleep(0.2)
    stdout, stderr = process.communicate()
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


class YouTubeExperimentalProvider:
    id = "youtube"

    def _require_enabled(self) -> tuple[str, str]:
        if resolve_runtime_profile() != "local":
            raise AudioSourceDisabledError("YouTube link analysis is available only in local mode.")
        if not _flag_enabled("ASA_ENABLE_YOUTUBE_LINKS"):
            raise AudioSourceDisabledError("Experimental YouTube link analysis is disabled.")
        yt_dlp = shutil.which("yt-dlp")
        ffmpeg = shutil.which("ffmpeg")
        if not yt_dlp or not ffmpeg:
            raise AudioSourceDisabledError("YouTube analysis requires yt-dlp and FFmpeg.")
        return yt_dlp, ffmpeg

    def prepare(
        self,
        url: str,
        destination_dir: Path,
        *,
        should_cancel: CancelCheck,
        update_status: StatusUpdate,
    ) -> PreparedAudioSource:
        if classify_audio_source(url) != self.id:
            raise AudioSourceUnsupportedError("That link is not a YouTube URL.")
        yt_dlp, ffmpeg = self._require_enabled()
        inspect_command = [
            yt_dlp,
            "--ignore-config",
            "--no-playlist",
            "--skip-download",
            "--dump-single-json",
            "--no-warnings",
            "--",
            url,
        ]
        inspected = _run_cancellable_command(
            inspect_command,
            should_cancel=should_cancel,
            timeout_seconds=120,
        )
        if inspected.returncode != 0:
            raise AudioSourceFetchError("YouTube could not inspect that link.")
        try:
            metadata = json.loads(inspected.stdout)
        except json.JSONDecodeError as exc:
            raise AudioSourceFetchError("YouTube returned invalid metadata.") from exc
        if metadata.get("_type") in {"playlist", "multi_video"} or metadata.get("playlist_count"):
            raise AudioSourcePlaylistError("YouTube playlists are not supported.")
        if metadata.get("is_live") or metadata.get("live_status") in {"is_live", "is_upcoming"}:
            raise AudioSourceUnsupportedError("YouTube livestreams are not supported.")
        duration = float(metadata.get("duration") or 0)
        if duration <= 0 or duration > MAX_TRACK_DURATION_SECONDS:
            raise AudioSourceDurationError("The YouTube track exceeds the 15 minute limit.")
        update_status("normalizing")
        output_template = str(destination_dir / "source.%(ext)s")
        download_command = [
            yt_dlp,
            "--ignore-config",
            "--no-playlist",
            "--no-warnings",
            "--max-filesize",
            str(upload_limits.MAX_UPLOAD_SIZE_BYTES),
            "--ffmpeg-location",
            ffmpeg,
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--output",
            output_template,
            "--",
            url,
        ]
        downloaded = _run_cancellable_command(
            download_command,
            should_cancel=should_cancel,
            timeout_seconds=YOUTUBE_TIMEOUT_SECONDS,
        )
        if downloaded.returncode != 0:
            raise AudioSourceFetchError("YouTube audio preparation failed.")
        candidates = list(destination_dir.glob("source.*"))
        path = next((candidate for candidate in candidates if candidate.suffix == ".mp3"), None)
        if path is None or not path.is_file():
            raise AudioSourceFetchError("YouTube did not produce an audio file.")
        if path.stat().st_size > upload_limits.MAX_UPLOAD_SIZE_BYTES:
            raise UrlTooLargeError("The prepared YouTube audio exceeds 100 MiB.")
        measured_duration = _validate_prepared_audio(path)
        video_id = str(metadata.get("id") or "")
        return PreparedAudioSource(
            provider=self.id,
            path=str(path),
            filename=f"{video_id or 'youtube-audio'}.mp3",
            mime_type="audio/mpeg",
            duration_seconds=measured_duration,
            title=str(metadata.get("title") or "YouTube audio"),
            creator=str(metadata.get("uploader") or metadata.get("channel") or "") or None,
            attribution_url=f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
            experimental=True,
        )


def provider_for(provider_id: str) -> Any:
    if provider_id == "direct":
        return DirectAudioProvider()
    if provider_id == "soundcloud":
        return SoundCloudProvider()
    if provider_id == "youtube":
        return YouTubeExperimentalProvider()
    if provider_id in {"bandcamp", "spotify", "apple_music"}:
        label = provider_id.replace("_", " ").title()
        raise AudioSourceUnsupportedError(f"{label} links are recognised but not supported yet.")
    raise AudioSourceUnsupportedError("That music-link provider is not supported.")
