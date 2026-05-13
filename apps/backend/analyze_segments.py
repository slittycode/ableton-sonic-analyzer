"""Per-segment analysis — loudness, stereo, spectral, key, and chords."""

import sys
from collections import Counter

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None

from dsp_utils import (
    _compute_bark_db,
    _compute_stereo_metrics,
    _safe_db,
    _slice_segments,
    _to_finite_float,
)


def analyze_segment_loudness(
    structure_data: dict | None,
    stereo: np.ndarray | None,
    sample_rate: int = 44100,
) -> dict:
    """Compute LUFS/LRA per structure segment using LoudnessEBUR128."""
    try:
        if structure_data is None or stereo is None:
            return {"segmentLoudness": None}

        stereo_arr = np.asarray(stereo, dtype=np.float32)
        if stereo_arr.ndim == 1:
            stereo_arr = stereo_arr[:, np.newaxis]
        if stereo_arr.ndim != 2 or stereo_arr.shape[0] == 0:
            return {"segmentLoudness": None}

        segment_slices = _slice_segments(
            structure_data, int(stereo_arr.shape[0]), sample_rate
        )
        if segment_slices is None:
            return {"segmentLoudness": None}

        out = []

        for segment in segment_slices:
            start = float(segment["start"])
            end = float(segment["end"])
            index = int(segment["segmentIndex"])
            start_idx = int(segment["start_idx"])
            end_idx = int(segment["end_idx"])
            lufs = None
            lra = None
            if end_idx > start_idx:
                try:
                    segment_audio = stereo_arr[start_idx:end_idx]
                    _m, _s, integrated, loudness_range = es.LoudnessEBUR128(
                        sampleRate=sample_rate
                    )(segment_audio)
                    if np.isfinite(integrated):
                        lufs = round(float(integrated), 1)
                    if np.isfinite(loudness_range):
                        lra = round(float(loudness_range), 1)
                except Exception:
                    lufs = None
                    lra = None

            out.append(
                {
                    "segmentIndex": index,
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "lufs": lufs,
                    "lra": lra,
                }
            )

        return {"segmentLoudness": out}
    except Exception as e:
        print(f"[warn] Segment loudness analysis failed: {e}", file=sys.stderr)
        return {"segmentLoudness": None}


def analyze_segment_stereo(
    structure_data: dict | None,
    stereo: np.ndarray | None,
    sample_rate: int = 44100,
) -> dict:
    """Compute stereo metrics per segment using shared segment slicing."""
    try:
        if structure_data is None or stereo is None:
            return {"segmentStereo": None}

        stereo_arr = np.asarray(stereo, dtype=np.float64)
        if stereo_arr.ndim != 2 or stereo_arr.shape[0] == 0:
            return {"segmentStereo": None}

        segment_slices = _slice_segments(
            structure_data, int(stereo_arr.shape[0]), sample_rate
        )
        if segment_slices is None:
            return {"segmentStereo": None}

        if stereo_arr.shape[1] < 2:
            left_all = stereo_arr[:, 0]
            right_all = stereo_arr[:, 0]
        else:
            left_all = stereo_arr[:, 0]
            right_all = stereo_arr[:, 1]

        out = []
        for segment in segment_slices:
            index = int(segment["segmentIndex"])
            start_idx = int(segment["start_idx"])
            end_idx = int(segment["end_idx"])

            if end_idx - start_idx < 2:
                metrics = {"stereoWidth": None, "stereoCorrelation": None}
            else:
                metrics = _compute_stereo_metrics(
                    left_all[start_idx:end_idx], right_all[start_idx:end_idx]
                )

            out.append(
                {
                    "segmentIndex": index,
                    "stereoWidth": metrics.get("stereoWidth"),
                    "stereoCorrelation": metrics.get("stereoCorrelation"),
                }
            )

        return {"segmentStereo": out}
    except Exception as e:
        print(f"[warn] Segment stereo analysis failed: {e}", file=sys.stderr)
        return {"segmentStereo": None}


