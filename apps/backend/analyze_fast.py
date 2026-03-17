"""Fast analysis mode for analyze.py.

This module provides a streamlined analysis pipeline that runs only core
descriptors (BPM, key, loudness, basic dynamics) for rapid results.

Usage:
    from analyze_fast import analyze_fast
    result = analyze_fast(audio_path, sample_rate)
"""

import sys
import numpy as np
import essentia.standard as es


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

    # Run RhythmExtractor2013 for BPM and beat data
    try:
        rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
        bpm, beats, bpm_confidence, _, _ = rhythm_extractor(mono)
        result["bpm"] = round(float(bpm), 2) if bpm is not None else None
        result["bpmConfidence"] = round(float(bpm_confidence), 3) if bpm_confidence is not None else None
    except Exception as e:
        print(f"[warn] Fast mode BPM analysis failed: {e}", file=sys.stderr)
        result["bpm"] = None
        result["bpmConfidence"] = None
        beats = None

    # Percival BPM for cross-check
    try:
        percival = es.PercivalBpmEstimator()
        bpm_percival = percival(mono)
        result["bpmPercival"] = round(float(bpm_percival), 2) if bpm_percival is not None else None
    except Exception as e:
        print(f"[warn] Fast mode Percival BPM failed: {e}", file=sys.stderr)
        result["bpmPercival"] = None

    # BPM agreement
    if result.get("bpm") is not None and result.get("bpmPercival") is not None:
        result["bpmAgreement"] = abs(result["bpm"] - result["bpmPercival"]) < 2.0
    else:
        result["bpmAgreement"] = None

    # Key extraction
    try:
        key_extractor = es.KeyExtractor(profileType="temperley")
        key, scale, strength = key_extractor(mono)
        result["key"] = f"{key} {scale}".title() if key and scale else None
        result["keyConfidence"] = round(float(strength), 3) if strength is not None else None
    except Exception as e:
        print(f"[warn] Fast mode key analysis failed: {e}", file=sys.stderr)
        result["key"] = None
        result["keyConfidence"] = None

    # Time signature (default to 4/4 if we have rhythm data)
    if beats is not None and len(beats) > 0:
        result["timeSignature"] = "4/4"
    else:
        result["timeSignature"] = None

    # Duration
    result["durationSeconds"] = round(float(len(mono) / sample_rate), 3)
    result["sampleRate"] = sample_rate

    # Basic loudness (LUFS integrated and range)
    try:
        # Need stereo for LUFS — Essentia expects shape (N, 2), not (2, N)
        stereo = np.stack([mono, mono], axis=-1)
        loudness_algo = es.LoudnessEBUR128(sampleRate=sample_rate)
        _, _, lufs_integrated, lufs_range = loudness_algo(stereo)
        result["lufsIntegrated"] = round(float(lufs_integrated), 2) if lufs_integrated is not None else None
        result["lufsRange"] = round(float(lufs_range), 2) if lufs_range is not None else None
    except Exception as e:
        print(f"[warn] Fast mode loudness analysis failed: {e}", file=sys.stderr)
        result["lufsIntegrated"] = None
        result["lufsRange"] = None

    # True peak (from stereo)
    try:
        if stereo is not None:
            max_peak = np.max(np.abs(stereo))
            result["truePeak"] = round(float(max_peak), 6) if max_peak > 0 else None
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
    result["stereoDetail"] = None
    result["spectralBalance"] = None
    result["spectralDetail"] = None
    result["rhythmDetail"] = None
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
