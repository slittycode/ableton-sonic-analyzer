"""Detection analyzers — effects, acid, reverb, vocal, supersaw, and genre."""

import sys

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None

from dsp_utils import _safe_db, _compute_bark_db


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


def analyze_reverb_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
) -> dict:
    """Estimate RT60 reverberation time from energy decay slopes after transients.

    Ported from sonic-architect-app/services/reverbAnalysis.ts.
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
            return {"reverbDetail": {"rt60": None, "isWet": False, "tailEnergyRatio": None, "measured": False}}

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
            return {"reverbDetail": {"rt60": None, "isWet": False, "tailEnergyRatio": None, "measured": False}}

        max_decay_frames = int(np.floor((_ANALYSIS_WINDOW_S * 1000.0) / _HOP_MS))
        direct_end_frames = max(1, int(np.floor(_DIRECT_MS / _HOP_MS)))
        rt60_estimates: list[float] = []
        tail_ratios: list[float] = []

        for t_idx in range(len(transient_indices) - 1):
            start_f = transient_indices[t_idx]
            peak_e = envelope[start_f]
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
            rt60 = abs(-60.0 / (slope / (_HOP_MS / 1000.0)))
            if 0.0 < rt60 < 5.0:
                rt60_estimates.append(rt60)

        if not rt60_estimates:
            return {"reverbDetail": {"rt60": None, "isWet": False, "tailEnergyRatio": None, "measured": False}}

        avg_rt60 = float(np.mean(rt60_estimates))
        avg_tail = float(np.mean(tail_ratios)) if tail_ratios else 0.2
        capped_rt60 = round(min(3.0, avg_rt60), 2)
        return {
            "reverbDetail": {
                "rt60": capped_rt60,
                "isWet": avg_rt60 > 0.5,
                "tailEnergyRatio": round(float(np.clip(avg_tail, 0.0, 1.0)), 2),
                "measured": True,
            }
        }
    except Exception as e:
        print(f"[warn] Reverb analysis failed: {e}", file=sys.stderr)
        return {"reverbDetail": None}


def analyze_vocal_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
) -> dict:
    """Detect vocal presence via spectral energy ratio, formant peaks, and MFCC likelihood.

    Ported from sonic-architect-app/services/vocalDetection.ts.
    Uses Essentia MFCC (already computed elsewhere), Spectrum, and SpectralPeaks
    for formant detection instead of browser FFT.
    """
    try:
        mono_arr = np.asarray(mono, dtype=np.float32)
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
        formant_tolerance = 200.0  # Hz
        formant_match_total = 0
        formant_frames = 0

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

            # Formant peak matching via SpectralPeaks (every 4th frame for speed)
            formant_frames += 1
            if formant_frames % 4 == 0:
                peak_freqs, peak_mags = spectral_peaks_algo(spec)
                frame_matches = 0
                for ef in expected_formants:
                    for pf in peak_freqs:
                        if abs(float(pf) - ef) < formant_tolerance:
                            frame_matches += 1
                            break
                formant_match_total += frame_matches

        vocal_energy_ratio = vocal_energy_sum / total_energy_sum if total_energy_sum > 0 else 0.0

        sampled_formant_frames = max(1, formant_frames // 4)
        formant_strength = min(1.0, formant_match_total / sampled_formant_frames / 3.0)

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
        has_vocals = confidence > 0.45

        return {
            "vocalDetail": {
                "hasVocals": has_vocals,
                "confidence": round(float(confidence), 2),
                "vocalEnergyRatio": round(float(vocal_energy_ratio), 2),
                "formantStrength": round(float(formant_strength), 2),
                "mfccLikelihood": round(float(mfcc_likelihood), 2),
            }
        }
    except Exception as e:
        print(f"[warn] Vocal detection failed: {e}", file=sys.stderr)
        return {"vocalDetail": None}


def analyze_supersaw_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
) -> dict:
    """Detect detuned sawtooth stacks characteristic of supersaw patches.

    Ported from sonic-architect-app/services/supersawDetection.ts.
    The JS version uses pitch bend data; in Python we use Essentia
    SpectralPeaks to find near-unison partials, measure detune spread, and
    check for sawtooth harmonic decay patterns.
    """
    try:
        mono_arr = np.asarray(mono, dtype=np.float32)
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