def analyze_segment_spectral(
    structure_data: dict | None,
    mono: np.ndarray,
    segment_stereo_data: list[dict] | None = None,
    sample_rate: int = 44100,
) -> dict:
    """Compute Bark, centroid/rolloff, and stereo metrics per segment."""
    try:
        if structure_data is None:
            return {"segmentSpectral": None}

        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size == 0:
            return {"segmentSpectral": None}

        segment_slices = _slice_segments(
            structure_data, int(mono_arr.shape[0]), sample_rate
        )
        if segment_slices is None:
            return {"segmentSpectral": None}

        stereo_map = {}
        if isinstance(segment_stereo_data, list):
            for item in segment_stereo_data:
                try:
                    stereo_map[int(item.get("segmentIndex"))] = {
                        "stereoWidth": item.get("stereoWidth"),
                        "stereoCorrelation": item.get("stereoCorrelation"),
                    }
                except Exception:
                    continue

        frame_size = 2048
        hop_size = 1024
        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        centroid_algo = es.SpectralCentroidTime(sampleRate=sample_rate)
        rolloff_algo = es.RollOff(sampleRate=sample_rate)

        out = []

        for segment in segment_slices:
            index = int(segment["segmentIndex"])
            start_idx = int(segment["start_idx"])
            end_idx = int(segment["end_idx"])

            bark_bands = None
            if end_idx > start_idx:
                bark_bands = _compute_bark_db(
                    mono_arr[start_idx:end_idx],
                    sample_rate=sample_rate,
                    frame_size=2048,
                    hop_size=1024,
                    number_bands=24,
                )
            if bark_bands is None:
                bark_bands = [-100.0] * 24

            spectral_centroid = None
            spectral_rolloff = None
            if end_idx > start_idx:
                seg_audio = mono_arr[start_idx:end_idx]
                if seg_audio.size < frame_size:
                    seg_audio = np.pad(seg_audio, (0, frame_size - seg_audio.size))
                centroid_vals = []
                rolloff_vals = []
                for frame in es.FrameGenerator(
                    seg_audio, frameSize=frame_size, hopSize=hop_size
                ):
                    try:
                        spec = spectrum(window(frame))
                        centroid_vals.append(float(centroid_algo(frame)))
                        rolloff_vals.append(float(rolloff_algo(spec)))
                    except Exception:
                        continue
                if len(centroid_vals) > 0:
                    spectral_centroid = round(float(np.mean(centroid_vals)), 1)
                if len(rolloff_vals) > 0:
                    spectral_rolloff = round(float(np.mean(rolloff_vals)), 1)

            stereo_item = stereo_map.get(index, {})
            out.append(
                {
                    "segmentIndex": index,
                    "barkBands": bark_bands,
                    "spectralCentroid": spectral_centroid,
                    "spectralRolloff": spectral_rolloff,
                    "stereoWidth": stereo_item.get("stereoWidth"),
                    "stereoCorrelation": stereo_item.get("stereoCorrelation"),
                }
            )

        return {"segmentSpectral": out}
    except Exception as e:
        print(f"[warn] Segment spectral analysis failed: {e}", file=sys.stderr)
        return {"segmentSpectral": None}


def analyze_segment_key(
    structure_data: dict | None,
    mono: np.ndarray,
    sample_rate: int = 44100,
) -> dict:
    """Compute key and confidence per segment using KeyExtractor."""
    try:
        if structure_data is None:
            return {"segmentKey": None}

        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size == 0:
            return {"segmentKey": None}

        segment_slices = _slice_segments(
            structure_data, int(mono_arr.shape[0]), sample_rate
        )
        if segment_slices is None:
            return {"segmentKey": None}

        key_extractor = es.KeyExtractor(profileType="edma")
        out = []
        for segment in segment_slices:
            index = int(segment["segmentIndex"])
            start_idx = int(segment["start_idx"])
            end_idx = int(segment["end_idx"])

            key_value = None
            key_confidence = None
            if end_idx - start_idx >= 2:
                seg_audio = mono_arr[start_idx:end_idx]
                try:
                    key, scale, strength = key_extractor(seg_audio)
                    key_value = f"{key} {scale.capitalize()}"
                    if np.isfinite(strength):
                        key_confidence = round(float(strength), 2)
                except Exception:
                    key_value = None
                    key_confidence = None

            out.append(
                {
                    "segmentIndex": index,
                    "key": key_value,
                    "keyConfidence": key_confidence,
                }
            )

        return {"segmentKey": out}
    except Exception as e:
        print(f"[warn] Segment key analysis failed: {e}", file=sys.stderr)
        return {"segmentKey": None}


