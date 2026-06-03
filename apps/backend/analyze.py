#!/usr/bin/env python3
"""
analyze.py — DSP accuracy testing tool.

Takes an audio file, runs it through Essentia's algorithms,
and prints a clean JSON result to stdout.

Usage:
    ./venv/bin/python analyze.py "path/to/track.mp3" [--separate] [--fast] [--transcribe] [--yes]
"""

import gc
import json
import heapq
import math
import os
import shutil
import sys
import tempfile
import warnings
import wave
from collections import Counter
from typing import Any

import numpy as np

# Suppress C++ level warnings from Essentia to keep stderr minimal
warnings.filterwarnings("ignore")

try:
    import essentia
    import essentia.standard as es

    essentia.log.warningActive = False
    essentia.log.infoActive = False
except ImportError:
    print("Error: essentia is not installed.", file=sys.stderr)
    sys.exit(1)

# Import fast analysis mode
try:
    from analyze_fast import analyze_fast
except ImportError:
    analyze_fast = None

from dsp_utils import (  # noqa: E402
    midi_to_note_name,
    _safe_db,
    _compute_bark_db,
    _compute_stereo_metrics,
    _slice_segments,
    _downsample_evenly,
    _to_finite_float,
    _normalize_confidence,
    _emit_progress_marker,
)
from analyze_audio_io import (  # noqa: E402
    load_mono,
    load_stereo,
    _write_wav_pcm16,
    _demucs_chunked_inference,
    _load_stem_mono,
    _load_stem_stereo,
    analyze_crepe_pitch,
    cleanup_stems,
)
from separation_backend import separate_stems_backend  # noqa: E402
from analyze_estimate import (  # noqa: E402
    _format_duration_label,
    _estimate_stage_seconds,
    get_audio_duration_seconds,
    build_analysis_estimate,
    print_analysis_estimate,
    should_prompt_for_confirmation,
    prompt_to_continue,
)
from analyze_core import (  # noqa: E402
    extract_rhythm,
    apply_bpm_correction,
    analyze_bpm,
    analyze_key,
    analyze_loudness,
    analyze_true_peak,
    analyze_dynamics,
    analyze_dynamic_character,
    analyze_saturation_detail,
    TEXTURE_FLATNESS_BANDS,
    _build_texture_character,
    analyze_texture_character,
    SPECTRAL_BALANCE_BANDS,
    analyze_spectral_balance,
    analyze_plr,
    analyze_spectral_detail,
    analyze_stereo,
    analyze_perceptual,
    analyze_essentia_features,
    analyze_duration_and_sr,
    analyze_time_signature,
)
from loudness_backend import apply_loudness_backend  # noqa: E402
from analyze_structure import (  # noqa: E402
    STRUCTURE_FRAME_SIZE,
    STRUCTURE_HOP_SIZE,
    STRUCTURE_MFCC_COEFFICIENTS,
    STRUCTURE_MFCC_FEATURE_PRESET,
    STRUCTURE_SBIC_PARAMS,
    STRUCTURE_TARGET_DURATION_MIN_SECONDS,
    STRUCTURE_TARGET_DURATION_MAX_SECONDS,
    STRUCTURE_COARSE_MIN_SEGMENT_COUNT,
    STRUCTURE_COARSE_MEDIAN_SEGMENT_SECONDS,
    STRUCTURE_NOVELTY_EXCLUSION_SECONDS,
    STRUCTURE_SNAP_THRESHOLD_SECONDS,
    STRUCTURE_MERGE_POLICY,
    STRUCTURE_MERGE_BASELINE_SECONDS,
    STRUCTURE_MERGE_BASELINE_BEATS,
    STRUCTURE_MERGE_ADAPTIVE_SECONDS,
    STRUCTURE_MERGE_ADAPTIVE_BEATS,
    STRUCTURE_MERGE_ADAPTIVE_DURATION_FACTOR,
    STRUCTURE_MAX_SEGMENTS,
    _pick_novelty_peaks,
    _compute_arrangement_novelty_summary,
    _zscore_feature_matrix,
    _extract_structure_feature_matrix,
    _run_structure_sbic_boundaries,
    _normalize_structure_boundaries,
    _is_structure_output_too_coarse,
    _fuse_novelty_boundaries,
    _boundaries_to_structure_segments,
    _compute_structure_merge_floor,
    _resolve_downbeats_and_interval,
    _merge_short_structure_segments,
    analyze_arrangement_detail,
    analyze_synthesis_character,
    analyze_danceability,
    analyze_structure as _analyze_structure_impl,
)
from analyze_rhythm import (  # noqa: E402
    _extract_beat_loudness_data,
    _detect_onset_times,
    analyze_rhythm_detail,
    analyze_melody,
    analyze_groove,
    _build_bar_position_pattern,
    analyze_rhythm_timeline,
    analyze_beats_loudness,
)
from analyze_detection import (  # noqa: E402
    analyze_effects_detail,
    analyze_acid_detail,
    analyze_reverb_detail,
    analyze_vocal_detail,
    analyze_supersaw_detail,
    analyze_per_band_transient_density,
    _GENRE_SIGNATURES,
    _GENRE_FAMILY_MAP,
    _genre_range_score,
    analyze_genre_detail,
)
from analyze_segments import (  # noqa: E402
    analyze_segment_loudness,
    analyze_segment_stereo,
    analyze_segment_spectral,
    analyze_segment_key,
    analyze_chords,
)
from analyze_transcription import (  # noqa: E402
    TRANSCRIPTION_CONFIDENCE_FLOOR,
    TRANSCRIPTION_NOTE_CAP,
    FULL_MIX_TRANSCRIPTION_NOTE_CAP,
    TRANSCRIPTION_MIN_ACTIVE_WINDOW_SECONDS,
    TRANSCRIPTION_NEAR_DUPLICATE_SECONDS,
    DEFAULT_TRANSCRIPTION_BACKEND,
    SUPPORTED_TRANSCRIPTION_BACKEND_IDS,
    resolve_transcription_backend_id,
    TranscriptionBackend,
    _transcription_source_paths,
    _transcription_active_end,
    _transcription_stem_priority,
    _transcription_stem_priority_for_pitch,
    _merge_transcription_notes,
    _is_near_duplicate_pitch,
    _notes_overlap_for_dedup,
    _select_transcription_winner,
    _deduplicate_transcription_notes,
    _per_stem_average_confidence,
    _extract_contour_notes,
    TORCHCREPE_SAMPLE_RATE,
    TORCHCREPE_HOP_LENGTH,
    TORCHCREPE_FMIN,
    TORCHCREPE_FMAX,
    TORCHCREPE_PERIODICITY_THRESHOLD,
    TORCHCREPE_MODEL,
    TORCHCREPE_MIN_NOTE_SECONDS,
    TORCHCREPE_PITCH_JUMP_SPLIT_SEMITONES,
    TRANSCRIPTION_BACKEND_ENV,
    _extract_torchcrepe_notes,
    TorchcrepeBackend,
    analyze_transcription,
)


def analyze_structure(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
) -> dict:
    """Structure segmentation with SBic, returned as capped segment objects."""
    try:
        duration = float(len(mono) / sample_rate) if sample_rate > 0 else 0.0
        if duration <= 0.0:
            return {"structure": {"segments": [], "segmentCount": 0}}

        boundaries_seconds = np.asarray([], dtype=np.float64)

        feature_payload = _extract_structure_feature_matrix(
            mono,
            sample_rate,
            feature_preset=STRUCTURE_MFCC_FEATURE_PRESET,
            frame_size=STRUCTURE_FRAME_SIZE,
            hop_size=STRUCTURE_HOP_SIZE,
        )
        if feature_payload is not None:
            feature_matrix, hop_size = feature_payload
            try:
                boundaries_seconds = _run_structure_sbic_boundaries(
                    feature_matrix,
                    sample_rate=sample_rate,
                    hop_size=hop_size,
                )
            except Exception:
                boundaries_seconds = np.asarray([], dtype=np.float64)

        boundaries_seconds = _normalize_structure_boundaries(boundaries_seconds, duration)
        needs_novelty_fallback = (
            boundaries_seconds.size == 0
            or _is_structure_output_too_coarse(boundaries_seconds, duration)
        )
        if needs_novelty_fallback:
            novelty_summary = _compute_arrangement_novelty_summary(mono, sample_rate)
            novelty_peaks = None
            if isinstance(novelty_summary, dict):
                novelty_peaks = novelty_summary.get("noveltyPeaks")

            if boundaries_seconds.size == 0:
                boundaries_seconds = np.asarray([0.0, duration], dtype=np.float64)

            boundaries_seconds = _fuse_novelty_boundaries(
                boundaries_seconds,
                novelty_peaks=novelty_peaks,
                duration=duration,
            )
            boundaries_seconds = _normalize_structure_boundaries(boundaries_seconds, duration)

        if boundaries_seconds.size == 0:
            boundaries_seconds = np.asarray([0.0, duration], dtype=np.float64)

        downbeats, median_beat_interval = _resolve_downbeats_and_interval(rhythm_data)
        if downbeats.size > 0 and median_beat_interval is not None:
            snap_threshold = min(STRUCTURE_SNAP_THRESHOLD_SECONDS, 0.5 * median_beat_interval)
            snapped_boundaries = [float(boundaries_seconds[0])]
            for boundary in boundaries_seconds[1:-1]:
                nearest_downbeat = float(
                    downbeats[np.argmin(np.abs(downbeats - boundary))],
                )
                if abs(nearest_downbeat - float(boundary)) <= snap_threshold:
                    snapped_boundaries.append(nearest_downbeat)
                else:
                    snapped_boundaries.append(float(boundary))
            snapped_boundaries.append(float(boundaries_seconds[-1]))
            boundaries_seconds = _normalize_structure_boundaries(
                np.asarray(snapped_boundaries, dtype=np.float64),
                duration,
            )

        segments = _boundaries_to_structure_segments(boundaries_seconds)
        minimum_duration_seconds = _compute_structure_merge_floor(
            duration,
            median_beat_interval=median_beat_interval,
        )
        segments = _merge_short_structure_segments(
            segments,
            minimum_duration_seconds=minimum_duration_seconds,
        )
        segments = segments[:STRUCTURE_MAX_SEGMENTS]
        if len(segments) == 0:
            segments = [{"start": 0.0, "end": round(duration, 3), "index": 0}]

        return {
            "structure": {
                "segments": segments,
                "segmentCount": len(segments),
            }
        }
    except Exception as e:
        print(f"[warn] Structure analysis failed: {e}", file=sys.stderr)
        return {"structure": None}


