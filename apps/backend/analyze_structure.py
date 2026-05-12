"""Structure segmentation, arrangement detail, synthesis character, and danceability."""

import sys

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None

from dsp_utils import _downsample_evenly

STRUCTURE_FRAME_SIZE = 2048
STRUCTURE_HOP_SIZE = 1024
STRUCTURE_MFCC_COEFFICIENTS = 13
STRUCTURE_MFCC_FEATURE_PRESET = "mfcc_z"
STRUCTURE_SBIC_PARAMS = {
    "cpw": 0.7,
    "size1": 300,
    "size2": 200,
    "inc1": 60,
    "inc2": 20,
    "minLength": 24,
}
STRUCTURE_TARGET_DURATION_MIN_SECONDS = 90.0
STRUCTURE_TARGET_DURATION_MAX_SECONDS = 360.0
STRUCTURE_COARSE_MIN_SEGMENT_COUNT = 4
STRUCTURE_COARSE_MEDIAN_SEGMENT_SECONDS = 35.0
STRUCTURE_NOVELTY_EXCLUSION_SECONDS = 2.5
STRUCTURE_SNAP_THRESHOLD_SECONDS = 0.75
STRUCTURE_MERGE_POLICY = "adaptive_clamped"
STRUCTURE_MERGE_BASELINE_SECONDS = 8.0
STRUCTURE_MERGE_BASELINE_BEATS = 4.0
STRUCTURE_MERGE_ADAPTIVE_SECONDS = 6.0
STRUCTURE_MERGE_ADAPTIVE_BEATS = 2.0
STRUCTURE_MERGE_ADAPTIVE_DURATION_FACTOR = 0.05
STRUCTURE_MAX_SEGMENTS = 20


def _pick_novelty_peaks(
    novelty: np.ndarray,
    sample_rate: int,
    hop_size: int,
    max_peaks: int = 8,
    min_spacing_sec: float = 2.0,
) -> list[dict]:
    """Pick strongest novelty peaks with minimum spacing."""
    arr = np.asarray(novelty, dtype=np.float64)
    if arr.size < 3 or sample_rate <= 0 or hop_size <= 0:
        return []

    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr))
    threshold = mean_val + (0.5 * std_val if std_val > 0 else 0.0)

    local_maxima = []
    for i in range(1, arr.size - 1):
        if arr[i] >= arr[i - 1] and arr[i] > arr[i + 1] and arr[i] >= threshold:
            local_maxima.append(i)

    if len(local_maxima) == 0:
        return []

    min_spacing_frames = max(
        1, int(round((min_spacing_sec * sample_rate) / float(hop_size)))
    )
    ranked = sorted(local_maxima, key=lambda idx: arr[idx], reverse=True)

    selected = []
    for idx in ranked:
        if all(abs(idx - chosen) >= min_spacing_frames for chosen in selected):
            selected.append(idx)
        if len(selected) >= max_peaks:
            break

    selected.sort()
    return [
        {
            "time": round(float((idx * hop_size) / float(sample_rate)), 3),
            "strength": round(float(arr[idx]), 4),
        }
        for idx in selected
    ]


