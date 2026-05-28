"""Convert ``transcriptionDetail.notes`` to a velocity-encoded pianoroll matrix.

Derived view — Phase 1's ``transcriptionDetail`` is the authority and is never
overridden here (invariant #1 from ``PURPOSE.md``). This module re-renders that
measurement as a 2D heatmap-ready ``uint8`` matrix using ``symusic`` for the
rasterization. The pianoroll cites the same notes and Phase 1 ``bpm`` /
``timeSignature`` the HTTP envelope already carries; chain of custody is
preserved (invariant #2).

Public surface:

1. :func:`render_pianoroll` — top-level entry point. Takes a
   ``transcriptionDetail`` dict + Phase 1 tempo/meter, returns a
   :class:`PianorollPayload` (mode, pitch axis bounds, frames matrix, metadata).
2. :func:`payload_to_json_dict` — JSON-friendly projection of the payload for the
   HTTP envelope. ``frames`` becomes a nested list. At ``tpq=4`` typical clips
   stay well under a megabyte, but larger matrices should be persisted through
   ``artifact_storage`` instead of inlining.
3. :func:`build_score` — exposed for tests and any future Score-level consumer
   (MIDI download, etc.). Tempo / time-signature events are emitted at ``t=0``
   to match Phase 1's static (per-track) analysis.

Shape contract (per the symusic tutorial):

- ``Score.pianoroll(modes=[m], pitch_range=[low, high], encode_velocity=True)``
  returns ``(num_modes, num_tracks, high - low, time_steps)`` uint8.
- We render a single mode + single track, so the result is sliced to
  ``(pitch_count, time_steps)`` before being handed back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from symusic import Note, Score, Tempo, TimeSignature, Track

PianorollMode = Literal["frame", "onset"]

# Default to the 88-key piano range (A0 = 21 inclusive, C8 = 108 inclusive ⇒
# upper bound 109 exclusive). Phase 1 transcription rarely emits notes outside
# this range; clamping keeps the matrix compact for transport.
DEFAULT_PITCH_LOW = 21
DEFAULT_PITCH_HIGH = 109

# tpq=4 is one row per 16th note at typical tempos. A 30 s clip at 120 BPM at
# tpq=4 fits in ~88 × 240 cells ≈ 21 KB uncompressed — small enough to inline.
# Lower values risk losing onsets close together; higher values blow up the
# matrix for marginal perceptual gain.
DEFAULT_TPQ = 4

# Internal score resolution before the resample. 480 tpq is the General MIDI
# convention and is more than enough precision for note times that arrive in
# seconds from the transcription backend.
SCORE_TPQ = 480

# Confidence ∈ [0, 1] is mapped onto MIDI velocity ∈ [VELOCITY_FLOOR, 127] so a
# zero-confidence note is still visible in the heatmap (otherwise it would be
# indistinguishable from a silent cell), and a maximally confident note maxes
# out at 127. The floor is also what callers can assert against in tests.
VELOCITY_FLOOR = 64
VELOCITY_RANGE = 127 - VELOCITY_FLOOR


@dataclass(frozen=True)
class PianorollPayload:
    """A flat 2D ``(pitch, time)`` velocity matrix + the axis metadata."""

    mode: PianorollMode
    pitch_low: int
    pitch_high: int
    ticks_per_quarter: int
    quarters_per_minute: float | None
    time_signature: tuple[int, int] | None
    note_count: int
    frames: np.ndarray  # shape: (pitch_high - pitch_low, time_steps), dtype=uint8


def _parse_time_signature(value: str | None) -> tuple[int, int] | None:
    """Parse a ``"4/4"`` / ``"3/4"`` string. Returns ``None`` on anything weird.

    Phase 1 emits ``timeSignature`` as a string like ``"4/4"`` (currently the
    assumed-4/4 fallback per ``JSON_SCHEMA.md``); we tolerate ``None`` and
    malformed inputs so this module remains useful when meter is uncertain.
    """
    if not isinstance(value, str):
        return None
    parts = value.strip().split("/")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _velocity_from_confidence(confidence: object) -> int:
    """Map ``[0, 1]`` confidence onto velocity ``[VELOCITY_FLOOR, 127]``.

    Out-of-range / non-numeric values clamp to the endpoints rather than raise
    — Phase 1 confidence floors at ``TRANSCRIPTION_CONFIDENCE_FLOOR = 0.05`` so
    the typical input is well-behaved, but a defensive clamp here means a
    surprise upstream emits a still-visible heatmap row.
    """
    try:
        value = float(confidence)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = 0.0
    clipped = max(0.0, min(1.0, value))
    return int(round(VELOCITY_FLOOR + VELOCITY_RANGE * clipped))


def build_score(
    transcription_detail: dict,
    *,
    bpm: float | None,
    time_signature: str | None,
) -> Score:
    """Build a ``symusic.Score`` (seconds time-unit) from a transcription dict.

    The Score carries Phase 1 tempo and meter at ``t=0`` so downstream consumers
    (e.g. a ``.mid`` download) inherit the citation. Notes that fail validation
    (missing keys, non-numeric times, out-of-range pitches, zero/negative
    duration) are silently skipped — the matrix is a derived view, so emitting
    an obviously corrupt cell is worse than dropping the note.
    """
    score = Score(SCORE_TPQ, ttype="Second")

    if bpm is not None and float(bpm) > 0:
        score.tempos.append(Tempo(time=0.0, qpm=float(bpm), ttype="Second"))

    parsed_signature = _parse_time_signature(time_signature)
    if parsed_signature is not None:
        numerator, denominator = parsed_signature
        score.time_signatures.append(
            TimeSignature(
                time=0.0,
                numerator=numerator,
                denominator=denominator,
                ttype="Second",
            )
        )

    track = Track(name="transcription", program=0, ttype="Second")
    notes = (
        transcription_detail.get("notes")
        if isinstance(transcription_detail, dict)
        else None
    )
    if isinstance(notes, list):
        for note in notes:
            if not isinstance(note, dict):
                continue
            try:
                pitch = int(note["pitchMidi"])
                onset = float(note["onsetSeconds"])
                duration = float(note["durationSeconds"])
            except (KeyError, TypeError, ValueError):
                continue
            if duration <= 0 or pitch < 0 or pitch > 127 or onset < 0:
                continue
            velocity = _velocity_from_confidence(note.get("confidence", 0.0))
            track.notes.append(
                Note(
                    time=onset,
                    duration=duration,
                    pitch=pitch,
                    velocity=velocity,
                    ttype="Second",
                )
            )
    score.tracks.append(track)
    return score


def render_pianoroll(
    transcription_detail: dict,
    *,
    bpm: float | None,
    time_signature: str | None = None,
    mode: PianorollMode = "frame",
    pitch_low: int = DEFAULT_PITCH_LOW,
    pitch_high: int = DEFAULT_PITCH_HIGH,
    tpq: int = DEFAULT_TPQ,
) -> PianorollPayload:
    """Render transcription notes as a ``(pitch, time)`` uint8 matrix.

    ``mode`` is one of ``"frame"`` (sustains visible) or ``"onset"`` (note
    starts only — useful for rhythmic visualization). ``pitch_low`` is
    inclusive, ``pitch_high`` is exclusive.

    Raises ``ValueError`` on out-of-band axis arguments rather than silently
    clamping — the route layer should validate query params before reaching
    here, and an invalid value is almost always a caller bug.
    """
    if pitch_low < 0 or pitch_high > 128 or pitch_low >= pitch_high:
        raise ValueError(
            f"invalid pitch range [{pitch_low}, {pitch_high}); "
            "must satisfy 0 <= pitch_low < pitch_high <= 128"
        )
    if tpq < 1:
        raise ValueError(f"tpq must be >= 1; got {tpq}")
    if mode not in ("frame", "onset"):
        raise ValueError(f"mode must be 'frame' or 'onset'; got {mode!r}")

    score = build_score(
        transcription_detail, bpm=bpm, time_signature=time_signature
    )
    resampled = score.resample(tpq=tpq, min_dur=1)
    matrix = resampled.pianoroll(
        modes=[mode],
        pitch_range=[pitch_low, pitch_high],
        encode_velocity=True,
    )
    # Slice to (pitch, time): single mode + single track in this module.
    frames = np.ascontiguousarray(matrix[0, 0], dtype=np.uint8)

    return PianorollPayload(
        mode=mode,
        pitch_low=pitch_low,
        pitch_high=pitch_high,
        ticks_per_quarter=tpq,
        quarters_per_minute=(
            float(bpm) if bpm is not None and float(bpm) > 0 else None
        ),
        time_signature=_parse_time_signature(time_signature),
        note_count=len(score.tracks[0].notes) if score.tracks else 0,
        frames=frames,
    )


def payload_to_json_dict(payload: PianorollPayload) -> dict:
    """Project the payload into a JSON-serializable dict for the HTTP envelope.

    ``frames`` becomes a nested list of ints (rows are pitches, columns are
    time steps). Keep the field names camelCase to match the rest of the
    ``phase1`` envelope — there is no conversion layer (see ``CLAUDE.md``
    tripwire #3).
    """
    return {
        "mode": payload.mode,
        "pitchLow": payload.pitch_low,
        "pitchHigh": payload.pitch_high,
        "ticksPerQuarter": payload.ticks_per_quarter,
        "quartersPerMinute": payload.quarters_per_minute,
        "timeSignature": (
            None
            if payload.time_signature is None
            else f"{payload.time_signature[0]}/{payload.time_signature[1]}"
        ),
        "noteCount": payload.note_count,
        "frames": payload.frames.tolist(),
    }
