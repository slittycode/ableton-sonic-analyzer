"""Shared DSP utility functions used across analysis modules."""

import json
import sys

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None


def midi_to_note_name(midi_num: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (midi_num // 12) - 1
    name = names[midi_num % 12]
    return f"{name}{octave}"


def _safe_db(value: float) -> float:
    """Convert linear power/energy to dB with a safe floor."""
    return round(float(10.0 * np.log10(value)), 4) if value > 0 else -100.0


def _compute_bark_db(
    mono_slice: np.ndarray,
    sample_rate: int,
    frame_size: int = 2048,
    hop_size: int = 1024,
    number_bands: int = 24,
) -> list[float] | None:
    """Compute mean Bark band energies in dB for a mono slice."""
    try:
        if mono_slice is None or len(mono_slice) == 0:
            return None

        signal = np.asarray(mono_slice, dtype=np.float32)
        if signal.size < frame_size:
            signal = np.pad(signal, (0, frame_size - signal.size))

        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        bark_bands = es.BarkBands(numberBands=number_bands, sampleRate=sample_rate)

        bark_values = []
        for frame in es.FrameGenerator(signal, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum(window(frame))
            bark_values.append(np.asarray(bark_bands(spec), dtype=np.float64))

        if len(bark_values) == 0:
            return None

        mean_linear = np.mean(np.asarray(bark_values, dtype=np.float64), axis=0)
        return [_safe_db(float(v)) for v in mean_linear]
    except Exception:
        return None


def _compute_stereo_metrics(left: np.ndarray, right: np.ndarray) -> dict:
    """Compute stereo width and L/R correlation safely."""
    try:
        left_arr = np.asarray(left, dtype=np.float64)
        right_arr = np.asarray(right, dtype=np.float64)
        if left_arr.size == 0 or right_arr.size == 0:
            return {"stereoWidth": None, "stereoCorrelation": None}

        n = min(left_arr.size, right_arr.size)
        if n < 2:
            return {"stereoWidth": None, "stereoCorrelation": None}
        left_arr = left_arr[:n]
        right_arr = right_arr[:n]

        correlation = float(np.corrcoef(left_arr, right_arr)[0, 1])
        if not np.isfinite(correlation):
            correlation = 0.0

        mid = (left_arr + right_arr) / 2.0
        side = (left_arr - right_arr) / 2.0
        mid_energy = float(np.mean(mid**2))
        side_energy = float(np.mean(side**2))
        width = side_energy / mid_energy if mid_energy > 0 else 0.0

        return {
            "stereoWidth": round(float(width), 2),
            "stereoCorrelation": round(float(correlation), 2),
        }
    except Exception:
        return {"stereoWidth": None, "stereoCorrelation": None}


def _slice_segments(
    structure_data: dict | None, total_samples: int, sample_rate: int
) -> list[dict] | None:
    """Create canonical sample-index segment slices from structure output."""
    try:
        if (
            structure_data is None
            or total_samples <= 0
            or sample_rate <= 0
            or not isinstance(structure_data, dict)
        ):
            return None

        segments = structure_data.get("segments")
        if not isinstance(segments, list) or len(segments) == 0:
            return None

        sliced = []
        for i, segment in enumerate(segments):
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start))
            index = int(segment.get("index", i))
            if not np.isfinite(start) or not np.isfinite(end):
                continue

            start_idx = max(0, min(int(total_samples), int(round(start * sample_rate))))
            end_idx = max(
                start_idx, min(int(total_samples), int(round(end * sample_rate)))
            )

            sliced.append(
                {
                    "segmentIndex": index,
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "start_idx": start_idx,
                    "end_idx": end_idx,
                }
            )

        return sliced if len(sliced) > 0 else None
    except Exception:
        return None


def _downsample_evenly(
    values: np.ndarray, max_points: int, decimals: int = 4
) -> list[float]:
    """Evenly subsample an array to max_points and round values."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0 or max_points <= 0:
        return []
    if arr.size > max_points:
        indices = np.linspace(0, arr.size - 1, max_points, dtype=int)
        arr = arr[indices]
    return [round(float(v), decimals) for v in arr]


def _downsample_lufs_array(
    values: np.ndarray,
    target_points: int = 200,
    frame_hop_seconds: float = 0.1,
    value_decimals: int = 1,
    time_decimals: int = 2,
) -> list[dict[str, float]]:
    """Downsample an EBU R128 momentary/short-term LUFS array to ``[{t, lufs}, ...]``.

    Each output point is the bin-center timestamp paired with the mean of finite
    LUFS values in that bin. Returns ``[]`` when the input has no finite samples.
    The default ``frame_hop_seconds`` matches Essentia's ``LoudnessEBUR128``
    output rate (100 ms between frames).
    """
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0 or target_points <= 0:
        return []
    if not np.any(np.isfinite(arr)):
        return []
    n = arr.size
    bin_size = max(1, int(np.ceil(n / target_points)))
    points: list[dict[str, float]] = []
    for start in range(0, n, bin_size):
        stop = min(n, start + bin_size)
        chunk = arr[start:stop]
        chunk_finite = chunk[np.isfinite(chunk)]
        if chunk_finite.size == 0:
            continue
        center_frame = (start + stop - 1) / 2.0
        t = round(center_frame * frame_hop_seconds, time_decimals)
        lufs_value = round(float(np.mean(chunk_finite)), value_decimals)
        points.append({"t": t, "lufs": lufs_value})
    return points


def _downsample_band_energies_curve(
    band_energies: dict[str, list[float]],
    band_names: list[str],
    frame_hop_seconds: float,
    target_points: int = 200,
    db_decimals: int = 1,
    time_decimals: int = 2,
) -> list[dict[str, float]]:
    """Convert per-frame band-energy lists to a downsampled time series.

    Returns rows of the shape ``{t, <band>: dB, ...}`` so a single row carries
    all bands at a given timestamp — the schema the UI and Phase 2 prompt expect.
    Energies that are zero or negative collapse to a -100 dB floor so JSON
    serialization stays finite.
    """
    if not band_energies or not band_names:
        return []
    first_band = band_names[0]
    series_len = len(band_energies.get(first_band, []))
    if series_len == 0:
        return []
    bin_size = max(1, int(np.ceil(series_len / target_points)))
    points: list[dict[str, float]] = []
    for start in range(0, series_len, bin_size):
        stop = min(series_len, start + bin_size)
        center_frame = (start + stop - 1) / 2.0
        t = round(center_frame * frame_hop_seconds, time_decimals)
        point: dict[str, float] = {"t": t}
        for name in band_names:
            chunk = band_energies.get(name, [])[start:stop]
            if not chunk:
                point[name] = -100.0
                continue
            chunk_arr = np.asarray(chunk, dtype=np.float64)
            chunk_arr = chunk_arr[chunk_arr > 0]
            if chunk_arr.size == 0:
                point[name] = -100.0
                continue
            mean_energy = float(np.mean(chunk_arr))
            point[name] = round(_safe_db(mean_energy), db_decimals)
        points.append(point)
    return points


def _compute_tempo_curve_from_ticks(
    ticks: np.ndarray,
    smoothing_window_beats: int = 4,
    target_points: int = 200,
    bpm_decimals: int = 1,
    time_decimals: int = 2,
) -> list[dict[str, float]]:
    """Instantaneous BPM from beat ticks, smoothed with a rolling median.

    For each pair of consecutive ticks we compute ``60 / (t_{i+1} - t_i)``; the
    series is then smoothed with a centered ``smoothing_window_beats``-wide
    median to reject single-beat jitter, downsampled to ``target_points``, and
    returned as ``[{t, bpm}, ...]`` rows aligned to interval midpoints.
    """
    arr = np.asarray(ticks, dtype=np.float64)
    if arr.size < 2:
        return []
    intervals = np.diff(arr)
    intervals = np.where(intervals > 0, intervals, np.nan)
    instant_bpm = np.full_like(intervals, np.nan, dtype=np.float64)
    valid = np.isfinite(intervals)
    instant_bpm[valid] = 60.0 / intervals[valid]
    if not np.any(np.isfinite(instant_bpm)):
        return []

    window = max(1, smoothing_window_beats)
    half = window // 2
    n = instant_bpm.size
    smoothed = np.copy(instant_bpm)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = instant_bpm[lo:hi]
        chunk_finite = chunk[np.isfinite(chunk)]
        if chunk_finite.size > 0:
            smoothed[i] = float(np.median(chunk_finite))

    midpoints = (arr[:-1] + arr[1:]) / 2.0
    bin_size = max(1, int(np.ceil(n / target_points)))
    points: list[dict[str, float]] = []
    for start in range(0, n, bin_size):
        stop = min(n, start + bin_size)
        chunk_bpm = smoothed[start:stop]
        chunk_t = midpoints[start:stop]
        chunk_bpm_finite = chunk_bpm[np.isfinite(chunk_bpm)]
        if chunk_bpm_finite.size == 0:
            continue
        points.append(
            {
                "t": round(float(np.mean(chunk_t)), time_decimals),
                "bpm": round(float(np.mean(chunk_bpm_finite)), bpm_decimals),
            }
        )
    return points


def _compute_stereo_correlation_curve(
    left: np.ndarray,
    right: np.ndarray,
    left_sub: np.ndarray,
    right_sub: np.ndarray,
    sample_rate: int,
    window_seconds: float = 1.0,
    correlation_decimals: int = 3,
    time_decimals: int = 2,
) -> list[dict[str, float | None]]:
    """1-second windowed L/R correlation, full-band and sub-band side-by-side.

    Emits one row per non-overlapping window ``[{t, full, sub}, ...]``. Sub
    correlation is ``None`` when the sub band is silent in that window so the
    UI can render a gap rather than a misleading zero.
    """
    if sample_rate <= 0 or window_seconds <= 0:
        return []
    samples_per_window = int(window_seconds * sample_rate)
    if samples_per_window <= 0:
        return []
    full_n = min(left.size, right.size)
    sub_n = min(left_sub.size, right_sub.size)
    n = min(full_n, sub_n)
    if n < samples_per_window:
        return []
    points: list[dict[str, float | None]] = []
    for start in range(0, n - samples_per_window + 1, samples_per_window):
        stop = start + samples_per_window
        full_corr = _pearson_corr(left[start:stop], right[start:stop])
        sub_corr = _pearson_corr(left_sub[start:stop], right_sub[start:stop])
        t = round((start + samples_per_window / 2.0) / sample_rate, time_decimals)
        points.append(
            {
                "t": t,
                "full": round(full_corr, correlation_decimals)
                if np.isfinite(full_corr)
                else None,
                "sub": round(sub_corr, correlation_decimals)
                if np.isfinite(sub_corr)
                else None,
            }
        )
    return points


def _pearson_corr(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation between two equal-length arrays, NaN on degenerate input."""
    if a.size == 0 or b.size == 0:
        return float("nan")
    n = min(a.size, b.size)
    a64 = np.asarray(a[:n], dtype=np.float64)
    b64 = np.asarray(b[:n], dtype=np.float64)
    a_var = float(np.var(a64))
    b_var = float(np.var(b64))
    if a_var <= 0.0 or b_var <= 0.0:
        return float("nan")
    cov = float(np.mean((a64 - np.mean(a64)) * (b64 - np.mean(b64))))
    return cov / np.sqrt(a_var * b_var)


def _to_finite_float(value, default=None):
    try:
        numeric = float(value)
    except Exception:
        return default
    return numeric if np.isfinite(numeric) else default


def _normalize_confidence(value) -> float:
    numeric = _to_finite_float(value, 1.0)
    if numeric is None:
        numeric = 1.0
    return round(float(np.clip(numeric, 0.0, 1.0)), 4)


def _emit_progress_marker(
    step_key: str,
    message: str,
    fraction: float | None = None,
) -> None:
    payload: dict[str, object] = {
        "stepKey": step_key,
        "message": message,
    }
    if isinstance(fraction, (int, float)):
        payload["fraction"] = min(max(float(fraction), 0.0), 1.0)
    print(f"@@ASA_PROGRESS {json.dumps(payload)}", file=sys.stderr, flush=True)
