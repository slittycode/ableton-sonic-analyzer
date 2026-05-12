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
    separate_stems,
    analyze_crepe_pitch,
    cleanup_stems,
)
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

        # Build a 16th-note grid from beat intervals.
        sixteenth_times = []
        for i in range(beats.size - 1):
            start = float(beats[i])
            end = float(beats[i + 1])
            if not np.isfinite(start) or not np.isfinite(end) or end <= start:
                continue
            step = (end - start) / 4.0
            sixteenth_times.extend([start + j * step for j in range(4)])

        if len(sixteenth_times) == 0:
            return {
                "sidechainDetail": {
                    "pumpingStrength": 0.0,
                    "pumpingRegularity": 0.0,
                    "pumpingRate": None,
                    "pumpingConfidence": 0.0,
                }
            }
        sixteenth_times.append(float(beats[-1]))
        sixteenth_times = np.asarray(sixteenth_times, dtype=np.float64)

        rms_algo = es.RMS()
        rms_values = []
        centers = []
        for i in range(sixteenth_times.size - 1):
            start_t = float(sixteenth_times[i])
            end_t = float(sixteenth_times[i + 1])
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

            rate_scores = {}
            for label, target in (
                ("quarter", 4.0),
                ("eighth", 2.0),
                ("sixteenth", 1.0),
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

        # Envelope shape: median RMS across bars at 16th-note resolution (16 values)
        envelope_shape = None
        if rms_values.size >= 16:
            n_bars = rms_values.size // 16
            if n_bars >= 1:
                bars_matrix = rms_values[:n_bars * 16].reshape(n_bars, 16)
                median_bar = np.median(bars_matrix, axis=0)
                bar_max = float(np.max(median_bar))
                if bar_max > 0:
                    normalized = median_bar / bar_max
                    envelope_shape = [round(float(v), 3) for v in normalized]

        return {
            "sidechainDetail": {
                "pumpingStrength": round(pumping_strength, 4),
                "pumpingRegularity": round(
                    float(np.clip(pumping_regularity, 0.0, 1.0)), 4
                ),
                "pumpingRate": pumping_rate,
                "pumpingConfidence": round(pumping_confidence, 4),
                "envelopeShape": envelope_shape,
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

        for idx in range(len(onsets) - 1):
            onset_sample = onsets[idx]
            next_onset = onsets[idx + 1]
            max_decay_samples = min(
                next_onset - onset_sample,
                int((MAX_DECAY_MS / 1000.0) * sample_rate),
            )
            # Find peak near onset (50 ms search window)
            search_end = min(onset_sample + int(sample_rate * 0.05), bass.size)
            peak_val = float(np.max(np.abs(bass[onset_sample:search_end]))) if search_end > onset_sample else 0.0
            if peak_val < 0.001:
                continue
            threshold_val = peak_val * (10.0 ** (DECAY_THRESHOLD_DB / 20.0))
            found = False
            for s in range(max_decay_samples):
                if onset_sample + s >= bass.size:
                    break
                if abs(float(bass[onset_sample + s])) < threshold_val:
                    decay_times.append((s / float(sample_rate)) * 1000.0)
                    found = True
                    break
            if not found:
                decay_times.append((max_decay_samples / float(sample_rate)) * 1000.0)

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
        separated = separate_stems(audio_path, output_dir=temp_dir)
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


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: ./venv/bin/python analyze.py <audio_file> [--separate] [--fast] [--standard] [--transcribe] [--yes] [--pitch-note-only] [--stem-dir DIR] [--stem-output-dir DIR] [--pitch-note-backend BACKEND]",
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
            "truePeak": result.get("truePeak"),
            "plr": fast_plr,
            "crestFactor": result.get("crestFactor"),
            "dynamicSpread": result.get("dynamicSpread"),
            "dynamicCharacter": result.get("dynamicCharacter"),
            "textureCharacter": result.get("textureCharacter"),
            "stereoDetail": result.get("stereoDetail"),
            "monoCompatible": fast_mono_compatible,
            "spectralBalance": result.get("spectralBalance"),
            "spectralDetail": result.get("spectralDetail"),
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
        stems = separate_stems(audio_path)
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
    result.update(analyze_time_signature(rhythm_data))
    result.update(analyze_duration_and_sr(mono, sample_rate))

    # LUFS + LRA (needs stereo)
    if stereo is not None:
        result.update(analyze_loudness(stereo))
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

    # Rhythm detail
    result.update(analyze_rhythm_detail(mono, sample_rate, rhythm_data))

    # Shared beat-domain loudness data used by groove + sidechain analyses.
    beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)

    # Groove detail (Tier 2 — always run)
    result.update(analyze_groove(mono, sample_rate, rhythm_data, beat_data))
    result.update(analyze_beats_loudness(mono, sample_rate, rhythm_data, beat_data))
    result.update(analyze_rhythm_timeline(mono, sample_rate, rhythm_data, beat_data))
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

    # Build final output in the exact requested key order
    output = {
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
        "truePeak": result.get("truePeak"),
        "plr": result.get("plr"),
        "crestFactor": result.get("crestFactor"),
        "dynamicSpread": result.get("dynamicSpread"),
        "dynamicCharacter": result.get("dynamicCharacter"),
        "textureCharacter": result.get("textureCharacter"),
        "stereoDetail": result.get("stereoDetail"),
        "monoCompatible": result.get("monoCompatible"),
        "spectralBalance": result.get("spectralBalance"),
        "spectralDetail": result.get("spectralDetail"),
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

    _emit_progress_marker("complete", "Analysis complete.", 1.0)
    print("Done.", file=sys.stderr)
    print(json.dumps(output, indent=2))

    if run_separation and stems is not None:
        cleanup_stems(stems)


if __name__ == "__main__":
    main()
