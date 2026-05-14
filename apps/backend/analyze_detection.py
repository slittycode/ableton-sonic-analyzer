"""Detection analyzers — effects, acid, reverb, vocal, supersaw, and genre."""

import functools
import sys

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None

try:
    import librosa
except ImportError:
    librosa = None  # type: ignore[assignment]

try:
    from scipy import signal as scipy_signal  # type: ignore[import-not-found]
except ImportError:
    scipy_signal = None  # type: ignore[assignment]

from dsp_utils import _safe_db, _compute_bark_db
from analyze_audio_io import _load_stem_mono
from dsp_bandbank import BatchedBandpass


# Phase 1.D #5 — bands for per-band RT60 estimation. Chosen to roughly mirror
# the SPECTRAL_BALANCE_BANDS aggregation but at octave granularity for
# decay-slope stability — wider bands give more energy per band → less
# noise-floor contamination during the dB-decay fit.
_REVERB_BANDS = (
    ("low", 20.0, 250.0),
    ("lowMids", 250.0, 2000.0),
    ("highMids", 2000.0, 8000.0),
    ("highs", 8000.0, 16000.0),
)


@functools.lru_cache(maxsize=4)
def _bandbank_for(sample_rate: int) -> BatchedBandpass:
    """One BatchedBandpass per sample rate (4 slots covers 22050/44100/48000/96000)."""
    return BatchedBandpass(int(sample_rate))


def _bandpass_signal(mono: np.ndarray, sample_rate: int, lo_hz: float, hi_hz: float) -> np.ndarray | None:
    """4th-order Butterworth bandpass via scipy.signal. Returns None on failure.

    Thin wrapper around ``BatchedBandpass.filter_one`` kept for callers that
    pass ``sample_rate`` per call. Output is bit-identical to the previous
    inline implementation; new code should obtain a ``BatchedBandpass``
    directly via ``_bandbank_for(sample_rate)`` and use ``filter_many``.
    """
    return _bandbank_for(sample_rate).filter_one(mono, lo_hz, hi_hz)


# Mirrors apps/backend/analyze_core.py SPECTRAL_BALANCE_BANDS — imported lazily
# below to avoid a circular import (analyze_core imports from this module's
# kin elsewhere). Falls back to a literal copy when the import path is
# unavailable at module-load time.
def _spectral_balance_bands() -> dict[str, tuple[int, int]]:
    try:
        from analyze_core import SPECTRAL_BALANCE_BANDS
        return SPECTRAL_BALANCE_BANDS
    except Exception:
        return {
            "subBass": (20, 80),
            "lowBass": (80, 250),
            "lowMids": (250, 500),
            "mids": (500, 2000),
            "upperMids": (2000, 5000),
            "highs": (5000, 10000),
            "brilliance": (10000, 20000),
        }


def analyze_per_band_transient_density(
    mono: np.ndarray,
    sample_rate: int = 44100,
) -> dict:
    """Per-frequency-band onset density across the 7 spectralBalance bands.

    Phase 1.C #1. Augments the global kick/transient detail with hi-hat
    density / snare hit counts per band, computed via librosa onset
    detection on bandpass-filtered audio. For each band we report:

    - onsetRatePerSecond: detected onset events per second (transient density)
    - meanOnsetStrength: mean onset-envelope value at detected peaks
    - peakOnsetStrength: max onset-envelope value across the track
    - eventCount: number of detected onsets

    Phase 2 cites e.g. ``transientDensityDetail.highs.onsetRatePerSecond``
    to anchor hi-hat-bus recommendations, ``transientDensityDetail.lowBass``
    for kick density, etc.
    """
    if librosa is None or mono is None or getattr(mono, "size", 0) == 0:
        return {"transientDensityDetail": None}

    try:
        from scipy.signal import butter, sosfiltfilt
    except Exception:
        return {"transientDensityDetail": None}

    duration_seconds = float(mono.size) / float(sample_rate) if sample_rate > 0 else 0.0
    if duration_seconds <= 0.0:
        return {"transientDensityDetail": None}

    bands = _spectral_balance_bands()
    result: dict[str, dict] = {}
    nyquist = sample_rate / 2.0
    mono_64 = np.asarray(mono, dtype=np.float64)

    for name, (lo, hi) in bands.items():
        try:
            lo_clamped = max(20.0, min(float(lo), nyquist - 2.0))
            hi_clamped = max(lo_clamped + 1.0, min(float(hi), nyquist - 1.0))
            sos = butter(
                4,
                [lo_clamped / nyquist, hi_clamped / nyquist],
                btype="band",
                output="sos",
            )
            band_audio = sosfiltfilt(sos, mono_64)
            onset_env = librosa.onset.onset_strength(
                y=np.asarray(band_audio, dtype=np.float32),
                sr=sample_rate,
                hop_length=512,
            )
            if onset_env.size == 0:
                result[name] = {
                    "onsetRatePerSecond": 0.0,
                    "meanOnsetStrength": 0.0,
                    "peakOnsetStrength": 0.0,
                    "eventCount": 0,
                }
                continue
            onset_frames = librosa.onset.onset_detect(
                onset_envelope=onset_env,
                sr=sample_rate,
                hop_length=512,
            )
            n_events = int(len(onset_frames))
            rate = n_events / duration_seconds if duration_seconds > 0 else 0.0
            if n_events > 0:
                mean_strength = float(np.mean(onset_env[onset_frames]))
            else:
                mean_strength = 0.0
            peak_strength = float(np.max(onset_env)) if onset_env.size > 0 else 0.0
            result[name] = {
                "onsetRatePerSecond": round(rate, 2),
                "meanOnsetStrength": round(mean_strength, 3),
                "peakOnsetStrength": round(peak_strength, 3),
                "eventCount": n_events,
            }
        except Exception as exc:
            print(f"[warn] transient density {name} failed: {exc}", file=sys.stderr)
            result[name] = {
                "onsetRatePerSecond": 0.0,
                "meanOnsetStrength": 0.0,
                "peakOnsetStrength": 0.0,
                "eventCount": 0,
            }
    return {"transientDensityDetail": result}


