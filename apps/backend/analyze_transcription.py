"""Transcription pipeline — pitch/note extraction from audio stems."""

import heapq
import os
import sys
from collections import Counter
from typing import Protocol

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None

from dsp_utils import midi_to_note_name, _normalize_confidence
from analyze_audio_io import load_mono


TRANSCRIPTION_CONFIDENCE_FLOOR = 0.05
TRANSCRIPTION_NOTE_CAP = 500
FULL_MIX_TRANSCRIPTION_NOTE_CAP = 200
TRANSCRIPTION_MIN_ACTIVE_WINDOW_SECONDS = 0.1
TRANSCRIPTION_NEAR_DUPLICATE_SECONDS = 0.03
DEFAULT_TRANSCRIPTION_BACKEND = "torchcrepe-viterbi"
SUPPORTED_TRANSCRIPTION_BACKEND_IDS = {
    "auto": DEFAULT_TRANSCRIPTION_BACKEND,
    "default": DEFAULT_TRANSCRIPTION_BACKEND,
    "": DEFAULT_TRANSCRIPTION_BACKEND,
    "torchcrepe": "torchcrepe-viterbi",
    "torchcrepe-viterbi": "torchcrepe-viterbi",
}

from typing import Protocol, runtime_checkable


def resolve_transcription_backend_id(requested_backend: str | None) -> str:
    normalized = str(requested_backend or "").strip().lower()
    if normalized not in SUPPORTED_TRANSCRIPTION_BACKEND_IDS:
        raise ValueError(f"Unsupported transcription backend '{normalized}'.")
    return SUPPORTED_TRANSCRIPTION_BACKEND_IDS[normalized]


@runtime_checkable
class TranscriptionBackend(Protocol):
    """Interface for pluggable pitch/note translation backends."""

    name: str  # written to transcriptionDetail.transcriptionMethod in output

    def transcribe(
        self,
        audio_path: str,
        stem_paths: dict | None = None,
        emit_progress_markers: bool = False,
    ) -> dict:
        """Return a transcriptionDetail dict.

        Return shape must match the existing transcriptionDetail contract
        documented in JSON_SCHEMA.md. On failure, return {"transcriptionDetail": None}.
        """
        ...


def _transcription_source_paths(
    audio_path: str, stem_paths: dict | None = None
) -> list[tuple[str, str]]:
    sources = []
    if isinstance(stem_paths, dict):
        for stem_name in ("bass", "other"):
            source_path = stem_paths.get(stem_name)
            if isinstance(source_path, str) and os.path.isfile(source_path):
                sources.append((stem_name, source_path))
    if len(sources) == 0:
        return [("full_mix", audio_path)]
    return sources


def _transcription_active_end(note: dict) -> float:
    onset = float(note.get("onsetSeconds", 0.0))
    duration = float(note.get("durationSeconds", 0.0))
    return onset + max(duration, TRANSCRIPTION_MIN_ACTIVE_WINDOW_SECONDS)


def _transcription_stem_priority(note: dict) -> int:
    pitch_midi = int(note.get("pitchMidi", 0))
    return _transcription_stem_priority_for_pitch(note.get("stemSource"), pitch_midi)


def _transcription_stem_priority_for_pitch(stem_source: str | None, pitch_midi: int) -> int:
    if pitch_midi < 48:
        order = {"bass": 3, "other": 2, "full_mix": 1}
    else:
        order = {"other": 3, "bass": 2, "full_mix": 1}
    return order.get(stem_source, 0)


def _merge_transcription_notes(preferred: dict, other: dict) -> dict:
    merged = dict(preferred)
    merged["durationSeconds"] = round(
        max(
            float(preferred.get("durationSeconds", 0.0)),
            float(other.get("durationSeconds", 0.0)),
        ),
        4,
    )
    return merged


