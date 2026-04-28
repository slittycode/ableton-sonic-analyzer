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
