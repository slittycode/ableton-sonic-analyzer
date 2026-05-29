"""MT3 polyphonic transcription — additive, flag-gated Phase 1 extension.

This module wraps Magenta's MT3 (Multi-Task Multitrack Music Transcription)
checkpoint as an *optional* secondary transcription stage. It runs only when
the env var ``ASA_ENABLE_MT3`` is set to ``"1"`` (default off) and is purely
additive to Phase 1 — it does NOT override or refine Phase 1's
chord/key/beat/melody measurements (see PURPOSE.md invariant #1, "Phase 1
measurements are ground truth"). All MT3 output is namespaced under the new
top-level ``transcription`` key in the analyze.py JSON envelope; that key is
*absent* (not null) when the flag is off.

One-time setup (host machine, not CI):

    # Install the MT3 / t5x / JAX extra into the product venv. ASA uses
    # requirements-*.txt files in place of pyproject.toml extras (mirroring
    # the existing requirements-eval.txt convention). See CLAUDE.md.
    ./apps/backend/venv/bin/pip install -r apps/backend/requirements-mt3.txt

    # Download the MT3 checkpoint to the model cache (gitignored).
    mkdir -p apps/backend/models/mt3
    gsutil -m cp -r gs://mt3/checkpoints/mt3 apps/backend/models/mt3/

    # Enable for one analyze.py invocation.
    export ASA_ENABLE_MT3=1

Lazy-import contract
====================
All MT3 / t5x / JAX deps are imported *inside* ``transcribe()``. Module-level
imports stay limited to the stdlib + ``numpy`` (already a base ASA dep). This
keeps app startup free of multi-second JAX initialization when the flag is
off, and ensures the base ASA install runs unchanged. No other file in the
backend imports ``jax`` — that isolation is load-bearing for keeping JAX/PyTorch
ABI conflicts contained.

The PyTorch port question
=========================
The goal text says "PyTorch first if a maintained port exists". As of
2026-05, no production-stable PyTorch port of MT3 is published; community
ports are research-quality and unmaintained. This module therefore wraps the
canonical t5x/JAX inference path via ``mt3.inference_model.InferenceModel``.
If a maintained PyTorch port lands later, the swap is contained here.

Contract emitted to JSON
========================
``transcribe()`` returns an ``Mt3Result`` dataclass. The Python attributes
are snake_case (per Python convention); the JSON projection through
``Mt3Result.to_payload()`` is camelCase (per CLAUDE.md tripwire #3 — ASA's
JSON envelope is camelCase end-to-end with no conversion layer between
analyze.py and the frontend). The mapping is:

    Python attr        →  JSON key
    ─────────────────     ────────────
    version            →  "version"
    stems_used         →  "stemsUsed"
    tracks[*].midi_b64 →  "midiB64"
    tracks[*].note_count → "noteCount"
    tracks[*].pitch_range → "pitchRange"

Phase 2 reads the ``version`` string verbatim to know what produced the
notes — keep ``MT3_CHECKPOINT_ID`` in sync with the checkpoint actually
loaded.
"""

from __future__ import annotations

import base64
import os
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Iterable

# Pinned checkpoint identifier — surfaces in Mt3Result.version so Phase 2
# (and any downstream symbolic consumer) knows exactly what produced the notes.
# This is a best-effort identifier: Magenta does not publish a content-hash
# or release-tag for the checkpoint at gs://mt3/checkpoints/mt3 that we can
# verify automatically. Operators downloading newer revisions should append
# a date or hash they record at download time, e.g.
# ``"magenta-mt3-base@2026-05-28"``. The format is checked by tests, so
# the suffix is optional but its shape is constrained when present.
MT3_CHECKPOINT_ID = "magenta-mt3-base"
MT3_MODULE_VERSION = "0.1.0"

# Default cache location for MT3 weights — gitignored via apps/backend/models/.
# Resolved relative to this module so it survives different cwd conventions.
DEFAULT_MT3_CHECKPOINT_DIR = (
    Path(__file__).resolve().parent / "models" / "mt3"
)