def _compute_arrangement_novelty_summary(
    mono: np.ndarray,
    sample_rate: int,
    frame_size: int = STRUCTURE_FRAME_SIZE,
    hop_size: int = STRUCTURE_HOP_SIZE,
    # Bumped from 64 to 256 for Phase 1.A.5. At STRUCTURE_HOP_SIZE the native
    # novelty resolution on a 4-minute track is ~3000 frames; 64 collapsed
    # that to roughly one point per 4 seconds (transitions inside a build
    # become invisible). 256 keeps the payload modest while resolving roughly
    # one point per second — enough for Phase 2 to cite "novelty ramps for
    # 8 bars before the drop" instead of just naming peaks.
    max_curve_points: int = 256,
    max_peaks: int = 8,
    min_spacing_sec: float = 2.0,
) -> dict | None:
    """Compute arrangement novelty curve and peaks from Bark-band change."""
    try:
        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size == 0 or sample_rate <= 0:
            return None

        if mono_arr.size < frame_size:
            mono_arr = np.pad(mono_arr, (0, frame_size - mono_arr.size))

        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        bark_bands = es.BarkBands(numberBands=24, sampleRate=sample_rate)

        bark_matrix = []
        for frame in es.FrameGenerator(
            mono_arr,
            frameSize=frame_size,
            hopSize=hop_size,
        ):
            spec = spectrum(window(frame))
            bands = np.asarray(bark_bands(spec), dtype=np.float32)
            if bands.size == 24 and np.all(np.isfinite(bands)):
                bark_matrix.append(bands)

        if len(bark_matrix) < 2:
            return {
                "noveltyCurve": [],
                "noveltyPeaks": [],
                "noveltyMean": 0.0,
                "noveltyStdDev": 0.0,
            }

        novelty_algo = es.NoveltyCurve(
            frameRate=float(sample_rate) / float(hop_size),
            normalize=True,
        )
        novelty = novelty_algo(np.asarray(bark_matrix, dtype=np.float32))
        novelty = np.asarray(novelty, dtype=np.float64)
        novelty = novelty[np.isfinite(novelty)]

        if novelty.size == 0:
            return {
                "noveltyCurve": [],
                "noveltyPeaks": [],
                "noveltyMean": 0.0,
                "noveltyStdDev": 0.0,
            }

        max_val = float(np.max(np.abs(novelty)))
        if max_val > 0.0:
            novelty = novelty / max_val

        novelty_mean = float(np.mean(novelty))
        novelty_std = float(np.std(novelty))
        novelty_curve = _downsample_evenly(
            novelty,
            max_points=max_curve_points,
            decimals=4,
        )
        novelty_peaks = _pick_novelty_peaks(
            novelty,
            sample_rate=sample_rate,
            hop_size=hop_size,
            max_peaks=max_peaks,
            min_spacing_sec=min_spacing_sec,
        )

        return {
            "noveltyCurve": novelty_curve,
            "noveltyPeaks": novelty_peaks,
            "noveltyMean": round(novelty_mean, 4),
            "noveltyStdDev": round(novelty_std, 4),
        }
    except Exception:
        return None


def _zscore_feature_matrix(feature_matrix: np.ndarray) -> np.ndarray:
    """Z-score normalize each feature row independently."""
    matrix = np.asarray(feature_matrix, dtype=np.float64)
    if matrix.ndim != 2 or matrix.size == 0:
        return np.asarray([], dtype=np.float32)

    means = np.mean(matrix, axis=1, keepdims=True)
    stds = np.std(matrix, axis=1, keepdims=True)
    stds = np.where(stds > 1e-8, stds, 1.0)
    normalized = (matrix - means) / stds
    return normalized.astype(np.float32)


def _extract_structure_feature_matrix(
    mono: np.ndarray,
    sample_rate: int,
    feature_preset: str = STRUCTURE_MFCC_FEATURE_PRESET,
    frame_size: int = STRUCTURE_FRAME_SIZE,
    hop_size: int = STRUCTURE_HOP_SIZE,
) -> tuple[np.ndarray, int] | None:
    """Create SBic input features as [feature, frame] matrix."""
    if sample_rate <= 0:
        return None

    mono_arr = np.asarray(mono, dtype=np.float32)
    if mono_arr.ndim != 1 or mono_arr.size == 0:
        return None
    if mono_arr.size < frame_size:
        mono_arr = np.pad(mono_arr, (0, frame_size - mono_arr.size))

    window = es.Windowing(type="hann", size=frame_size)
    spectrum = es.Spectrum(size=frame_size)
    mfcc = es.MFCC(
        inputSize=frame_size // 2 + 1,
        sampleRate=sample_rate,
        numberCoefficients=STRUCTURE_MFCC_COEFFICIENTS,
    )

    feature_rows = []
    for frame in es.FrameGenerator(
        mono_arr,
        frameSize=frame_size,
        hopSize=hop_size,
    ):
        spec = spectrum(window(frame))
        _bands, coeffs = mfcc(spec)
        feature_rows.append(np.asarray(coeffs, dtype=np.float64))

    if len(feature_rows) < 2:
        return None

    feature_matrix = np.asarray(feature_rows, dtype=np.float64).T
    if feature_preset == "mfcc_z":
        normalized = _zscore_feature_matrix(feature_matrix)
    elif feature_preset == "mfcc_delta_z":
        deltas = np.diff(feature_matrix, axis=1, prepend=feature_matrix[:, :1])
        normalized = _zscore_feature_matrix(np.vstack((feature_matrix, deltas)))
    else:
        return None

    if normalized.ndim != 2 or normalized.shape[1] < 2:
        return None
    return normalized, hop_size