def analyze_effects_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    lufs_integrated: float | None = None,
) -> dict:
    """Detect rhythmic gating/stutter patterns using StartStopSilence."""
    try:
        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < 2:
            return {"effectsDetail": None}

        if lufs_integrated is not None and np.isfinite(float(lufs_integrated)):
            gating_threshold = float(
                np.clip(float(lufs_integrated) - 15.0, -55.0, -20.0)
            )
        else:
            gating_threshold = -40.0

        frame_size = 1024
        hop_size = 512
        try:
            silence_detector = es.StartStopSilence(threshold=float(gating_threshold))
        except Exception:
            silence_detector = es.StartStopSilence(
                threshold=int(round(gating_threshold))
            )

        active_flags = []
        prev_stop = None
        for frame in es.FrameGenerator(
            mono_arr, frameSize=frame_size, hopSize=hop_size
        ):
            _start_frame, stop_frame = silence_detector(frame)
            try:
                stop_val = float(stop_frame)
            except Exception:
                stop_val = 0.0
            if not np.isfinite(stop_val):
                stop_val = 0.0
            is_active = stop_val > 0.0 if prev_stop is None else stop_val > prev_stop
            active_flags.append(1 if is_active else 0)
            prev_stop = stop_val

        if len(active_flags) < 3:
            return {
                "effectsDetail": {
                    "gatingDetected": False,
                    "gatingRate": None,
                    "gatingRegularity": 0.0,
                    "gatingEventCount": 0,
                }
            }

        active_arr = np.asarray(active_flags, dtype=np.int32)
        # Remove one-frame state flicker to reduce transient-induced false positives.
        for i in range(1, active_arr.size - 1):
            if (
                active_arr[i - 1] == active_arr[i + 1]
                and active_arr[i] != active_arr[i - 1]
            ):
                active_arr[i] = active_arr[i - 1]

        transition_indices = (
            np.where((active_arr[1:] == 1) & (active_arr[:-1] == 0))[0] + 1
        )
        event_times = (transition_indices.astype(np.float64) * float(hop_size)) / float(
            sample_rate
        )
        event_count = int(event_times.size)

        gating_regularity = 0.0
        gating_rate = None
        ioi = np.array([], dtype=np.float64)
        if event_times.size >= 2:
            ioi = np.diff(event_times)
            ioi = ioi[np.isfinite(ioi) & (ioi > 0.0)]
            if ioi.size > 0:
                mean_ioi = float(np.mean(ioi))
                if mean_ioi > 0:
                    gating_regularity = float(
                        np.clip(1.0 - (np.std(ioi) / mean_ioi), 0.0, 1.0)
                    )

                    bpm = None
                    if rhythm_data is not None and rhythm_data.get("bpm") is not None:
                        bpm = float(rhythm_data.get("bpm"))
                    if bpm is not None and np.isfinite(bpm) and bpm > 0:
                        quarter = 60.0 / bpm
                        candidates = {
                            "quarter": quarter,
                            "8th": quarter / 2.0,
                            "16th": quarter / 4.0,
                        }
                        best_label = None
                        best_error = None
                        for label, target in candidates.items():
                            rel_error = abs(mean_ioi - target) / (target + 1e-9)
                            if best_error is None or rel_error < best_error:
                                best_error = rel_error
                                best_label = label
                        if (
                            best_label is not None
                            and best_error is not None
                            and best_error <= 0.20
                        ):
                            gating_rate = best_label

        gating_detected = bool(
            event_count >= 6 and gating_regularity >= 0.45 and gating_rate is not None
        )
        return {
            "effectsDetail": {
                "gatingDetected": gating_detected,
                "gatingRate": gating_rate,
                "gatingRegularity": round(
                    float(np.clip(gating_regularity, 0.0, 1.0)), 4
                ),
                "gatingEventCount": event_count,
            }
        }
    except Exception as e:
        print(f"[warn] Effects analysis failed: {e}", file=sys.stderr)
        return {"effectsDetail": None}


def analyze_acid_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
) -> dict:
    """Detect TB-303-style acid basslines from resonance, filter sweeps, and rhythm density.

    Ported from sonic-architect-app/services/acidDetection.ts.
    """
    try:
        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < 2:
            return {"acidDetail": None}

        if bpm is None or not np.isfinite(bpm) or bpm <= 0:
            return {"acidDetail": None}

        frame_size = 2048
        hop_size = 512
        acid_bass_low = 100.0
        acid_bass_high = 800.0

        low_bin = int(np.floor(acid_bass_low * frame_size / sample_rate))
        high_bin = min(
            int(np.ceil(acid_bass_high * frame_size / sample_rate)),
            frame_size // 2 - 1,
        )
        if low_bin >= high_bin or low_bin < 0:
            return {"acidDetail": None}

        spectrum_algo = es.Spectrum(size=frame_size)
        windowing = es.Windowing(type="hann", size=frame_size)

        centroids: list[float] = []
        band_rms_values: list[float] = []
        prev_band_rms = 0.0
        onset_count = 0

        for frame in es.FrameGenerator(mono_arr, frameSize=frame_size, hopSize=hop_size):
            if frame.size < frame_size:
                padded = np.zeros(frame_size, dtype=np.float32)
                padded[: frame.size] = frame
                frame = padded
            windowed = windowing(frame)
            spectrum = spectrum_algo(windowed)

            band = spectrum[low_bin : high_bin + 1]
            if band.size == 0:
                continue

            freqs = np.arange(low_bin, high_bin + 1, dtype=np.float64) * (sample_rate / frame_size)
            mags = band.astype(np.float64)
            mag_sum = float(np.sum(mags))
            centroid = float(np.sum(freqs * mags) / mag_sum) if mag_sum > 0 else 0.0
            centroids.append(centroid)

            band_power = float(np.sum(mags ** 2))
            rms = float(np.sqrt(band_power / max(1, band.size)))
            band_rms_values.append(rms)

            if rms > prev_band_rms * 1.5 and rms > 0.001:
                onset_count += 1
            prev_band_rms = rms

        if len(centroids) < 10:
            return {
                "acidDetail": {
                    "isAcid": False,
                    "confidence": 0.0,
                    "resonanceLevel": 0.0,
                    "centroidOscillationHz": 0.0,
                    "bassRhythmDensity": 0.0,
                }
            }

        centroids_arr = np.array(centroids, dtype=np.float64)
        rms_arr = np.array(band_rms_values, dtype=np.float64)

        centroid_oscillation = float(np.std(centroids_arr))
        max_rms = float(np.max(rms_arr))
        mean_rms = float(np.mean(rms_arr))
        resonance_level = min(1.0, (max_rms - mean_rms) / mean_rms) if mean_rms > 0 else 0.0

        duration = float(mono_arr.size) / sample_rate
        bass_rhythm_density = onset_count / duration if duration > 0 else 0.0
        expected_16th_density = (bpm / 60.0) * 4.0
        rhythm_score = min(1.0, bass_rhythm_density / (expected_16th_density * 0.5))
        centroid_score = min(1.0, centroid_oscillation / 100.0)
        confidence = float(np.clip(centroid_score * 0.4 + resonance_level * 0.4 + rhythm_score * 0.2, 0.0, 1.0))
        is_acid = confidence > 0.45

        return {
            "acidDetail": {
                "isAcid": is_acid,
                "confidence": round(confidence, 2),
                "resonanceLevel": round(resonance_level, 2),
                "centroidOscillationHz": round(centroid_oscillation),
                "bassRhythmDensity": round(bass_rhythm_density, 1),
            }
        }
    except Exception as e:
        print(f"[warn] Acid detection failed: {e}", file=sys.stderr)
        return {"acidDetail": None}


