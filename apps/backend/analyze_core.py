"""Core measurement analysis functions — BPM, key, loudness, dynamics, spectral, stereo."""

import sys

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None

from dsp_utils import _safe_db, _compute_stereo_metrics


def extract_rhythm(mono: np.ndarray) -> dict | None:
    """Run RhythmExtractor2013 once and return all outputs as a dict."""
    try:
        rhythm = es.RhythmExtractor2013()
        bpm, ticks, confidence, estimates, bpm_intervals = rhythm(mono)
        return {
            "bpm": bpm,
            "ticks": ticks,
            "confidence": confidence,
            "estimates": estimates,
            "bpm_intervals": bpm_intervals,
        }
    except Exception as e:
        print(f"[warn] RhythmExtractor2013 failed: {e}", file=sys.stderr)
        return None


def apply_bpm_correction(
    bpm_raw: float | None, bpm_percival: float | None, bpm_agreement: bool | None
) -> dict:
    """Apply ratio-based BPM correction.

    Returns dict with keys: bpm, bpmDoubletime, bpmSource, bpmRawOriginal.
    """
    bpm_raw_original = bpm_raw

    if bpm_raw is not None and bpm_percival is not None and bpm_raw > 0:
        ratio = bpm_percival / bpm_raw

        if (1.92 <= ratio <= 2.08
                or 1.44 <= ratio <= 1.56
                or 0.48 <= ratio <= 0.52
                or 0.641 <= ratio <= 0.694):
            return {
                "bpm": round(bpm_percival, 1),
                "bpmDoubletime": True,
                "bpmSource": "percival_ratio_corrected",
                "bpmRawOriginal": bpm_raw_original,
            }
        elif bpm_agreement is True:
            return {
                "bpm": bpm_raw,
                "bpmDoubletime": False,
                "bpmSource": "rhythm_extractor_confirmed",
                "bpmRawOriginal": bpm_raw_original,
            }
        else:
            return {
                "bpm": bpm_raw,
                "bpmDoubletime": False,
                "bpmSource": "rhythm_extractor",
                "bpmRawOriginal": bpm_raw_original,
            }

    return {
        "bpm": bpm_raw,
        "bpmDoubletime": False,
        "bpmSource": "rhythm_extractor",
        "bpmRawOriginal": bpm_raw_original,
    }


def analyze_bpm(
    rhythm_data: dict | None, mono: np.ndarray, sample_rate: int = 44100
) -> dict:
    """Extract BPM/confidence from RhythmExtractor2013 and compare with Percival BPM."""
    try:
        bpm = None
        bpm_confidence = None
        bpm_percival = None
        bpm_agreement = None

        if rhythm_data is not None:
            bpm = round(float(rhythm_data["bpm"]), 1)
            bpm_confidence = round(float(rhythm_data["confidence"]), 2)

        percival_cls = getattr(es, "PercivalBpmEstimator", None)
        if percival_cls is not None:
            try:
                bpm_percival_val = percival_cls(sampleRate=sample_rate)(mono)
                bpm_percival = round(float(bpm_percival_val), 1)
            except Exception as e:
                print(f"[warn] PercivalBpmEstimator failed: {e}", file=sys.stderr)
                bpm_percival = None

        if bpm is not None and bpm_percival is not None:
            bpm_agreement = abs(float(bpm) - float(bpm_percival)) < 2.0

        correction = apply_bpm_correction(bpm, bpm_percival, bpm_agreement)

        return {
            "bpm": correction["bpm"],
            "bpmConfidence": bpm_confidence,
            "bpmPercival": bpm_percival,
            "bpmAgreement": bpm_agreement,
            "bpmDoubletime": correction["bpmDoubletime"],
            "bpmSource": correction["bpmSource"],
            "bpmRawOriginal": correction["bpmRawOriginal"],
        }
    except Exception as e:
        print(f"[warn] BPM extraction failed: {e}", file=sys.stderr)
        return {
            "bpm": None,
            "bpmConfidence": None,
            "bpmPercival": None,
            "bpmAgreement": None,
            "bpmDoubletime": None,
            "bpmSource": None,
            "bpmRawOriginal": None,
        }