def _run_structure_sbic_boundaries(
    feature_matrix: np.ndarray,
    sample_rate: int,
    hop_size: int,
    sbic_params: dict | None = None,
) -> np.ndarray:
    """Run SBic on feature matrix and convert frame boundaries to seconds."""
    if sample_rate <= 0 or hop_size <= 0:
        return np.asarray([], dtype=np.float64)

    params = dict(STRUCTURE_SBIC_PARAMS)
    if isinstance(sbic_params, dict):
        params.update(sbic_params)

    boundary_frames = np.asarray(es.SBic(**params)(feature_matrix), dtype=np.float64)
    if boundary_frames.size == 0:
        return np.asarray([], dtype=np.float64)

    return boundary_frames * (float(hop_size) / float(sample_rate))


def _normalize_structure_boundaries(
    boundaries_seconds: np.ndarray,
    duration: float,
) -> np.ndarray:
    """Clamp, sort, and ensure segment boundaries include start/end."""
    boundaries = np.asarray(boundaries_seconds, dtype=np.float64)
    if boundaries.size == 0 or duration <= 0.0:
        return np.asarray([], dtype=np.float64)

    boundaries = boundaries[np.isfinite(boundaries)]
    if boundaries.size == 0:
        return np.asarray([], dtype=np.float64)

    boundaries = np.clip(boundaries, 0.0, duration)
    boundaries = np.unique(boundaries)
    boundaries.sort()
    if boundaries.size == 0:
        return np.asarray([], dtype=np.float64)

    if boundaries.size == 1:
        only = float(boundaries[0])
        if only > 0.0:
            boundaries = np.array([0.0, only], dtype=np.float64)
        else:
            boundaries = np.array([0.0, duration], dtype=np.float64)

    if boundaries[0] > 0.0:
        boundaries = np.insert(boundaries, 0, 0.0)
    if boundaries[-1] < duration:
        boundaries = np.append(boundaries, duration)

    boundaries = np.unique(boundaries)
    boundaries.sort()
    return boundaries


def _is_structure_output_too_coarse(
    boundaries_seconds: np.ndarray,
    duration: float,
) -> bool:
    """Determine whether SBic boundaries are too coarse for target material."""
    boundaries = np.asarray(boundaries_seconds, dtype=np.float64)
    if boundaries.size < 2:
        return True

    if (
        duration < STRUCTURE_TARGET_DURATION_MIN_SECONDS
        or duration > STRUCTURE_TARGET_DURATION_MAX_SECONDS
    ):
        return False

    segment_count = int(boundaries.size - 1)
    if segment_count < STRUCTURE_COARSE_MIN_SEGMENT_COUNT:
        return True

    segment_lengths = np.diff(boundaries)
    finite_lengths = segment_lengths[np.isfinite(segment_lengths) & (segment_lengths > 0)]
    if finite_lengths.size == 0:
        return True
    return float(np.median(finite_lengths)) >= STRUCTURE_COARSE_MEDIAN_SEGMENT_SECONDS


def _fuse_novelty_boundaries(
    boundaries_seconds: np.ndarray,
    novelty_peaks: list[dict] | None,
    duration: float,
    exclusion_seconds: float = STRUCTURE_NOVELTY_EXCLUSION_SECONDS,
) -> np.ndarray:
    """Fuse novelty peaks into boundaries while avoiding near-duplicates."""
    boundaries = np.asarray(boundaries_seconds, dtype=np.float64)
    if (
        boundaries.size == 0
        or duration <= 0.0
        or not isinstance(novelty_peaks, list)
        or len(novelty_peaks) == 0
    ):
        return boundaries

    fused = list(float(v) for v in boundaries)
    for peak in novelty_peaks:
        if not isinstance(peak, dict):
            continue
        time_value = peak.get("time")
        if time_value is None:
            continue
        candidate = float(time_value)
        if not np.isfinite(candidate) or candidate <= 0.0 or candidate >= duration:
            continue
        if any(abs(existing - candidate) <= exclusion_seconds for existing in fused):
            continue
        fused.append(candidate)

    fused_boundaries = np.unique(np.asarray(fused, dtype=np.float64))
    fused_boundaries.sort()
    return _normalize_structure_boundaries(fused_boundaries, duration)


