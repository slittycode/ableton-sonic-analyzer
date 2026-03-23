"""Librosa-based spectrogram generation and spectral time-series extraction.

This module provides visualization-layer spectral data. It does NOT replace
Essentia's authoritative scalar measurements — it generates spectrogram images
and per-frame time-series for frontend rendering.

All functions are designed for server-side use with matplotlib's Agg backend
(thread-safe, non-interactive).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import librosa
import matplotlib
import numpy as np

matplotlib.use("Agg")

# Match analyze.py's frame parameters for timing consistency.
DEFAULT_SR = 44100
DEFAULT_N_FFT = 2048
DEFAULT_HOP_LENGTH = 1024

# Spectrogram image dimensions (inches at 100 dpi → pixels).
FIG_WIDTH_INCHES = 12
FIG_HEIGHT_INCHES = 4
FIG_DPI = 100

# Maximum data points for time-series JSON (keeps payload ~10-20 KB).
DEFAULT_MAX_POINTS = 500

# Mel spectrogram parameters.
N_MELS = 128

# Chroma parameters.
N_CHROMA = 12

# CQT parameters.
CQT_N_BINS = 84
CQT_BINS_PER_OCTAVE = 12

# HPSS parameters.
HPSS_MARGIN = 2.0

# Pitch class names for interactive chroma.
PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _load_audio(audio_path: str, sr: int = DEFAULT_SR) -> np.ndarray:
    """Load audio as mono float32 at the target sample rate."""
    y, _ = librosa.load(audio_path, sr=sr, mono=True)
    return y


def _downsample_time_series(arr: np.ndarray, max_points: int) -> np.ndarray:
    """Block-average a 1D array down to at most *max_points* values."""
    if arr.shape[0] <= max_points:
        return arr
    block_size = arr.shape[0] // max_points
    trimmed = arr[: block_size * max_points]
    return trimmed.reshape(max_points, block_size).mean(axis=1)


def generate_spectrograms(
    audio_path: str,
    output_dir: str,
    *,
    sr: int = DEFAULT_SR,
    n_fft: int = DEFAULT_N_FFT,
    hop_length: int = DEFAULT_HOP_LENGTH,
) -> dict[str, str]:
    """Generate mel spectrogram PNG.

    Returns a dict mapping artifact kind to the output file path:
        {
            "spectrogram_mel": "/path/to/mel.png",
        }
    """
    import matplotlib.figure as mpl_figure

    y = _load_audio(audio_path, sr=sr)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    # --- Mel spectrogram ---
    S_mel = librosa.feature.melspectrogram(
        y=y, sr=sr, n_fft=n_fft, hop_length=hop_length, n_mels=N_MELS
    )
    S_mel_db = librosa.power_to_db(S_mel, ref=np.max)

    fig = mpl_figure.Figure(figsize=(FIG_WIDTH_INCHES, FIG_HEIGHT_INCHES), dpi=FIG_DPI)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    librosa.display.specshow(
        S_mel_db, sr=sr, hop_length=hop_length, x_axis=None, y_axis=None, ax=ax, cmap="magma"
    )
    mel_path = out / "mel_spectrogram.png"
    fig.savefig(str(mel_path), dpi=FIG_DPI, bbox_inches="tight", pad_inches=0)
    fig.clear()
    results["spectrogram_mel"] = str(mel_path)

    return results


def compute_spectral_time_series(
    audio_path: str,
    *,
    sr: int = DEFAULT_SR,
    n_fft: int = DEFAULT_N_FFT,
    hop_length: int = DEFAULT_HOP_LENGTH,
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict[str, Any]:
    """Compute per-frame spectral features, downsampled to *max_points*.

    Returns a JSON-serializable dict:
        {
            "timePoints": [...],
            "spectralCentroid": [...],
            "spectralRolloff": [...],
            "spectralBandwidth": [...],
            "spectralFlatness": [...],
            "sampleRate": 44100,
            "hopLength": 1024,
            "originalFrameCount": N,
            "downsampledTo": M,
        }
    """
    y = _load_audio(audio_path, sr=sr)

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length)[0]
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length)[0]
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length)[0]
    flatness = librosa.feature.spectral_flatness(y=y, n_fft=n_fft, hop_length=hop_length)[0]

    original_frame_count = centroid.shape[0]

    centroid_ds = _downsample_time_series(centroid, max_points)
    rolloff_ds = _downsample_time_series(rolloff, max_points)
    bandwidth_ds = _downsample_time_series(bandwidth, max_points)
    flatness_ds = _downsample_time_series(flatness, max_points)

    actual_points = centroid_ds.shape[0]
    duration = librosa.get_duration(y=y, sr=sr)
    time_points = np.linspace(0, duration, actual_points)

    return {
        "timePoints": [round(float(t), 4) for t in time_points],
        "spectralCentroid": [round(float(v), 2) for v in centroid_ds],
        "spectralRolloff": [round(float(v), 2) for v in rolloff_ds],
        "spectralBandwidth": [round(float(v), 2) for v in bandwidth_ds],
        "spectralFlatness": [round(float(v), 6) for v in flatness_ds],
        "sampleRate": sr,
        "hopLength": hop_length,
        "originalFrameCount": original_frame_count,
        "downsampledTo": actual_points,
    }


def generate_cqt_spectrogram(
    audio_path: str,
    output_dir: str,
    *,
    sr: int = DEFAULT_SR,
    hop_length: int = DEFAULT_HOP_LENGTH,
) -> dict[str, str]:
    """Generate a CQT (Constant-Q Transform) spectrogram PNG.

    84 bins across 7 octaves, log-frequency aligned to musical pitch.

    Returns ``{"spectrogram_cqt": "/path/to/cqt_spectrogram.png"}``.
    """
    import matplotlib.figure as mpl_figure

    y = _load_audio(audio_path, sr=sr)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    C = librosa.cqt(y, sr=sr, hop_length=hop_length,
                    n_bins=CQT_N_BINS, bins_per_octave=CQT_BINS_PER_OCTAVE)
    C_db = librosa.amplitude_to_db(np.abs(C), ref=np.max)

    fig = mpl_figure.Figure(figsize=(FIG_WIDTH_INCHES, FIG_HEIGHT_INCHES), dpi=FIG_DPI)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    librosa.display.specshow(
        C_db, sr=sr, hop_length=hop_length, x_axis=None, y_axis=None, ax=ax, cmap="magma"
    )
    cqt_path = out / "cqt_spectrogram.png"
    fig.savefig(str(cqt_path), dpi=FIG_DPI, bbox_inches="tight", pad_inches=0)
    fig.clear()

    return {"spectrogram_cqt": str(cqt_path)}


def generate_hpss_spectrograms(
    audio_path: str,
    output_dir: str,
    *,
    sr: int = DEFAULT_SR,
    n_fft: int = DEFAULT_N_FFT,
    hop_length: int = DEFAULT_HOP_LENGTH,
) -> dict[str, str]:
    """Generate harmonic and percussive spectrogram PNGs via HPSS.

    Returns ``{"spectrogram_harmonic": "...", "spectrogram_percussive": "..."}``.
    """
    import matplotlib.figure as mpl_figure

    y = _load_audio(audio_path, sr=sr)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    S = librosa.stft(y, n_fft=n_fft, hop_length=hop_length)
    S_harmonic, S_percussive = librosa.decompose.hpss(S, margin=HPSS_MARGIN)

    results: dict[str, str] = {}
    for label, S_part in [("harmonic", S_harmonic), ("percussive", S_percussive)]:
        S_db = librosa.amplitude_to_db(np.abs(S_part), ref=np.max)
        fig = mpl_figure.Figure(figsize=(FIG_WIDTH_INCHES, FIG_HEIGHT_INCHES), dpi=FIG_DPI)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_axis_off()
        librosa.display.specshow(
            S_db, sr=sr, hop_length=hop_length, x_axis=None, y_axis=None, ax=ax, cmap="magma"
        )
        path = out / f"{label}_spectrogram.png"
        fig.savefig(str(path), dpi=FIG_DPI, bbox_inches="tight", pad_inches=0)
        fig.clear()
        results[f"spectrogram_{label}"] = str(path)

    return results


def compute_onset_strength(
    audio_path: str,
    *,
    sr: int = DEFAULT_SR,
    hop_length: int = DEFAULT_HOP_LENGTH,
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict[str, Any]:
    """Compute onset-strength envelope, downsampled to *max_points*.

    Returns a JSON-serializable dict with ``timePoints`` and ``onsetStrength``.
    """
    y = _load_audio(audio_path, sr=sr)

    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    original_frame_count = onset.shape[0]
    onset_ds = _downsample_time_series(onset, max_points)
    actual_points = onset_ds.shape[0]
    duration = librosa.get_duration(y=y, sr=sr)
    time_points = np.linspace(0, duration, actual_points)

    return {
        "timePoints": [round(float(t), 4) for t in time_points],
        "onsetStrength": [round(float(v), 4) for v in onset_ds],
        "sampleRate": sr,
        "hopLength": hop_length,
        "originalFrameCount": original_frame_count,
        "downsampledTo": actual_points,
    }


def compute_chroma_data(
    audio_path: str,
    *,
    sr: int = DEFAULT_SR,
    hop_length: int = DEFAULT_HOP_LENGTH,
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict[str, Any]:
    """Compute interactive chroma data (12 pitch classes over time).

    Returns a JSON-serializable dict with ``timePoints``, ``pitchClasses``,
    and a 12-element ``chroma`` array (one sub-array per pitch class).
    """
    y = _load_audio(audio_path, sr=sr)

    C = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length, n_chroma=N_CHROMA)
    original_frame_count = C.shape[1]

    chroma_ds = [_downsample_time_series(C[i], max_points) for i in range(N_CHROMA)]
    actual_points = chroma_ds[0].shape[0]
    duration = librosa.get_duration(y=y, sr=sr)
    time_points = np.linspace(0, duration, actual_points)

    return {
        "timePoints": [round(float(t), 4) for t in time_points],
        "pitchClasses": list(PITCH_CLASSES),
        "chroma": [[round(float(v), 4) for v in row] for row in chroma_ds],
        "sampleRate": sr,
        "hopLength": hop_length,
        "originalFrameCount": original_frame_count,
        "downsampledTo": actual_points,
    }


def generate_chroma_enhancement(
    audio_path: str,
    output_dir: str,
    *,
    sr: int = DEFAULT_SR,
    hop_length: int = DEFAULT_HOP_LENGTH,
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict[str, str]:
    """Generate chroma spectrogram PNG and interactive chroma JSON.

    Computes ``chroma_cqt`` once and produces both a static spectrogram
    image and a downsampled JSON payload for interactive rendering.

    Returns:
        {
            "spectrogram_chroma": "/path/to/chroma_over_time.png",
            "chroma_interactive": "/path/to/chroma_interactive.json",
        }
    """
    import matplotlib.figure as mpl_figure

    y = _load_audio(audio_path, sr=sr)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    C = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length, n_chroma=N_CHROMA)

    # --- Chroma spectrogram PNG ---
    fig = mpl_figure.Figure(figsize=(FIG_WIDTH_INCHES, 3), dpi=FIG_DPI)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    librosa.display.specshow(C, sr=sr, hop_length=hop_length, x_axis=None, y_axis=None, ax=ax, cmap="magma")
    chroma_path = out / "chroma_over_time.png"
    fig.savefig(str(chroma_path), dpi=FIG_DPI, bbox_inches="tight", pad_inches=0)
    fig.clear()
    results["spectrogram_chroma"] = str(chroma_path)

    # --- Interactive chroma JSON ---
    original_frame_count = C.shape[1]
    chroma_ds = [_downsample_time_series(C[i], max_points) for i in range(N_CHROMA)]
    actual_points = chroma_ds[0].shape[0]
    duration = librosa.get_duration(y=y, sr=sr)
    time_points = np.linspace(0, duration, actual_points)

    chroma_data = {
        "timePoints": [round(float(t), 4) for t in time_points],
        "pitchClasses": list(PITCH_CLASSES),
        "chroma": [[round(float(v), 4) for v in row] for row in chroma_ds],
        "sampleRate": sr,
        "hopLength": hop_length,
        "originalFrameCount": original_frame_count,
        "downsampledTo": actual_points,
    }
    json_path = out / "chroma_interactive.json"
    json_path.write_text(json.dumps(chroma_data), encoding="utf-8")
    results["chroma_interactive"] = str(json_path)

    return results


def generate_onset_enhancement(
    audio_path: str,
    output_dir: str,
    *,
    sr: int = DEFAULT_SR,
    hop_length: int = DEFAULT_HOP_LENGTH,
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict[str, str]:
    """Generate onset strength plot PNG and JSON data.

    Computes onset strength once and produces both a static time-series
    plot and a downsampled JSON payload for interactive rendering.

    Returns:
        {
            "spectrogram_onset": "/path/to/onset_strength_plot.png",
            "onset_strength": "/path/to/onset_strength.json",
        }
    """
    import matplotlib.figure as mpl_figure

    y = _load_audio(audio_path, sr=sr)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    duration = librosa.get_duration(y=y, sr=sr)
    full_times = np.linspace(0, duration, onset.shape[0])

    # --- Onset strength plot PNG ---
    fig = mpl_figure.Figure(figsize=(FIG_WIDTH_INCHES, FIG_HEIGHT_INCHES), dpi=FIG_DPI)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#1a1a2e")
    ax.fill_between(full_times, onset, color="#f87171", alpha=0.6)
    ax.plot(full_times, onset, color="#f87171", linewidth=0.5)
    ax.set_xlim(0, duration)
    ax.set_ylim(0, None)
    ax.set_axis_off()
    onset_path = out / "onset_strength_plot.png"
    fig.savefig(str(onset_path), dpi=FIG_DPI, bbox_inches="tight", pad_inches=0)
    fig.clear()
    results["spectrogram_onset"] = str(onset_path)

    # --- Onset strength JSON ---
    original_frame_count = onset.shape[0]
    onset_ds = _downsample_time_series(onset, max_points)
    actual_points = onset_ds.shape[0]
    ds_times = np.linspace(0, duration, actual_points)

    onset_data = {
        "timePoints": [round(float(t), 4) for t in ds_times],
        "onsetStrength": [round(float(v), 4) for v in onset_ds],
        "sampleRate": sr,
        "hopLength": hop_length,
        "originalFrameCount": original_frame_count,
        "downsampledTo": actual_points,
    }
    json_path = out / "onset_strength.json"
    json_path.write_text(json.dumps(onset_data), encoding="utf-8")
    results["onset_strength"] = str(json_path)

    return results


def generate_all_artifacts(
    audio_path: str,
    output_dir: str | None = None,
    *,
    sr: int = DEFAULT_SR,
    n_fft: int = DEFAULT_N_FFT,
    hop_length: int = DEFAULT_HOP_LENGTH,
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict[str, str]:
    """Generate all spectral visualization artifacts for a single audio file.

    Returns a dict mapping artifact kind to file path:
        {
            "spectrogram_mel": "/path/mel.png",
            "spectral_time_series": "/path/spectral_time_series.json",
        }
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="spectral_viz_")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = generate_spectrograms(
        audio_path, output_dir, sr=sr, n_fft=n_fft, hop_length=hop_length
    )

    ts_data = compute_spectral_time_series(
        audio_path, sr=sr, n_fft=n_fft, hop_length=hop_length, max_points=max_points
    )
    ts_path = out / "spectral_time_series.json"
    ts_path.write_text(json.dumps(ts_data), encoding="utf-8")
    results["spectral_time_series"] = str(ts_path)

    return results
