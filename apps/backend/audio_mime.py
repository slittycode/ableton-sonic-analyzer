"""Canonical, host-independent audio MIME-type resolution.

Python's stdlib :mod:`mimetypes` is host-dependent: macOS resolves ``.flac`` to
``audio/x-flac`` while Linux CI resolves it to ``audio/flac``. Relying on it
makes results vary by machine — that divergence failed the backend test gate on
macOS and could mislabel a FLAC handed to Gemini (which expects ``audio/flac``).

This module pins the filename -> MIME mapping for the audio formats ASA ingests,
mirroring the frontend contract in ``apps/ui/src/services/audioFile.ts`` so both
sides of the boundary agree and the result is identical on every OS. Keep the
two maps in sync if either changes.
"""

from __future__ import annotations

import os

# Mirror of AUDIO_EXTENSION_MIME_TYPES in apps/ui/src/services/audioFile.ts.
CANONICAL_AUDIO_MIME_BY_EXT: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
}


def canonical_audio_mime(filename: str) -> str | None:
    """Return the canonical audio MIME type for ``filename``'s extension.

    Host-independent: consults the explicit map above instead of the OS MIME
    database, so the same name resolves identically everywhere. Returns ``None``
    for extensions outside the audio map — callers choose their own fallback.
    """
    if not filename:
        return None
    _root, ext = os.path.splitext(filename.strip().lower())
    return CANONICAL_AUDIO_MIME_BY_EXT.get(ext)