# Stem filenames Demucs writes (see analyze_audio_io.separate_stems). MT3 runs
# best on instrumental stems; we skip drums by default because MT3's drum head
# is weaker than purpose-built drum trackers and Phase 1 already covers drums
# in detail (snareDetail, hihatDetail, kickDetail).
_DEFAULT_STEM_INSTRUMENTS = ("bass", "other", "vocals")


class Mt3NotAvailableError(RuntimeError):
    """Raised when the MT3 extra is not installed or the checkpoint is missing.

    Callers in ``analyze.py`` catch this (alongside ``Exception``) and emit a
    ``[warn]`` line to stderr — MT3 failure must never block Phase 1 JSON.
    """


@dataclass
class Mt3Track:
    """A single per-instrument MIDI track produced by MT3."""

    instrument: str
    midi_b64: str
    note_count: int
    pitch_range: tuple[int, int]


@dataclass
class Mt3Result:
    """Top-level MT3 result for one ``transcribe()`` call."""

    version: str
    stems_used: list[str]
    tracks: list[Mt3Track] = field(default_factory=list)

    def to_payload(self) -> dict:
        """camelCase JSON projection (the analyze.py envelope is camelCase end-to-end)."""
        return {
            "version": self.version,
            "stemsUsed": list(self.stems_used),
            "tracks": [
                {
                    "instrument": track.instrument,
                    "midiB64": track.midi_b64,
                    "noteCount": int(track.note_count),
                    "pitchRange": [
                        int(track.pitch_range[0]),
                        int(track.pitch_range[1]),
                    ],
                }
                for track in self.tracks
            ],
        }