def _is_near_duplicate_pitch(note: dict, candidate: dict) -> bool:
    return (
        int(note.get("pitchMidi", 0)) == int(candidate.get("pitchMidi", 0))
        and abs(float(note.get("onsetSeconds", 0.0)) - float(candidate.get("onsetSeconds", 0.0)))
        <= TRANSCRIPTION_NEAR_DUPLICATE_SECONDS
    )


def _notes_overlap_for_dedup(note: dict, candidate: dict) -> bool:
    if abs(int(note.get("pitchMidi", 0)) - int(candidate.get("pitchMidi", 0))) > 1:
        return False
    note_start = float(note.get("onsetSeconds", 0.0))
    note_end = _transcription_active_end(note)
    candidate_start = float(candidate.get("onsetSeconds", 0.0))
    candidate_end = _transcription_active_end(candidate)
    return min(note_end, candidate_end) >= max(note_start, candidate_start)


def _select_transcription_winner(note: dict, candidate: dict, prefer_confidence_first: bool) -> dict:
    note_conf = float(note.get("confidence", 0.0))
    candidate_conf = float(candidate.get("confidence", 0.0))
    priority_pitch = min(int(note.get("pitchMidi", 0)), int(candidate.get("pitchMidi", 0)))
    note_priority = _transcription_stem_priority_for_pitch(note.get("stemSource"), priority_pitch)
    candidate_priority = _transcription_stem_priority_for_pitch(candidate.get("stemSource"), priority_pitch)

    if prefer_confidence_first:
        if note_conf != candidate_conf:
            return note if note_conf > candidate_conf else candidate
        if note_priority != candidate_priority:
            return note if note_priority > candidate_priority else candidate
    else:
        if note_priority != candidate_priority:
            return note if note_priority > candidate_priority else candidate
        if note_conf != candidate_conf:
            return note if note_conf > candidate_conf else candidate

    note_duration = float(note.get("durationSeconds", 0.0))
    candidate_duration = float(candidate.get("durationSeconds", 0.0))
    if note_duration != candidate_duration:
        return note if note_duration > candidate_duration else candidate
    return note if float(note.get("onsetSeconds", 0.0)) <= float(candidate.get("onsetSeconds", 0.0)) else candidate