def analyze_key(mono: np.ndarray) -> dict:
    """Extract musical key and confidence using KeyExtractor with EDMA profile."""
    try:
        extractor = es.KeyExtractor(profileType="edma")
        key, scale, strength = extractor(mono)
        key_str = f"{key} {scale.capitalize()}"
        result = {
            "key": key_str,
            "keyConfidence": round(float(strength), 2),
            "keyProfile": "edma",
        }

        try:
            frame_size = 2048
            hop_size = 1024
            window = es.Windowing(type="hann", size=frame_size)
            spectrum_algo = es.Spectrum(size=frame_size)
            spectral_peaks = es.SpectralPeaks(
                orderBy="magnitude",
                magnitudeThreshold=0.00001,
                maxPeaks=60,
                sampleRate=44100,
            )
            tuning_algo = es.TuningFrequency()

            tuning_vals = []
            tuning_cents_vals = []
            for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
                spec = spectrum_algo(window(frame))
                peak_freqs, peak_mags = spectral_peaks(spec)
                if len(peak_freqs) > 0:
                    tf, tc = tuning_algo(peak_freqs, peak_mags)
                    if np.isfinite(tf) and tf > 0:
                        tuning_vals.append(float(tf))
                        tuning_cents_vals.append(float(tc))

            if tuning_vals:
                result["tuningFrequency"] = round(float(np.median(tuning_vals)), 2)
                result["tuningCents"] = round(float(np.median(tuning_cents_vals)), 2)
            else:
                result["tuningFrequency"] = None
                result["tuningCents"] = None
        except Exception:
            result["tuningFrequency"] = None
            result["tuningCents"] = None

        return result
    except Exception as e:
        print(f"[warn] Key extraction failed: {e}", file=sys.stderr)
        return {"key": None, "keyConfidence": None, "keyProfile": "edma", "tuningFrequency": None, "tuningCents": None}


def analyze_loudness(stereo: np.ndarray) -> dict:
    """LUFS integrated loudness, range, and max momentary/short-term via LoudnessEBUR128."""
    try:
        loudness = es.LoudnessEBUR128()
        momentary, short_term, integrated, loudness_range = loudness(stereo)
        momentary_arr = np.asarray(momentary, dtype=np.float64)
        short_term_arr = np.asarray(short_term, dtype=np.float64)
        lufs_momentary_max = None
        lufs_short_term_max = None
        if momentary_arr.size > 0:
            finite_momentary = momentary_arr[np.isfinite(momentary_arr)]
            if finite_momentary.size > 0:
                lufs_momentary_max = round(float(np.max(finite_momentary)), 1)
        if short_term_arr.size > 0:
            finite_short_term = short_term_arr[np.isfinite(short_term_arr)]
            if finite_short_term.size > 0:
                lufs_short_term_max = round(float(np.max(finite_short_term)), 1)
        return {
            "lufsIntegrated": round(float(integrated), 1),
            "lufsRange": round(float(loudness_range), 1),
            "lufsMomentaryMax": lufs_momentary_max,
            "lufsShortTermMax": lufs_short_term_max,
        }
    except Exception as e:
        print(f"[warn] LUFS extraction failed: {e}", file=sys.stderr)
        return {"lufsIntegrated": None, "lufsRange": None, "lufsMomentaryMax": None, "lufsShortTermMax": None}


def analyze_true_peak(stereo: np.ndarray) -> dict:
    """True peak detection via TruePeakDetector."""
    try:
        detector = es.TruePeakDetector()
        peaks = []
        for ch in range(stereo.shape[1]):
            output, peak_value = detector(stereo[:, ch])
            if hasattr(peak_value, "__len__"):
                peaks.append(float(np.max(peak_value)) if len(peak_value) > 0 else 0.0)
            else:
                peaks.append(float(peak_value))
        true_peak = max(peaks) if peaks else 0.0
        return {"truePeak": round(true_peak, 1)}
    except Exception as e:
        print(f"[warn] True peak detection failed: {e}", file=sys.stderr)
        return {"truePeak": None}