def _measure_rt60_from_envelope(
    envelope: np.ndarray,
    hop_ms: float,
    transient_indices: list[int],
    *,
    analysis_window_s: float = 2.0,
    direct_ms: float = 50.0,
) -> tuple[list[float], list[float], list[float]]:
    """Shared RT60-slope-fit helper.

    Returns three parallel lists for each transient that produced a measurable
    decay slope: (rt60_seconds, tail_ratio, pre_delay_ms). Caller decides how
    to aggregate (mean / median / per-band etc.).
    """
    max_decay_frames = int(np.floor((analysis_window_s * 1000.0) / hop_ms))
    direct_end_frames = max(1, int(np.floor(direct_ms / hop_ms)))

    rt60_estimates: list[float] = []
    tail_ratios: list[float] = []
    pre_delay_estimates_ms: list[float] = []

    for t_idx in range(len(transient_indices) - 1):
        start_f = transient_indices[t_idx]
        peak_e = float(envelope[start_f])
        if peak_e < 0.001:
            continue

        end_f = min(start_f + max_decay_frames, transient_indices[t_idx + 1])
        if end_f <= start_f + 5:
            continue

        direct_end = start_f + direct_end_frames
        direct_energy = float(np.sum(envelope[start_f : min(direct_end, end_f)] ** 2))
        tail_energy = float(np.sum(envelope[min(direct_end, end_f) : end_f] ** 2))
        total_energy = direct_energy + tail_energy
        if total_energy > 0:
            tail_ratios.append(tail_energy / total_energy)

        # Pre-delay heuristic: between the peak frame and the first envelope
        # minimum within the next 100 ms, then "the tail starts". For
        # impulsive content this is the dry-tail boundary; for sustained
        # content the minimum may be very close to the peak — that's the
        # honest signal that there's no measurable pre-delay.
        pre_delay_search_end = min(start_f + int(round(100.0 / hop_ms)), end_f)
        if pre_delay_search_end > start_f + 2:
            window_after_peak = envelope[start_f + 1 : pre_delay_search_end]
            if window_after_peak.size > 0:
                local_min_offset = int(np.argmin(window_after_peak))
                pre_delay_ms = (local_min_offset + 1) * hop_ms
                if 0.0 <= pre_delay_ms <= 100.0:
                    pre_delay_estimates_ms.append(pre_delay_ms)

        seg = envelope[start_f:end_f]
        valid = seg > 0
        if not np.any(valid):
            continue
        decay_db = 20.0 * np.log10(np.clip(seg[valid] / peak_e, 1e-10, None))
        if decay_db.size < 5:
            continue

        n = decay_db.size
        x = np.arange(n, dtype=np.float64)
        x_mean, y_mean = float(np.mean(x)), float(np.mean(decay_db))
        num = float(np.sum((x - x_mean) * (decay_db - y_mean)))
        den = float(np.sum((x - x_mean) ** 2))
        if den == 0:
            continue
        slope = num / den
        if slope >= 0:
            continue
        rt60 = abs(-60.0 / (slope / (hop_ms / 1000.0)))
        if 0.0 < rt60 < 5.0:
            rt60_estimates.append(rt60)

    return rt60_estimates, tail_ratios, pre_delay_estimates_ms


def analyze_reverb_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
) -> dict:
    """Estimate RT60 reverberation time from energy decay slopes after transients.

    Ported from sonic-architect-app/services/reverbAnalysis.ts. Phase 1.D #5
    adds:
    - `perBandRt60` — RT60 estimated separately in 4 octave bands (low /
      lowMids / highMids / highs) by bandpassing the input before envelope
      extraction. Each band measures the same transient stream.
    - `preDelayMs` — median time between direct peak and first envelope
      minimum within the next 100 ms, across all detected transients. A
      proxy for reverb pre-delay; close to zero on dry sources.
    """
    _TRANSIENT_THRESHOLD = 2.0
    _MIN_TRANSIENTS = 4
    _ANALYSIS_WINDOW_S = 2.0
    _HOP_MS = 20.0
    _SMOOTH_WINDOW = 10
    _DIRECT_MS = 50.0

    try:
        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < 2:
            return {"reverbDetail": None}

        if bpm is None or not np.isfinite(bpm) or bpm <= 0:
            bpm = 120.0

        hop_samples = max(1, int(round((_HOP_MS / 1000.0) * sample_rate)))
        n_frames = (mono_arr.size - hop_samples) // hop_samples + 1
        envelope = np.zeros(n_frames, dtype=np.float64)
        for i in range(n_frames):
            start = i * hop_samples
            seg = mono_arr[start : start + hop_samples].astype(np.float64)
            envelope[i] = float(np.sqrt(np.mean(seg ** 2)))

        if envelope.size < 20:
            return {"reverbDetail": {"rt60": None, "isWet": False, "tailEnergyRatio": None, "measured": False, "perBandRt60": None, "preDelayMs": None}}

        min_dist_frames = max(1, int(np.floor((((60.0 / bpm) * 1000.0) / _HOP_MS) * 0.5)))
        transient_indices: list[int] = []
        running_avg = 0.0

        for i in range(envelope.size):
            if i < _SMOOTH_WINDOW:
                running_avg = float(np.mean(envelope[: i + 1]))
            else:
                running_avg = (running_avg * (_SMOOTH_WINDOW - 1) + envelope[i]) / _SMOOTH_WINDOW

            if envelope[i] > running_avg * _TRANSIENT_THRESHOLD and envelope[i] > 0.001:
                last = transient_indices[-1] if transient_indices else -min_dist_frames
                if i - last >= min_dist_frames:
                    transient_indices.append(i)

        if len(transient_indices) < _MIN_TRANSIENTS:
            return {"reverbDetail": {"rt60": None, "isWet": False, "tailEnergyRatio": None, "measured": False, "perBandRt60": None, "preDelayMs": None}}

        rt60_estimates, tail_ratios, pre_delay_estimates_ms = _measure_rt60_from_envelope(
            envelope,
            hop_ms=_HOP_MS,
            transient_indices=transient_indices,
            analysis_window_s=_ANALYSIS_WINDOW_S,
            direct_ms=_DIRECT_MS,
        )

        if not rt60_estimates:
            return {"reverbDetail": {"rt60": None, "isWet": False, "tailEnergyRatio": None, "measured": False, "perBandRt60": None, "preDelayMs": None}}

        avg_rt60 = float(np.mean(rt60_estimates))
        avg_tail = float(np.mean(tail_ratios)) if tail_ratios else 0.2
        capped_rt60 = round(min(3.0, avg_rt60), 2)

        # Per-band RT60: re-use the SAME transient indices on the broadband
        # envelope so each band measures the same events. Bandpass the raw
        # signal once (filter_many designs each SOS only once and reuses
        # them), recompute the per-band envelope, then run the slope fit.
        # Requires scipy.signal — if unavailable, omit per-band.
        per_band_rt60: dict[str, float] | None = None
        if scipy_signal is not None:
            bandbank = _bandbank_for(sample_rate)
            filtered_bands = bandbank.filter_many(mono_arr, _REVERB_BANDS, dtype=np.float32)
            per_band: dict[str, float] = {}
            for band_name, _lo, _hi in _REVERB_BANDS:
                filtered = filtered_bands.get(band_name)
                if filtered is None:
                    continue
                band_envelope = np.zeros(n_frames, dtype=np.float64)
                for i in range(n_frames):
                    s = i * hop_samples
                    seg_b = filtered[s : s + hop_samples].astype(np.float64)
                    band_envelope[i] = float(np.sqrt(np.mean(seg_b ** 2)))
                band_rt60, _, _ = _measure_rt60_from_envelope(
                    band_envelope,
                    hop_ms=_HOP_MS,
                    transient_indices=transient_indices,
                    analysis_window_s=_ANALYSIS_WINDOW_S,
                    direct_ms=_DIRECT_MS,
                )
                if band_rt60:
                    per_band[band_name] = round(min(3.0, float(np.mean(band_rt60))), 2)
            if per_band:
                per_band_rt60 = per_band

        median_pre_delay_ms: float | None = None
        if pre_delay_estimates_ms:
            median_pre_delay_ms = round(float(np.median(pre_delay_estimates_ms)), 2)

        return {
            "reverbDetail": {
                "rt60": capped_rt60,
                "isWet": avg_rt60 > 0.5,
                "tailEnergyRatio": round(float(np.clip(avg_tail, 0.0, 1.0)), 2),
                "measured": True,
                "perBandRt60": per_band_rt60,
                "preDelayMs": median_pre_delay_ms,
            }
        }
    except Exception as e:
        print(f"[warn] Reverb analysis failed: {e}", file=sys.stderr)
        return {"reverbDetail": None}