def _per_stem_average_confidence(notes: list[dict]) -> dict[str, float]:
    """Mean confidence per stemSource for the notes that survived dedup + cap.

    Each transcription note carries the stem it came from ("bass", "other", or
    "full_mix"). Returning per-stem averages lets the UI show a different
    confidence band when the producer toggles the stem filter — a bass stem
    that tracked well shouldn't be hidden behind a noisy lead stem's
    confidence (or vice versa).
    """
    if not notes:
        return {}
    by_stem: dict[str, list[float]] = {}
    for note in notes:
        stem = note.get("stemSource")
        if not isinstance(stem, str) or not stem:
            continue
        try:
            conf = float(note.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        by_stem.setdefault(stem, []).append(conf)
    return {
        stem: round(float(np.mean(np.asarray(confidences, dtype=np.float64))), 4)
        for stem, confidences in by_stem.items()
        if confidences
    }


def _deduplicate_transcription_notes(notes: list[dict]) -> list[dict]:
    if len(notes) <= 1:
        return [dict(note) for note in notes]

    sorted_notes = sorted(
        (dict(note) for note in notes),
        key=lambda note: (
            float(note.get("onsetSeconds", 0.0)),
            int(note.get("pitchMidi", 0)),
            -float(note.get("confidence", 0.0)),
        ),
    )
    active_heap: list[tuple[float, int, int]] = []
    active_by_pitch: dict[int, dict[int, dict]] = {}
    deduplicated: list[dict] = []
    next_active_id = 0

    def register_active(note: dict) -> None:
        nonlocal next_active_id
        note["_activeId"] = next_active_id
        note["_heapVersion"] = 1
        active_by_pitch.setdefault(int(note["pitchMidi"]), {})[next_active_id] = note
        heapq.heappush(
            active_heap,
            (_transcription_active_end(note), next_active_id, int(note["_heapVersion"])),
        )
        deduplicated.append(note)
        next_active_id += 1

    def refresh_active(note: dict) -> None:
        note["_heapVersion"] = int(note.get("_heapVersion", 0)) + 1
        heapq.heappush(
            active_heap,
            (_transcription_active_end(note), int(note["_activeId"]), int(note["_heapVersion"])),
        )

    for note in sorted_notes:
        onset = float(note.get("onsetSeconds", 0.0))
        while active_heap and active_heap[0][0] < onset:
            _end_time, active_id, heap_version = heapq.heappop(active_heap)
            active_note = None
            for bucket in active_by_pitch.values():
                active_note = bucket.get(active_id)
                if active_note is not None:
                    break
            if active_note is None or int(active_note.get("_heapVersion", 0)) != heap_version:
                continue
            pitch_bucket = active_by_pitch.get(int(active_note["pitchMidi"]))
            if pitch_bucket is not None:
                pitch_bucket.pop(active_id, None)
                if len(pitch_bucket) == 0:
                    active_by_pitch.pop(int(active_note["pitchMidi"]), None)

        matching_candidates: list[tuple[bool, float, int, dict]] = []
        for pitch_midi in range(max(0, int(note["pitchMidi"]) - 1), min(127, int(note["pitchMidi"]) + 1) + 1):
            for candidate in active_by_pitch.get(pitch_midi, {}).values():
                if candidate.get("stemSource") == note.get("stemSource"):
                    continue
                is_near_duplicate = _is_near_duplicate_pitch(note, candidate)
                if not is_near_duplicate and not _notes_overlap_for_dedup(note, candidate):
                    continue
                matching_candidates.append(
                    (
                        is_near_duplicate,
                        abs(float(candidate.get("onsetSeconds", 0.0)) - onset),
                        abs(int(candidate.get("pitchMidi", 0)) - int(note.get("pitchMidi", 0))),
                        candidate,
                    )
                )

        if len(matching_candidates) == 0:
            register_active(note)
            continue

        matching_candidates.sort(key=lambda item: (not item[0], item[1], item[2]))
        candidate = matching_candidates[0][3]
        is_near_duplicate = matching_candidates[0][0]
        winner = _select_transcription_winner(note, candidate, prefer_confidence_first=is_near_duplicate)
        loser = candidate if winner is note else note
        merged = _merge_transcription_notes(winner, loser)

        if winner is note:
            active_id = int(candidate["_activeId"])
            pitch_bucket = active_by_pitch.get(int(candidate["pitchMidi"]))
            if pitch_bucket is not None:
                pitch_bucket.pop(active_id, None)
                if len(pitch_bucket) == 0:
                    active_by_pitch.pop(int(candidate["pitchMidi"]), None)
            deduplicated = [
                merged if int(existing.get("_activeId", -1)) == active_id else existing
                for existing in deduplicated
            ]
            merged["_activeId"] = active_id
            merged["_heapVersion"] = int(candidate.get("_heapVersion", 0)) + 1
            active_by_pitch.setdefault(int(merged["pitchMidi"]), {})[active_id] = merged
            heapq.heappush(
                active_heap,
                (_transcription_active_end(merged), active_id, int(merged["_heapVersion"])),
            )
        else:
            candidate.update(merged)
            refresh_active(candidate)

    cleaned_notes = []
    for note in deduplicated:
        cleaned_note = dict(note)
        cleaned_note.pop("_activeId", None)
        cleaned_note.pop("_heapVersion", None)
        cleaned_notes.append(cleaned_note)

    return sorted(cleaned_notes, key=lambda note: note["onsetSeconds"])


def _extract_contour_notes(
    pitch_hz: np.ndarray,
    periodicity_values: np.ndarray,
    *,
    stem_source: str,
    frame_duration: float,
    periodicity_threshold: float,
    min_note_seconds: float,
    pitch_jump_split_semitones: float,
) -> tuple[list[dict], list[int], list[float]]:
    pitch = np.nan_to_num(
        np.asarray(pitch_hz, dtype=np.float64),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    periodicity = np.nan_to_num(
        np.asarray(periodicity_values, dtype=np.float64),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    voiced = (pitch > 0.0) & (periodicity >= periodicity_threshold)
    notes: list[dict] = []
    midi_values: list[int] = []
    confidence_values: list[float] = []

    start_idx: int | None = None
    midi_track: list[float] = []
    confidence_track: list[float] = []
    last_midi: float | None = None

    def flush(end_idx: int) -> None:
        nonlocal start_idx, midi_track, confidence_track, last_midi
        if start_idx is None or len(midi_track) == 0:
            start_idx = None
            midi_track = []
            confidence_track = []
            last_midi = None
            return

        onset_seconds = start_idx * frame_duration
        duration_seconds = max(0.0, (end_idx - start_idx) * frame_duration)
        if duration_seconds < min_note_seconds:
            start_idx = None
            midi_track = []
            confidence_track = []
            last_midi = None
            return

        pitch_midi = int(np.clip(int(round(float(np.median(midi_track)))), 0, 127))
        confidence = _normalize_confidence(
            float(np.mean(np.asarray(confidence_track, dtype=np.float64)))
        )
        if confidence < TRANSCRIPTION_CONFIDENCE_FLOOR:
            start_idx = None
            midi_track = []
            confidence_track = []
            last_midi = None
            return

        note_obj = {
            "pitchMidi": pitch_midi,
            "pitchName": midi_to_note_name(pitch_midi),
            "onsetSeconds": round(float(onset_seconds), 4),
            "durationSeconds": round(float(duration_seconds), 4),
            "confidence": confidence,
            "stemSource": stem_source,
        }
        notes.append(note_obj)
        midi_values.append(pitch_midi)
        confidence_values.append(confidence)

        start_idx = None
        midi_track = []
        confidence_track = []
        last_midi = None

    for idx in range(len(pitch)):
        if not voiced[idx]:
            flush(idx)
            continue

        current_midi = float(69.0 + 12.0 * np.log2(max(pitch[idx], 1e-9) / 440.0))

        if start_idx is None:
            start_idx = idx
            midi_track = [current_midi]
            confidence_track = [float(periodicity[idx])]
            last_midi = current_midi
            continue

        if (
            last_midi is not None
            and abs(current_midi - last_midi) > pitch_jump_split_semitones
        ):
            flush(idx)
            start_idx = idx
            midi_track = [current_midi]
            confidence_track = [float(periodicity[idx])]
            last_midi = current_midi
            continue

        midi_track.append(current_midi)
        confidence_track.append(float(periodicity[idx]))
        last_midi = current_midi

    flush(len(pitch))
    return notes, midi_values, confidence_values


TORCHCREPE_SAMPLE_RATE = 16000
TORCHCREPE_HOP_LENGTH = 160
TORCHCREPE_FMIN = 50.0
TORCHCREPE_FMAX = 1000.0
TORCHCREPE_PERIODICITY_THRESHOLD = 0.21
TORCHCREPE_MODEL = "tiny"
TORCHCREPE_MIN_NOTE_SECONDS = 0.06
TORCHCREPE_PITCH_JUMP_SPLIT_SEMITONES = 2.0
TRANSCRIPTION_BACKEND_ENV = "ASA_TRANSCRIPTION_BACKEND"


def _extract_torchcrepe_notes(
    source_path: str,
    stem_source: str,
    *,
    torch_module,
    torchcrepe_module,
    device: str,
) -> tuple[list[dict], list[int], list[float]]:
    mono = np.asarray(
        load_mono(source_path, sample_rate=TORCHCREPE_SAMPLE_RATE), dtype=np.float32
    )
    if mono.size == 0:
        return [], [], []

    with torch_module.no_grad():
        audio = torch_module.as_tensor(mono, dtype=torch_module.float32, device=device)
        if audio.ndim == 1:
            audio = audio.unsqueeze(0)

        pitch_hz, periodicity = torchcrepe_module.predict(
            audio,
            TORCHCREPE_SAMPLE_RATE,
            hop_length=TORCHCREPE_HOP_LENGTH,
            fmin=TORCHCREPE_FMIN,
            fmax=TORCHCREPE_FMAX,
            model=TORCHCREPE_MODEL,
            return_periodicity=True,
            device=device,
            pad=False,
            batch_size=512,
        )

    pitch = np.asarray(pitch_hz.squeeze(0).detach().cpu().numpy(), dtype=np.float64)
    periodicity_values = np.asarray(
        periodicity.squeeze(0).detach().cpu().numpy(), dtype=np.float64
    )
    # Free torch tensors immediately — PyTorch's CPU allocator won't
    # return memory to the OS otherwise.
    del audio, pitch_hz, periodicity
    import gc; gc.collect()
    frame_duration = TORCHCREPE_HOP_LENGTH / float(TORCHCREPE_SAMPLE_RATE)
    return _extract_contour_notes(
        pitch,
        periodicity_values,
        stem_source=stem_source,
        frame_duration=frame_duration,
        periodicity_threshold=TORCHCREPE_PERIODICITY_THRESHOLD,
        min_note_seconds=TORCHCREPE_MIN_NOTE_SECONDS,
        pitch_jump_split_semitones=TORCHCREPE_PITCH_JUMP_SPLIT_SEMITONES,
    )


class TorchcrepeBackend:
    """Maintained transcription backend using torchcrepe F0 tracking + segmentation."""

    name = "torchcrepe-viterbi"

    def transcribe(
        self,
        audio_path: str,
        stem_paths: dict | None = None,
        emit_progress_markers: bool = False,
    ) -> dict:
        try:
            import torch
            import torchcrepe
        except Exception as e:
            print(f"[warn] Torchcrepe import failed: {e}", file=sys.stderr)
            return {"transcriptionDetail": None}

        try:
            transcription_sources = _transcription_source_paths(audio_path, stem_paths)
            full_mix_fallback = (
                len(transcription_sources) == 1
                and transcription_sources[0][0] == "full_mix"
            )
            if full_mix_fallback:
                print(
                    "[warn] transcriptionDetail: running on full mix — quality may be low for dense material",
                    file=sys.stderr,
                )

            device = "cuda" if torch.cuda.is_available() else "cpu"
            notes: list[dict] = []
            stems_transcribed = [
                stem_source for stem_source, _source_path in transcription_sources
            ]

            for stem_source, source_path in transcription_sources:
                if emit_progress_markers:
                    transcription_mode = (
                        "stems"
                        if stem_source in ("bass", "other")
                        else "full_mix"
                    )
                    print(
                        f"@@TRANSCRIPTION_SOURCE mode={transcription_mode} source={stem_source}",
                        file=sys.stderr,
                    )

                source_notes, _source_midi_values, _source_confidence_values = (
                    _extract_torchcrepe_notes(
                        source_path,
                        stem_source,
                        torch_module=torch,
                        torchcrepe_module=torchcrepe,
                        device=device,
                    )
                )
                notes.extend(source_notes)

            notes.sort(key=lambda note: note["onsetSeconds"])
            notes = _deduplicate_transcription_notes(notes)

            stem_separation_used = any(
                stem_source in ("bass", "other") for stem_source in stems_transcribed
            )
            note_cap = (
                FULL_MIX_TRANSCRIPTION_NOTE_CAP
                if full_mix_fallback
                else TRANSCRIPTION_NOTE_CAP
            )
            if len(notes) > note_cap:
                original_count = len(notes)
                ranked_notes = sorted(
                    notes,
                    key=lambda note: (
                        -float(note.get("confidence", 0.0)),
                        -float(note.get("durationSeconds", 0.0)),
                        float(note.get("onsetSeconds", 0.0)),
                    ),
                )
                notes = sorted(
                    ranked_notes[:note_cap],
                    key=lambda note: note["onsetSeconds"],
                )
                print(
                    f"[warn] transcriptionDetail: truncated to {note_cap} notes (was {original_count})",
                    file=sys.stderr,
                )

            if len(notes) == 0:
                return {
                    "transcriptionDetail": {
                        "transcriptionMethod": self.name,
                        "noteCount": 0,
                        "averageConfidence": 0.0,
                        "dominantPitches": [],
                        "pitchRange": {
                            "minMidi": None,
                            "maxMidi": None,
                            "minName": None,
                            "maxName": None,
                        },
                        "stemSeparationUsed": stem_separation_used,
                        "fullMixFallback": full_mix_fallback,
                        "stemsTranscribed": stems_transcribed,
                        "perStemAverageConfidence": {},
                        "notes": [],
                    }
                }

            midi_values = [int(note["pitchMidi"]) for note in notes]
            confidence_values = [float(note["confidence"]) for note in notes]
            dominant_pitches = [
                {
                    "pitchMidi": int(pitch_midi),
                    "pitchName": midi_to_note_name(int(pitch_midi)),
                    "count": int(count),
                }
                for pitch_midi, count in Counter(midi_values).most_common(5)
            ]

            min_midi = int(min(midi_values))
            max_midi = int(max(midi_values))
            average_confidence = round(
                float(np.mean(np.asarray(confidence_values, dtype=np.float64))), 4
            )
            # Empty in full-mix fallback so the UI doesn't show a per-stem
            # band when there's no meaningful separation to report. The
            # frontend falls back to averageConfidence in that case.
            per_stem_confidence = (
                {} if full_mix_fallback else _per_stem_average_confidence(notes)
            )

            return {
                "transcriptionDetail": {
                    "transcriptionMethod": self.name,
                    "noteCount": int(len(notes)),
                    "averageConfidence": average_confidence,
                    "dominantPitches": dominant_pitches,
                    "pitchRange": {
                        "minMidi": min_midi,
                        "maxMidi": max_midi,
                        "minName": midi_to_note_name(min_midi),
                        "maxName": midi_to_note_name(max_midi),
                    },
                    "stemSeparationUsed": stem_separation_used,
                    "fullMixFallback": full_mix_fallback,
                    "stemsTranscribed": stems_transcribed,
                    "perStemAverageConfidence": per_stem_confidence,
                    "notes": notes,
                }
            }
        except Exception as e:
            print(f"[warn] Torchcrepe transcription failed: {e}", file=sys.stderr)
            return {"transcriptionDetail": None}


def analyze_transcription(
    audio_path: str,
    stem_paths: dict | None = None,
    backend: TranscriptionBackend | None = None,
    emit_progress_markers: bool = False,
    backend_id: str | None = None,
) -> dict:
    """Run transcription via the specified backend (torchcrepe by default)."""
    def _invoke_backend(candidate: TranscriptionBackend) -> dict:
        try:
            return candidate.transcribe(
                audio_path,
                stem_paths,
                emit_progress_markers=emit_progress_markers,
            )
        except TypeError as exc:
            if "emit_progress_markers" not in str(exc):
                raise
            return candidate.transcribe(audio_path, stem_paths)

    if backend is None:
        requested_backend = (
            backend_id
            if backend_id is not None
            else os.getenv(TRANSCRIPTION_BACKEND_ENV, "auto")
        )
        if backend_id is not None:
            resolve_transcription_backend_id(requested_backend)
        else:
            try:
                resolve_transcription_backend_id(requested_backend)
            except ValueError:
                print(
                    f"[warn] Unknown {TRANSCRIPTION_BACKEND_ENV}='{requested_backend}', defaulting to {DEFAULT_TRANSCRIPTION_BACKEND}",
                    file=sys.stderr,
                )

        backend = TorchcrepeBackend()

    return _invoke_backend(backend)