def analyze_dynamics(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Crest factor and dynamic spread from the mono signal."""
    try:
        peak = float(np.max(np.abs(mono)))
        rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
        if rms > 0 and peak > 0:
            crest = 20.0 * np.log10(peak / rms)
        else:
            crest = 0.0

        bands = {"sub": (20, 200), "mid": (200, 4000), "high": (4000, 20000)}
        frame_size = 2048
        hop_size = 1024
        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)

        energy_band_algos = {
            name: es.EnergyBand(
                startCutoffFrequency=lo, stopCutoffFrequency=hi, sampleRate=sample_rate
            )
            for name, (lo, hi) in bands.items()
        }
        band_energies = {name: [] for name in bands}
        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum(window(frame))
            for name, eb in energy_band_algos.items():
                band_energies[name].append(float(eb(spec)))

        means = [np.mean(v) for v in band_energies.values() if v]
        means = [m for m in means if m > 0]
        if len(means) >= 2:
            spread = float(max(means) / min(means))
        else:
            spread = 0.0

        return {
            "crestFactor": round(float(crest), 1),
            "dynamicSpread": round(spread, 2),
        }
    except Exception as e:
        print(f"[warn] Dynamics analysis failed: {e}", file=sys.stderr)
        return {"crestFactor": None, "dynamicSpread": None}


def analyze_dynamic_character(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Dynamic complexity, spectral flatness, and attack-time metrics."""
    try:
        dynamic_complexity = 0.0
        loudness_db = 0.0
        spectral_flatness = 0.0
        log_attack_time = 0.0
        attack_time_stddev = 0.0

        try:
            dynamic_algo = es.DynamicComplexity(sampleRate=sample_rate)
            dynamic_complexity, loudness_db = dynamic_algo(mono)
            dynamic_complexity = float(dynamic_complexity)
            loudness_db = float(loudness_db)
        except Exception:
            dynamic_complexity = 0.0
            loudness_db = 0.0

        try:
            frame_size = 2048
            hop_size = 1024
            window = es.Windowing(type="hann", size=frame_size)
            spectrum = es.Spectrum(size=frame_size)
            flatness_algo = es.Flatness()
            flatness_vals = []
            for frame in es.FrameGenerator(
                mono, frameSize=frame_size, hopSize=hop_size
            ):
                spec = spectrum(window(frame))
                flatness_vals.append(float(flatness_algo(spec)))
            if len(flatness_vals) > 0:
                spectral_flatness = float(np.mean(flatness_vals))
        except Exception:
            spectral_flatness = 0.0

        try:
            envelope = es.Envelope(sampleRate=sample_rate)(mono)
            envelope = np.asarray(envelope, dtype=np.float32)
        except Exception:
            envelope = np.asarray(np.abs(mono), dtype=np.float32)

        log_attack_algo = None
        try:
            log_attack_algo = es.LogAttackTime(sampleRate=sample_rate)
        except Exception:
            log_attack_algo = None

        fallback_log_attack = None
        if log_attack_algo is not None and envelope.size > 0:
            try:
                lat, _start, _stop = log_attack_algo(envelope)
                if np.isfinite(lat):
                    fallback_log_attack = float(lat)
            except Exception:
                fallback_log_attack = None

        per_onset_log_attacks = []
        if log_attack_algo is not None and envelope.size > 0:
            try:
                onset_frame_size = 1024
                onset_hop_size = 512
                onset_window = es.Windowing(type="hann", size=onset_frame_size)
                onset_spectrum = es.Spectrum(size=onset_frame_size)
                onset_detection = es.OnsetDetection(
                    method="hfc", sampleRate=sample_rate
                )
                onset_values = []

                for frame in es.FrameGenerator(
                    mono, frameSize=onset_frame_size, hopSize=onset_hop_size
                ):
                    spec = onset_spectrum(onset_window(frame))
                    onset_val = None
                    try:
                        onset_val = float(onset_detection(spec))
                    except Exception:
                        try:
                            onset_val = float(
                                onset_detection(
                                    spec, np.zeros_like(spec, dtype=np.float32)
                                )
                            )
                        except Exception:
                            onset_val = None

                    if onset_val is not None and np.isfinite(onset_val):
                        onset_values.append(onset_val)

                if len(onset_values) > 0:
                    onsets_algo = es.Onsets(
                        frameRate=float(sample_rate) / float(onset_hop_size)
                    )
                    onset_times = onsets_algo(
                        np.asarray([onset_values], dtype=np.float32),
                        np.asarray([1.0], dtype=np.float32),
                    )
                    onset_times = np.asarray(onset_times, dtype=np.float64)
                    duration_seconds = float(len(envelope) / sample_rate)

                    for idx, onset in enumerate(onset_times):
                        start_t = max(0.0, float(onset))
                        next_onset = (
                            float(onset_times[idx + 1])
                            if idx + 1 < len(onset_times)
                            else duration_seconds
                        )
                        end_t = min(next_onset, start_t + 0.5, duration_seconds)
                        start_sample = int(start_t * sample_rate)
                        end_sample = int(end_t * sample_rate)
                        if end_sample - start_sample < 8:
                            continue
                        seg_env = np.asarray(
                            envelope[start_sample:end_sample], dtype=np.float32
                        )
                        try:
                            lat, _start, _stop = log_attack_algo(seg_env)
                            if np.isfinite(lat):
                                per_onset_log_attacks.append(float(lat))
                        except Exception:
                            continue
            except Exception:
                per_onset_log_attacks = []
        else:
            per_onset_log_attacks = []

        attack_log_values = per_onset_log_attacks
        if len(attack_log_values) == 0 and fallback_log_attack is not None:
            attack_log_values = [fallback_log_attack]

        if len(attack_log_values) > 0:
            log_attack_time = float(np.mean(attack_log_values))
            linear_attack_times = [10.0**v for v in attack_log_values if np.isfinite(v)]
            if len(linear_attack_times) > 1:
                attack_time_stddev = float(np.std(linear_attack_times))
            else:
                attack_time_stddev = 0.0

        return {
            "dynamicCharacter": {
                "dynamicComplexity": round(dynamic_complexity, 4),
                "loudnessDb": round(loudness_db, 4),
                "loudnessVariation": round(loudness_db, 4),
                "spectralFlatness": round(spectral_flatness, 4),
                "logAttackTime": round(log_attack_time, 4),
                "attackTimeStdDev": round(attack_time_stddev, 4),
            }
        }
    except Exception as e:
        print(f"[warn] Dynamic character analysis failed: {e}", file=sys.stderr)
        return {"dynamicCharacter": None}


TEXTURE_FLATNESS_BANDS = {
    "lowBandFlatness": (20.0, 250.0),
    "midBandFlatness": (250.0, 2000.0),
    "highBandFlatness": (2000.0, 12000.0),
}


def _build_texture_character(
    low_band_flatness: float,
    mid_band_flatness: float,
    high_band_flatness: float,
    inharmonicity: float | None,
) -> dict[str, float | None]:
    normalized_inharmonicity = None
    if inharmonicity is not None and np.isfinite(inharmonicity):
        normalized_inharmonicity = min(1.0, max(0.0, float(inharmonicity) / 0.25))

    weighted_terms: list[tuple[float, float]] = [
        (0.15, low_band_flatness),
        (0.30, mid_band_flatness),
        (0.35, high_band_flatness),
    ]
    if normalized_inharmonicity is not None:
        weighted_terms.append((0.20, normalized_inharmonicity))

    total_weight = sum(weight for weight, _ in weighted_terms)
    texture_score = (
        sum(weight * value for weight, value in weighted_terms) / total_weight
        if total_weight > 0
        else 0.0
    )

    return {
        "textureScore": round(float(texture_score), 4),
        "lowBandFlatness": round(float(low_band_flatness), 4),
        "midBandFlatness": round(float(mid_band_flatness), 4),
        "highBandFlatness": round(float(high_band_flatness), 4),
        "inharmonicity": round(float(inharmonicity), 4)
        if inharmonicity is not None and np.isfinite(inharmonicity)
        else None,
    }


def analyze_texture_character(
    mono: np.ndarray,
    sample_rate: int = 44100,
    inharmonicity: float | None = None,
) -> dict:
    """Band-aware texture metrics that better capture noise-heavy material."""
    try:
        frame_size = 2048
        hop_size = 1024
        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        frequencies = np.fft.rfftfreq(frame_size, d=1.0 / float(sample_rate))
        band_masks = {
            name: (frequencies >= low_hz) & (frequencies < high_hz)
            for name, (low_hz, high_hz) in TEXTURE_FLATNESS_BANDS.items()
        }
        band_values: dict[str, list[float]] = {name: [] for name in TEXTURE_FLATNESS_BANDS}

        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
            spec = np.asarray(spectrum(window(frame)), dtype=np.float64)
            for name, mask in band_masks.items():
                band = spec[mask]
                if band.size == 0 or np.all(band <= 0):
                    band_values[name].append(0.0)
                    continue
                band = np.maximum(band, 1e-12)
                arithmetic_mean = float(np.mean(band))
                if arithmetic_mean <= 0:
                    band_values[name].append(0.0)
                    continue
                geometric_mean = float(np.exp(np.mean(np.log(band))))
                band_values[name].append(geometric_mean / arithmetic_mean)

        averages = {
            name: float(np.mean(values)) if values else 0.0
            for name, values in band_values.items()
        }
        return {
            "textureCharacter": _build_texture_character(
                averages["lowBandFlatness"],
                averages["midBandFlatness"],
                averages["highBandFlatness"],
                inharmonicity,
            )
        }
    except Exception as e:
        print(f"[warn] Texture character analysis failed: {e}", file=sys.stderr)
        return {"textureCharacter": None}


SPECTRAL_BALANCE_BANDS = {
    "subBass": (20, 80),
    "lowBass": (80, 250),
    "lowMids": (250, 500),
    "mids": (500, 2000),
    "upperMids": (2000, 5000),
    "highs": (5000, 10000),
    "brilliance": (10000, 20000),
}


def analyze_spectral_balance(
    mono: np.ndarray,
    sample_rate: int = 44100,
    *,
    precomputed_band_energies: dict | None = None,
) -> dict:
    """Spectral balance across 7 frequency bands using EnergyBand + spectrum."""
    try:
        if precomputed_band_energies is not None:
            band_energies = precomputed_band_energies
        else:
            bands = SPECTRAL_BALANCE_BANDS
            frame_size = 2048
            hop_size = 1024
            window = es.Windowing(type="hann", size=frame_size)
            spectrum = es.Spectrum(size=frame_size)

            band_algos = {
                name: es.EnergyBand(
                    startCutoffFrequency=lo,
                    stopCutoffFrequency=hi,
                    sampleRate=sample_rate,
                )
                for name, (lo, hi) in bands.items()
            }
            band_energies = {name: [] for name in bands}

            for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
                spec = spectrum(window(frame))
                for name, algo in band_algos.items():
                    band_energies[name].append(float(algo(spec)))

        result = {}
        for name, energies in band_energies.items():
            mean_energy = np.mean(energies) if energies else 0.0
            db = 10 * np.log10(mean_energy) if mean_energy > 0 else -100.0
            result[name] = round(float(db), 1)

        return {"spectralBalance": result}
    except Exception as e:
        print(f"[warn] Spectral balance analysis failed: {e}", file=sys.stderr)
        return {"spectralBalance": None}


def analyze_plr(lufs_integrated: float | None, true_peak: float | None) -> dict:
    """Peak-to-loudness ratio (PLR): truePeak - LUFS integrated."""
    try:
        if lufs_integrated is None or true_peak is None:
            return {"plr": None}
        lufs_value = float(lufs_integrated)
        true_peak_value = float(true_peak)
        if not np.isfinite(lufs_value) or not np.isfinite(true_peak_value):
            return {"plr": None}
        return {"plr": round(true_peak_value - lufs_value, 2)}
    except Exception:
        return {"plr": None}


def analyze_spectral_detail(
    mono: np.ndarray, sample_rate: int = 44100, *, _balance_bands: dict | None = None
) -> dict:
    """Frame-by-frame SpectralCentroid, SpectralRolloff, MFCC, and HPCP (Chroma)."""
    try:
        frame_size = 2048
        hop_size = 1024
        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)

        centroid_algo = es.SpectralCentroidTime(sampleRate=sample_rate)
        rolloff_algo = es.RollOff(sampleRate=sample_rate)
        mfcc_algo = es.MFCC(
            inputSize=frame_size // 2 + 1, sampleRate=sample_rate, numberCoefficients=13
        )
        spectral_peaks = es.SpectralPeaks(
            orderBy="magnitude",
            magnitudeThreshold=0.00001,
            maxPeaks=60,
            sampleRate=sample_rate,
        )
        hpcp_algo = es.HPCP(sampleRate=sample_rate)
        bark_algo = es.BarkBands(numberBands=24, sampleRate=sample_rate)

        erb_algo = None
        try:
            erb_algo = es.ERBBands(
                inputSize=frame_size // 2 + 1,
                sampleRate=sample_rate,
                numberBands=40,
                type="power",
            )
        except Exception:
            try:
                erb_algo = es.ERBBands(
                    sampleRate=sample_rate, numberBands=40, type="power"
                )
            except Exception:
                try:
                    erb_algo = es.ERBBands(sampleRate=sample_rate, numberBands=40)
                except Exception:
                    erb_algo = None

        spectral_contrast_algo = None
        try:
            spectral_contrast_algo = es.SpectralContrast(
                inputSize=frame_size // 2 + 1,
                sampleRate=sample_rate,
            )
        except Exception:
            try:
                spectral_contrast_algo = es.SpectralContrast(
                    frameSize=frame_size, sampleRate=sample_rate
                )
            except Exception:
                spectral_contrast_algo = None

        balance_algos = None
        balance_energies = None
        if _balance_bands is not None:
            balance_algos = {
                name: es.EnergyBand(
                    startCutoffFrequency=lo,
                    stopCutoffFrequency=hi,
                    sampleRate=sample_rate,
                )
                for name, (lo, hi) in _balance_bands.items()
            }
            balance_energies = {name: [] for name in _balance_bands}

        flatness_algo = es.Flatness()

        centroid_vals, rolloff_vals = [], []
        flatness_vals = []
        bandwidth_vals = []
        mfcc_matrix = []
        hpcp_matrix = []
        bark_matrix = []
        erb_matrix = []
        contrast_matrix = []
        valley_matrix = []

        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
            windowed = window(frame)
            spec = spectrum(windowed)

            centroid_vals.append(float(centroid_algo(frame)))
            rolloff_vals.append(float(rolloff_algo(spec)))

            try:
                flatness_vals.append(float(flatness_algo(spec)))
            except Exception:
                pass

            try:
                spec_arr = np.asarray(spec, dtype=np.float64)
                if spec_arr.sum() > 0:
                    freqs = np.linspace(0, sample_rate / 2, len(spec_arr))
                    centroid_hz = float(centroid_algo(frame))
                    bw = float(
                        np.sqrt(np.sum(spec_arr * (freqs - centroid_hz) ** 2) / np.sum(spec_arr))
                    )
                    bandwidth_vals.append(bw)
            except Exception:
                pass

            _bands, mfcc_coeffs = mfcc_algo(spec)
            mfcc_matrix.append(mfcc_coeffs)

            try:
                freqs, mags = spectral_peaks(spec)
                if len(freqs) > 0:
                    hpcp = hpcp_algo(freqs, mags)
                    hpcp_matrix.append(hpcp)
            except Exception:
                pass

            try:
                bark_vals = np.asarray(bark_algo(spec), dtype=np.float64)
                if bark_vals.ndim == 1 and bark_vals.size > 0:
                    bark_matrix.append(bark_vals)
            except Exception:
                pass

            if erb_algo is not None:
                try:
                    erb_vals = np.asarray(erb_algo(spec), dtype=np.float64)
                    if erb_vals.ndim == 1 and erb_vals.size > 0:
                        erb_matrix.append(erb_vals)
                except Exception:
                    pass

            if spectral_contrast_algo is not None:
                try:
                    contrast_vals, valley_vals = spectral_contrast_algo(spec)
                    contrast_vals = np.asarray(contrast_vals, dtype=np.float64)
                    valley_vals = np.asarray(valley_vals, dtype=np.float64)
                    if (
                        contrast_vals.ndim == 1
                        and valley_vals.ndim == 1
                        and contrast_vals.size > 0
                        and valley_vals.size > 0
                    ):
                        contrast_matrix.append(contrast_vals)
                        valley_matrix.append(valley_vals)
                except Exception:
                    pass

            if balance_algos is not None:
                for name, algo in balance_algos.items():
                    balance_energies[name].append(float(algo(spec)))

        mean_centroid = (
            round(float(np.mean(centroid_vals)), 1) if centroid_vals else 0.0
        )
        mean_rolloff = round(float(np.mean(rolloff_vals)), 1) if rolloff_vals else 0.0
        mean_mfcc = (
            [round(float(v), 4) for v in np.mean(mfcc_matrix, axis=0)]
            if mfcc_matrix
            else [0.0] * 13
        )
        mean_chroma = (
            [round(float(v), 4) for v in np.mean(hpcp_matrix, axis=0)]
            if hpcp_matrix
            else [0.0] * 12
        )
        mean_bark = (
            [
                _safe_db(float(v))
                for v in np.mean(np.asarray(bark_matrix, dtype=np.float64), axis=0)
            ]
            if bark_matrix
            else [-100.0] * 24
        )
        mean_erb = (
            [
                _safe_db(float(v))
                for v in np.mean(np.asarray(erb_matrix, dtype=np.float64), axis=0)
            ]
            if erb_matrix
            else [-100.0] * 40
        )
        mean_contrast = (
            [
                round(float(v), 4)
                for v in np.mean(np.asarray(contrast_matrix, dtype=np.float64), axis=0)
            ]
            if contrast_matrix
            else []
        )
        mean_valley = (
            [
                round(float(v), 4)
                for v in np.mean(np.asarray(valley_matrix, dtype=np.float64), axis=0)
            ]
            if valley_matrix
            else []
        )

        mean_flatness = (
            round(float(np.mean(flatness_vals)), 6) if flatness_vals else 0.0
        )
        mean_bandwidth = (
            round(float(np.mean(bandwidth_vals)), 1) if bandwidth_vals else 0.0
        )

        result = {
            "spectralDetail": {
                "spectralCentroid": mean_centroid,
                "spectralRolloff": mean_rolloff,
                "spectralBandwidth": mean_bandwidth,
                "spectralFlatness": mean_flatness,
                "mfcc": mean_mfcc,
                "chroma": mean_chroma,
                "barkBands": mean_bark,
                "erbBands": mean_erb,
                "spectralContrast": mean_contrast,
                "spectralValley": mean_valley,
            }
        }
        if balance_energies is not None:
            result["_spectralBalanceBands"] = balance_energies
        return result
    except Exception as e:
        print(f"[warn] Spectral detail analysis failed: {e}", file=sys.stderr)
        return {"spectralDetail": None}