def analyze_vocal_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
    stems: dict | None = None,
) -> dict:
    """Detect vocal presence via spectral energy ratio, formant peaks, and MFCC likelihood.

    Ported from sonic-architect-app/services/vocalDetection.ts.
    Uses Essentia MFCC (already computed elsewhere), Spectrum, and SpectralPeaks
    for formant detection instead of browser FFT.
    """
    try:
        # Demucs-ghost-stem check #1: vocals-stem RMS vs full-mix RMS. A vocals
        # stem on a vocal-led track typically lands at 15-45% of full-mix RMS;
        # a Demucs ghost stem on a track with NO real vocal drops below ~5%
        # because Demucs has nothing real to extract and emits residual leakage.
        full_mix_rms = float(
            np.sqrt(np.mean(np.asarray(mono, dtype=np.float32) ** 2))
        ) if mono is not None and getattr(mono, "size", 0) > 0 else 0.0

        source_mono = _load_stem_mono(stems, "vocals", sample_rate)
        stem_energy_ratio: float | None = None
        if source_mono is not None and full_mix_rms > 1e-6:
            stem_rms = float(
                np.sqrt(np.mean(np.asarray(source_mono, dtype=np.float32) ** 2))
            )
            stem_energy_ratio = float(min(2.0, stem_rms / full_mix_rms))

        # Demucs-ghost-stem check #2: vocals-vs-other cross-correlation. The
        # energy check above only catches *quiet* ghost stems; tracks with a
        # melodic lead that Demucs misclassifies push real lead-synth content
        # into the vocals stem at 20-40% RMS — energy alone won't flag those.
        # But a genuine vocal is uncorrelated with the synth/melody stem (they
        # come from different sources, different mics, different rooms); a
        # misclassified lead is heavily correlated with the "other" stem
        # because both are looking at the same underlying source. We compute
        # Pearson correlation on a 200 Hz envelope-rate downsample, which is
        # robust to phase differences while preserving amplitude structure.
        stem_other_correlation: float | None = None
        if source_mono is not None and stems is not None:
            try:
                other_mono = _load_stem_mono(stems, "other", sample_rate)
                if (
                    other_mono is not None
                    and source_mono is not None
                    and getattr(source_mono, "size", 0) > sample_rate // 100
                    and getattr(other_mono, "size", 0) > sample_rate // 100
                ):
                    # Decimate to a 200 Hz envelope via |signal| then mean-pool.
                    target_rate_hz = 200
                    decimate = max(1, sample_rate // target_rate_hz)
                    v_arr = np.abs(np.asarray(source_mono, dtype=np.float32))
                    o_arr = np.abs(np.asarray(other_mono, dtype=np.float32))
                    common = min(v_arr.size, o_arr.size)
                    common -= common % decimate
                    if common >= decimate * 4:
                        v_env = v_arr[:common].reshape(-1, decimate).mean(axis=1)
                        o_env = o_arr[:common].reshape(-1, decimate).mean(axis=1)
                        v_std = float(np.std(v_env))
                        o_std = float(np.std(o_env))
                        if v_std > 1e-9 and o_std > 1e-9:
                            corr = float(
                                np.mean(
                                    (v_env - v_env.mean()) * (o_env - o_env.mean())
                                )
                                / (v_std * o_std)
                            )
                            if np.isfinite(corr):
                                stem_other_correlation = float(
                                    max(-1.0, min(1.0, corr))
                                )
            except Exception:
                stem_other_correlation = None

        if source_mono is None:
            source_mono = mono
        mono_arr = np.asarray(source_mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < 2048:
            return {"vocalDetail": None}

        frame_size = 2048
        hop_size = 512

        # --- Frequency band boundaries ---
        vocal_fund_low = 150.0   # Hz — low male voice
        vocal_fund_high = 1500.0 # Hz — high female voice
        formant_low = 300.0      # Hz — first formant
        formant_high = 4000.0    # Hz — third formant

        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)

        vocal_energy_sum = 0.0
        formant_energy_sum = 0.0
        total_energy_sum = 0.0

        # Expected formant centre frequencies for an average adult voice
        expected_formants = [500.0, 1500.0, 2500.0]
        formant_tolerance = 100.0  # Hz — tightened from 200 to reject sustained
                                   # synth harmonics that trivially fall inside a
                                   # 400 Hz window around each expected formant.
        formant_frames = 0
        # Per-sampled-frame record of which expected formants were matched and at
        # what peak frequency. Used after the loop to compute a temporal-stability
        # penalty: real vocals shift formants by 100+ Hz across syllables; a
        # sustained synth lead has near-static "formants" because the harmonic
        # series of a fixed pitch lands at nearly the same bin every frame.
        per_frame_matches: list[list[float | None]] = []

        spectral_peaks_algo = es.SpectralPeaks(
            orderBy="frequency",
            magnitudeThreshold=0.00001,
            maxPeaks=60,
            sampleRate=sample_rate,
        )

        for frame in es.FrameGenerator(mono_arr, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum(window(frame))
            if spec.size == 0:
                continue

            freq_resolution = float(sample_rate) / float(frame_size)
            # Band energy via spectrum bins
            for k in range(spec.size):
                freq = k * freq_resolution
                energy = float(spec[k]) ** 2
                total_energy_sum += energy
                if vocal_fund_low <= freq <= vocal_fund_high:
                    vocal_energy_sum += energy
                if formant_low <= freq <= formant_high:
                    formant_energy_sum += energy

            # Formant peak matching via SpectralPeaks (every 4th frame for speed).
            # Record the *closest* matched peak per expected formant so we can
            # later compute the temporal variance of each formant's position.
            formant_frames += 1
            if formant_frames % 4 == 0:
                peak_freqs, _peak_mags = spectral_peaks_algo(spec)
                matched: list[float | None] = []
                for ef in expected_formants:
                    closest: float | None = None
                    closest_dist = formant_tolerance
                    for pf in peak_freqs:
                        d = abs(float(pf) - ef)
                        if d < closest_dist:
                            closest_dist = d
                            closest = float(pf)
                    matched.append(closest)
                per_frame_matches.append(matched)

        vocal_energy_ratio = vocal_energy_sum / total_energy_sum if total_energy_sum > 0 else 0.0

        sampled_formant_frames = max(1, len(per_frame_matches))
        # 1) Count frames with at least 2 of 3 expected formants matched
        #    (single-formant matches are noise; real vocal phones produce
        #    coherent F1+F2 or F1+F2+F3 patterns).
        coherent_frames = sum(
            1 for matches in per_frame_matches
            if sum(1 for m in matches if m is not None) >= 2
        )
        coherent_fraction = coherent_frames / sampled_formant_frames

        # 2) Temporal-stability penalty: compute std-dev of the matched peak
        #    frequency for each expected formant across the sampled frames.
        #    A singer's formants drift 100-500 Hz with syllables and vibrato;
        #    a sustained synth tone produces near-zero variance.
        formant_movement_hz = 0.0
        if sampled_formant_frames >= 4:
            stds: list[float] = []
            for slot in range(len(expected_formants)):
                values = [
                    matches[slot]
                    for matches in per_frame_matches
                    if matches[slot] is not None
                ]
                if len(values) >= 4:
                    stds.append(float(np.std(values)))
            if stds:
                formant_movement_hz = float(np.mean(stds))
        # Map mean std-dev to a [0.2, 1.0] multiplier. Below ~30 Hz movement
        # the score is clamped at 0.2 (static-tone penalty); above ~120 Hz
        # it saturates at 1.0 (normal vocal motion).
        if formant_movement_hz <= 30.0:
            movement_factor = 0.2
        elif formant_movement_hz >= 120.0:
            movement_factor = 1.0
        else:
            movement_factor = 0.2 + 0.8 * (formant_movement_hz - 30.0) / 90.0

        formant_strength = min(1.0, coherent_fraction * movement_factor)

        # --- MFCC vocal likelihood ---
        mfcc_algo = es.MFCC(
            numberCoefficients=13,
            inputSize=frame_size // 2 + 1,
            sampleRate=sample_rate,
        )
        mfcc_accum = np.zeros(13, dtype=np.float64)
        mfcc_count = 0
        for frame in es.FrameGenerator(mono_arr, frameSize=frame_size, hopSize=hop_size * 4):
            spec = spectrum(window(frame))
            _, coeffs = mfcc_algo(spec)
            coeffs_arr = np.asarray(coeffs, dtype=np.float64)
            if coeffs_arr.size >= 13 and np.all(np.isfinite(coeffs_arr[:13])):
                mfcc_accum += coeffs_arr[:13]
                mfcc_count += 1

        if mfcc_count > 0:
            avg_mfcc = mfcc_accum / mfcc_count
            low_e = float(np.sum(np.abs(avg_mfcc[1:4])))
            mid_e = float(np.sum(np.abs(avg_mfcc[4:9])))
            high_e = float(np.sum(np.abs(avg_mfcc[9:13])))
            total_e = low_e + mid_e + high_e
            if total_e > 0:
                low_r = low_e / total_e
                mid_r = mid_e / total_e
                high_r = high_e / total_e
                mfcc_likelihood = (
                    (1.0 - abs(low_r - 0.40))
                    + (1.0 - abs(mid_r - 0.35))
                    + (1.0 - abs(high_r - 0.25))
                ) / 3.0
            else:
                mfcc_likelihood = 0.5
        else:
            mfcc_likelihood = 0.5

        # --- Composite score (35 / 35 / 30 weighting) ---
        energy_score = min(1.0, max(0.0, (vocal_energy_ratio - 0.1) / 0.3))
        confidence = energy_score * 0.35 + formant_strength * 0.35 + mfcc_likelihood * 0.30

        # Demucs-ghost-stem scaling #1 (low energy): when a vocals stem was
        # loaded and its RMS is below ~5% of the full-mix RMS, the "vocals"
        # Demucs produced are leakage from a track with no real vocal content.
        # Scale composite confidence down linearly: at 0% stem energy → 0.0×;
        # at 5% stem energy → 1.0× (no penalty). Above 5% the multiplier stays
        # at 1.0.
        if stem_energy_ratio is not None and stem_energy_ratio < 0.05:
            ghost_multiplier = max(0.0, stem_energy_ratio / 0.05)
            confidence = confidence * ghost_multiplier

        # Demucs-ghost-stem scaling #2 (other-correlation): when the vocals
        # stem is highly correlated with the "other" stem at the 200 Hz
        # envelope rate, Demucs is splitting one source (typically a melodic
        # lead) into two stems; the vocals stem is then misclassified content
        # rather than a genuine voice. Empirical thresholds — corr ≤ 0.30 is
        # uncorrelated and gets no penalty; corr ≥ 0.55 is heavily entangled
        # and gets a 0.30× multiplier; in between we ramp.
        if stem_other_correlation is not None and stem_other_correlation > 0.30:
            if stem_other_correlation >= 0.55:
                corr_multiplier = 0.30
            else:
                corr_multiplier = 1.0 - (
                    (stem_other_correlation - 0.30) / 0.25
                ) * 0.70
            confidence = confidence * corr_multiplier

        # Threshold raised from 0.45 to 0.55 (2026-05-12): the temporal-stability
        # check on formant_strength now downweights synth leads that previously
        # scored ~1.0 there. With the tighter formant logic, real vocals on
        # representative material still clear 0.55 (energy_score≈0.7 +
        # formant_strength≈0.6 + mfcc_likelihood≈0.7 ≈ 0.66 composite).
        #
        # Hard formant-strength gate (2026-05-12 follow-up): a sustained synth
        # lead can still drag composite confidence above 0.55 via high
        # energy_score + mfcc_likelihood, even with the static-formant penalty.
        # Require formant_strength > 0.3 for the boolean decision — without
        # measurable formant motion, the content is melodic/instrumental, not
        # vocal phonemes. The numeric confidence field is unchanged so the UI
        # can still display the hedged value; only `hasVocals` flips.
        has_vocals = confidence > 0.55 and formant_strength > 0.3

        return {
            "vocalDetail": {
                "hasVocals": has_vocals,
                "confidence": round(float(confidence), 2),
                "vocalEnergyRatio": round(float(vocal_energy_ratio), 2),
                "formantStrength": round(float(formant_strength), 2),
                "mfccLikelihood": round(float(mfcc_likelihood), 2),
                "stemEnergyRatio": (
                    round(float(stem_energy_ratio), 3)
                    if stem_energy_ratio is not None else None
                ),
                "stemOtherCorrelation": (
                    round(float(stem_other_correlation), 3)
                    if stem_other_correlation is not None else None
                ),
            }
        }
    except Exception as e:
        print(f"[warn] Vocal detection failed: {e}", file=sys.stderr)
        return {"vocalDetail": None}


def analyze_supersaw_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
    stems: dict | None = None,
) -> dict:
    """Detect detuned sawtooth stacks characteristic of supersaw patches.

    Ported from sonic-architect-app/services/supersawDetection.ts.
    The JS version uses pitch bend data; in Python we use Essentia
    SpectralPeaks to find near-unison partials, measure detune spread, and
    check for sawtooth harmonic decay patterns.
    """
    try:
        source_mono = _load_stem_mono(stems, "other", sample_rate)
        if source_mono is None:
            source_mono = mono
        mono_arr = np.asarray(source_mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < 4096:
            return {"supersawDetail": None}

        frame_size = 4096
        hop_size = 2048

        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        spectral_peaks = es.SpectralPeaks(
            orderBy="magnitude",
            magnitudeThreshold=0.00001,
            maxPeaks=80,
            sampleRate=sample_rate,
        )

        # Supersaw range: 200 Hz – 5 kHz
        sup_low = 200.0
        sup_high = 5000.0

        all_voice_counts: list[int] = []
        all_detune_cents: list[float] = []
        frames_analyzed = 0

        for frame in es.FrameGenerator(mono_arr, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum(window(frame))
            peak_freqs, peak_mags = spectral_peaks(spec)

            # Filter to supersaw range
            in_range = [
                (float(f), float(m))
                for f, m in zip(peak_freqs, peak_mags)
                if sup_low <= float(f) <= sup_high and float(m) > 0
            ]
            if len(in_range) < 3:
                continue
            frames_analyzed += 1

            # Group peaks into clusters of near-unison voices
            # Two peaks within 50 cents are considered "near-unison"
            in_range.sort(key=lambda x: x[0])
            clusters: list[list[float]] = []
            current_cluster: list[float] = [in_range[0][0]]

            for i in range(1, len(in_range)):
                prev_f = current_cluster[-1]
                cur_f = in_range[i][0]
                if prev_f > 0:
                    cents = 1200.0 * abs(np.log2(cur_f / prev_f))
                else:
                    cents = 999.0
                if cents < 50.0:
                    current_cluster.append(cur_f)
                else:
                    if len(current_cluster) >= 3:
                        clusters.append(current_cluster)
                    current_cluster = [cur_f]
            if len(current_cluster) >= 3:
                clusters.append(current_cluster)

            for cluster in clusters:
                all_voice_counts.append(len(cluster))
                # Measure detune spread within cluster
                for j in range(1, len(cluster)):
                    if cluster[j - 1] > 0:
                        d = 1200.0 * abs(np.log2(cluster[j] / cluster[j - 1]))
                        if 5.0 < d < 50.0:
                            all_detune_cents.append(d)

        if frames_analyzed == 0 or len(all_voice_counts) == 0:
            return {
                "supersawDetail": {
                    "isSupersaw": False,
                    "confidence": 0.0,
                    "voiceCount": 0,
                    "avgDetuneCents": 0.0,
                    "spectralComplexity": 0.0,
                }
            }

        avg_voice_count = float(np.mean(all_voice_counts))
        avg_detune = float(np.mean(all_detune_cents)) if all_detune_cents else 0.0

        # Spectral complexity — number of peaks per frame in supersaw range
        spectral_complexity = avg_voice_count

        # --- Scoring ---
        voice_count_score = min(1.0, max(0.0, (avg_voice_count - 3.0) / 4.0))

        # Detune score: peak at 20 cents, falling off
        if avg_detune < 5.0 or avg_detune > 50.0:
            detune_score = 0.0
        else:
            distance = abs(avg_detune - 20.0)
            if distance <= 10.0:
                detune_score = 1.0 - distance * 0.05
            else:
                detune_score = max(0.0, 0.5 - (distance - 10.0) * 0.05)

        consistency_score = min(1.0, len(all_voice_counts) / max(1, frames_analyzed) * 2.0)

        confidence = voice_count_score * 0.35 + detune_score * 0.35 + consistency_score * 0.30
        is_supersaw = confidence > 0.4 and avg_voice_count >= 3.0

        return {
            "supersawDetail": {
                "isSupersaw": is_supersaw,
                "confidence": round(float(min(1.0, confidence)), 2),
                "voiceCount": round(float(avg_voice_count)),
                "avgDetuneCents": round(float(avg_detune), 1),
                "spectralComplexity": round(float(spectral_complexity), 1),
            }
        }
    except Exception as e:
        print(f"[warn] Supersaw detection failed: {e}", file=sys.stderr)
        return {"supersawDetail": None}




_GENRE_SIGNATURES: list[dict] = [
    # AMBIENT / DOWNTEMPO
    {"id": "ambient-drone", "bpm": (40, 90), "subBassDb": (-40, -20), "crestFactor": (12, 25), "onsetDensity": (0.5, 3), "spectralCentroid": (1000, 4000), "sidechainStrength": (0, 0.15), "bassDecay": (0.8, 1.5), "rt60": (1.0, 3.0)},
    {"id": "ambient-techno", "bpm": (90, 120), "subBassDb": (-30, -15), "crestFactor": (10, 20), "onsetDensity": (2, 5), "spectralCentroid": (1500, 4500), "sidechainStrength": (0, 0.2), "bassDecay": (0.5, 1.0), "rt60": (0.6, 1.5)},
    {"id": "dub-techno", "bpm": (100, 125), "subBassDb": (-28, -12), "crestFactor": (8, 16), "onsetDensity": (2, 5), "spectralCentroid": (1200, 3500), "sidechainStrength": (0, 0.25), "bassDecay": (0.6, 1.2), "rt60": (0.8, 2.0)},
    # DEEP / ORGANIC HOUSE
    {"id": "deep-house", "bpm": (118, 126), "subBassDb": (-24, -10), "crestFactor": (7, 13), "onsetDensity": (3, 7), "spectralCentroid": (1800, 4000), "sidechainStrength": (0.35, 0.65), "bassDecay": (0.2, 0.5)},
    {"id": "organic-house", "bpm": (115, 124), "subBassDb": (-26, -14), "crestFactor": (9, 18), "onsetDensity": (3, 6), "spectralCentroid": (2000, 4500), "sidechainStrength": (0.25, 0.5), "bassDecay": (0.3, 0.6)},
    # HOUSE VARIANTS
    {"id": "classic-house", "bpm": (120, 130), "subBassDb": (-22, -10), "crestFactor": (6, 12), "onsetDensity": (4, 8), "spectralCentroid": (2000, 4500), "sidechainStrength": (0.4, 0.7), "bassDecay": (0.2, 0.45)},
    {"id": "tech-house", "bpm": (124, 130), "subBassDb": (-20, -8), "crestFactor": (5, 10), "onsetDensity": (4, 7), "spectralCentroid": (2200, 5000), "sidechainStrength": (0.45, 0.75), "bassDecay": (0.15, 0.4)},
    {"id": "progressive-house", "bpm": (126, 132), "subBassDb": (-22, -10), "crestFactor": (6, 11), "onsetDensity": (4, 8), "spectralCentroid": (1800, 4500), "sidechainStrength": (0.35, 0.6), "bassDecay": (0.3, 0.55)},
    {"id": "afro-house", "bpm": (118, 126), "subBassDb": (-24, -12), "crestFactor": (7, 14), "onsetDensity": (5, 10), "spectralCentroid": (2500, 5500), "sidechainStrength": (0.3, 0.55), "bassDecay": (0.25, 0.5)},
    # TECHNO VARIANTS
    {"id": "minimal-techno", "bpm": (125, 130), "subBassDb": (-24, -14), "crestFactor": (7, 13), "onsetDensity": (2, 5), "spectralCentroid": (1500, 4000), "sidechainStrength": (0.1, 0.35), "bassDecay": (0.4, 0.7), "rt60": (0.2, 0.6)},
    {"id": "melodic-techno", "bpm": (122, 128), "subBassDb": (-22, -12), "crestFactor": (8, 15), "onsetDensity": (3, 6), "spectralCentroid": (2000, 5000), "sidechainStrength": (0.25, 0.5), "bassDecay": (0.4, 0.7)},
    {"id": "driving-techno", "bpm": (127, 133), "subBassDb": (-18, -8), "crestFactor": (4, 8), "onsetDensity": (5, 9), "spectralCentroid": (1500, 4000), "sidechainStrength": (0.3, 0.6), "bassDecay": (0.5, 0.85), "rt60": (0.1, 0.5)},
    {"id": "industrial-techno", "bpm": (130, 145), "subBassDb": (-16, -4), "crestFactor": (3, 8), "onsetDensity": (6, 12), "spectralCentroid": (1800, 5000), "sidechainStrength": (0.25, 0.55), "bassDecay": (0.4, 0.8), "kickDistortion": (0.2, 0.6)},
    {"id": "hard-techno", "bpm": (145, 160), "subBassDb": (-14, -4), "crestFactor": (3, 8), "onsetDensity": (7, 14), "spectralCentroid": (2000, 5500), "sidechainStrength": (0.3, 0.6), "bassDecay": (0.4, 0.75), "rt60": (0.1, 0.4), "kickDistortion": (0.15, 0.5)},
    {"id": "acid-techno", "bpm": (125, 135), "subBassDb": (-20, -8), "crestFactor": (6, 12), "onsetDensity": (5, 10), "spectralCentroid": (2200, 6000), "sidechainStrength": (0.3, 0.6), "bassDecay": (0.3, 0.6)},
    {"id": "detroit-techno", "bpm": (125, 135), "subBassDb": (-22, -10), "crestFactor": (7, 14), "onsetDensity": (4, 8), "spectralCentroid": (1800, 4500), "sidechainStrength": (0.2, 0.45), "bassDecay": (0.4, 0.75)},
    # TRANCE & PROGRESSIVE
    {"id": "trance", "bpm": (136, 142), "subBassDb": (-20, -8), "crestFactor": (6, 12), "onsetDensity": (4, 8), "spectralCentroid": (2000, 5000), "sidechainStrength": (0.25, 0.55), "bassDecay": (0.35, 0.65)},
    {"id": "psytrance", "bpm": (140, 148), "subBassDb": (-18, -6), "crestFactor": (5, 11), "onsetDensity": (7, 14), "spectralCentroid": (2200, 5500), "sidechainStrength": (0.35, 0.65), "bassDecay": (0.3, 0.6)},
    # BASS MUSIC
    {"id": "dubstep", "bpm": (138, 145), "subBassDb": (-18, -4), "crestFactor": (7, 14), "onsetDensity": (3, 7), "spectralCentroid": (1200, 3500), "sidechainStrength": (0.2, 0.5), "bassDecay": (0.6, 1.2)},
    {"id": "bass-house", "bpm": (124, 130), "subBassDb": (-18, -6), "crestFactor": (5, 10), "onsetDensity": (5, 9), "spectralCentroid": (2000, 4800), "sidechainStrength": (0.4, 0.7), "bassDecay": (0.25, 0.5)},
    # D&B & BREAKS
    {"id": "drum-bass", "bpm": (168, 180), "subBassDb": (-18, -6), "crestFactor": (6, 13), "onsetDensity": (8, 18), "spectralCentroid": (2000, 5000), "sidechainStrength": (0.3, 0.6), "bassDecay": (0.3, 0.6)},
    {"id": "neurofunk", "bpm": (170, 180), "subBassDb": (-16, -4), "crestFactor": (5, 11), "onsetDensity": (9, 20), "spectralCentroid": (2200, 5500), "sidechainStrength": (0.25, 0.55), "bassDecay": (0.25, 0.55)},
    {"id": "breaks", "bpm": (125, 135), "subBassDb": (-22, -10), "crestFactor": (7, 14), "onsetDensity": (5, 10), "spectralCentroid": (2200, 5200), "sidechainStrength": (0.25, 0.55), "bassDecay": (0.3, 0.6)},
    # UK BASS / GARAGE
    {"id": "uk-garage", "bpm": (128, 136), "subBassDb": (-20, -8), "crestFactor": (6, 12), "onsetDensity": (5, 10), "spectralCentroid": (2200, 5000), "sidechainStrength": (0.35, 0.65), "bassDecay": (0.25, 0.5)},
    {"id": "bassline", "bpm": (130, 138), "subBassDb": (-18, -6), "crestFactor": (5, 11), "onsetDensity": (6, 12), "spectralCentroid": (2500, 5500), "sidechainStrength": (0.4, 0.7), "bassDecay": (0.2, 0.45)},
    # LEGACY / BROAD GENRES
    {"id": "edm", "bpm": (120, 135), "subBassDb": (-16, -8), "crestFactor": (5, 9), "onsetDensity": (4, 10), "spectralCentroid": (1500, 4000), "sidechainStrength": (0.3, 0.6), "bassDecay": (0.25, 0.5)},
    {"id": "hiphop", "bpm": (70, 110), "subBassDb": (-16, -4), "crestFactor": (7, 11), "onsetDensity": (2, 7), "spectralCentroid": (800, 2500), "sidechainStrength": (0.1, 0.4), "bassDecay": (0.3, 0.6)},
    {"id": "rock", "bpm": (100, 160), "subBassDb": (-30, -15), "crestFactor": (9, 14), "onsetDensity": (4, 10), "spectralCentroid": (1500, 4500), "sidechainStrength": (0.05, 0.25), "bassDecay": (0.2, 0.5)},
    {"id": "pop", "bpm": (95, 130), "subBassDb": (-20, -10), "crestFactor": (6, 10), "onsetDensity": (3, 8), "spectralCentroid": (1200, 3500), "sidechainStrength": (0.2, 0.5), "bassDecay": (0.25, 0.5)},
    {"id": "acoustic", "bpm": (70, 140), "subBassDb": (-40, -22), "crestFactor": (12, 20), "onsetDensity": (1, 5), "spectralCentroid": (1000, 3000), "sidechainStrength": (0, 0.1), "bassDecay": (0.3, 0.8)},
    {"id": "techno", "bpm": (125, 150), "subBassDb": (-18, -6), "crestFactor": (4, 9), "onsetDensity": (4, 10), "spectralCentroid": (1200, 3500), "sidechainStrength": (0.2, 0.5), "bassDecay": (0.4, 0.8)},
    {"id": "house", "bpm": (118, 132), "subBassDb": (-20, -8), "crestFactor": (5, 10), "onsetDensity": (3, 8), "spectralCentroid": (1200, 3500), "sidechainStrength": (0.35, 0.65), "bassDecay": (0.2, 0.45)},
    {"id": "ambient", "bpm": (60, 110), "subBassDb": (-32, -16), "crestFactor": (10, 20), "onsetDensity": (0, 3), "spectralCentroid": (500, 2500), "sidechainStrength": (0, 0.15), "bassDecay": (0.6, 1.5)},
    {"id": "dnb", "bpm": (160, 180), "subBassDb": (-16, -5), "crestFactor": (6, 12), "onsetDensity": (6, 14), "spectralCentroid": (1500, 4000), "sidechainStrength": (0.25, 0.55), "bassDecay": (0.3, 0.6)},
    {"id": "garage", "bpm": (128, 142), "subBassDb": (-16, -5), "crestFactor": (6, 11), "onsetDensity": (4, 9), "spectralCentroid": (1500, 3500), "sidechainStrength": (0.3, 0.6), "bassDecay": (0.25, 0.5)},
]

_GENRE_FAMILY_MAP: dict[str, str] = {
    "house": "house", "classic-house": "house", "tech-house": "house",
    "deep-house": "house", "organic-house": "house", "progressive-house": "house",
    "afro-house": "house", "bass-house": "house",
    "techno": "techno", "minimal-techno": "techno", "melodic-techno": "techno",
    "driving-techno": "techno", "industrial-techno": "techno", "hard-techno": "techno",
    "acid-techno": "techno", "detroit-techno": "techno", "dub-techno": "techno",
    "ambient-techno": "techno",
    "drum-bass": "dnb", "neurofunk": "dnb", "dnb": "dnb",
    "ambient": "ambient", "ambient-drone": "ambient",
    "trance": "trance", "psytrance": "trance",
    "dubstep": "dubstep",
    "breaks": "breaks",
}


def _genre_range_score(
    value: float, range_min: float, range_max: float, steepness: float = 2.0
) -> float:
    """Gaussian-like score: 1.0 inside [range_min, range_max], decays outside."""
    if range_min <= value <= range_max:
        return 1.0
    center = (range_min + range_max) / 2.0
    half_range = (range_max - range_min) / 2.0
    if half_range <= 0:
        return 0.0
    distance = abs(value - center)
    normalized_dist = (distance - half_range) / half_range
    return max(0.0, 1.0 - normalized_dist ** steepness)


def analyze_genre_detail(result: dict) -> dict:
    """Classify genre using all previously computed detector outputs.

    Designed to run last in the pipeline so it can consume sidechainDetail,
    bassDetail, reverbDetail, kickDetail, acidDetail, and supersawDetail
    without re-running DSP. Feature weights mirror genreClassifierEnhanced.ts:
    sidechain strength (0.95) and bass decay (0.85) are the primary
    discriminators for electronic subgenres.
    """
    try:
        spectral_balance = result.get("spectralBalance") or {}
        spectral_detail = result.get("spectralDetail") or {}
        rhythm_detail = result.get("rhythmDetail") or {}
        sidechain = result.get("sidechainDetail") or {}
        bass_det = result.get("bassDetail") or {}
        reverb_det = result.get("reverbDetail") or {}
        kick_det = result.get("kickDetail") or {}
        acid_det = result.get("acidDetail") or {}
        supersaw_det = result.get("supersawDetail") or {}
        vocal_det = result.get("vocalDetail") or {}

        # Extract core features, tracking which have real (non-fallback) values.
        # If fewer than 3 of 7 core features are present, the classifier
        # abstains rather than forcing a genre from default values.
        _bpm_raw = result.get("bpm")
        _crest_raw = result.get("crestFactor")
        _sub_raw = spectral_balance.get("subBass")
        _cent_raw = spectral_detail.get("spectralCentroid")
        _onset_raw = rhythm_detail.get("onsetRate")
        _sc_raw = sidechain.get("pumpingStrength")
        _bd_raw = bass_det.get("averageDecayMs")

        real_feature_count = sum(
            v is not None
            for v in (_bpm_raw, _crest_raw, _sub_raw, _cent_raw, _onset_raw, _sc_raw, _bd_raw)
        )
        if real_feature_count < 3:
            return {"genreDetail": None}

        bpm = float(_bpm_raw) if _bpm_raw is not None else 120.0
        crest_factor = float(_crest_raw) if _crest_raw is not None else 10.0
        sub_bass_db = float(_sub_raw) if _sub_raw is not None else -25.0
        spectral_centroid = float(_cent_raw) if _cent_raw is not None else 2000.0
        onset_density = float(_onset_raw) if _onset_raw is not None else 4.0
        sidechain_strength = float(_sc_raw) if _sc_raw is not None else 0.0
        bass_decay_ms = float(_bd_raw) if _bd_raw is not None else 400.0
        bass_decay_s = bass_decay_ms / 1000.0

        # Optional features — only scored when both the signature and
        # the measured value are non-None
        rt60_raw = reverb_det.get("rt60")
        rt60: float | None = float(rt60_raw) if rt60_raw is not None else None
        kick_thd_raw = kick_det.get("thd")
        kick_thd: float | None = float(kick_thd_raw) if kick_thd_raw is not None else None

        is_acid = bool(acid_det.get("isAcid", False))
        is_supersaw = bool(supersaw_det.get("isSupersaw", False))
        is_vocal = bool(vocal_det.get("hasVocals", False))

        scores: list[tuple[str, float]] = []

        for sig in _GENRE_SIGNATURES:
            raw: dict[str, float] = {
                "bpm": _genre_range_score(bpm, *sig["bpm"]),
                "subBassDb": _genre_range_score(sub_bass_db, *sig["subBassDb"], 1.5),
                "crestFactor": _genre_range_score(crest_factor, *sig["crestFactor"], 1.5),
                "onsetDensity": _genre_range_score(onset_density, *sig["onsetDensity"], 1.5),
                "spectralCentroid": _genre_range_score(spectral_centroid, *sig["spectralCentroid"], 0.0003),
                "sidechainStrength": _genre_range_score(sidechain_strength, *sig["sidechainStrength"]),
                "bassDecay": _genre_range_score(bass_decay_s, *sig["bassDecay"], 1.5),
            }
            weights: dict[str, float] = {
                "bpm": 1.0,
                "subBassDb": 0.9,
                "crestFactor": 0.7,
                "onsetDensity": 0.6,
                "spectralCentroid": 0.5,
                "sidechainStrength": 0.95,
                "bassDecay": 0.85,
            }

            if sig.get("rt60") is not None and rt60 is not None:
                raw["rt60"] = _genre_range_score(rt60, *sig["rt60"])
                weights["rt60"] = 0.5

            if sig.get("kickDistortion") is not None and kick_thd is not None:
                raw["kickDistortion"] = _genre_range_score(kick_thd, *sig["kickDistortion"])
                weights["kickDistortion"] = 0.6

            total_weight = sum(weights.values())
            weighted_score = sum(raw.get(k, 0.0) * w for k, w in weights.items()) / total_weight

            if sig["id"] == "acid-techno" and is_acid:
                weighted_score = min(1.0, weighted_score * 1.3)
            if sig["id"] in ("trance", "psytrance", "progressive-house") and is_supersaw:
                weighted_score = min(1.0, weighted_score * 1.2)
            if is_vocal and sig["id"] in (
                "pop", "hiphop", "breaks", "house", "classic-house", "deep-house",
                "afro-house", "tech-house", "bass-house", "uk-garage", "trance",
            ):
                weighted_score = min(1.0, weighted_score * 1.15)

            scores.append((sig["id"], round(weighted_score, 4)))

        scores.sort(key=lambda x: x[1], reverse=True)
        primary_id, primary_score = scores[0]

        # Abstain when the best match is too weak to be meaningful
        if primary_score < 0.25:
            return {"genreDetail": None}

        secondary_id = scores[1][0] if len(scores) > 1 and scores[1][1] > 0.5 else None
        secondary_score = scores[1][1] if secondary_id else 0.0

        score_gap = primary_score - secondary_score
        confidence = round(min(1.0, primary_score * (1.0 + score_gap)), 4)

        # When top genres are nearly tied, cap confidence to signal ambiguity
        raw_gap = primary_score - (scores[1][1] if len(scores) > 1 else 0.0)
        if raw_gap < 0.05:
            confidence = min(confidence, 0.4)

        return {
            "genreDetail": {
                "genre": primary_id,
                "confidence": confidence,
                "secondaryGenre": secondary_id,
                "genreFamily": _GENRE_FAMILY_MAP.get(primary_id, "other"),
                "topScores": [
                    {"genre": gid, "score": s} for gid, s in scores[:5]
                ],
            }
        }
    except Exception as e:
        print(f"[warn] Genre classification failed: {e}", file=sys.stderr)
        return {"genreDetail": None}

