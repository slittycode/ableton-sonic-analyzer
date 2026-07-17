"""Phase 1 stem-separation backend seam (Demucs).

ASA's authoritative separation is torchaudio Hybrid Demucs
(``analyze_audio_io.separate_stems``). This module is the thin entry point
called from ``analyze.py``'s three separation sites (measurement ``--separate``,
``--pitch-note-only``, ``--mt3-only``).

The former MSST / BS-RoFormer optional path was a research-only licence gate
with no recorded win over Demucs and was removed in the 2026-07 trust diet
(``plans/trust-diet-2026-07.md``, Wave 2 B2). The licence pre-registration
record remains at ``incorporations/msst-separation-licence-gate-2026-06-05.md``.
Restore the old path from tag ``archive/pre-trust-diet-2026-07`` if needed.

``ASA_SEPARATION_BACKEND`` is accepted for back-compat but only ``demucs`` (or
unset / unknown) is supported — unknown values fall back to Demucs.
"""

from __future__ import annotations

import os

from analyze_audio_io import separate_stems


def separation_backend_name() -> str:
    """Resolve the selected separation backend. Always demucs after the MSST cut."""
    name = (os.environ.get("ASA_SEPARATION_BACKEND") or "demucs").strip().lower()
    return name if name == "demucs" else "demucs"


def separate_stems_backend(audio_path: str, output_dir: str | None = None):
    """Run Demucs separation, returning ``{stem_name: wav_path}``.

    The return shape is identical to ``separate_stems`` so every downstream
    consumer — the ``stemAnalysis`` overlay, pitch/note translation, MT3, and
    ``cleanup_stems`` — is byte-compatible.
    """
    return separate_stems(audio_path, output_dir=output_dir)