def analyze_chords(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Frame-wise HPCP analysis and chord detection via ChordsDetection."""
    try:
        hp_filter = es.HighPass(cutoffFrequency=120, sampleRate=sample_rate)
        mono_filtered = hp_filter(mono)

        frame_size = 4096
        hop_size = 2048
        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        spectral_peaks = es.SpectralPeaks(
            orderBy="magnitude",
            magnitudeThreshold=0.00001,
            maxPeaks=60,
            sampleRate=sample_rate,
        )
        hpcp_algo = es.HPCP(sampleRate=sample_rate)
        chords_algo = es.ChordsDetection(sampleRate=sample_rate, hopSize=hop_size)

        hpcp_sequence = []
        for frame in es.FrameGenerator(
            mono_filtered, frameSize=frame_size, hopSize=hop_size
        ):
            spec = spectrum(window(frame))
            try:
                freqs, mags = spectral_peaks(spec)
                if len(freqs) > 0:
                    hpcp = hpcp_algo(freqs, mags)
                    hpcp_sequence.append(np.asarray(hpcp, dtype=np.float32))
            except Exception:
                continue

        if len(hpcp_sequence) == 0:
            return {
                "chordDetail": {
                    "chordSequence": [],
                    "chordStrength": 0.0,
                    "progression": [],
                    "dominantChords": [],
                }
            }

        chords, strength = chords_algo(np.asarray(hpcp_sequence, dtype=np.float32))
        chords = [str(c) for c in chords]
        strength = np.asarray(strength, dtype=np.float64)

        if len(chords) == 0:
            return {
                "chordDetail": {
                    "chordSequence": [],
                    "chordStrength": 0.0,
                    "progression": [],
                    "dominantChords": [],
                    "chordTimeline": [],
                    "chordChangeCount": 0,
                }
            }

        # Keep payload manageable.
        if len(chords) > 32:
            indices = np.linspace(0, len(chords) - 1, 32, dtype=int)
            chord_sequence = [chords[i] for i in indices]
        else:
            chord_sequence = chords

        chord_strength = (
            round(float(np.mean(strength)), 4) if strength.size > 0 else 0.0
        )

        progression = []
        for chord in chords:
            if not progression or progression[-1] != chord:
                progression.append(chord)
            if len(progression) >= 16:
                break

        dominant_chords = [label for label, _count in Counter(chords).most_common(4)]

        # Phase 1.D #2 — temporal chord timeline. Each per-frame label is
        # smoothed with a 5-frame median (≈ 250 ms at hop_size=2048/44.1k),
        # then consecutive same-label frames are merged into segments with
        # start/end times and the mean strength across that segment. Segments
        # shorter than the smoothing window (after merging) are dropped to
        # suppress noise; the cap of 64 segments keeps the payload bounded.
        frame_duration_s = float(hop_size) / float(sample_rate)
        smooth_window = 5  # frames

        def _median_label(window: list[str]) -> str:
            counts: dict[str, int] = {}
            for label in window:
                counts[label] = counts.get(label, 0) + 1
            return max(counts.items(), key=lambda kv: kv[1])[0]

        smoothed: list[str] = []
        n_chords = len(chords)
        for i in range(n_chords):
            lo = max(0, i - smooth_window // 2)
            hi = min(n_chords, i + smooth_window // 2 + 1)
            smoothed.append(_median_label(chords[lo:hi]))

        chord_timeline: list[dict] = []
        if smoothed:
            seg_label = smoothed[0]
            seg_start_idx = 0
            for idx in range(1, n_chords):
                if smoothed[idx] != seg_label:
                    seg_end_idx = idx
                    seg_strength_slice = strength[seg_start_idx:seg_end_idx]
                    seg_conf = (
                        float(np.mean(seg_strength_slice))
                        if seg_strength_slice.size > 0 else 0.0
                    )
                    chord_timeline.append({
                        "startSec": round(seg_start_idx * frame_duration_s, 3),
                        "endSec": round(seg_end_idx * frame_duration_s, 3),
                        "label": seg_label,
                        "confidence": round(seg_conf, 4),
                    })
                    seg_label = smoothed[idx]
                    seg_start_idx = idx
            # Flush the final open segment.
            seg_strength_slice = strength[seg_start_idx:n_chords]
            seg_conf = (
                float(np.mean(seg_strength_slice))
                if seg_strength_slice.size > 0 else 0.0
            )
            chord_timeline.append({
                "startSec": round(seg_start_idx * frame_duration_s, 3),
                "endSec": round(n_chords * frame_duration_s, 3),
                "label": seg_label,
                "confidence": round(seg_conf, 4),
            })

            # Drop segments shorter than the smoothing-window equivalent
            # (≈ 250 ms). They typically reflect chord-detector noise around
            # transitions rather than real harmonic events.
            min_segment_s = smooth_window * frame_duration_s
            chord_timeline = [
                seg for seg in chord_timeline
                if (seg["endSec"] - seg["startSec"]) >= min_segment_s
            ]

            # Cap at 64 segments. If we overflow, keep the 64 longest
            # by duration — those carry the most musical weight.
            if len(chord_timeline) > 64:
                chord_timeline.sort(
                    key=lambda seg: seg["endSec"] - seg["startSec"], reverse=True
                )
                chord_timeline = sorted(chord_timeline[:64], key=lambda s: s["startSec"])

        # Count of unique chord-to-chord transitions in the smoothed sequence
        # (a proxy for "how harmonically active is this track" — flat 1-chord
        # tracks score 0; rapid-changes tracks score 16+).
        chord_change_count = sum(
            1 for i in range(1, len(chord_timeline))
            if chord_timeline[i]["label"] != chord_timeline[i - 1]["label"]
        )

        return {
            "chordDetail": {
                "chordSequence": chord_sequence,
                "chordStrength": chord_strength,
                "progression": progression,
                "dominantChords": dominant_chords,
                "chordTimeline": chord_timeline,
                "chordChangeCount": chord_change_count,
            }
        }
    except Exception as e:
        print(f"[warn] Chord analysis failed: {e}", file=sys.stderr)
        return {"chordDetail": None}




