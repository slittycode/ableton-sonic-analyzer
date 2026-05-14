"""Phase 3 audition sample generation orchestrator.

Reads a Phase 1 result + optional Phase 2 result, produces audition WAV/MIDI
artifacts, and emits a manifest with citation metadata so every generated
sample traces back to a Phase 1 field. The manifest *is* the chain of custody
for this stage — it must remain the source of truth for "what justifies this
audio?"

Shape of the manifest is documented in `docs/SAMPLE_GENERATION.md`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

import sample_drums
import sample_synthesis
import sample_theory

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "samples.v1"
FRAMING_NOTE = (
    "Heuristic audition. Verifies tonal/rhythmic foundation derived from "
    "Phase 1 measurements. Not an Ableton-accurate reconstruction — follow "
    "Phase 2 in Ableton for production character."
)


@dataclass(frozen=True)
class GenerationResult:
    manifest: dict[str, Any]
    artifact_paths: dict[str, Path]  # sample_id -> WAV path
    midi_paths: dict[str, Path]  # sample_id -> MIDI path (subset of samples)
    manifest_path: Path


def generate_samples(
    *,
    run_id: str,
    phase1: dict[str, Any],
    phase2: dict[str, Any] | None,
    output_dir: Path,
    pitch_note_hints: list[int] | None = None,
    prefer_fluidsynth: bool = True,
) -> GenerationResult:
    """Build the full audition set for a single run.

    `pitch_note_hints` may carry scale degrees pulled from the stem-summary
    pitch/note translation output. When absent we render the default ascent.

    `prefer_fluidsynth` is plumbed through so tests can force the fallback
    even if FluidSynth is installed on the dev machine.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths: dict[str, Path] = {}
    midi_paths: dict[str, Path] = {}
    samples: list[dict[str, Any]] = []
    selected_backend: sample_synthesis.Backend | None = None
    selected_soundfont: str | None = None

    key_string = _safe_get(phase1, "key")
    key_confidence = _safe_float(_safe_get(phase1, "keyConfidence"))
    bpm = _safe_float(_safe_get(phase1, "bpm")) or 120.0

    # --- Tonal samples (chord progression + bass) -------------------------- #
    ctx: sample_theory.TheoryContext | None = None
    if key_string:
        try:
            ctx = sample_theory.build_context(
                key=key_string, bpm=bpm, key_confidence=key_confidence
            )
        except ValueError as exc:
            logger.info("Skipping tonal samples; unparsed key %r (%s)", key_string, exc)

    if ctx is not None:
        low_confidence = bool(key_confidence is not None and key_confidence < 0.5)

        chord_plan = sample_theory.plan_chord_progression(ctx, bars=8)
        chord_result = sample_synthesis.render_clip(
            chord_plan, prefer_fluidsynth=prefer_fluidsynth
        )
        selected_backend = chord_result.backend
        selected_soundfont = chord_result.soundfont_path
        chord_wav = output_dir / "tonal_chord_progression.wav"
        chord_mid = output_dir / "tonal_chord_progression.mid"
        sample_synthesis.write_wav(chord_result.samples, path=chord_wav)
        sample_synthesis.write_midi(chord_plan, path=chord_mid)
        artifact_paths["tonal_chord_progression"] = chord_wav
        midi_paths["tonal_chord_progression"] = chord_mid
        samples.append(
            _sample_record(
                sample_id="tonal_chord_progression",
                label=_compose_chord_label(ctx, low_confidence),
                category="tonal",
                filename=chord_wav.name,
                midi_filename=chord_mid.name,
                duration_seconds=chord_result.duration_seconds,
                confidence=_confidence_band(key_confidence),
                low_confidence=low_confidence,
                phase1_fields=["key", "keyConfidence", "bpm"],
                phase2_recommendations=_phase2_tonal_citations(phase2),
                rationale=(
                    f"8-bar diatonic progression in {ctx.root_name} {ctx.mode} at "
                    f"{ctx.tempo_bpm:.0f} BPM (key confidence "
                    f"{_format_confidence(key_confidence)})."
                ),
            )
        )

        bass_plan = sample_theory.plan_bass_root(ctx, bars=8)
        bass_result = sample_synthesis.render_clip(
            bass_plan, prefer_fluidsynth=prefer_fluidsynth
        )
        # `selected_backend` is already pinned by the chord render above —
        # `render_clip` always returns a concrete backend string, so the bass
        # render can never narrow or widen the choice.
        bass_wav = output_dir / "tonal_bass_root.wav"
        bass_mid = output_dir / "tonal_bass_root.mid"
        sample_synthesis.write_wav(bass_result.samples, path=bass_wav)
        sample_synthesis.write_midi(bass_plan, path=bass_mid)
        artifact_paths["tonal_bass_root"] = bass_wav
        midi_paths["tonal_bass_root"] = bass_mid
        samples.append(
            _sample_record(
                sample_id="tonal_bass_root",
                label=f"Bass root on {ctx.root_name}",
                category="tonal",
                filename=bass_wav.name,
                midi_filename=bass_mid.name,
                duration_seconds=bass_result.duration_seconds,
                confidence=_confidence_band(key_confidence),
                low_confidence=low_confidence,
                phase1_fields=["key", "keyConfidence", "bpm", "bassDetail"]
                if _safe_get(phase1, "bassDetail")
                else ["key", "keyConfidence", "bpm"],
                phase2_recommendations=_phase2_tonal_citations(phase2),
                rationale=(
                    f"Sustained root tone at MIDI bass register. Tonic "
                    f"derived from Phase 1 key ({ctx.root_name} {ctx.mode})."
                ),
            )
        )

    # --- Drum one-shots ---------------------------------------------------- #
    kick_detail = _safe_get(phase1, "kickDetail") or {}
    kick_fundamental = _safe_float(kick_detail.get("fundamentalHz")) or 55.0
    kick_decay = _safe_float(kick_detail.get("decayTimeMs")) or 250.0
    kick_confidence_raw = _safe_float(kick_detail.get("confidence"))

    kick = sample_drums.synth_kick(
        fundamental_hz=kick_fundamental,
        decay_time_ms=kick_decay,
    )
    kick_path = output_dir / "drum_kick.wav"
    sf.write(str(kick_path), kick.samples, kick.sample_rate, subtype="PCM_16")
    artifact_paths["drum_kick"] = kick_path
    samples.append(
        _sample_record(
            sample_id="drum_kick",
            label=kick.label,
            category="drums",
            filename=kick_path.name,
            midi_filename=None,
            duration_seconds=kick.duration_seconds,
            confidence=_confidence_band(kick_confidence_raw),
            low_confidence=bool(
                kick_confidence_raw is not None and kick_confidence_raw < 0.5
            ),
            phase1_fields=["kickDetail.fundamentalHz", "kickDetail.decayTimeMs"]
            if kick_detail
            else [],
            phase2_recommendations=_phase2_kick_citations(phase2),
            rationale=(
                f"Sub-sine at {kick_fundamental:.0f} Hz with {kick_decay:.0f} ms "
                "decay, derived from measured kickDetail."
                if kick_detail
                else "Default kick — Phase 1 did not surface kickDetail."
            ),
        )
    )

    snare = sample_drums.synth_snare()
    snare_path = output_dir / "drum_snare.wav"
    sf.write(str(snare_path), snare.samples, snare.sample_rate, subtype="PCM_16")
    artifact_paths["drum_snare"] = snare_path
    samples.append(
        _sample_record(
            sample_id="drum_snare",
            label=snare.label,
            category="drums",
            filename=snare_path.name,
            midi_filename=None,
            duration_seconds=snare.duration_seconds,
            confidence="LOW",
            low_confidence=True,
            phase1_fields=[],
            phase2_recommendations=[],
            rationale=(
                "Heuristic snare — Phase 1 does not measure a snare fundamental. "
                "Provided for kit completeness; do not treat as measurement-grounded."
            ),
        )
    )

    hat = sample_drums.synth_hat()
    hat_path = output_dir / "drum_hat.wav"
    sf.write(str(hat_path), hat.samples, hat.sample_rate, subtype="PCM_16")
    artifact_paths["drum_hat"] = hat_path
    samples.append(
        _sample_record(
            sample_id="drum_hat",
            label=hat.label,
            category="drums",
            filename=hat_path.name,
            midi_filename=None,
            duration_seconds=hat.duration_seconds,
            confidence="LOW",
            low_confidence=True,
            phase1_fields=[],
            phase2_recommendations=[],
            rationale=(
                "Heuristic closed hi-hat — Phase 1 does not measure a hat. "
                "Provided for kit completeness; do not treat as measurement-grounded."
            ),
        )
    )

    # --- Melody lead phrase ------------------------------------------------ #
    if ctx is not None:
        melody_detail = _safe_get(phase1, "melodyDetail")
        melody_plan = sample_theory.plan_melody_phrase(
            ctx, scale_degrees=pitch_note_hints, bars=4
        )
        if melody_plan is not None:
            melody_result = sample_synthesis.render_clip(
                melody_plan, prefer_fluidsynth=prefer_fluidsynth
            )
            # See bass-render note above — `selected_backend` is pinned at the
            # first chord render and `render_clip` never returns falsy.
            melody_wav = output_dir / "melody_lead.wav"
            melody_mid = output_dir / "melody_lead.mid"
            sample_synthesis.write_wav(melody_result.samples, path=melody_wav)
            sample_synthesis.write_midi(melody_plan, path=melody_mid)
            artifact_paths["melody_lead"] = melody_wav
            midi_paths["melody_lead"] = melody_mid

            phase1_fields = ["key", "keyConfidence", "bpm"]
            if melody_detail:
                phase1_fields.append("melodyDetail")
            hints_used = pitch_note_hints is not None and len(pitch_note_hints) > 0
            samples.append(
                _sample_record(
                    sample_id="melody_lead",
                    label="Lead phrase in detected key",
                    category="melody",
                    filename=melody_wav.name,
                    midi_filename=melody_mid.name,
                    duration_seconds=melody_result.duration_seconds,
                    confidence=_confidence_band(key_confidence),
                    low_confidence=bool(
                        key_confidence is not None and key_confidence < 0.5
                    ),
                    phase1_fields=phase1_fields,
                    phase2_recommendations=[],
                    rationale=(
                        "Scale-degree sequence from pitch/note translation hints, "
                        f"rendered on a square-lead voice in {ctx.root_name} {ctx.mode}."
                        if hints_used
                        else (
                            f"Default 1-2-3-5 ascent in {ctx.root_name} {ctx.mode} — "
                            "no pitch/note translation hints available."
                        )
                    ),
                )
            )

    manifest: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        "generatedAt": datetime.now(UTC).isoformat(),
        "synthesisBackend": selected_backend or "sine_fallback",
        "soundfont": selected_soundfont,
        "framing": FRAMING_NOTE,
        "theoryBackend": (
            "pytheory" if sample_theory.pytheory_available() else "fallback"
        ),
        "samples": samples,
    }
    manifest_path = output_dir / "samples_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return GenerationResult(
        manifest=manifest,
        artifact_paths=artifact_paths,
        midi_paths=midi_paths,
        manifest_path=manifest_path,
    )


