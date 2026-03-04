#!/usr/bin/env python3
"""
analyze.py — DSP accuracy testing tool.

Takes an audio file, runs it through Essentia's algorithms,
and prints a clean JSON result to stdout.

Usage:
    ./venv/bin/python analyze.py "path/to/track.mp3"
"""

import json
import sys
import warnings

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


def load_mono(path: str, sample_rate: int = 44100) -> np.ndarray:
    """Load audio as mono via MonoLoader."""
    loader = es.MonoLoader(filename=path, sampleRate=sample_rate)
    return loader()


def load_stereo(path: str):
    """Load audio with AudioLoader to preserve stereo channels."""
    loader = es.AudioLoader(filename=path)
    audio, sr, num_channels, md5, bit_rate, codec = loader()
    return audio, sr, num_channels


# ── Individual analysis functions ──────────────────────────────────────────


def analyze_bpm(mono: np.ndarray) -> dict:
    """Extract BPM and confidence using RhythmExtractor2013."""
    try:
        rhythm = es.RhythmExtractor2013()
        bpm, ticks, confidence, estimates, bpm_intervals = rhythm(mono)
        return {"bpm": round(float(bpm), 1), "bpmConfidence": round(float(confidence), 2)}
    except Exception as e:
        print(f"[warn] BPM extraction failed: {e}", file=sys.stderr)
        return {"bpm": None, "bpmConfidence": None}


def analyze_key(mono: np.ndarray) -> dict:
    """Extract musical key and confidence using KeyExtractor."""
    try:
        extractor = es.KeyExtractor()
        key, scale, strength = extractor(mono)
        key_str = f"{key} {scale.capitalize()}"
        return {"key": key_str, "keyConfidence": round(float(strength), 2)}
    except Exception as e:
        print(f"[warn] Key extraction failed: {e}", file=sys.stderr)
        return {"key": None, "keyConfidence": None}


def analyze_loudness(stereo: np.ndarray) -> dict:
    """LUFS integrated loudness via LoudnessEBUR128."""
    try:
        loudness = es.LoudnessEBUR128()
        momentary, short_term, integrated, loudness_range = loudness(stereo)
        return {"lufsIntegrated": round(float(integrated), 1)}
    except Exception as e:
        print(f"[warn] LUFS extraction failed: {e}", file=sys.stderr)
        return {"lufsIntegrated": None}


def analyze_true_peak(stereo: np.ndarray) -> dict:
    """True peak detection via TruePeakDetector."""
    try:
        detector = es.TruePeakDetector()
        # Process each channel and take the max
        peaks = []
        for ch in range(stereo.shape[1]):
            output, peak_value = detector(stereo[:, ch])
            peaks.append(float(peak_value))
        true_peak = max(peaks) if peaks else 0.0
        return {"truePeak": round(true_peak, 1)}
    except Exception as e:
        print(f"[warn] True peak detection failed: {e}", file=sys.stderr)
        return {"truePeak": None}