def analyze_stereo(stereo: np.ndarray, sample_rate: int = 44100) -> dict:
    """Global stereo detail including sub-bass mono check."""
    try:
        stereo_arr = np.asarray(stereo, dtype=np.float64)
        if stereo_arr.ndim != 2 or stereo_arr.shape[0] < 2:
            return {
                "stereoDetail": {
                    "stereoWidth": None,
                    "stereoCorrelation": None,
                    "subBassCorrelation": None,
                    "subBassMono": None,
                }
            }

        if stereo_arr.shape[1] < 2:
            left = stereo_arr[:, 0]
            right = stereo_arr[:, 0]
        else:
            left = stereo_arr[:, 0]
            right = stereo_arr[:, 1]

        stereo_metrics = _compute_stereo_metrics(left, right)

        left_sub = left.astype(np.float32)
        right_sub = right.astype(np.float32)
        filtered = False

        bandpass_cls = getattr(es, "BandPass", None)
        if bandpass_cls is not None:
            bandpass_kwargs = [
                {"cutoffFrequency": 50.0, "bandwidth": 60.0, "sampleRate": sample_rate},
                {"cutoffFrequency": 50.0, "bandwidth": 60.0},
            ]
            for kwargs in bandpass_kwargs:
                try:
                    bp_l = bandpass_cls(**kwargs)
                    bp_r = bandpass_cls(**kwargs)
                    left_sub = np.asarray(bp_l(left_sub), dtype=np.float32)
                    right_sub = np.asarray(bp_r(right_sub), dtype=np.float32)
                    filtered = True
                    break
                except Exception:
                    continue

        if not filtered:
            lowpass_kwargs = [
                {"cutoffFrequency": 80.0, "sampleRate": sample_rate},
                {"cutoffFrequency": 80.0},
            ]
            for kwargs in lowpass_kwargs:
                try:
                    lp_l = es.LowPass(**kwargs)
                    lp_r = es.LowPass(**kwargs)
                    left_sub = np.asarray(lp_l(left_sub), dtype=np.float32)
                    right_sub = np.asarray(lp_r(right_sub), dtype=np.float32)
                    filtered = True
                    break
                except Exception:
                    continue

        sub_metrics = _compute_stereo_metrics(left_sub, right_sub)
        sub_corr = sub_metrics.get("stereoCorrelation")
        sub_mono = None if sub_corr is None else bool(float(sub_corr) > 0.85)

        return {
            "stereoDetail": {
                "stereoWidth": stereo_metrics.get("stereoWidth"),
                "stereoCorrelation": stereo_metrics.get("stereoCorrelation"),
                "subBassCorrelation": sub_corr,
                "subBassMono": sub_mono,
            }
        }
    except Exception as e:
        print(f"[warn] Stereo analysis failed: {e}", file=sys.stderr)
        return {
            "stereoDetail": {
                "stereoWidth": None,
                "stereoCorrelation": None,
                "subBassCorrelation": None,
                "subBassMono": None,
            }
        }


