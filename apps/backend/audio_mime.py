"""Canonical, host-independent audio MIME-type resolution."""

from __future__ import annotations

import os


CANONICAL_AUDIO_MIME_BY_EXT: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
}


def canonical_audio_mime(filename: str) -> str | None:
    """Return the canonical audio MIME type for ``filename``'s extension."""
    if not filename:
        return None
    _root, ext = os.path.splitext(filename.strip().lower())
    return CANONICAL_AUDIO_MIME_BY_EXT.get(ext)