def analyze_sidechain_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    beat_data: dict | None = None,
    stems: dict | None = None,
) -> dict:
    """Detect sidechain-style pumping from RMS dips aligned to kick activity."""
    try:
        if beat_data is None:
            beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)
        if beat_data is None:
            return {"sidechainDetail": None}

        beats = np.asarray(beat_data.get("beats", []), dtype=np.float64)
        low_band = np.asarray(beat_data.get("lowBand", []), dtype=np.float64)
        beat_loudness = np.asarray(beat_data.get("beatLoudness", []), dtype=np.float64)
        if beats.size < 2 or low_band.size < 2 or beat_loudness.size < 2:
            return {"sidechainDetail": None}

        source_mono = _load_stem_mono(stems, "bass", sample_rate=sample_rate)
        if source_mono is None:
            source_mono = mono

        mono_arr = np.asarray(source_mono, dtype=np.float32)
        total_samples = int(mono_arr.size)
        if total_samples < 2:
            return {"sidechainDetail": None}

        # Build a 32nd-note grid (8 steps per beat). Internally the analyzer
        # works at 32nd-note resolution so rate detection can distinguish
        # 32nd-note from 16th-note pumping (Phase 1.C #6); the legacy
        # `envelopeShape` field is still emitted at 16-step resolution by
        # downsampling 32 → 16 to keep the existing contract green.
        GRID_STEPS_PER_BEAT = 8  # 1 beat → 8 thirty-second-note slots
        thirty_second_times: list[float] = []
        for i in range(beats.size - 1):
            start = float(beats[i])
            end = float(beats[i + 1])
            if not np.isfinite(start) or not np.isfinite(end) or end <= start:
                continue
            step = (end - start) / GRID_STEPS_PER_BEAT
            thirty_second_times.extend(
                [start + j * step for j in range(GRID_STEPS_PER_BEAT)]
            )

        if len(thirty_second_times) == 0:
            return {
                "sidechainDetail": {
                    "pumpingStrength": 0.0,
                    "pumpingRegularity": 0.0,
                    "pumpingRate": None,
                    "pumpingConfidence": 0.0,
                }
            }
        thirty_second_times.append(float(beats[-1]))
        thirty_second_times = np.asarray(thirty_second_times, dtype=np.float64)

        rms_algo = es.RMS()
        rms_values = []
        centers = []
        for i in range(thirty_second_times.size - 1):
            start_t = float(thirty_second_times[i])
            end_t = float(thirty_second_times[i + 1])
            if end_t <= start_t:
                continue
            start_idx = max(0, min(total_samples, int(round(start_t * sample_rate))))
            end_idx = max(
                start_idx, min(total_samples, int(round(end_t * sample_rate)))
            )
            if end_idx - start_idx < 2:
                continue
            segment = mono_arr[start_idx:end_idx]
            try:
                rms_val = float(rms_algo(segment))
            except Exception:
                rms_val = float(np.sqrt(np.mean(segment.astype(np.float64) ** 2)))
            if not np.isfinite(rms_val):
                continue
            rms_values.append(rms_val)
            centers.append((start_t + end_t) / 2.0)

        rms_values = np.asarray(rms_values, dtype=np.float64)
        centers = np.asarray(centers, dtype=np.float64)
        if rms_values.size < 4 or centers.size < 4:
            return {
                "sidechainDetail": {
                    "pumpingStrength": 0.0,
                    "pumpingRegularity": 0.0,
                    "pumpingRate": None,
                    "pumpingConfidence": 0.0,
                }
            }

        kick_series = np.interp(
            centers, beats, low_band, left=low_band[0], right=low_band[-1]
        )

        def zscore(values: np.ndarray) -> np.ndarray:
            arr = np.asarray(values, dtype=np.float64)
            std = float(np.std(arr))
            if std <= 1e-12:
                return np.zeros_like(arr)
            return (arr - float(np.mean(arr))) / std

        rms_z = zscore(rms_values)
        kick_z = zscore(kick_series)
        if np.std(rms_z) > 1e-12 and np.std(kick_z) > 1e-12:
            dip_corr = float(np.corrcoef(-rms_z, kick_z)[0, 1])
            if not np.isfinite(dip_corr):
                dip_corr = 0.0
        else:
            dip_corr = 0.0

        rms_q90 = float(np.percentile(rms_values, 90))
        rms_q10 = float(np.percentile(rms_values, 10))
        dip_depth = (rms_q90 - rms_q10) / (rms_q90 + 1e-9) if rms_q90 > 0 else 0.0
        dip_depth = float(np.clip(dip_depth, 0.0, 1.0))
        pumping_strength = float(
            np.clip(0.6 * max(0.0, dip_corr) + 0.4 * dip_depth, 0.0, 1.0)
        )

        rms_mean = float(np.mean(rms_values))
        rms_std = float(np.std(rms_values))
        kick_mean = float(np.mean(kick_series))
        dip_mask = (rms_values <= (rms_mean - 0.35 * rms_std)) & (
            kick_series >= kick_mean
        )
        dip_indices = np.where(dip_mask)[0]

        pumping_regularity = 0.0
        pumping_rate = None
        interval_steps = np.array([], dtype=np.float64)
        if dip_indices.size >= 3:
            interval_steps = np.diff(dip_indices.astype(np.float64))
            mean_step = (
                float(np.mean(interval_steps)) if interval_steps.size > 0 else 0.0
            )
            if mean_step > 0:
                pumping_regularity = float(
                    np.clip(1.0 - (np.std(interval_steps) / mean_step), 0.0, 1.0)
                )

            # Grid is now at 32nd-note resolution (8 steps per beat).
            # quarter = 1 beat = 8 steps, eighth = 1/2 beat = 4 steps,
            # sixteenth = 1/4 beat = 2 steps, thirty_second = 1/8 beat = 1 step.
            rate_scores = {}
            for label, target in (
                ("quarter", 8.0),
                ("eighth", 4.0),
                ("sixteenth", 2.0),
                ("thirty_second", 1.0),
            ):
                if interval_steps.size == 0:
                    rate_scores[label] = 0.0
                    continue
                error = float(
                    np.mean(np.abs(interval_steps - target) / (target + 1e-9))
                )
                rate_scores[label] = float(np.clip(1.0 - error, 0.0, 1.0))

            best_rate = max(rate_scores, key=rate_scores.get)
            pumping_rate = best_rate if rate_scores[best_rate] >= 0.45 else None

        beat_intervals = np.diff(beats.astype(np.float64))
        mean_interval = (
            float(np.mean(beat_intervals)) if beat_intervals.size > 0 else 0.0
        )
        if mean_interval > 0:
            timing_stability = float(
                np.clip(1.0 - (np.std(beat_intervals) / mean_interval), 0.0, 1.0)
            )
        else:
            timing_stability = 0.0

        mean_total_beat_loudness = float(np.mean(beat_loudness))
        mean_kick = float(np.mean(low_band))
        kick_presence = (
            mean_kick / (mean_total_beat_loudness + 1e-9)
            if mean_total_beat_loudness > 0
            else 0.0
        )

        kick_p90 = float(np.percentile(low_band, 90))
        kick_p50 = float(np.percentile(low_band, 50))
        kick_contrast = (
            (kick_p90 - kick_p50) / (kick_p90 + 1e-9) if kick_p90 > 0 else 0.0
        )
        kick_contrast = float(np.clip(kick_contrast, 0.0, 1.0))

        confidence = float(
            np.clip(
                0.45 * max(0.0, dip_corr)
                + 0.35 * kick_contrast
                + 0.20 * timing_stability,
                0.0,
                1.0,
            )
        )
        if kick_presence < 0.12:
            confidence *= 0.6
        if dip_corr < 0.20:
            confidence *= 0.6
        if beats.size < 8:
            confidence *= 0.7
        pumping_confidence = float(np.clip(confidence, 0.0, 1.0))

        # Envelope shape: median RMS across bars at 32nd-note (32-step) resolution.
        # Then downsample 32 → 16 for the legacy `envelopeShape` contract while
        # preserving the full 32-step detail under `envelopeShape32`.
        envelope_shape: list[float] | None = None
        envelope_shape_32: list[float] | None = None
        if rms_values.size >= 32:
            n_bars = rms_values.size // 32
            if n_bars >= 1:
                bars_matrix = rms_values[:n_bars * 32].reshape(n_bars, 32)
                median_bar_32 = np.median(bars_matrix, axis=0)
                bar_max_32 = float(np.max(median_bar_32))
                if bar_max_32 > 0:
                    normalized_32 = median_bar_32 / bar_max_32
                    envelope_shape_32 = [round(float(v), 3) for v in normalized_32]
                    # Downsample to 16 by max-pairing adjacent 32nd-note samples
                    # — preserves the "peak at the kick" shape that the legacy
                    # consumer expects, rather than averaging and smearing dips.
                    paired = normalized_32.reshape(16, 2)
                    median_bar_16 = paired.max(axis=1)
                    bar_max_16 = float(np.max(median_bar_16))
                    if bar_max_16 > 0:
                        normalized_16 = median_bar_16 / bar_max_16
                        envelope_shape = [round(float(v), 3) for v in normalized_16]

        return {
            "sidechainDetail": {
                "pumpingStrength": round(pumping_strength, 4),
                "pumpingRegularity": round(
                    float(np.clip(pumping_regularity, 0.0, 1.0)), 4
                ),
                "pumpingRate": pumping_rate,
                "pumpingConfidence": round(pumping_confidence, 4),
                "envelopeShape": envelope_shape,
                "envelopeShape32": envelope_shape_32,
            }
        }
    except Exception as e:
        print(f"[warn] Sidechain analysis failed: {e}", file=sys.stderr)
        return {"sidechainDetail": None}