# --- Helpers ---------------------------------------------------------------- #


def _sample_record(
    *,
    sample_id: str,
    label: str,
    category: str,
    filename: str,
    midi_filename: str | None,
    duration_seconds: float,
    confidence: str,
    low_confidence: bool,
    phase1_fields: list[str],
    phase2_recommendations: list[str],
    rationale: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": sample_id,
        "label": label,
        "category": category,
        "filename": filename,
        "mimeType": "audio/wav",
        "durationSeconds": round(duration_seconds, 3),
        "confidence": confidence,
        "lowConfidence": low_confidence,
        "cites": {
            "phase1Fields": phase1_fields,
            "phase2Recommendations": phase2_recommendations,
            "rationale": rationale,
        },
    }
    if midi_filename is not None:
        record["midiFilename"] = midi_filename
    return record


def _safe_get(payload: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(payload, dict):
        return None
    return payload.get(key)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN check
        return None
    return result


def _confidence_band(value: float | None) -> str:
    if value is None:
        return "MED"
    if value >= 0.75:
        return "HIGH"
    if value >= 0.5:
        return "MED"
    return "LOW"


def _format_confidence(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _compose_chord_label(
    ctx: sample_theory.TheoryContext, low_confidence: bool
) -> str:
    base = f"Chord progression in {ctx.root_name} {ctx.mode}"
    return f"{base} (low-confidence key)" if low_confidence else base


def _phase2_tonal_citations(phase2: dict[str, Any] | None) -> list[str]:
    if not isinstance(phase2, dict):
        return []
    cites: list[str] = []
    if phase2.get("styleProfile"):
        cites.append("styleProfile.authoritativeMeasurements.key")
    if isinstance(phase2.get("sonicElements"), dict):
        if phase2["sonicElements"].get("harmonicContent"):
            cites.append("sonicElements.harmonicContent")
    return cites


def _phase2_kick_citations(phase2: dict[str, Any] | None) -> list[str]:
    if not isinstance(phase2, dict):
        return []
    sonic = phase2.get("sonicElements")
    if isinstance(sonic, dict) and sonic.get("kick"):
        return ["sonicElements.kick"]
    return []