def _boundaries_to_structure_segments(boundaries_seconds: np.ndarray) -> list[dict[str, float | int]]:
    """Convert sorted boundary times into segment objects."""
    boundaries = np.asarray(boundaries_seconds, dtype=np.float64)
    if boundaries.size < 2:
        return []

    segments = []
    for i in range(len(boundaries) - 1):
        start = float(boundaries[i])
        end = float(boundaries[i + 1])
        if end <= start:
            continue
        segments.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "index": int(i),
            },
        )
    return segments


def _compute_structure_merge_floor(
    duration: float,
    median_beat_interval: float | None,
    policy: str | None = None,
) -> float:
    """Resolve minimum segment duration floor for merge pass."""
    selected_policy = policy or STRUCTURE_MERGE_POLICY

    baseline_floor = STRUCTURE_MERGE_BASELINE_SECONDS
    if median_beat_interval is not None:
        baseline_floor = max(
            baseline_floor,
            STRUCTURE_MERGE_BASELINE_BEATS * float(median_beat_interval),
        )

    clamped_duration = float(
        min(
            max(duration, STRUCTURE_TARGET_DURATION_MIN_SECONDS),
            STRUCTURE_TARGET_DURATION_MAX_SECONDS,
        )
    )
    adaptive_floor = max(
        STRUCTURE_MERGE_ADAPTIVE_SECONDS,
        STRUCTURE_MERGE_ADAPTIVE_DURATION_FACTOR * clamped_duration,
    )
    if median_beat_interval is not None:
        adaptive_floor = max(
            adaptive_floor,
            STRUCTURE_MERGE_ADAPTIVE_BEATS * float(median_beat_interval),
        )

    if selected_policy == "baseline":
        return float(baseline_floor)
    if selected_policy == "adaptive_clamped":
        return float(adaptive_floor)
    if selected_policy == "min_of_baseline_adaptive":
        return float(min(baseline_floor, adaptive_floor))
    return float(baseline_floor)


def _resolve_downbeats_and_interval(
    rhythm_data: dict | None,
) -> tuple[np.ndarray, float | None]:
    """Return assumed downbeats and the median beat interval when rhythm exists."""
    if rhythm_data is None:
        return np.asarray([], dtype=np.float64), None

    ticks = np.asarray(rhythm_data.get("ticks", []), dtype=np.float64)
    ticks = ticks[np.isfinite(ticks)]
    if ticks.size == 0:
        return np.asarray([], dtype=np.float64), None

    median_beat_interval = None
    if ticks.size >= 2:
        beat_intervals = np.diff(ticks)
        finite_intervals = beat_intervals[np.isfinite(beat_intervals) & (beat_intervals > 0)]
        if finite_intervals.size > 0:
            median_beat_interval = float(np.median(finite_intervals))

    return ticks[::4], median_beat_interval