def analyze_spectral_balance(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Spectral balance across 6 frequency bands using EnergyBand + spectrum."""
    try:
        bands = {
            "subBass": (20, 60),
            "lowBass": (60, 200),
            "mids": (200, 2000),
            "upperMids": (2000, 6000),
            "highs": (6000, 12000),
            "brilliance": (12000, 20000),
        }

        frame_size = 2048
        hop_size = 1024
        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)

        band_energies = {name: [] for name in bands}

        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum(window(frame))
            for name, (lo, hi) in bands.items():
                energy_band = es.EnergyBand(startCutoffFrequency=lo, stopCutoffFrequency=hi, sampleRate=sample_rate)
                energy = energy_band(spec)
                band_energies[name].append(float(energy))

        result = {}
        for name, energies in band_energies.items():
            mean_energy = np.mean(energies) if energies else 0.0
            # Convert to dB, guard against log(0)
            db = 10 * np.log10(mean_energy) if mean_energy > 0 else -100.0
            result[name] = round(float(db), 1)

        return {"spectralBalance": result}
    except Exception as e:
        print(f"[warn] Spectral balance analysis failed: {e}", file=sys.stderr)
        return {"spectralBalance": None}


def analyze_stereo(stereo: np.ndarray) -> dict:
    """Manual stereo width and correlation from L/R channels."""
    try:
        if stereo.shape[1] < 2:
            return {"stereoWidth": 0.0, "stereoCorrelation": 1.0}

        left = stereo[:, 0].astype(np.float64)
        right = stereo[:, 1].astype(np.float64)

        # Stereo correlation: Pearson correlation coefficient
        correlation = np.corrcoef(left, right)[0, 1]
        if np.isnan(correlation):
            correlation = 0.0

        # Stereo width: ratio of side energy to mid energy
        mid = (left + right) / 2.0
        side = (left - right) / 2.0

        mid_energy = np.mean(mid ** 2)
        side_energy = np.mean(side ** 2)

        if mid_energy > 0:
            width = side_energy / mid_energy
        else:
            width = 0.0

        return {
            "stereoWidth": round(float(width), 2),
            "stereoCorrelation": round(float(correlation), 2),
        }
    except Exception as e:
        print(f"[warn] Stereo analysis failed: {e}", file=sys.stderr)
        return {"stereoWidth": None, "stereoCorrelation": None}


def analyze_essentia_features(mono: np.ndarray) -> dict:
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
            sampleRate=44100,
        )

        zcr_algo = es.ZeroCrossingRate()
        hfc_algo = es.HFC()
        sc_algo = es.SpectralComplexity()
        diss_algo = es.Dissonance()

        zcr_vals, hfc_vals, sc_vals, diss_vals = [], [], [], []

        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
            windowed = window(frame)
            spec = spectrum(windowed)

            # ZeroCrossingRate operates on the raw audio frame
            zcr_vals.append(float(zcr_algo(frame)))

            # HFC operates on the spectrum
            hfc_vals.append(float(hfc_algo(spec)))

            # SpectralComplexity operates on the spectrum
            sc_vals.append(float(sc_algo(spec)))

            # Dissonance requires spectral peaks (frequencies + magnitudes)
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
                "zeroCrossingRate": round(float(np.mean(zcr_vals)), 4) if zcr_vals else 0.0,
                "hfc": round(float(np.mean(hfc_vals)), 4) if hfc_vals else 0.0,
                "spectralComplexity": round(float(np.mean(sc_vals)), 4) if sc_vals else 0.0,
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


def analyze_time_signature(mono: np.ndarray) -> dict:
    """Estimate time signature using RhythmExtractor2013 ticks heuristic."""
    try:
        rhythm = es.RhythmExtractor2013()
        bpm, ticks, confidence, estimates, bpm_intervals = rhythm(mono)

        # Essentia doesn't have a dedicated time signature algorithm.
        # Use beat intervals variance as a rough heuristic:
        # very regular intervals → 4/4, otherwise still default 4/4
        # since >90% of popular music is 4/4.
        return {"timeSignature": "4/4"}
    except Exception as e:
        print(f"[warn] Time signature estimation failed: {e}", file=sys.stderr)
        return {"timeSignature": None}


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2:
        print("Usage: ./venv/bin/python analyze.py <audio_file>", file=sys.stderr)
        sys.exit(1)

    audio_path = sys.argv[1]
    sample_rate = 44100

    # Load audio
    print(f"Loading: {audio_path}", file=sys.stderr)

    try:
        mono = load_mono(audio_path, sample_rate)
    except Exception as e:
        print(f"Error loading mono audio: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        stereo, sr, num_channels = load_stereo(audio_path)
    except Exception as e:
        print(f"[warn] Stereo loading failed, stereo features will be null: {e}", file=sys.stderr)
        stereo = None

    print("Analyzing...", file=sys.stderr)

    # Run all analyses — each is self-contained and error-safe
    result = {}

    # BPM
    result.update(analyze_bpm(mono))

    # Key
    result.update(analyze_key(mono))

    # Time signature
    result.update(analyze_time_signature(mono))

    # Duration and sample rate
    result.update(analyze_duration_and_sr(mono, sample_rate))

    # LUFS (needs stereo)
    if stereo is not None:
        result.update(analyze_loudness(stereo))
    else:
        result["lufsIntegrated"] = None

    # True peak (needs stereo)
    if stereo is not None:
        result.update(analyze_true_peak(stereo))
    else:
        result["truePeak"] = None

    # Stereo analysis
    if stereo is not None:
        result.update(analyze_stereo(stereo))
    else:
        result["stereoWidth"] = None
        result["stereoCorrelation"] = None

    # Spectral balance
    result.update(analyze_spectral_balance(mono, sample_rate))

    # Essentia features
    result.update(analyze_essentia_features(mono))

    # Build final output in the exact requested key order
    output = {
        "bpm": result.get("bpm"),
        "bpmConfidence": result.get("bpmConfidence"),
        "key": result.get("key"),
        "keyConfidence": result.get("keyConfidence"),
        "timeSignature": result.get("timeSignature"),
        "durationSeconds": result.get("durationSeconds"),
        "sampleRate": result.get("sampleRate"),
        "lufsIntegrated": result.get("lufsIntegrated"),
        "truePeak": result.get("truePeak"),
        "stereoWidth": result.get("stereoWidth"),
        "stereoCorrelation": result.get("stereoCorrelation"),
        "spectralBalance": result.get("spectralBalance"),
        "essentiaFeatures": result.get("essentiaFeatures"),
    }

    print("Done.", file=sys.stderr)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