def analyze_perceptual(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Frame-by-frame sharpness and roughness (approximated via Dissonance)."""
    try:
        frame_size = 2048
        hop_size = 1024
        window = es.Windowing(type="hann", size=frame_size)
        spectrum_algo = es.Spectrum(size=frame_size)
        spectral_peaks = es.SpectralPeaks(
            orderBy="magnitude",
            magnitudeThreshold=0.00001,
            maxPeaks=50,
            sampleRate=sample_rate,
        )
        diss_algo = es.Dissonance()

        sharpness_vals = []
        roughness_vals = []

        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum_algo(window(frame))

            freqs = np.linspace(0, sample_rate / 2.0, len(spec))
            total_energy = float(np.sum(spec))
            if total_energy > 0:
                weights = (freqs / (sample_rate / 2.0)) ** 2
                sharpness = float(np.sum(spec * weights) / total_energy)
            else:
                sharpness = 0.0
            sharpness_vals.append(sharpness)

            try:
                peak_freqs, peak_mags = spectral_peaks(spec)
                if len(peak_freqs) > 1:
                    roughness_vals.append(float(diss_algo(peak_freqs, peak_mags)))
                else:
                    roughness_vals.append(0.0)
            except Exception:
                roughness_vals.append(0.0)

        return {
            "perceptual": {
                "sharpness": round(float(np.mean(sharpness_vals)), 4)
                if sharpness_vals
                else 0.0,
                "roughness": round(float(np.mean(roughness_vals)), 4)
                if roughness_vals
                else 0.0,
            }
        }
    except Exception as e:
        print(f"[warn] Perceptual analysis failed: {e}", file=sys.stderr)
        return {"perceptual": None}


def analyze_essentia_features(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Frame-by-frame averages of ZeroCrossingRate, HFC, SpectralComplexity, Dissonance."""
    try:
        frame_size = 2048
        hop_size = 1024

        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        spectral_peaks = es.SpectralPeaks(
            orderBy="magnitude",
            magnitudeThreshold=0.00001,
            maxPeaks=50,
            sampleRate=sample_rate,
        )

        zcr_algo = es.ZeroCrossingRate()
        hfc_algo = es.HFC()
        sc_algo = es.SpectralComplexity()
        diss_algo = es.Dissonance()

        zcr_vals, hfc_vals, sc_vals, diss_vals = [], [], [], []

        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
            windowed = window(frame)
            spec = spectrum(windowed)

            zcr_vals.append(float(zcr_algo(frame)))
            hfc_vals.append(float(hfc_algo(spec)))
            sc_vals.append(float(sc_algo(spec)))

            try:
                freqs, mags = spectral_peaks(spec)
                if len(freqs) > 1:
                    diss_vals.append(float(diss_algo(freqs, mags)))
                else:
                    diss_vals.append(0.0)
            except Exception:
                diss_vals.append(0.0)

        return {
            "essentiaFeatures": {
                "zeroCrossingRate": round(float(np.mean(zcr_vals)), 4)
                if zcr_vals
                else 0.0,
                "hfc": round(float(np.mean(hfc_vals)), 4) if hfc_vals else 0.0,
                "spectralComplexity": round(float(np.mean(sc_vals)), 4)
                if sc_vals
                else 0.0,
                "dissonance": round(float(np.mean(diss_vals)), 4) if diss_vals else 0.0,
            }
        }
    except Exception as e:
        print(f"[warn] Essentia features extraction failed: {e}", file=sys.stderr)
        return {"essentiaFeatures": None}


def analyze_duration_and_sr(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Compute duration from sample count and sample rate."""
    try:
        duration = round(float(len(mono) / sample_rate), 1)
        return {"durationSeconds": duration, "sampleRate": sample_rate}
    except Exception as e:
        print(f"[warn] Duration calculation failed: {e}", file=sys.stderr)
        return {"durationSeconds": None, "sampleRate": None}


def analyze_time_signature(rhythm_data: dict | None) -> dict:
    """Estimate time signature from shared rhythm data."""
    try:
        if rhythm_data is None:
            return {
                "timeSignature": None,
                "timeSignatureSource": None,
                "timeSignatureConfidence": None,
            }
        return {
            "timeSignature": "4/4",
            "timeSignatureSource": "assumed_four_four",
            "timeSignatureConfidence": 0.0,
        }
    except Exception as e:
        print(f"[warn] Time signature estimation failed: {e}", file=sys.stderr)
        return {
            "timeSignature": None,
            "timeSignatureSource": None,
            "timeSignatureConfidence": None,
        }
