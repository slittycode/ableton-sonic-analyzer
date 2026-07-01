"""Fast analysis mode for analyze.py.

This module provides a streamlined analysis pipeline that runs only core
descriptors (BPM, key, loudness, basic dynamics) for rapid results.

Usage:
    from analyze_fast import analyze_fast
    result = analyze_fast(audio_path, sample_rate)
"""

import sys
import numpy as np

from analyze_core import (
    analyze_bpm,
    analyze_key,
    analyze_loudness,
    analyze_time_signature,
    analyze_true_peak,
    extract_rhythm,
)


def analyze_fast(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Run fast analysis on mono audio.

    Performs only core analyses:
    - BPM (RhythmExtractor2013 + Percival cross-check)
    - Key (KeyExtractor)
    - Time signature (from rhythm data)
    - Duration and sample rate
    - Basic loudness (LUFS integrated, range, true peak)
    - Basic dynamics (crest factor only)

    All other fields are set to None for speed.

    Args:
        mono: Mono audio array
        sample_rate: Sample rate in Hz (default: 44100)

    Returns:
        Dictionary with core analysis results, other fields set to None
    """
    result = {}

    rhythm_data = extract_rhythm(mono)
    result.update(analyze_bpm(rhythm_data, mono, sample_rate))
    result.update(analyze_key(mono, include_tuning=False))
    result.update(analyze_time_signature(rhythm_data, mono=mono, sample_rate=sample_rate))
    result["durationSeconds"] = round(float(len(mono) / sample_rate), 3)
    result["sampleRate"] = sample_rate

    # Basic loudness (LUFS integrated and range)
    try:
        # Need stereo for LUFS — Essentia expects shape (N, 2), not (2, N)
        stereo = np.stack([mono, mono], axis=-1)
        result.update(analyze_loudness(stereo, sample_rate=sample_rate))
    except Exception as e:
        print(f"[warn] Fast mode loudness analysis failed: {e}", file=sys.stderr)
        result["lufsIntegrated"] = None
        result["lufsRange"] = None

    # True peak (from stereo), emitted in dBTP (Phase 1 v2).
    try:
        if stereo is not None:
            result.update(analyze_true_peak(stereo))
        else:
            result["truePeak"] = None
    except Exception as e:
        print(f"[warn] Fast mode true peak failed: {e}", file=sys.stderr)
        result["truePeak"] = None

    # Basic dynamics - crest factor only
    try:
        peak = np.max(np.abs(mono))
        rms = np.sqrt(np.mean(mono**2))
        if rms > 0:
            crest_db = 20 * np.log10(peak / rms)
            result["crestFactor"] = round(float(crest_db), 2)
        else:
            result["crestFactor"] = None
    except Exception as e:
        print(f"[warn] Fast mode crest factor failed: {e}", file=sys.stderr)
        result["crestFactor"] = None

    # Set all other fields to None for fast mode
    result["dynamicSpread"] = None
    result["dynamicCharacter"] = None
    result["textureCharacter"] = None
    result["stereoDetail"] = None
    result["spectralBalance"] = None
    result["spectralBalanceTimeSeries"] = None
    result["spectralDetail"] = None
    result["stemAnalysis"] = None
    result["transientDensityDetail"] = None
    result["saturationDetail"] = None
    result["snareDetail"] = None
    result["hihatDetail"] = None
    result["rhythmDetail"] = None
    result["lufsCurve"] = None
    result["melodyDetail"] = None
    result["transcriptionDetail"] = None
    result["grooveDetail"] = None
    result["sidechainDetail"] = None
    result["effectsDetail"] = None
    result["synthesisCharacter"] = None
    result["danceability"] = None
    result["structure"] = None
    result["arrangementDetail"] = None
    result["segmentLoudness"] = None
    result["segmentSpectral"] = None
    result["segmentStereo"] = None
    result["segmentKey"] = None
    result["chordDetail"] = None
    result["perceptual"] = None
    result["essentiaFeatures"] = None

    return result