def _merge_short_structure_segments(
    segments: list[dict[str, float | int]],
    minimum_duration_seconds: float,
) -> list[dict[str, float | int]]:
    """Merge segments shorter than the floor into neighbours."""
    if len(segments) <= 1 or minimum_duration_seconds <= 0.0:
        return list(segments)

    merged_segments = list(segments)
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(merged_segments):
            seg = merged_segments[i]
            seg_duration = float(seg["end"]) - float(seg["start"])
            if seg_duration >= minimum_duration_seconds or len(merged_segments) <= 1:
                i += 1
                continue

            if i == 0 and i + 1 < len(merged_segments):
                merged_segments[i + 1] = {
                    "start": seg["start"],
                    "end": merged_segments[i + 1]["end"],
                    "index": merged_segments[i + 1]["index"],
                }
                merged_segments.pop(i)
                changed = True
            elif i == len(merged_segments) - 1:
                merged_segments[i - 1] = {
                    "start": merged_segments[i - 1]["start"],
                    "end": seg["end"],
                    "index": merged_segments[i - 1]["index"],
                }
                merged_segments.pop(i)
                changed = True
            else:
                prev_dur = float(merged_segments[i - 1]["end"]) - float(
                    merged_segments[i - 1]["start"]
                )
                next_dur = float(merged_segments[i + 1]["end"]) - float(
                    merged_segments[i + 1]["start"]
                )
                if prev_dur <= next_dur:
                    merged_segments[i - 1] = {
                        "start": merged_segments[i - 1]["start"],
                        "end": seg["end"],
                        "index": merged_segments[i - 1]["index"],
                    }
                else:
                    merged_segments[i + 1] = {
                        "start": seg["start"],
                        "end": merged_segments[i + 1]["end"],
                        "index": merged_segments[i + 1]["index"],
                    }
                merged_segments.pop(i)
                changed = True
            break

    return [
        {
            "start": round(float(segment["start"]), 3),
            "end": round(float(segment["end"]), 3),
            "index": int(index),
        }
        for index, segment in enumerate(merged_segments)
        if float(segment["end"]) > float(segment["start"])
    ]


def analyze_arrangement_detail(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Novelty timeline from Bark bands to expose structural events."""
    try:
        novelty_summary = _compute_arrangement_novelty_summary(mono, sample_rate)
        return {"arrangementDetail": novelty_summary}
    except Exception as e:
        print(f"[warn] Arrangement detail analysis failed: {e}", file=sys.stderr)
        return {"arrangementDetail": None}


def analyze_synthesis_character(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Frame-wise synthesis character from inharmonicity and odd/even ratio."""
    try:
        frame_size = 2048
        hop_size = 1024
        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        spectral_peaks = es.SpectralPeaks(
            orderBy="frequency",
            magnitudeThreshold=0.00001,
            maxPeaks=60,
            sampleRate=sample_rate,
        )

        inharmonicity_algo = es.Inharmonicity()
        odd_even_algo = es.OddToEvenHarmonicEnergyRatio()

        inharmonicity_vals = []
        odd_even_vals = []

        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum(window(frame))

            try:
                freqs, mags = spectral_peaks(spec)
                freqs = np.asarray(freqs, dtype=np.float64)
                mags = np.asarray(mags, dtype=np.float64)

                valid = freqs > 0.0
                freqs = freqs[valid]
                mags = mags[valid]
                if freqs.size == 0:
                    continue

                try:
                    inh = float(inharmonicity_algo(freqs, mags))
                    if np.isfinite(inh):
                        inharmonicity_vals.append(inh)
                except Exception:
                    pass

                try:
                    ratio = float(odd_even_algo(freqs, mags))
                    if np.isfinite(ratio):
                        odd_even_vals.append(ratio)
                except Exception:
                    pass
            except Exception:
                continue

        return {
            "synthesisCharacter": {
                "inharmonicity": round(float(np.mean(inharmonicity_vals)), 4)
                if inharmonicity_vals
                else 0.0,
                "oddToEvenRatio": round(float(np.mean(odd_even_vals)), 4)
                if odd_even_vals
                else 0.0,
            }
        }
    except Exception as e:
        print(f"[warn] Synthesis character analysis failed: {e}", file=sys.stderr)
        return {"synthesisCharacter": None}


def analyze_danceability(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Danceability and DFA complexity indicator from Essentia Danceability."""
    try:
        danceability_algo = es.Danceability(sampleRate=sample_rate)
        danceability_value, dfa_values = danceability_algo(mono)

        dfa_array = np.asarray(dfa_values, dtype=np.float64)
        if dfa_array.size == 0:
            dfa_value = 0.0
        else:
            dfa_value = float(np.mean(dfa_array))

        return {
            "danceability": {
                "danceability": round(float(danceability_value), 4),
                "dfa": round(dfa_value, 4),
            }
        }
    except Exception as e:
        print(f"[warn] Danceability analysis failed: {e}", file=sys.stderr)
        return {"danceability": None}


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