def analyze_bass_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
    stems: dict | None = None,
) -> dict:
    """Analyze bass character: sub-bass decay time, transient ratio, fundamental Hz, swing.

    Ported from sonic-architect-app/services/bassAnalysis.ts.
    Uses Essentia LowPass for bass extraction, energy-based onset detection,
    decay measurement to -6 dB, and ZCR fundamental estimation.
    """
    try:
        source_mono = _load_stem_mono(stems, "bass", sample_rate=sample_rate)
        if source_mono is None:
            source_mono = mono

        mono_arr = np.asarray(source_mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < sample_rate:
            return {"bassDetail": None}

        effective_bpm = bpm if (bpm is not None and np.isfinite(bpm) and bpm > 0) else 120.0

        # --- 1. Extract bass band: one-pole lowpass at 150 Hz ---
        fc = 150.0 / float(sample_rate)
        alpha = float(np.exp(-2.0 * np.pi * fc))
        a0 = 1.0 - alpha
        bass = np.zeros(mono_arr.size, dtype=np.float64)
        y1 = 0.0
        for i in range(mono_arr.size):
            y1 = a0 * float(mono_arr[i]) + alpha * y1
            bass[i] = y1
        bass = bass.astype(np.float32)

        # --- 2. Find bass transients (energy-based onset detection) ---
        hop_onset = max(1, int(sample_rate * 0.01))   # 10 ms hops
        frame_onset = max(1, int(sample_rate * 0.04))  # 40 ms frames
        beat_dur_s = 60.0 / effective_bpm
        min_onset_dist = int(beat_dur_s * 0.25 * sample_rate)  # ~1/16th note

        onsets: list[int] = []
        prev_energy = 0.0
        last_onset = -min_onset_dist

        i = 0
        while i + frame_onset < bass.size:
            frame_slice = bass[i : i + frame_onset]
            energy = float(np.sqrt(np.mean(frame_slice ** 2)))
            diff = energy - prev_energy
            rel_diff = diff / prev_energy if prev_energy > 0.001 else 0.0
            if rel_diff > 0.5 and energy > 0.01 and (i - last_onset) >= min_onset_dist:
                onsets.append(i)
                last_onset = i
            prev_energy = energy * 0.8 + prev_energy * 0.2
            i += hop_onset

        # --- 3. Fundamental estimation via ZCR on middle 50% ---
        start_zcr = bass.size // 4
        end_zcr = (bass.size * 3) // 4
        crossings = 0
        for j in range(start_zcr + 1, end_zcr):
            if (bass[j - 1] < 0 and bass[j] >= 0) or (bass[j - 1] >= 0 and bass[j] < 0):
                crossings += 1
        dur_zcr = float(end_zcr - start_zcr) / float(sample_rate)
        zcr = crossings / dur_zcr if dur_zcr > 0 else 0.0
        fundamental_hz = max(30.0, min(120.0, zcr / 2.0))

        if len(onsets) < 3:
            return {
                "bassDetail": {
                    "averageDecayMs": 1000,
                    "type": "sustained",
                    "transientRatio": 0.2,
                    "fundamentalHz": round(fundamental_hz),
                    "transientCount": len(onsets),
                    "swingPercent": 0,
                    "grooveType": "straight",
                }
            }

        # --- 4. Measure decay time per onset to -6 dB ---
        DECAY_THRESHOLD_DB = -6.0
        MAX_DECAY_MS = 2000.0
        decay_times: list[float] = []

        # Pre-compute an RMS envelope of the bass band so decay-to-threshold
        # is measured on the envelope, not the raw oscillating waveform
        # (a 50 Hz sine crosses zero every 10 ms, which made the old loop
        # record sub-millisecond decays for every note).
        env_hop = max(1, int(sample_rate * 0.005))   # 5 ms hop
        env_win = max(env_hop, int(sample_rate * 0.02))  # 20 ms window
        if bass.size >= env_win:
            n_frames = 1 + (bass.size - env_win) // env_hop
            bass_envelope = np.empty(n_frames, dtype=np.float32)
            for fi in range(n_frames):
                start = fi * env_hop
                segment = bass[start:start + env_win]
                bass_envelope[fi] = float(np.sqrt(np.mean(segment ** 2)))
        else:
            bass_envelope = np.array([float(np.sqrt(np.mean(bass ** 2)))], dtype=np.float32)

        def _sample_to_env(sample_index: int) -> int:
            return int(min(max(0, sample_index // env_hop), bass_envelope.size - 1))

        for idx in range(len(onsets) - 1):
            onset_sample = onsets[idx]
            next_onset = onsets[idx + 1]
            max_decay_samples = min(
                next_onset - onset_sample,
                int((MAX_DECAY_MS / 1000.0) * sample_rate),
            )
            # Find peak of the envelope inside a 50 ms search window starting at
            # the onset trigger.
            env_start = _sample_to_env(onset_sample)
            env_search_end = _sample_to_env(min(onset_sample + int(sample_rate * 0.05), bass.size - 1)) + 1
            if env_search_end <= env_start:
                continue
            window_env = bass_envelope[env_start:env_search_end]
            if window_env.size == 0:
                continue
            peak_env_offset = int(np.argmax(window_env))
            peak_env_val = float(window_env[peak_env_offset])
            if peak_env_val < 0.001:
                continue
            threshold_val = peak_env_val * (10.0 ** (DECAY_THRESHOLD_DB / 20.0))

            # Decay window in envelope frames, anchored at the peak (not the onset).
            peak_env_index = env_start + peak_env_offset
            max_decay_env = max(0, max_decay_samples // env_hop - peak_env_offset)
            found = False
            for s in range(max_decay_env):
                env_pos = peak_env_index + s
                if env_pos >= bass_envelope.size:
                    break
                if bass_envelope[env_pos] < threshold_val:
                    decay_times.append((s * env_hop / float(sample_rate)) * 1000.0)
                    found = True
                    break
            if not found and max_decay_env > 0:
                decay_times.append((max_decay_env * env_hop / float(sample_rate)) * 1000.0)

        avg_decay = float(np.mean(decay_times)) if decay_times else 800.0

        if avg_decay < 300:
            bass_type = "punchy"
        elif avg_decay < 600:
            bass_type = "medium"
        elif avg_decay < 1000:
            bass_type = "rolling"
        else:
            bass_type = "sustained"

        # --- 5. Transient ratio ---
        transient_window_samples = int(0.1 * sample_rate)  # 100 ms
        transient_energy = 0.0
        marked: set[int] = set()
        for ons in onsets:
            for s in range(ons, min(ons + transient_window_samples, bass.size)):
                if s not in marked:
                    transient_energy += float(bass[s]) ** 2
                    marked.add(s)
        total_bass_energy = float(np.sum(bass ** 2))
        transient_ratio = transient_energy / total_bass_energy if total_bass_energy > 0 else 0.0

        # --- 6. Swing detection from onset intervals ---
        swing_percent = 0
        groove_type = "straight"
        if len(onsets) >= 8:
            intervals = [float(onsets[k + 1] - onsets[k]) / float(sample_rate)
                         for k in range(len(onsets) - 1)]
            if len(intervals) >= 4:
                mean_int = float(np.mean(intervals))
                var_int = float(np.var(intervals))
                std_int = float(np.sqrt(var_int))
                cv = std_int / mean_int if mean_int > 0 else 0.0
                # Lag-1 autocorrelation for alternation detection
                if var_int > 0:
                    alt_sum = sum(
                        (intervals[j] - mean_int) * (intervals[j + 1] - mean_int)
                        for j in range(len(intervals) - 1)
                    )
                    alt_corr = alt_sum / (len(intervals) - 1) / var_int
                else:
                    alt_corr = 0.0
                if alt_corr < -0.1 and cv > 0.05:
                    swing_percent = int(min(50, max(0, cv * 400)))
                if swing_percent < 10:
                    groove_type = "straight"
                elif swing_percent < 25:
                    groove_type = "slight-swing"
                elif swing_percent < 40:
                    groove_type = "heavy-swing"
                else:
                    groove_type = "shuffle"

        return {
            "bassDetail": {
                "averageDecayMs": round(avg_decay),
                "type": bass_type,
                "transientRatio": round(float(np.clip(transient_ratio, 0.0, 1.0)), 2),
                "fundamentalHz": round(fundamental_hz),
                "transientCount": len(onsets),
                "swingPercent": swing_percent,
                "grooveType": groove_type,
            }
        }
    except Exception as e:
        print(f"[warn] Bass analysis failed: {e}", file=sys.stderr)
        return {"bassDetail": None}


def analyze_kick_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
    stems: dict | None = None,
) -> dict:
    """Analyze kick drum characteristics: onset sharpness, fundamental pitch, THD, harmonic ratio.

    Ported from sonic-architect-app/services/kickAnalysis.ts.
    Uses Essentia Spectrum + Windowing in the kick band (30-120 Hz),
    OnsetDetection for transients, per-kick THD measurement up to 10th harmonic.
    """
    try:
        source_mono = _load_stem_mono(stems, "drums", sample_rate=sample_rate)
        if source_mono is None:
            source_mono = mono

        mono_arr = np.asarray(source_mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < 4096:
            return {"kickDetail": None}

        effective_bpm = bpm if (bpm is not None and np.isfinite(bpm) and bpm > 0) else 120.0

        frame_size = 2048
        hop_size = 256
        kick_low = 30.0
        kick_high = 120.0

        window = es.Windowing(type="hann", size=frame_size)
        spectrum_algo = es.Spectrum(size=frame_size)

        freq_resolution = float(sample_rate) / float(frame_size)
        low_bin = max(1, int(kick_low / freq_resolution))
        high_bin = min(frame_size // 2 - 1, int(kick_high / freq_resolution))

        # --- 1. Build energy envelope in kick band ---
        envelope: list[float] = []
        for frame in es.FrameGenerator(mono_arr, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum_algo(window(frame))
            kick_energy = 0.0
            for k in range(low_bin, high_bin + 1):
                kick_energy += float(spec[k]) ** 2
            n_bins = max(1, high_bin - low_bin + 1)
            envelope.append(float(np.sqrt(kick_energy / n_bins)))

        if len(envelope) < 5:
            return {"kickDetail": None}

        # --- 2. Detect kick transients (peaks in envelope) ---
        beat_dur_s = 60.0 / effective_bpm
        min_dist_samples = int(beat_dur_s * 0.25 * sample_rate)  # 16th note
        min_dist_frames = max(1, min_dist_samples // hop_size)

        transients: list[int] = []  # indices into envelope
        last_transient = -min_dist_frames
        for i in range(2, len(envelope) - 2):
            if (
                envelope[i] > envelope[i - 1]
                and envelope[i] > envelope[i + 1]
                and envelope[i] > 0.01
                and i - last_transient >= min_dist_frames
            ):
                transients.append(i)
                last_transient = i

        if len(transients) < 2:
            return {
                "kickDetail": {
                    "isDistorted": False,
                    "thd": 0.0,
                    "harmonicRatio": 0.0,
                    "fundamentalHz": 50.0,
                    "kickCount": len(transients),
                }
            }

        # --- 3. Per-kick THD and harmonic analysis ---
        thd_values: list[float] = []
        harmonic_ratios: list[float] = []
        fundamentals: list[float] = []

        for t_idx in transients:
            start_sample = t_idx * hop_size
            kick_frame_len = min(int(0.08 * sample_rate), frame_size)  # 80 ms
            if start_sample + frame_size > mono_arr.size:
                continue
            raw_frame = mono_arr[start_sample : start_sample + frame_size]
            spec = spectrum_algo(window(raw_frame))

            # Find fundamental (strongest peak in kick band)
            max_mag = 0.0
            fund_bin = low_bin
            for k in range(low_bin, high_bin + 1):
                mag = float(spec[k])
                if mag > max_mag:
                    max_mag = mag
                    fund_bin = k
            fund_hz = fund_bin * freq_resolution
            fund_power = max_mag ** 2

            # THD: sum of harmonic powers / fundamental power
            max_harmonic = min(10, int((sample_rate / 2.0) / fund_hz)) if fund_hz > 0 else 1
            harmonic_power = 0.0
            for h in range(2, max_harmonic + 1):
                h_bin = round(fund_bin * h)
                if 0 < h_bin < spec.size:
                    harmonic_power += float(spec[h_bin]) ** 2

            thd = float(np.sqrt(harmonic_power) / np.sqrt(fund_power)) if fund_power > 0 else 0.0

            # Harmonic vs inharmonic ratio in kick band
            harmonic_energy = 0.0
            inharmonic_energy = 0.0
            bin_width = freq_resolution
            for k in range(low_bin, min(high_bin + 1, spec.size)):
                freq = k * freq_resolution
                mag = float(spec[k])
                is_harmonic = False
                if fund_hz > 0:
                    for hh in range(1, 11):
                        if abs(freq - fund_hz * hh) < bin_width * 1.5:
                            is_harmonic = True
                            break
                if is_harmonic:
                    harmonic_energy += mag ** 2
                else:
                    inharmonic_energy += mag ** 2
            total_e = harmonic_energy + inharmonic_energy
            h_ratio = harmonic_energy / total_e if total_e > 0 else 0.0

            thd_values.append(min(1.0, thd))
            harmonic_ratios.append(h_ratio)
            fundamentals.append(fund_hz)

        if not thd_values:
            return {
                "kickDetail": {
                    "isDistorted": False,
                    "thd": 0.0,
                    "harmonicRatio": 0.0,
                    "fundamentalHz": 50.0,
                    "kickCount": len(transients),
                }
            }

        avg_thd = float(np.mean(thd_values))
        avg_harmonic_ratio = float(np.mean(harmonic_ratios))
        avg_fundamental = float(np.mean(fundamentals))
        is_distorted = avg_thd > 0.15 or avg_harmonic_ratio < 0.5

        return {
            "kickDetail": {
                "isDistorted": is_distorted,
                "thd": round(avg_thd, 2),
                "harmonicRatio": round(avg_harmonic_ratio, 2),
                "fundamentalHz": round(avg_fundamental),
                "kickCount": len(transients),
            }
        }
    except Exception as e:
        print(f"[warn] Kick analysis failed: {e}", file=sys.stderr)
        return {"kickDetail": None}


def _analyze_band_drum_detail(
    mono: np.ndarray,
    sample_rate: int,
    band_lo_hz: float,
    band_hi_hz: float,
    bpm: float | None,
    stems: dict | None,
    *,
    min_event_dist_subdivisions: float = 0.25,  # 16th-note default
    body_split_ratio: float = 0.5,
) -> dict | None:
    """Phase 1.C #4 shared helper — band-limited drum onset + character analysis.

    Returns a dict with hit count, mean attack sharpness, body-vs-snap energy
    ratio, mean band centroid, and decay character. The same shape is used for
    snare and hi-hat — only the band range differs. Returns None on failure or
    when fewer than 2 onsets are detected.
    """
    if es is None or mono is None or getattr(mono, "size", 0) < 4096:
        return None
    try:
        source_mono = _load_stem_mono(stems, "drums", sample_rate=sample_rate)
        if source_mono is None:
            source_mono = mono
        mono_arr = np.asarray(source_mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < 4096:
            return None

        effective_bpm = bpm if (bpm is not None and np.isfinite(bpm) and bpm > 0) else 120.0
        frame_size = 2048
        hop_size = 256
        nyquist = sample_rate / 2.0
        lo = max(20.0, min(band_lo_hz, nyquist - 2.0))
        hi = max(lo + 50.0, min(band_hi_hz, nyquist - 1.0))

        window = es.Windowing(type="hann", size=frame_size)
        spectrum_algo = es.Spectrum(size=frame_size)
        freq_resolution = float(sample_rate) / float(frame_size)
        low_bin = max(1, int(lo / freq_resolution))
        high_bin = min(frame_size // 2 - 1, int(hi / freq_resolution))
        mid_bin = max(low_bin + 1, int((lo + (hi - lo) * body_split_ratio) / freq_resolution))

        envelope: list[float] = []
        for frame in es.FrameGenerator(mono_arr, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum_algo(window(frame))
            band_energy = 0.0
            for k in range(low_bin, high_bin + 1):
                band_energy += float(spec[k]) ** 2
            n_bins = max(1, high_bin - low_bin + 1)
            envelope.append(float(np.sqrt(band_energy / n_bins)))

        if len(envelope) < 5:
            return None

        beat_dur_s = 60.0 / effective_bpm
        min_dist_samples = int(beat_dur_s * min_event_dist_subdivisions * sample_rate)
        min_dist_frames = max(1, min_dist_samples // hop_size)

        envelope_arr = np.asarray(envelope, dtype=np.float64)
        env_max = float(envelope_arr.max()) if envelope_arr.size > 0 else 0.0
        if env_max <= 0.0:
            return None
        # Adaptive threshold: 10% of envelope max is "real" event territory.
        peak_floor = max(env_max * 0.10, 0.005)

        transients: list[int] = []
        last_t = -min_dist_frames
        for i in range(2, len(envelope) - 2):
            if (
                envelope[i] > envelope[i - 1]
                and envelope[i] > envelope[i + 1]
                and envelope[i] > peak_floor
                and i - last_t >= min_dist_frames
            ):
                transients.append(i)
                last_t = i

        if len(transients) < 2:
            return None

        attack_sharpness_values: list[float] = []
        body_energy_values: list[float] = []
        snap_energy_values: list[float] = []
        centroid_values: list[float] = []
        decay_frames_values: list[int] = []

        for t_idx in transients:
            # Attack sharpness: envelope rise across the 2 frames before peak.
            if t_idx >= 2:
                rise = envelope[t_idx] - envelope[t_idx - 2]
                attack_sharpness_values.append(max(0.0, rise))

            # Decay: how many frames after the peak until envelope drops below
            # peak * 0.3. Caps at 60 frames (~350 ms at 256-hop 44.1k).
            decay_target = envelope[t_idx] * 0.3
            decay_count = 0
            for j in range(t_idx + 1, min(t_idx + 60, len(envelope))):
                if envelope[j] < decay_target:
                    break
                decay_count += 1
            decay_frames_values.append(decay_count)

            # Per-hit spectral split: body (lower half of band) vs snap (upper half).
            start_sample = t_idx * hop_size
            if start_sample + frame_size > mono_arr.size:
                continue
            raw_frame = mono_arr[start_sample : start_sample + frame_size]
            spec = spectrum_algo(window(raw_frame))
            body_e = 0.0
            snap_e = 0.0
            num_weighted = 0.0
            denom_weighted = 0.0
            for k in range(low_bin, min(high_bin + 1, spec.size)):
                mag = float(spec[k])
                power = mag * mag
                if k <= mid_bin:
                    body_e += power
                else:
                    snap_e += power
                num_weighted += k * freq_resolution * mag
                denom_weighted += mag
            total_e = body_e + snap_e
            if total_e > 0.0:
                body_energy_values.append(body_e / total_e)
                snap_energy_values.append(snap_e / total_e)
            if denom_weighted > 0.0:
                centroid_values.append(num_weighted / denom_weighted)

        if not attack_sharpness_values:
            return None

        return {
            "hitCount": len(transients),
            "hitsPerSecond": round(len(transients) / (mono_arr.size / float(sample_rate)), 2),
            "meanAttackSharpness": round(float(np.mean(attack_sharpness_values)), 4),
            "meanBodyEnergyRatio": round(float(np.mean(body_energy_values)), 3) if body_energy_values else None,
            "meanSnapEnergyRatio": round(float(np.mean(snap_energy_values)), 3) if snap_energy_values else None,
            "meanCentroidHz": round(float(np.mean(centroid_values)), 1) if centroid_values else None,
            "meanDecayFrames": round(float(np.mean(decay_frames_values)), 1),
            "meanDecaySeconds": round(float(np.mean(decay_frames_values)) * hop_size / float(sample_rate), 3),
            "bandHz": [round(lo, 1), round(hi, 1)],
        }
    except Exception as exc:
        print(f"[warn] band drum analysis [{band_lo_hz}-{band_hi_hz} Hz] failed: {exc}", file=sys.stderr)
        return None


def analyze_snare_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
    stems: dict | None = None,
) -> dict:
    """Phase 1.C #4 — snare-band character: hit count, attack sharpness,
    body-vs-snap energy ratio. Mirrors analyze_kick_detail but in the
    120-2000 Hz band where snare fundamentals and body live.

    Uses the drums stem when stems are available, otherwise falls back to
    full-mix audio bandpassed by spectrum-bin selection. Phase 2 cites
    `snareDetail.meanBodyEnergyRatio` for snare-bus body/saturation choices,
    `snareDetail.hitsPerSecond` for groove-density claims.
    """
    return {
        "snareDetail": _analyze_band_drum_detail(
            mono,
            sample_rate,
            band_lo_hz=120.0,
            band_hi_hz=2000.0,
            bpm=bpm,
            stems=stems,
            min_event_dist_subdivisions=0.5,  # 8th-note minimum (snare typically on 2 & 4)
            body_split_ratio=0.35,  # body=120-755 Hz, snap=755-2000 Hz
        )
    }


def analyze_hihat_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
    stems: dict | None = None,
) -> dict:
    """Phase 1.C #4 — hi-hat-band character: hit count, attack sharpness,
    decay character, mean brightness. Mirrors analyze_kick_detail but in the
    2000-12000 Hz band where hi-hat content sits.

    `meanDecaySeconds` is a rough open-vs-closed proxy: closed hats decay
    quickly (~30-60 ms), open hats sustain longer. Phase 2 cites
    `hihatDetail.hitsPerSecond` for 16th-note hat density and
    `hihatDetail.meanDecaySeconds` for open/closed inference.
    """
    return {
        "hihatDetail": _analyze_band_drum_detail(
            mono,
            sample_rate,
            band_lo_hz=2000.0,
            band_hi_hz=12000.0,
            bpm=bpm,
            stems=stems,
            min_event_dist_subdivisions=0.125,  # 32nd-note (hats can be dense)
            body_split_ratio=0.4,
        )
    }


# ─────────────────────────────────────────────────────────────────────────────
# GENRE CLASSIFICATION
# Backport of genreClassifierEnhanced.ts — scores 35 electronic subgenres
# using features already computed by the other analyzers in this pipeline.
# ─────────────────────────────────────────────────────────────────────────────

# ── Main ───────────────────────────────────────────────────────────────────


def _run_pitch_note_translation(
    audio_path: str,
    stem_dir: str | None = None,
    stem_output_dir: str | None = None,
    backend_id: str | None = None,
):
    """Run pitch/note translation only and print JSON to stdout.

    Used by server.py to run pitch/note translation work in a subprocess so that
    Demucs/torchcrepe memory is freed when the process exits.

    If --stem-dir is provided, stems are read from that directory
    (bass.wav, other.wav, etc.) instead of running Demucs again.
    """
    stem_paths = None
    if stem_dir is not None and os.path.isdir(stem_dir):
        # Look for pre-separated stems
        for name in ("bass", "other", "drums", "vocals"):
            path = os.path.join(stem_dir, f"{name}.wav")
            if os.path.isfile(path):
                if stem_paths is None:
                    stem_paths = {}
                stem_paths[name] = path

    need_separation = stem_paths is None
    temp_dir = None

    if need_separation:
        temp_dir = stem_output_dir or tempfile.mkdtemp(prefix="asa_pitch_note_stems_")
        separated = separate_stems_backend(audio_path, output_dir=temp_dir)
        if isinstance(separated, dict) and separated:
            stem_paths = separated

    try:
        result = analyze_transcription(
            audio_path,
            stem_paths=stem_paths,
            backend_id=backend_id,
        )
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    finally:
        if temp_dir is not None and stem_output_dir is None:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _run_mt3_transcription(
    audio_path: str,
    stem_dir: str | None = None,
    stem_output_dir: str | None = None,
) -> None:
    """Run MT3 polyphonic transcription only and print JSON to stdout.

    Companion to :func:`_run_pitch_note_translation`. Used by the analyse
    server's MT3 stage executor (`_execute_mt3_attempt` in server.py) so
    JAX/t5x memory is freed when the subprocess exits.

    Stems handover:
        - If ``stem_dir`` is provided and contains canonical Demucs
          stems (bass.wav / other.wav / vocals.wav), MT3 consumes those
          directly — no Demucs invocation needed. This is the path taken
          when pitch_note ran first and persisted its stems.
        - If ``stem_dir`` is missing AND ``stem_output_dir`` is provided,
          run Demucs into ``stem_output_dir`` so the caller can persist
          the resulting stems back as artifacts. This is the path taken
          when MT3 runs first and pitch_note may follow.
        - If both are missing, MT3 falls back to running on the full mix
          (via ``_resolve_sources`` inside ``mt3_transcription.transcribe``).

    Errors propagate as non-zero exit + stderr text; the executor matches on
    "MT3 backend not installed" / "MT3 checkpoint missing" to distinguish
    MT3_NOT_AVAILABLE (retryable=false) from MT3_TRANSCRIPTION_FAILED.
    """
    # Lazy imports — keep JAX / t5x out of analyze.py's import graph for
    # every code path other than --mt3-only. The pathlib import is also
    # deferred for symmetry; nothing else in analyze.py needs Path today.
    from pathlib import Path
    from mt3_transcription import transcribe as mt3_transcribe

    stems_dir_path: Path | None = None
    if stem_dir is not None and os.path.isdir(stem_dir):
        stems_dir_path = Path(stem_dir)

    # If no pre-separated stems were provided but the caller asked us to
    # write them somewhere, run Demucs into that directory. The caller
    # (server.py::_execute_mt3_attempt) reads the resulting files and
    # records them as stem_<name> artifacts so the next stage (pitch_note
    # if it runs later) can reuse them. Mirrors --pitch-note-only's
    # handover convention so both stages can short-circuit Demucs.
    if stems_dir_path is None and stem_output_dir is not None:
        os.makedirs(stem_output_dir, exist_ok=True)
        separated = separate_stems_backend(audio_path, output_dir=stem_output_dir)
        if isinstance(separated, dict) and separated:
            # separate_stems_backend returns {"bass": "/path/...wav", ...}. Recover
            # the shared parent — all stem files live in one directory.
            for stem_path in separated.values():
                if isinstance(stem_path, str) and os.path.isfile(stem_path):
                    stems_dir_path = Path(stem_path).parent
                    break

    result = mt3_transcribe(audio_path, stems_dir=stems_dir_path)
    json.dump(result.to_payload(), sys.stdout, indent=2)
    sys.stdout.write("\n")


def _run_per_stem_analyses(
    stems: dict | None,
    sample_rate: int,
) -> dict | None:
    """Run the high-value full-mix analyzers against each Demucs stem and
    return their results namespaced under ``stemAnalysis.{stem}.{field}``.

    This is the Phase 1.B "stem-first overlay" from the depth roadmap. Each
    stem becomes its own analytical surface so Phase 2 can recommend
    different processing for kick vs bass vs lead vs vocals — e.g. cite
    ``stemAnalysis.bass.spectralBalance.subBass`` for a bass-only EQ move
    instead of relying on a full-mix scalar that conflates every element.

    The subset of analyzers run per-stem is deliberately narrow:
    - spectralBalance / spectralBalanceTimeSeries — per-element EQ shape.
    - spectralDetail — per-element timbre summary.
    - LUFS (integrated, range, momentary/short-term max, lufsCurve) — per-element loudness.
    - stereo (width, correlation, sub-bass mono check, correlationCurve) — only meaningful when stems are stereo, which Demucs output is.
    - dynamics + dynamicCharacter — per-element transient/dynamic shape.

    BPM, key, time signature, structure novelty, sidechain pumping, etc. are
    intentionally NOT per-stem — they're properties of the song, not any
    one element.

    Sequential implementation. Per the plan, parallelism over stems is a
    follow-up gated on a benchmark — Essentia's C++ side can use OpenMP
    threads internally, so naive Python-thread parallelism risks CPU
    oversubscription on Apple Silicon.
    """
    if not isinstance(stems, dict) or not stems:
        return None

    stem_results: dict[str, dict[str, Any]] = {}
    for stem_name in ("drums", "bass", "other", "vocals"):
        try:
            mono = _load_stem_mono(stems, stem_name, sample_rate=sample_rate)
        except Exception:
            mono = None
        if mono is None or mono.size == 0:
            continue
        try:
            stereo = _load_stem_stereo(stems, stem_name)
        except Exception:
            stereo = None

        per_stem: dict[str, Any] = {}
        try:
            spectral_balance_block = analyze_spectral_balance(mono, sample_rate)
            per_stem["spectralBalance"] = spectral_balance_block.get("spectralBalance")
            per_stem["spectralBalanceTimeSeries"] = spectral_balance_block.get("spectralBalanceTimeSeries")
        except Exception as exc:
            print(f"[stem:{stem_name}] spectralBalance failed: {exc}", file=sys.stderr)

        try:
            spectral_detail_block = analyze_spectral_detail(mono, sample_rate)
            per_stem["spectralDetail"] = spectral_detail_block.get("spectralDetail")
        except Exception as exc:
            print(f"[stem:{stem_name}] spectralDetail failed: {exc}", file=sys.stderr)

        if stereo is not None and isinstance(stereo, np.ndarray) and stereo.ndim == 2 and stereo.shape[1] >= 2:
            try:
                # Demucs writes stems at 44.1 kHz regardless of the source's
                # native rate (see analyze_audio_io._load_stem_stereo, which
                # does not resample). The function's `sample_rate` parameter
                # targets the resampled mono path, not the stereo stem, so
                # we hardcode 44.1 kHz here for the K-weighting filter.
                loudness_block = analyze_loudness(stereo, sample_rate=44_100)
                per_stem["lufsIntegrated"] = loudness_block.get("lufsIntegrated")
                per_stem["lufsRange"] = loudness_block.get("lufsRange")
                per_stem["lufsMomentaryMax"] = loudness_block.get("lufsMomentaryMax")
                per_stem["lufsShortTermMax"] = loudness_block.get("lufsShortTermMax")
                per_stem["lufsCurve"] = loudness_block.get("lufsCurve")
            except Exception as exc:
                print(f"[stem:{stem_name}] LUFS failed: {exc}", file=sys.stderr)
            try:
                stereo_block = analyze_stereo(stereo, sample_rate)
                per_stem["stereoDetail"] = stereo_block.get("stereoDetail")
            except Exception as exc:
                print(f"[stem:{stem_name}] stereoDetail failed: {exc}", file=sys.stderr)
            try:
                true_peak_block = analyze_true_peak(stereo)
                per_stem["truePeak"] = true_peak_block.get("truePeak")
            except Exception as exc:
                print(f"[stem:{stem_name}] truePeak failed: {exc}", file=sys.stderr)

        try:
            dynamics_block = analyze_dynamics(mono, sample_rate)
            per_stem["crestFactor"] = dynamics_block.get("crestFactor")
            per_stem["dynamicSpread"] = dynamics_block.get("dynamicSpread")
        except Exception as exc:
            print(f"[stem:{stem_name}] dynamics failed: {exc}", file=sys.stderr)
        try:
            dynamic_character_block = analyze_dynamic_character(mono, sample_rate)
            per_stem["dynamicCharacter"] = dynamic_character_block.get("dynamicCharacter")
        except Exception as exc:
            print(f"[stem:{stem_name}] dynamicCharacter failed: {exc}", file=sys.stderr)

        # Phase 1.D #5: per-stem reverb (RT60 + perBandRt60 + preDelayMs).
        # Drums and "other" benefit most — bass/vocals are often dry; the
        # analyzer gates with `measured=False` when there aren't enough
        # transients, so dry sources don't pollute the output.
        try:
            reverb_block = analyze_reverb_detail(mono, sample_rate)
            per_stem["reverbDetail"] = reverb_block.get("reverbDetail")
        except Exception as exc:
            print(f"[stem:{stem_name}] reverbDetail failed: {exc}", file=sys.stderr)

        if per_stem:
            stem_results[stem_name] = per_stem

    return stem_results if stem_results else None


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: ./venv/bin/python analyze.py <audio_file> [--separate] [--fast] [--standard] [--transcribe] [--yes] [--pitch-note-only] [--mt3-only] [--stem-dir DIR] [--stem-output-dir DIR] [--pitch-note-backend BACKEND]",
            file=sys.stderr,
        )
        sys.exit(1)

    audio_path = sys.argv[1]
    sample_rate = 44100
    optional_args = sys.argv[2:]
    run_separation = "--separate" in optional_args
    run_fast = "--fast" in optional_args
    run_standard = "--standard" in optional_args
    run_transcribe = "--transcribe" in optional_args
    auto_yes = "--yes" in optional_args
    pitch_note_only = "--pitch-note-only" in optional_args
    mt3_only = "--mt3-only" in optional_args

    # --pitch-note-only: run pitch/note translation, print JSON, exit
    if pitch_note_only:
        stem_dir = None
        stem_output_dir = None
        backend_id = None
        if "--stem-dir" in optional_args:
            idx = optional_args.index("--stem-dir")
            if idx + 1 < len(optional_args):
                stem_dir = optional_args[idx + 1]
        if "--stem-output-dir" in optional_args:
            idx = optional_args.index("--stem-output-dir")
            if idx + 1 < len(optional_args):
                stem_output_dir = optional_args[idx + 1]
        if "--pitch-note-backend" in optional_args:
            idx = optional_args.index("--pitch-note-backend")
            if idx + 1 < len(optional_args):
                backend_id = optional_args[idx + 1]
        _run_pitch_note_translation(
            audio_path,
            stem_dir=stem_dir,
            stem_output_dir=stem_output_dir,
            backend_id=backend_id,
        )
        sys.exit(0)

    # --mt3-only: run MT3 polyphonic transcription, print JSON, exit.
    # Companion to --pitch-note-only — used by the staged-runtime MT3
    # stage executor (server.py::_execute_mt3_attempt). Stems handover
    # is bidirectional: --stem-dir consumes stems pitch_note already
    # wrote; --stem-output-dir writes new stems for pitch_note to pick
    # up later. Falls back to full-mix MT3 when neither is supplied.
    if mt3_only:
        stem_dir = None
        stem_output_dir = None
        if "--stem-dir" in optional_args:
            idx = optional_args.index("--stem-dir")
            if idx + 1 < len(optional_args):
                stem_dir = optional_args[idx + 1]
        if "--stem-output-dir" in optional_args:
            idx = optional_args.index("--stem-output-dir")
            if idx + 1 < len(optional_args):
                stem_output_dir = optional_args[idx + 1]
        _run_mt3_transcription(
            audio_path,
            stem_dir=stem_dir,
            stem_output_dir=stem_output_dir,
        )
        sys.exit(0)

    stems = None

    analysis_estimate = get_audio_duration_seconds(audio_path)
    if analysis_estimate is not None:
        estimate = build_analysis_estimate(
            analysis_estimate,
            run_separation,
            run_transcribe,
            run_fast=run_fast,
            run_standard=run_standard,
        )
        if sys.stdin.isatty():
            print_analysis_estimate(audio_path, estimate)
        if should_prompt_for_confirmation(sys.stdin.isatty(), auto_yes):
            if not prompt_to_continue():
                print("Analysis cancelled.", file=sys.stderr)
                sys.exit(0)

    # Load audio
    print(f"Loading: {audio_path}", file=sys.stderr)
    _emit_progress_marker(
        "loading_audio",
        "Loading and validating uploaded audio for local analysis.",
        0.05,
    )

    try:
        mono = load_mono(audio_path, sample_rate)
    except Exception as e:
        print(f"Error loading mono audio: {e}", file=sys.stderr)
        sys.exit(1)

    if run_fast:
        if analyze_fast is None:
            print("Error: analyze_fast module not available.", file=sys.stderr)
            sys.exit(1)
        print("Running fast analysis...", file=sys.stderr)
        _emit_progress_marker(
            "fast_analysis",
            "Running the reduced fast-analysis preset.",
            0.5,
        )
        result = analyze_fast(mono, sample_rate)
        fast_stereo_detail = result.get("stereoDetail")
        fast_mono_compatible = (
            fast_stereo_detail.get("subBassMono")
            if isinstance(fast_stereo_detail, dict)
            else None
        )
        fast_plr = analyze_plr(result.get("lufsIntegrated"), result.get("truePeak")).get("plr")
        output = {
            "phase1Version": "phase1.v2",
            "bpm": result.get("bpm"),
            "bpmConfidence": result.get("bpmConfidence"),
            "bpmPercival": result.get("bpmPercival"),
            "bpmAgreement": result.get("bpmAgreement"),
            "bpmDoubletime": result.get("bpmDoubletime"),
            "bpmSource": result.get("bpmSource"),
            "bpmRawOriginal": result.get("bpmRawOriginal"),
            "key": result.get("key"),
            "keyConfidence": result.get("keyConfidence"),
            "timeSignature": result.get("timeSignature"),
            "timeSignatureSource": result.get("timeSignatureSource"),
            "timeSignatureConfidence": result.get("timeSignatureConfidence"),
            "durationSeconds": result.get("durationSeconds"),
            "sampleRate": result.get("sampleRate"),
            "lufsIntegrated": result.get("lufsIntegrated"),
            "lufsRange": result.get("lufsRange"),
            "lufsCurve": result.get("lufsCurve"),
            "truePeak": result.get("truePeak"),
            "plr": fast_plr,
            "crestFactor": result.get("crestFactor"),
            "dynamicSpread": result.get("dynamicSpread"),
            "dynamicCharacter": result.get("dynamicCharacter"),
            "textureCharacter": result.get("textureCharacter"),
            "stereoDetail": result.get("stereoDetail"),
            "monoCompatible": fast_mono_compatible,
            "spectralBalance": result.get("spectralBalance"),
            "spectralBalanceTimeSeries": result.get("spectralBalanceTimeSeries"),
            "spectralDetail": result.get("spectralDetail"),
            "stemAnalysis": result.get("stemAnalysis"),
            "transientDensityDetail": result.get("transientDensityDetail"),
            "saturationDetail": result.get("saturationDetail"),
            "snareDetail": result.get("snareDetail"),
            "hihatDetail": result.get("hihatDetail"),
            "rhythmDetail": result.get("rhythmDetail"),
            "melodyDetail": result.get("melodyDetail"),
            "transcriptionDetail": result.get("transcriptionDetail"),
            "grooveDetail": result.get("grooveDetail"),
            "beatsLoudness": result.get("beatsLoudness"),
            "rhythmTimeline": result.get("rhythmTimeline"),
            "sidechainDetail": result.get("sidechainDetail"),
            "acidDetail": result.get("acidDetail"),
            "reverbDetail": result.get("reverbDetail"),
            "vocalDetail": result.get("vocalDetail"),
            "supersawDetail": result.get("supersawDetail"),
            "bassDetail": result.get("bassDetail"),
            "kickDetail": result.get("kickDetail"),
            "genreDetail": result.get("genreDetail"),
            "effectsDetail": result.get("effectsDetail"),
            "synthesisCharacter": result.get("synthesisCharacter"),
            "danceability": result.get("danceability"),
            "structure": result.get("structure"),
            "arrangementDetail": result.get("arrangementDetail"),
            "segmentLoudness": result.get("segmentLoudness"),
            "segmentSpectral": result.get("segmentSpectral"),
            "segmentStereo": result.get("segmentStereo"),
            "segmentKey": result.get("segmentKey"),
            "chordDetail": result.get("chordDetail"),
            "perceptual": result.get("perceptual"),
            "essentiaFeatures": result.get("essentiaFeatures"),
        }
        _emit_progress_marker("complete", "Analysis complete.", 1.0)
        print("Done.", file=sys.stderr)
        print(json.dumps(output, indent=2))
        return

    try:
        stereo, sr, num_channels = load_stereo(audio_path)
    except Exception as e:
        print(
            f"[warn] Stereo loading failed, stereo features will be null: {e}",
            file=sys.stderr,
        )
        stereo = None

    if run_separation:
        _emit_progress_marker(
            "legacy_stem_separation",
            "Running legacy stem separation before DSP analysis.",
            0.12,
        )
        print(
            "Running source separation (this may take 30-60 seconds)...",
            file=sys.stderr,
        )
        stems = separate_stems_backend(audio_path)
        print("@@SEPARATION_COMPLETE", file=sys.stderr)

    # Run torchcrepe pitch extraction on separated stems (if available)
    if stems is not None:
        print("Running pitch extraction (torchcrepe)...", file=sys.stderr)
        pitch_result = analyze_crepe_pitch(stems)
        print("@@PITCH_EXTRACTION_COMPLETE", file=sys.stderr)
    else:
        pitch_result = {"pitchDetail": None}

    print("Analyzing...", file=sys.stderr)

    # Run RhythmExtractor2013 once, share across BPM / time sig / rhythm detail
    _emit_progress_marker(
        "core_measurements",
        "Measuring tempo, key, loudness, and dynamics.",
        0.2,
    )
    rhythm_data = extract_rhythm(mono)

    # Run all analyses — each is self-contained and error-safe
    result = {}

    result.update(analyze_bpm(rhythm_data, mono, sample_rate))
    result.update(analyze_key(mono))
    result.update(analyze_time_signature(rhythm_data, mono=mono, sample_rate=sample_rate))
    result.update(analyze_duration_and_sr(mono, sample_rate))

    # LUFS + LRA (needs stereo at its native sample rate — load_stereo does
    # not resample, so a 48 kHz source must be measured against 48 kHz
    # K-weighting coefficients. `sr` here is the source rate returned by
    # load_stereo above; thread it through so Essentia's filter is correct.
    if stereo is not None:
        loudness = analyze_loudness(stereo, sample_rate=sr)
        # WS3b: optionally override the LUFS scalars with the asa-dsp (WASM core)
        # reading when ASA_LOUDNESS_BACKEND=wasm. No-op by default; degrades back
        # to Essentia on any failure. truePeak + lufsCurve stay Essentia.
        loudness = apply_loudness_backend(loudness, stereo, sr)
        result.update(loudness)
    else:
        result["lufsIntegrated"] = None
        result["lufsRange"] = None

    # True peak (needs stereo)
    if stereo is not None:
        result.update(analyze_true_peak(stereo))
    else:
        result["truePeak"] = None

    # Dynamics
    result.update(analyze_dynamics(mono, sample_rate))
    result.update(analyze_dynamic_character(mono, sample_rate))

    # Stereo analysis
    if stereo is not None:
        result.update(analyze_stereo(stereo, sample_rate))
    else:
        result["stereoDetail"] = {
            "stereoWidth": None,
            "stereoCorrelation": None,
            "subBassCorrelation": None,
            "subBassMono": None,
        }
    stereo_detail = result.get("stereoDetail")
    result["monoCompatible"] = (
        stereo_detail.get("subBassMono") if isinstance(stereo_detail, dict) else None
    )

    # Spectral detail (also computes EnergyBand values for spectral balance in the same loop)
    spectral_result = analyze_spectral_detail(
        mono, sample_rate, _balance_bands=SPECTRAL_BALANCE_BANDS
    )
    precomputed_balance = spectral_result.pop("_spectralBalanceBands", None)
    result.update(spectral_result)

    # Spectral balance (uses precomputed band energies — no redundant frame loop)
    result.update(
        analyze_spectral_balance(mono, sample_rate, precomputed_band_energies=precomputed_balance)
    )
    result.update(analyze_plr(result.get("lufsIntegrated"), result.get("truePeak")))

    # Shared beat-domain loudness data used by rhythm detail + groove + sidechain.
    beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)

    # Rhythm detail — real meter-aware downbeats derived from the per-beat
    # kick-accent pattern (beat_data) and the detected time signature.
    result.update(
        analyze_rhythm_detail(
            mono,
            sample_rate,
            rhythm_data,
            beat_data=beat_data,
            time_signature=result.get("timeSignature"),
        )
    )

    # Groove detail (Tier 2 — always run)
    result.update(analyze_groove(mono, sample_rate, rhythm_data, beat_data))
    result.update(analyze_beats_loudness(mono, sample_rate, rhythm_data, beat_data))
    result.update(analyze_rhythm_timeline(mono, sample_rate, rhythm_data, beat_data))
    # Phase 1.C #1: per-band transient density. ~5-8s on a 2-min track.
    result.update(analyze_per_band_transient_density(mono, sample_rate))

    # Phase 1.C #5: saturation / clipping / over-compression telltales.
    # Cheap (~0.5s), no new deps. Hint-only — Phase 2 must hedge.
    saturation_stereo = stereo if stereo is not None else None
    result.update(analyze_saturation_detail(mono, saturation_stereo, sample_rate))
    result.update(
        analyze_sidechain_detail(
            mono,
            sample_rate,
            rhythm_data,
            beat_data,
            stems=stems,
        )
    )

    # Danceability (Tier 2 — single Essentia call, fast)
    result.update(analyze_danceability(mono, sample_rate))

    # Structure + arrangement (Tier 2)
    result.update(analyze_structure(mono, sample_rate, rhythm_data))
    result.update(analyze_arrangement_detail(mono, sample_rate))

    if run_standard:
        # Standard mode: skip Tier 3 analyses (expensive or niche).
        result["melodyDetail"] = None
        result["acidDetail"] = None
        result["reverbDetail"] = None
        result["vocalDetail"] = None
        result["supersawDetail"] = None
        result["bassDetail"] = None
        result["kickDetail"] = None
        result["effectsDetail"] = None
        result["synthesisCharacter"] = None
        result.update(analyze_texture_character(mono, sample_rate, inharmonicity=None))
        result["segmentLoudness"] = None
        result["segmentSpectral"] = None
        result["segmentStereo"] = None
        result["segmentKey"] = None
        result["chordDetail"] = None
        result["perceptual"] = None
        result["essentiaFeatures"] = None
        result.update(analyze_genre_detail(result))

        # Stereo array no longer needed — release memory.
        del stereo
        gc.collect()
    else:
        # Full mode: run all Tier 3 analyses.

        # Melody detail (expensive: PredominantPitchMelodia hop=128)
        result.update(analyze_melody(audio_path, sample_rate, rhythm_data, stems))

        # Detection detail
        result.update(analyze_acid_detail(mono, sample_rate, bpm=result.get("bpm")))
        result.update(analyze_reverb_detail(mono, sample_rate, bpm=result.get("bpm")))
        result.update(analyze_vocal_detail(mono, sample_rate, bpm=result.get("bpm"), stems=stems))
        result.update(analyze_supersaw_detail(mono, sample_rate, bpm=result.get("bpm"), stems=stems))
        result.update(
            analyze_bass_detail(
                mono,
                sample_rate,
                bpm=result.get("bpm"),
                stems=stems,
            )
        )
        result.update(
            analyze_kick_detail(
                mono,
                sample_rate,
                bpm=result.get("bpm"),
                stems=stems,
            )
        )
        # Phase 1.C #4: snare + hi-hat character analyzers.
        result.update(
            analyze_snare_detail(
                mono,
                sample_rate,
                bpm=result.get("bpm"),
                stems=stems,
            )
        )
        result.update(
            analyze_hihat_detail(
                mono,
                sample_rate,
                bpm=result.get("bpm"),
                stems=stems,
            )
        )
        result.update(
            analyze_effects_detail(
                mono,
                sample_rate,
                rhythm_data,
                lufs_integrated=result.get("lufsIntegrated"),
            )
        )
        result.update(analyze_genre_detail(result))

        # Synthesis character
        result.update(analyze_synthesis_character(mono, sample_rate))
        synthesis_character = result.get("synthesisCharacter")
        inharmonicity = (
            synthesis_character.get("inharmonicity")
            if isinstance(synthesis_character, dict)
            else None
        )
        result.update(
            analyze_texture_character(
                mono,
                sample_rate,
                inharmonicity=inharmonicity,
            )
        )

        # Segment analyses (need stereo)
        result.update(analyze_segment_stereo(result.get("structure"), stereo, sample_rate))
        result.update(
            analyze_segment_loudness(result.get("structure"), stereo, sample_rate)
        )
        result.update(
            analyze_segment_spectral(
                result.get("structure"),
                mono,
                segment_stereo_data=result.get("segmentStereo"),
                sample_rate=sample_rate,
            )
        )
        result.update(analyze_segment_key(result.get("structure"), mono, sample_rate))

        # Stereo array no longer needed — release memory.
        del stereo
        gc.collect()

        # Chords
        result.update(analyze_chords(mono, sample_rate))

        # Perceptual
        result.update(analyze_perceptual(mono, sample_rate))

        # Essentia features
        result.update(analyze_essentia_features(mono, sample_rate))

    # Optional torchcrepe transcription pass
    if run_transcribe:
        transcription_stem_paths = None
        if stems is not None:
            transcription_stem_paths = {}
            for stem_name in ("bass", "other"):
                source_path = stems.get(stem_name)
                if isinstance(source_path, str) and os.path.isfile(source_path):
                    transcription_stem_paths[stem_name] = source_path
            if len(transcription_stem_paths) == 0:
                transcription_stem_paths = None
        transcription_mode = (
            "stems" if transcription_stem_paths is not None else "full_mix"
        )
        _emit_progress_marker(
            "legacy_transcription",
            "Running the legacy transcription pass.",
            0.94 if not run_standard else 0.86,
        )
        print(f"@@TRANSCRIPTION_START mode={transcription_mode}", file=sys.stderr)
        result.update(
            analyze_transcription(
                audio_path,
                stem_paths=transcription_stem_paths,
                emit_progress_markers=True,
            )
        )
        print(f"@@TRANSCRIPTION_COMPLETE mode={transcription_mode}", file=sys.stderr)
        gc.collect()
    else:
        result["transcriptionDetail"] = None

    # Merge pitch extraction results
    result.update(pitch_result)

    # Phase 1.B stem-first overlay: run high-value analyzers per Demucs stem
    # and namespace results under ``stemAnalysis``. Returns ``None`` when
    # stems aren't available (no separation requested or separation failed),
    # so callers downstream can treat ``stemAnalysis`` as an additive
    # capability rather than a contract change.
    try:
        result["stemAnalysis"] = _run_per_stem_analyses(stems, sample_rate)
    except Exception as exc:
        print(f"[warn] stem-first overlay failed: {exc}", file=sys.stderr)
        result["stemAnalysis"] = None

    # Optional MT3 polyphonic transcription pass. Gated on the ASA_ENABLE_MT3
    # env var (default off) so the base ASA install + the standard request
    # path never touch MT3 / t5x / JAX. The result lives in its own top-level
    # ``transcription`` namespace and is *purely additive* to Phase 1 — it
    # does not override or refine any Essentia chord/key/beat/melody output
    # (PURPOSE.md invariant #1, "Phase 1 measurements are ground truth").
    # Failures are caught, logged as [warn], and never block the Phase 1 JSON.
    if os.getenv("ASA_ENABLE_MT3", "").strip() == "1":
        # Lazy import — keeps the mt3_transcription module (and its lazy
        # JAX import inside transcribe()) out of the import graph entirely
        # when the flag is off. analyze.py itself doesn't need pathlib;
        # transcribe() coerces audio_path internally so we can pass the
        # raw string straight through.
        try:
            from mt3_transcription import (
                discover_stems_dir as _mt3_discover_stems_dir,
                transcribe as mt3_transcribe,
            )
            mt3_stems_dir = _mt3_discover_stems_dir(stems)
            print("@@MT3_TRANSCRIPTION_START", file=sys.stderr)
            mt3_result = mt3_transcribe(audio_path, stems_dir=mt3_stems_dir)
            result["transcription"] = {"mt3": mt3_result.to_payload()}
            print("@@MT3_TRANSCRIPTION_COMPLETE", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - MT3 must never block Phase 1
            print(f"[warn] MT3 transcription failed: {exc}", file=sys.stderr)
            # Intentionally do NOT set result["transcription"] = None — the
            # JSON contract is "absent when the flag is off OR when MT3 fails."
            # Adding a null key would make the field always-present.

    # Build final output in the exact requested key order
    output = {
        "phase1Version": "phase1.v2",
        "bpm": result.get("bpm"),
        "bpmConfidence": result.get("bpmConfidence"),
        "bpmPercival": result.get("bpmPercival"),
        "bpmAgreement": result.get("bpmAgreement"),
        "bpmDoubletime": result.get("bpmDoubletime"),
        "bpmSource": result.get("bpmSource"),
        "bpmRawOriginal": result.get("bpmRawOriginal"),
        "key": result.get("key"),
        "keyConfidence": result.get("keyConfidence"),
        "keyProfile": result.get("keyProfile"),
        "tuningFrequency": result.get("tuningFrequency"),
        "tuningCents": result.get("tuningCents"),
        "timeSignature": result.get("timeSignature"),
        "timeSignatureSource": result.get("timeSignatureSource"),
        "timeSignatureConfidence": result.get("timeSignatureConfidence"),
        "durationSeconds": result.get("durationSeconds"),
        "sampleRate": result.get("sampleRate"),
        "lufsIntegrated": result.get("lufsIntegrated"),
        "lufsRange": result.get("lufsRange"),
        "lufsMomentaryMax": result.get("lufsMomentaryMax"),
        "lufsShortTermMax": result.get("lufsShortTermMax"),
        "lufsCurve": result.get("lufsCurve"),
        "truePeak": result.get("truePeak"),
        "plr": result.get("plr"),
        "crestFactor": result.get("crestFactor"),
        "dynamicSpread": result.get("dynamicSpread"),
        "dynamicCharacter": result.get("dynamicCharacter"),
        "textureCharacter": result.get("textureCharacter"),
        "stereoDetail": result.get("stereoDetail"),
        "monoCompatible": result.get("monoCompatible"),
        "spectralBalance": result.get("spectralBalance"),
        "spectralBalanceTimeSeries": result.get("spectralBalanceTimeSeries"),
        "spectralDetail": result.get("spectralDetail"),
        "stemAnalysis": result.get("stemAnalysis"),
        "transientDensityDetail": result.get("transientDensityDetail"),
        "saturationDetail": result.get("saturationDetail"),
        "snareDetail": result.get("snareDetail"),
        "hihatDetail": result.get("hihatDetail"),
        "rhythmDetail": result.get("rhythmDetail"),
        "melodyDetail": result.get("melodyDetail"),
        "transcriptionDetail": result.get("transcriptionDetail"),
        "pitchDetail": result.get("pitchDetail"),
        "grooveDetail": result.get("grooveDetail"),
        "beatsLoudness": result.get("beatsLoudness"),
        "rhythmTimeline": result.get("rhythmTimeline"),
        "sidechainDetail": result.get("sidechainDetail"),
        "acidDetail": result.get("acidDetail"),
        "reverbDetail": result.get("reverbDetail"),
        "vocalDetail": result.get("vocalDetail"),
        "supersawDetail": result.get("supersawDetail"),
        "bassDetail": result.get("bassDetail"),
        "kickDetail": result.get("kickDetail"),
        "genreDetail": result.get("genreDetail"),
        "effectsDetail": result.get("effectsDetail"),
        "synthesisCharacter": result.get("synthesisCharacter"),
        "danceability": result.get("danceability"),
        "structure": result.get("structure"),
        "arrangementDetail": result.get("arrangementDetail"),
        "segmentLoudness": result.get("segmentLoudness"),
        "segmentSpectral": result.get("segmentSpectral"),
        "segmentStereo": result.get("segmentStereo"),
        "segmentKey": result.get("segmentKey"),
        "chordDetail": result.get("chordDetail"),
        "perceptual": result.get("perceptual"),
        "essentiaFeatures": result.get("essentiaFeatures"),
    }

    # Conditional MT3 namespace — *absent* (not null) by default. Only added
    # when ASA_ENABLE_MT3=1 AND the transcribe() call succeeded. See the gate
    # above. Placed after the literal output dict so the key never appears
    # with a null value, which would silently change the contract for every
    # caller that introspects `set(payload.keys())`.
    if "transcription" in result:
        output["transcription"] = result["transcription"]

    _emit_progress_marker("complete", "Analysis complete.", 1.0)
    print("Done.", file=sys.stderr)
    print(json.dumps(output, indent=2))

    if run_separation and stems is not None:
        cleanup_stems(stems)


if __name__ == "__main__":
    main()