def _resolve_checkpoint_dir() -> Path:
    """Honor ``ASA_MT3_CHECKPOINT_DIR`` for advanced users; otherwise default."""
    override = os.getenv("ASA_MT3_CHECKPOINT_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_MT3_CHECKPOINT_DIR


def discover_stems_dir(stems: dict | None) -> Path | None:
    """Recover the Demucs stems directory from an analyze.py ``stems`` dict.

    ``analyze_audio_io.separate_stems()`` returns a mapping like
    ``{"drums": "/path/to/.../drums.wav", "bass": "...", ...}`` — every stem
    file is written into the same parent directory. This helper recovers
    that parent so ``transcribe()`` can discover per-stem files by canonical
    filename via :func:`_resolve_sources`.

    Lives here (not in analyze.py) so the gate in analyze.py can stay
    trivial and unit-testable behind a single import. Returns ``None`` when
    ``stems`` is missing, empty, or contains no on-disk paths — callers
    then fall back to running MT3 on the full mix.
    """
    if not isinstance(stems, dict):
        return None
    for source_path in stems.values():
        if isinstance(source_path, str) and os.path.isfile(source_path):
            return Path(source_path).parent
    return None


def _resolve_sources(
    audio_path: Path,
    stems_dir: Path | None,
    *,
    instruments: Iterable[str] = _DEFAULT_STEM_INSTRUMENTS,
) -> list[tuple[str, Path]]:
    """Stems-first, full-mix fallback.

    Discovers per-stem files inside ``stems_dir`` by the canonical Demucs
    filenames (``bass.wav``, ``other.wav``, ``vocals.wav``). If ``stems_dir``
    is missing or contains none of the expected files, falls back to running
    MT3 once on the full mix (allowed by the goal's Constraints).
    """
    sources: list[tuple[str, Path]] = []
    if stems_dir is not None:
        stems_dir = Path(stems_dir)
        if stems_dir.is_dir():
            for stem_name in instruments:
                for suffix in (".wav", ".flac"):
                    candidate = stems_dir / f"{stem_name}{suffix}"
                    if candidate.is_file():
                        sources.append((stem_name, candidate))
                        break
    if not sources:
        return [("full_mix", Path(audio_path))]
    return sources


def transcribe(audio_path: Path, *, stems_dir: Path | None) -> Mt3Result:
    """Run MT3 transcription against ``audio_path``, stems-first when possible.

    Args:
        audio_path: Absolute path to the source audio (full mix).
        stems_dir: Optional directory containing Demucs stems. When present,
            MT3 runs once per discovered stem and emits one track per stem;
            otherwise it falls back to a single full-mix pass.

    Returns:
        ``Mt3Result`` with the pinned version string, the list of stem names
        actually transcribed, and one ``Mt3Track`` per stem (each carrying a
        base64-encoded MIDI blob).

    Raises:
        Mt3NotAvailableError: when the ``[mt3]`` extra isn't installed or the
            checkpoint directory is missing. Callers wrap this so the failure
            surfaces as a ``[warn]`` rather than blocking Phase 1 JSON.
        FileNotFoundError: when ``audio_path`` doesn't exist on disk.
    """
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise FileNotFoundError(f"MT3 audio path missing: {audio_path}")

    # Lazy import — keeps JAX/t5x out of the import graph until MT3 is
    # explicitly requested. Any ImportError surfaces as Mt3NotAvailableError
    # so analyze.py's outer try/except can convert it to a [warn] line
    # without leaking implementation detail.
    try:
        import librosa  # already a base ASA dep, but kept inside the try
        import note_seq
        from mt3 import inference_model  # type: ignore
    except ImportError as exc:
        raise Mt3NotAvailableError(
            "MT3 backend not installed. Install via: "
            "./apps/backend/venv/bin/pip install -r apps/backend/requirements-mt3.txt "
            "(see apps/backend/mt3_transcription.py module docstring for the "
            "weight-download command)."
        ) from exc

    checkpoint_dir = _resolve_checkpoint_dir()
    if not checkpoint_dir.is_dir():
        raise Mt3NotAvailableError(
            f"MT3 checkpoint missing at {checkpoint_dir}. Download via: "
            f"gsutil -m cp -r gs://mt3/checkpoints/mt3 {checkpoint_dir.parent}/"
        )

    sources = _resolve_sources(audio_path, stems_dir)
    full_mix_fallback = (
        len(sources) == 1 and sources[0][0] == "full_mix"
    )
    if full_mix_fallback:
        print(
            "[warn] MT3: running on full mix — Demucs stems not found at "
            f"{stems_dir}; per-instrument separation will be weaker.",
            file=sys.stderr,
        )

    # Build the inferencer once and reuse across stems — model load is the
    # expensive step (~5-15s, multi-GB weights). MT3's InferenceModel handles
    # the gin config + checkpoint restore internally.
    try:
        inferencer = inference_model.InferenceModel(
            checkpoint_path=str(checkpoint_dir),
            model_type="mt3",
        )
    except Exception as exc:  # noqa: BLE001 - surface as a typed init failure
        raise Mt3NotAvailableError(
            f"Failed to initialize MT3 InferenceModel from {checkpoint_dir}: {exc}"
        ) from exc

    tracks: list[Mt3Track] = []
    stems_used: list[str] = []

    for stem_name, source_path in sources:
        try:
            # MT3 was trained on 16 kHz mono audio. librosa handles resample +
            # mono mixdown deterministically.
            audio, _sr = librosa.load(str(source_path), sr=16000, mono=True)

            note_sequence = inferencer(audio)

            midi_buffer = BytesIO()
            note_seq.note_sequence_to_pretty_midi(note_sequence).write(midi_buffer)
            midi_b64 = base64.b64encode(midi_buffer.getvalue()).decode("ascii")

            pitches = [int(note.pitch) for note in note_sequence.notes]
            pitch_range = (
                (min(pitches), max(pitches)) if pitches else (0, 0)
            )

            tracks.append(
                Mt3Track(
                    instrument=stem_name,
                    midi_b64=midi_b64,
                    note_count=len(note_sequence.notes),
                    pitch_range=pitch_range,
                )
            )
            stems_used.append(stem_name)
        except Exception as exc:  # noqa: BLE001 - per-stem failure is non-fatal
            print(
                f"[warn] MT3 stem {stem_name!r} failed: {exc}",
                file=sys.stderr,
            )
            # Continue to the next stem; partial results are valid output.

    return Mt3Result(
        version=f"mt3-py-{MT3_MODULE_VERSION}+{MT3_CHECKPOINT_ID}",
        stems_used=stems_used,
        tracks=tracks,
    )


__all__ = [
    "DEFAULT_MT3_CHECKPOINT_DIR",
    "MT3_CHECKPOINT_ID",
    "MT3_MODULE_VERSION",
    "Mt3NotAvailableError",
    "Mt3Result",
    "Mt3Track",
    "discover_stems_dir",
    "transcribe",
]
