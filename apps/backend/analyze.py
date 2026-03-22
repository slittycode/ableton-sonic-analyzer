#!/usr/bin/env python3
"""
analyze.py — DSP accuracy testing tool.

Takes an audio file, runs it through Essentia's algorithms,
and prints a clean JSON result to stdout.

Usage:
    ./venv/bin/python analyze.py "path/to/track.mp3" [--separate] [--fast] [--transcribe] [--yes]
"""

import gc
import json
import heapq
import math
import os
import shutil
import sys
import tempfile
import warnings
import wave
from collections import Counter

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

# Import fast analysis mode
try:
    from analyze_fast import analyze_fast
except ImportError:
    analyze_fast = None


def load_mono(path: str, sample_rate: int = 44100) -> np.ndarray:
    """Load audio as mono via MonoLoader."""
    loader = es.MonoLoader(filename=path, sampleRate=sample_rate)
    return loader()


def load_stereo(path: str):
    """Load audio with AudioLoader to preserve stereo channels."""
    loader = es.AudioLoader(filename=path)
    audio, sr, num_channels, md5, bit_rate, codec = loader()
    return audio, sr, num_channels


def _write_wav_pcm16(path: str, audio: np.ndarray, sample_rate: int) -> None:
    """Write a float waveform array to PCM16 WAV."""
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 1:
        data = data[np.newaxis, :]
    data = np.clip(data, -1.0, 1.0)
    interleaved = (data.T * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(interleaved.shape[1] if interleaved.ndim == 2 else 1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(interleaved.tobytes())


def _demucs_chunked_inference(model, mix, device, segment_seconds=7.8, overlap=0.25):
    """Run Demucs inference in overlapping chunks to bound memory usage.

    Instead of feeding the entire song through the model at once (which
    requires holding all intermediate activations — easily 10-15 GB for a
    5-minute track), this processes ~8-second segments with a cross-fade
    overlap and blends them together.

    Args:
        model: HDemucs model instance (already on device, eval mode).
        mix: Tensor of shape [C, T] (stereo waveform at model sample rate).
        device: torch device string.
        segment_seconds: Length of each chunk in seconds (default 7.8s,
            matching the original Demucs default).
        overlap: Fraction of segment used for cross-fade blending (0.25 = 25%).

    Returns:
        Tensor of shape [num_sources, C, T].
    """
    import torch

    sample_rate = 44100  # HDEMUCS_HIGH_MUSDB_PLUS target rate
    segment_length = int(segment_seconds * sample_rate)
    total_length = mix.shape[-1]

    # Short audio — process in one shot (no chunking overhead needed)
    if total_length <= segment_length:
        with torch.no_grad():
            sources = model(mix.unsqueeze(0).to(device))
        return sources.squeeze(0).cpu()

    overlap_frames = int(segment_length * overlap)
    stride = segment_length - overlap_frames
    num_sources = len(model.sources)
    channels = mix.shape[0]

    # Pre-allocate output and weight buffers
    out = torch.zeros(num_sources, channels, total_length)
    weight = torch.zeros(total_length)

    # Triangular cross-fade window for smooth blending
    ramp = torch.linspace(0, 1, overlap_frames + 2)[1:-1]
    window = torch.ones(segment_length)
    window[:overlap_frames] = ramp
    window[-overlap_frames:] = ramp.flip(0)

    offset = 0
    chunk_idx = 0
    while offset < total_length:
        end = min(offset + segment_length, total_length)
        chunk = mix[:, offset:end]

        # Pad the last chunk if shorter than segment_length
        if chunk.shape[-1] < segment_length:
            pad_amount = segment_length - chunk.shape[-1]
            chunk = torch.nn.functional.pad(chunk, (0, pad_amount))

        with torch.no_grad():
            chunk_sources = model(chunk.unsqueeze(0).to(device))  # [1, S, C, seg]
        chunk_sources = chunk_sources.squeeze(0).cpu()  # [S, C, seg]

        actual_len = end - offset
        w = window[:actual_len]
        out[:, :, offset:end] += chunk_sources[:, :, :actual_len] * w
        weight[offset:end] += w

        del chunk, chunk_sources
        chunk_idx += 1
        if chunk_idx % 4 == 0:
            gc.collect()

        offset += stride

    # Normalize by accumulated weights
    weight = weight.clamp(min=1e-8)
    out /= weight

    return out


def separate_stems(audio_path: str, output_dir: str | None = None):
    """Run torchaudio Hybrid Demucs separation and return written source stem paths.

    Uses torchaudio.pipelines.HDEMUCS_HIGH_MUSDB_PLUS (in-process, no archived
    demucs package dependency).  Falls back gracefully if torchaudio is missing.

    Audio is processed in overlapping ~8-second chunks to keep memory usage
    bounded (~1-2 GB) regardless of track length.
    """
    try:
        import torch
        import soundfile as sf
        import torchaudio.functional as F
        from torchaudio.pipelines import HDEMUCS_HIGH_MUSDB_PLUS
    except Exception:
        return None

    temp_dir_created = False
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="sonic_analyzer_demucs_")
        temp_dir_created = True
    else:
        os.makedirs(output_dir, exist_ok=True)

    try:
        bundle = HDEMUCS_HIGH_MUSDB_PLUS
        model = bundle.get_model()
        model.eval()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)

        target_sr = bundle.sample_rate

        # Load audio with soundfile (avoids torchcodec dependency issues)
        data, file_sr = sf.read(audio_path, always_2d=True, dtype="float32")
        mix = torch.from_numpy(data.T)  # [C, T]
        if file_sr != target_sr:
            mix = F.resample(mix, file_sr, target_sr)

        duration_s = mix.shape[-1] / target_sr
        print(f"[demucs] separating {duration_s:.0f}s on {device} (chunked)...", file=sys.stderr)
        sources = _demucs_chunked_inference(model, mix, device)

        source_names = list(model.sources)
        if len(source_names) == 0:
            raise RuntimeError("Demucs output does not contain any sources")

        stem_paths = {}
        model_sr = int(target_sr)
        for idx, source_name in enumerate(source_names):
            stem_audio = sources[idx].detach().cpu().numpy()
            stem_path = os.path.join(output_dir, f"{source_name}.wav")
            _write_wav_pcm16(stem_path, stem_audio, model_sr)
            stem_paths[source_name] = stem_path

        del sources, mix, model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return stem_paths if len(stem_paths) > 0 else None
    except Exception:
        if temp_dir_created:
            shutil.rmtree(output_dir, ignore_errors=True)
        return None


def analyze_crepe_pitch(stem_paths: dict | None) -> dict:
    """Run torchcrepe pitch extraction on vocal and other stems.

    Returns ``{"pitchDetail": {...}}`` with per-stem pitch statistics and the
    raw pitch/periodicity arrays.  Only runs when separated stems are available;
    returns ``{"pitchDetail": None}`` otherwise.
    """
    if stem_paths is None:
        return {"pitchDetail": None}

    try:
        import torch
        import torchcrepe
        import soundfile as sf
    except Exception:
        return {"pitchDetail": None}

    device = "cuda" if torch.cuda.is_available() else "cpu"

    stem_configs = {
        "vocals": {"fmin": 80.0, "fmax": 1000.0},
        "other":  {"fmin": 50.0, "fmax": 1000.0},
    }

    stems_result = {}
    for stem_name, cfg in stem_configs.items():
        source_path = stem_paths.get(stem_name)
        if not isinstance(source_path, str) or not os.path.isfile(source_path):
            continue

        try:
            data, sr = sf.read(source_path, always_2d=True, dtype="float32")
            # Downmix to mono [1, T]
            mono = torch.from_numpy(data.T.mean(axis=0, keepdims=True))

            print(f"[crepe:{stem_name}] extracting pitch...", file=sys.stderr)
            pitch, periodicity = torchcrepe.predict(
                mono,
                sr,
                hop_length=512,
                fmin=cfg["fmin"],
                fmax=cfg["fmax"],
                model="tiny",
                decoder=torchcrepe.decode.viterbi,
                return_periodicity=True,
                batch_size=256,
                device=device,
                pad=True,
            )
            pitch_np = pitch.squeeze().numpy()
            period_np = periodicity.squeeze().numpy()

            # Compute stats on voiced frames only
            voiced_mask = period_np > 0.5
            voiced_pct = round(float(voiced_mask.mean() * 100), 1)
            mean_periodicity = round(float(period_np.mean()), 3)

            if voiced_mask.sum() > 0:
                voiced_pitch = pitch_np[voiced_mask]
                voiced_pitch = voiced_pitch[np.isfinite(voiced_pitch)]
                median_hz = round(float(np.median(voiced_pitch)), 1)
                p5_hz = round(float(np.percentile(voiced_pitch, 5)), 1)
                p95_hz = round(float(np.percentile(voiced_pitch, 95)), 1)
            else:
                median_hz = None
                p5_hz = None
                p95_hz = None

            stems_result[stem_name] = {
                "medianPitchHz": median_hz,
                "pitchRangeLowHz": p5_hz,
                "pitchRangeHighHz": p95_hz,
                "meanPeriodicity": mean_periodicity,
                "voicedFramePercent": voiced_pct,
                "hopLength": 512,
                "sampleRate": sr,
                "model": "tiny",
            }

            del mono, pitch, periodicity
        except Exception as exc:
            print(f"[crepe:{stem_name}] failed: {exc}", file=sys.stderr)
            continue

    gc.collect()

    if len(stems_result) == 0:
        return {"pitchDetail": None}

    return {"pitchDetail": {"method": "torchcrepe", "stems": stems_result}}


def cleanup_stems(stems: dict | None) -> None:
    """Cleanup temporary stem files and directories created by separate_stems."""
    if stems is None:
        return
    try:
        stem_paths = []
        for path in stems.values():
            if isinstance(path, str) and path:
                stem_paths.append(path)

        for path in stem_paths:
            if os.path.isfile(path):
                os.remove(path)

        parent_dirs = {os.path.dirname(path) for path in stem_paths if path}
        if len(parent_dirs) == 1:
            parent = next(iter(parent_dirs))
            if os.path.basename(parent).startswith("sonic_analyzer_demucs_"):
                shutil.rmtree(parent, ignore_errors=True)
    except Exception:
        pass


def _format_duration_label(seconds: float) -> str:
    total_seconds = max(0, int(round(float(seconds))))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def _estimate_stage_seconds(
    duration_seconds: float,
    min_ratio: float,
    max_ratio: float,
    min_overhead: float,
    max_overhead: float,
) -> dict:
    safe_duration = max(0.0, float(duration_seconds))
    stage_min = max(min_overhead, safe_duration * min_ratio)
    stage_max = max(max_overhead, safe_duration * max_ratio)
    if stage_max < stage_min:
        stage_max = stage_min
    return {
        "min": int(round(stage_min)),
        "max": int(round(stage_max)),
    }


def get_audio_duration_seconds(audio_path: str) -> float | None:
    try:
        reader = es.MetadataReader(filename=audio_path)
        metadata = dict(zip(reader.outputNames(), reader()))
        duration_seconds = metadata.get("duration")
        if duration_seconds is None:
            return None
        duration_value = float(duration_seconds)
        return (
            duration_value
            if np.isfinite(duration_value) and duration_value > 0
            else None
        )
    except Exception:
        return None


def build_analysis_estimate(
    duration_seconds: float,
    run_separation: bool,
    run_transcribe: bool,
    run_fast: bool = False,
) -> dict:
    stages = []

    dsp_seconds = _estimate_stage_seconds(duration_seconds, 0.06, 0.14, 20.0, 45.0)
    stages.append(
        {
            "key": "dsp",
            "label": "DSP analysis",
            "seconds": dsp_seconds,
        }
    )

    if run_separation:
        separation_seconds = _estimate_stage_seconds(
            duration_seconds, 0.16, 0.32, 45.0, 90.0
        )
        stages.append(
            {
                "key": "separation",
                "label": "Demucs separation",
                "seconds": separation_seconds,
            }
        )

    if run_transcribe:
        transcription_key = (
            "transcription_stems" if run_separation else "transcription_full_mix"
        )
        transcription_label = (
            "Torchcrepe on bass + other stems"
            if run_separation
            else "Torchcrepe on full mix"
        )
        transcription_seconds = (
            _estimate_stage_seconds(duration_seconds, 0.22, 0.42, 60.0, 150.0)
            if run_separation
            else _estimate_stage_seconds(duration_seconds, 0.10, 0.22, 25.0, 75.0)
        )
        stages.append(
            {
                "key": transcription_key,
                "label": transcription_label,
                "seconds": transcription_seconds,
            }
        )

    total_min = sum(stage["seconds"]["min"] for stage in stages)
    total_max = sum(stage["seconds"]["max"] for stage in stages)

    return {
        "durationSeconds": round(float(duration_seconds), 1),
        "stages": stages,
        "totalSeconds": {
            "min": total_min,
            "max": total_max,
        },
    }


def print_analysis_estimate(audio_path: str, estimate: dict) -> None:
    print(
        f"Estimated analysis time for {os.path.basename(audio_path)}: "
        f"{_format_duration_label(estimate['totalSeconds']['min'])}-"
        f"{_format_duration_label(estimate['totalSeconds']['max'])}",
        file=sys.stderr,
    )
    for stage in estimate.get("stages", []):
        seconds = stage.get("seconds", {})
        print(
            f"- {stage.get('label')}: "
            f"{_format_duration_label(seconds.get('min', 0))}-"
            f"{_format_duration_label(seconds.get('max', 0))}",
            file=sys.stderr,
        )


def should_prompt_for_confirmation(is_tty: bool, auto_yes: bool) -> bool:
    return bool(is_tty) and not auto_yes


def prompt_to_continue() -> bool:
    try:
        response = input("Continue? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return response in {"y", "yes"}


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


def _extract_beat_loudness_data(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
) -> dict | None:
    """Shared beat/band loudness extraction for groove and sidechain analyses."""
    try:
        if rhythm_data is None:
            return None

        ticks = np.asarray(rhythm_data.get("ticks", []), dtype=np.float64)
        if ticks.size < 2:
            return None

        frequency_bands = [20, 200, 200, 4000, 4000, 20000]

        beat_loudness_cls = getattr(es, "BeatLoudness", None)
        use_ratio_output = False
        if beat_loudness_cls is None:
            beat_loudness_cls = getattr(es, "BeatsLoudness", None)
            use_ratio_output = True
        if beat_loudness_cls is None:
            return None

        beat_loudness_algo = beat_loudness_cls(
            beats=ticks.tolist(),
            sampleRate=sample_rate,
            frequencyBands=frequency_bands,
        )
        beat_loudness, band_loudness = beat_loudness_algo(mono)

        beat_loudness = np.asarray(beat_loudness, dtype=np.float64)
        band_loudness = np.asarray(band_loudness, dtype=np.float64)
        if band_loudness.ndim != 2 or band_loudness.shape[0] == 0:
            return None

        if use_ratio_output:
            if beat_loudness.size != band_loudness.shape[0]:
                return None
            band_loudness = band_loudness * beat_loudness[:, np.newaxis]

        low_band = band_loudness[:, 0]
        high_band = band_loudness[:, -1]
        count = min(
            ticks.size,
            beat_loudness.size,
            band_loudness.shape[0],
            low_band.size,
            high_band.size,
        )
        if count < 2:
            return None

        beats = ticks[:count]
        beat_loudness = beat_loudness[:count]
        band_loudness = band_loudness[:count, :]
        low_band = low_band[:count]
        high_band = high_band[:count]

        return {
            "beats": beats,
            "beatLoudness": beat_loudness,
            "bandLoudness": band_loudness,
            "lowBand": low_band,
            "highBand": high_band,
        }
    except Exception:
        return None


# ── Shared rhythm extraction (run once, reuse everywhere) ──────────────────


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

        # Ratio windows: 2x (1.92-2.08), 1.5x (1.44-1.56),
        # 0.5x (0.48-0.52), 2/3 (0.641-0.694)
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


# ── Individual analysis functions ──────────────────────────────────────────


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

        # Secondary BPM estimation. Keep safe if unavailable in this Essentia build.
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

        # Tuning frequency via frame-by-frame spectral peaks
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
        # Crest factor: 20 * log10(peak / rms)
        peak = float(np.max(np.abs(mono)))
        rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
        if rms > 0 and peak > 0:
            crest = 20.0 * np.log10(peak / rms)
        else:
            crest = 0.0

        # Dynamic spread: ratio of max to min energy across 3 broad bands
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
        loudness_variation = 0.0
        spectral_flatness = 0.0
        log_attack_time = 0.0
        attack_time_stddev = 0.0

        # DynamicComplexity on full signal
        try:
            dynamic_algo = es.DynamicComplexity(sampleRate=sample_rate)
            dynamic_complexity, loudness_variation = dynamic_algo(mono)
            dynamic_complexity = float(dynamic_complexity)
            loudness_variation = float(loudness_variation)
        except Exception:
            dynamic_complexity = 0.0
            loudness_variation = 0.0

        # Frame-wise flatness
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

        # Reliable fallback-first attack-time path.
        # If envelope extraction fails, keep a simple absolute-amplitude fallback.
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
                "loudnessVariation": round(loudness_variation, 4),
                "spectralFlatness": round(spectral_flatness, 4),
                "logAttackTime": round(log_attack_time, 4),
                "attackTimeStdDev": round(attack_time_stddev, 4),
            }
        }
    except Exception as e:
        print(f"[warn] Dynamic character analysis failed: {e}", file=sys.stderr)
        return {"dynamicCharacter": None}


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
    """Spectral balance across 7 frequency bands using EnergyBand + spectrum.

    When precomputed_band_energies is provided (from analyze_spectral_detail's
    piggybacked loop), the per-frame FrameGenerator pass is skipped entirely.
    """
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
    """Frame-by-frame SpectralCentroid, SpectralRolloff, MFCC, and HPCP (Chroma).

    When _balance_bands is provided (dict mapping band name to (lo, hi) Hz),
    EnergyBand values are computed in the same loop and returned under the key
    ``_spectralBalanceBands``. This avoids a redundant second FrameGenerator pass
    in analyze_spectral_balance().
    """
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
            # Keep input size aligned with Spectrum output to avoid silent wrong values.
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

        # Optional: EnergyBand algos for spectral balance (piggyback on this loop)
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

        centroid_vals, rolloff_vals = [], []
        mfcc_matrix = []
        hpcp_matrix = []
        bark_matrix = []
        erb_matrix = []
        contrast_matrix = []
        valley_matrix = []

        for frame in es.FrameGenerator(mono, frameSize=frame_size, hopSize=hop_size):
            windowed = window(frame)
            spec = spectrum(windowed)

            # SpectralCentroid (time-domain version works on frames)
            centroid_vals.append(float(centroid_algo(frame)))

            # SpectralRolloff
            rolloff_vals.append(float(rolloff_algo(spec)))

            # MFCC (returns bands and coefficients)
            _bands, mfcc_coeffs = mfcc_algo(spec)
            mfcc_matrix.append(mfcc_coeffs)

            # HPCP (chroma) from spectral peaks
            try:
                freqs, mags = spectral_peaks(spec)
                if len(freqs) > 0:
                    hpcp = hpcp_algo(freqs, mags)
                    hpcp_matrix.append(hpcp)
            except Exception:
                pass

            # Bark bands
            try:
                bark_vals = np.asarray(bark_algo(spec), dtype=np.float64)
                if bark_vals.ndim == 1 and bark_vals.size > 0:
                    bark_matrix.append(bark_vals)
            except Exception:
                pass

            # ERB bands
            if erb_algo is not None:
                try:
                    erb_vals = np.asarray(erb_algo(spec), dtype=np.float64)
                    if erb_vals.ndim == 1 and erb_vals.size > 0:
                        erb_matrix.append(erb_vals)
                except Exception:
                    pass

            # Spectral contrast
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

            # EnergyBand for spectral balance (piggybacking)
            if balance_algos is not None:
                for name, algo in balance_algos.items():
                    balance_energies[name].append(float(algo(spec)))

        # Compute means
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

        result = {
            "spectralDetail": {
                "spectralCentroid": mean_centroid,
                "spectralRolloff": mean_rolloff,
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

        # Preferred path: BandPass centered at 50Hz with 60Hz bandwidth (~20-80Hz).
        # Fallback: LowPass at 80Hz when BandPass lower-bound control isn't available.
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


def analyze_rhythm_detail(rhythm_data: dict | None) -> dict:
    """Onset rate, beat positions, and groove amount from shared rhythm data."""
    try:
        if rhythm_data is None:
            return {"rhythmDetail": None}

        ticks = np.asarray(rhythm_data["ticks"], dtype=np.float64)

        # OnsetRate
        try:
            onset_rate_algo = es.OnsetRate()
            # OnsetRate not used here — we derive onset rate from ticks
            # Actual OnsetRate needs the audio, so compute from ticks
            if len(ticks) >= 2:
                duration = float(ticks[-1] - ticks[0])
                onset_rate = float(len(ticks)) / duration if duration > 0 else 0.0
            else:
                onset_rate = 0.0
        except Exception:
            onset_rate = 0.0

        beat_grid = [round(float(t), 3) for t in ticks]
        beat_positions = [((index % 4) + 1) for index in range(len(beat_grid))]
        downbeats = beat_grid[::4]

        # Groove amount: stdev of beat interval diffs, normalized by mean interval
        if len(ticks) >= 3:
            intervals = np.diff(ticks.astype(np.float64))
            mean_interval = float(np.mean(intervals))
            if mean_interval > 0:
                groove = float(np.std(intervals) / mean_interval)
            else:
                groove = 0.0
        else:
            groove = 0.0

        # Tempo stability: 1.0 = metronomic, 0.0 = arrhythmic
        tempo_stability = round(float(np.clip(1.0 - groove, 0.0, 1.0)), 4)

        # Phrase grid: group downbeats into 4-bar, 8-bar, 16-bar phrases
        phrase_grid = None
        if len(downbeats) >= 2:
            phrases_4bar = [downbeats[i] for i in range(0, len(downbeats), 4)]
            phrases_8bar = [downbeats[i] for i in range(0, len(downbeats), 8)]
            phrases_16bar = [downbeats[i] for i in range(0, len(downbeats), 16)]
            phrase_grid = {
                "phrases4Bar": phrases_4bar,
                "phrases8Bar": phrases_8bar,
                "phrases16Bar": phrases_16bar,
                "totalBars": len(downbeats),
                "totalPhrases8Bar": len(phrases_8bar),
            }

        return {
            "rhythmDetail": {
                "onsetRate": round(onset_rate, 2),
                "beatGrid": beat_grid,
                "downbeats": downbeats,
                "beatPositions": beat_positions,
                "grooveAmount": round(groove, 4),
                "tempoStability": tempo_stability,
                "phraseGrid": phrase_grid,
            }
        }
    except Exception as e:
        print(f"[warn] Rhythm detail analysis failed: {e}", file=sys.stderr)
        return {"rhythmDetail": None}


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

            # Sharpness: spectral-energy weighted towards high frequencies
            # Essentia doesn't have a dedicated Sharpness algo, so we compute
            # a Zwicker-like sharpness from the spectrum:
            # weighted centroid biased towards high frequencies
            freqs = np.linspace(0, sample_rate / 2.0, len(spec))
            total_energy = float(np.sum(spec))
            if total_energy > 0:
                # Weight by frequency (higher freqs contribute more to sharpness)
                weights = (freqs / (sample_rate / 2.0)) ** 2
                sharpness = float(np.sum(spec * weights) / total_energy)
            else:
                sharpness = 0.0
            sharpness_vals.append(sharpness)

            # Roughness approximated via Dissonance
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
            return {"timeSignature": None}
        # Essentia has no dedicated time signature algorithm.
        # Default to 4/4 (>90% of popular music).
        return {"timeSignature": "4/4"}
    except Exception as e:
        print(f"[warn] Time signature estimation failed: {e}", file=sys.stderr)
        return {"timeSignature": None}


def analyze_melody(
    audio_path: str,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    stems: dict | None = None,
) -> dict:
    """Melody extraction with contour segmentation and optional MIDI export."""
    try:
        source_path = audio_path
        source_separated = False
        if stems is not None:
            other_path = stems.get("other")
            if isinstance(other_path, str) and os.path.exists(other_path):
                source_path = other_path
                source_separated = True

        loader = es.EqloudLoader(filename=source_path, sampleRate=sample_rate)
        audio_eq = loader()

        pitch_extractor = es.PredominantPitchMelodia(frameSize=2048, hopSize=128)
        pitch_values, pitch_confidence = pitch_extractor(audio_eq)
        pitch_values = np.asarray(pitch_values, dtype=np.float64)
        pitch_confidence = np.asarray(pitch_confidence, dtype=np.float64)
        mean_conf = (
            float(np.mean(pitch_confidence)) if pitch_confidence.size > 0 else 0.0
        )
        vibrato_metrics = {
            "vibratoPresent": False,
            "vibratoExtent": 0.0,
            "vibratoRate": 0.0,
            "vibratoConfidence": 0.0,
        }

        # Reuse existing pitch contour (do not re-run Melodia) for vibrato extraction.
        try:
            pitch_frame_rate = float(sample_rate) / 128.0 if sample_rate > 0 else 0.0
            min_pitch_frames = (
                int(np.ceil((2.0 * pitch_frame_rate) / 4.0))
                if pitch_frame_rate > 0
                else 0
            )
            voiced_pitch = pitch_values[
                np.isfinite(pitch_values) & (pitch_values > 0.0)
            ]

            if min_pitch_frames > 0 and voiced_pitch.size >= min_pitch_frames:
                vibrato_algo = es.Vibrato(
                    sampleRate=pitch_frame_rate,
                    minFrequency=4.0,
                    maxFrequency=8.0,
                    minExtend=50.0,
                    maxExtend=250.0,
                )
                vibrato_frequency, vibrato_extend = vibrato_algo(
                    np.asarray(voiced_pitch, dtype=np.float32)
                )
                vibrato_frequency = np.asarray(vibrato_frequency, dtype=np.float64)
                vibrato_extend = np.asarray(vibrato_extend, dtype=np.float64)

                valid = (
                    np.isfinite(vibrato_frequency)
                    & np.isfinite(vibrato_extend)
                    & (vibrato_frequency > 0.0)
                    & (vibrato_extend > 0.0)
                )
                if vibrato_extend.size > 0:
                    confidence = float(np.sum(valid)) / float(vibrato_extend.size)
                else:
                    confidence = 0.0

                extent = float(np.mean(vibrato_extend[valid])) if np.any(valid) else 0.0
                rate = (
                    float(np.mean(vibrato_frequency[valid])) if np.any(valid) else 0.0
                )
                vibrato_metrics = {
                    "vibratoPresent": bool(extent > 50.0),
                    "vibratoExtent": round(extent, 4),
                    "vibratoRate": round(rate, 4),
                    "vibratoConfidence": round(float(np.clip(confidence, 0.0, 1.0)), 4),
                }
        except Exception:
            vibrato_metrics = {
                "vibratoPresent": False,
                "vibratoExtent": 0.0,
                "vibratoRate": 0.0,
                "vibratoConfidence": 0.0,
            }

        contour_segmenter = es.PitchContourSegmentation(
            hopSize=128, sampleRate=sample_rate
        )
        onsets, durations, notes = contour_segmenter(pitch_values, audio_eq)

        onsets = np.asarray(onsets, dtype=np.float64)
        durations = np.asarray(durations, dtype=np.float64)
        notes = np.asarray(notes, dtype=np.float64)

        count = min(onsets.size, durations.size, notes.size)
        if count == 0:
            return {
                "melodyDetail": {
                    "noteCount": 0,
                    "notes": [],
                    "dominantNotes": [],
                    "pitchRange": {"min": None, "max": None},
                    "pitchConfidence": round(mean_conf, 4),
                    "midiFile": None,
                    "sourceSeparated": source_separated,
                    "vibratoPresent": vibrato_metrics["vibratoPresent"],
                    "vibratoExtent": vibrato_metrics["vibratoExtent"],
                    "vibratoRate": vibrato_metrics["vibratoRate"],
                    "vibratoConfidence": vibrato_metrics["vibratoConfidence"],
                }
            }

        note_events = []
        midi_values = []
        for i in range(count):
            onset = float(onsets[i])
            duration = float(durations[i])
            midi_note = int(np.rint(notes[i]))
            if duration <= 0:
                continue
            midi_note = int(np.clip(midi_note, 0, 127))
            note_events.append((onset, duration, midi_note))
            midi_values.append(midi_note)

        if len(note_events) == 0:
            return {
                "melodyDetail": {
                    "noteCount": 0,
                    "notes": [],
                    "dominantNotes": [],
                    "pitchRange": {"min": None, "max": None},
                    "pitchConfidence": round(mean_conf, 4),
                    "midiFile": None,
                    "sourceSeparated": source_separated,
                    "vibratoPresent": vibrato_metrics["vibratoPresent"],
                    "vibratoExtent": vibrato_metrics["vibratoExtent"],
                    "vibratoRate": vibrato_metrics["vibratoRate"],
                    "vibratoConfidence": vibrato_metrics["vibratoConfidence"],
                }
            }

        note_objects = [
            {
                "midi": int(m),
                "onset": round(float(o), 3),
                "duration": round(float(d), 3),
            }
            for (o, d, m) in note_events
        ]
        if len(note_objects) > 64:
            indices = np.linspace(0, len(note_objects) - 1, 64, dtype=int)
            sampled_notes = [note_objects[i] for i in indices]
        else:
            sampled_notes = note_objects

        dominant_notes = [
            label for label, _count in Counter(midi_values).most_common(5)
        ]
        pitch_range = {"min": int(min(midi_values)), "max": int(max(midi_values))}

        midi_file_path = None
        try:
            import mido

            bpm = 120.0
            if rhythm_data is not None and rhythm_data.get("bpm") is not None:
                bpm = float(rhythm_data["bpm"])
            if not np.isfinite(bpm) or bpm <= 0:
                bpm = 120.0

            ppq = 96
            ticks_per_second = (ppq * bpm) / 60.0
            midi_out = mido.MidiFile(ticks_per_beat=ppq)
            track = mido.MidiTrack()
            midi_out.tracks.append(track)
            track.append(
                mido.MetaMessage("set_tempo", tempo=int(mido.bpm2tempo(bpm)), time=0)
            )

            events = []
            for onset, duration, midi_note in note_events:
                start_tick = max(0, int(round(onset * ticks_per_second)))
                end_tick = max(
                    start_tick + 1, int(round((onset + duration) * ticks_per_second))
                )
                events.append((start_tick, 1, midi_note))
                events.append((end_tick, 0, midi_note))
            events.sort(key=lambda e: (e[0], e[1]))

            prev_tick = 0
            for tick, is_note_on, midi_note in events:
                delta = max(0, tick - prev_tick)
                if is_note_on == 1:
                    track.append(
                        mido.Message("note_on", note=midi_note, velocity=90, time=delta)
                    )
                else:
                    track.append(
                        mido.Message("note_off", note=midi_note, velocity=0, time=delta)
                    )
                prev_tick = tick

            output_dir = os.path.dirname(audio_path)
            base_name = os.path.splitext(os.path.basename(audio_path))[0]
            midi_file_path = os.path.join(output_dir, f"{base_name}_melody.mid")
            midi_out.save(midi_file_path)
        except Exception as e:
            print(f"[warn] Melody MIDI export failed: {e}", file=sys.stderr)
            midi_file_path = None

        return {
            "melodyDetail": {
                "noteCount": len(note_events),
                "notes": sampled_notes,
                "dominantNotes": dominant_notes,
                "pitchRange": pitch_range,
                "pitchConfidence": round(mean_conf, 4),
                "midiFile": midi_file_path,
                "sourceSeparated": source_separated,
                "vibratoPresent": vibrato_metrics["vibratoPresent"],
                "vibratoExtent": vibrato_metrics["vibratoExtent"],
                "vibratoRate": vibrato_metrics["vibratoRate"],
                "vibratoConfidence": vibrato_metrics["vibratoConfidence"],
            }
        }
    except Exception as e:
        print(f"[warn] Melody analysis failed: {e}", file=sys.stderr)
        return {"melodyDetail": None}


def analyze_groove(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    beat_data: dict | None = None,
) -> dict:
    """Per-beat groove detail from beat-synchronous band loudness."""
    try:
        if beat_data is None:
            beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)
        if beat_data is None:
            return {"grooveDetail": None}

        beats = np.asarray(beat_data.get("beats", []), dtype=np.float64)
        low_band = np.asarray(beat_data.get("lowBand", []), dtype=np.float64)
        high_band = np.asarray(beat_data.get("highBand", []), dtype=np.float64)
        if beats.size < 2 or low_band.size < 2 or high_band.size < 2:
            return {"grooveDetail": None}

        # Swing: stdev(intervals between beats above mean), normalized by mean interval.
        def calc_swing(band_values: np.ndarray, beat_positions: np.ndarray) -> float:
            if band_values.size < 2 or beat_positions.size < 2:
                return 0.0

            mean_val = float(np.mean(band_values))
            selected_beats = beat_positions[band_values > mean_val]
            if selected_beats.size < 2:
                return 0.0

            intervals = np.diff(selected_beats)
            mean_interval = float(np.mean(intervals))
            if mean_interval <= 0:
                return 0.0
            return float(np.std(intervals) / mean_interval)

        def sample_accents(values: np.ndarray, max_points: int = 16) -> list[float]:
            if values.size == 0:
                return []
            if values.size > max_points:
                indices = np.linspace(0, values.size - 1, max_points, dtype=int)
                values = values[indices]
            return [round(float(v), 4) for v in values]

        raw_kick_swing = calc_swing(low_band, beats)
        raw_hihat_swing = calc_swing(high_band, beats)
        # Normalize to 0-1 scale using tanh compression
        kick_swing = round(math.tanh(raw_kick_swing * 0.5), 4)
        hihat_swing = round(math.tanh(raw_hihat_swing * 0.5), 4)
        kick_accent = sample_accents(low_band, 16)
        hihat_accent = sample_accents(high_band, 16)

        return {
            "grooveDetail": {
                "kickSwing": kick_swing,
                "hihatSwing": hihat_swing,
                "kickAccent": kick_accent,
                "hihatAccent": hihat_accent,
            }
        }
    except Exception as e:
        print(f"[warn] Groove analysis failed: {e}", file=sys.stderr)
        return {"grooveDetail": None}


def analyze_beats_loudness(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    beat_data: dict | None = None,
) -> dict:
    """Beat-synchronous loudness summary with band dominance and accent pattern."""
    try:
        if beat_data is None:
            beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)
        if beat_data is None:
            return {"beatsLoudness": None}

        beat_loudness = np.asarray(beat_data.get("beatLoudness", []), dtype=np.float64)
        band_loudness = np.asarray(beat_data.get("bandLoudness", []), dtype=np.float64)
        low_band = np.asarray(beat_data.get("lowBand", []), dtype=np.float64)
        high_band = np.asarray(beat_data.get("highBand", []), dtype=np.float64)

        if beat_loudness.size < 2 or band_loudness.ndim != 2 or band_loudness.shape[0] < 2:
            return {"beatsLoudness": None}

        mean_total = float(np.mean(beat_loudness))
        if mean_total <= 0:
            return {"beatsLoudness": None}

        # Band dominance ratios
        mean_low = float(np.mean(low_band)) if low_band.size > 0 else 0.0
        mean_high = float(np.mean(high_band)) if high_band.size > 0 else 0.0
        # Mid band is column 1 of bandLoudness (200-4000 Hz)
        mid_band = band_loudness[:, 1] if band_loudness.shape[1] > 1 else np.zeros(band_loudness.shape[0])
        mean_mid = float(np.mean(mid_band))

        kick_dominant_ratio = round(float(np.clip(mean_low / mean_total, 0.0, 1.0)), 4)
        mid_dominant_ratio = round(float(np.clip(mean_mid / mean_total, 0.0, 1.0)), 4)
        high_dominant_ratio = round(float(np.clip(mean_high / mean_total, 0.0, 1.0)), 4)

        # Accent pattern: average beat loudness by bar position (4 beats per bar)
        n_beats = beat_loudness.size
        accent_pattern = [0.0, 0.0, 0.0, 0.0]
        counts = [0, 0, 0, 0]
        for i in range(n_beats):
            pos = i % 4
            accent_pattern[pos] += float(beat_loudness[i])
            counts[pos] += 1
        for pos in range(4):
            if counts[pos] > 0:
                accent_pattern[pos] /= counts[pos]
        # Normalize so max = 1.0
        accent_max = max(accent_pattern)
        if accent_max > 0:
            accent_pattern = [round(v / accent_max, 4) for v in accent_pattern]
        else:
            accent_pattern = [0.0, 0.0, 0.0, 0.0]

        # Summary stats
        std_total = float(np.std(beat_loudness))
        beat_loudness_variation = round(std_total / mean_total, 4) if mean_total > 0 else 0.0

        result = {
            "beatsLoudness": {
                "kickDominantRatio": kick_dominant_ratio,
                "midDominantRatio": mid_dominant_ratio,
                "highDominantRatio": high_dominant_ratio,
                "accentPattern": accent_pattern,
                "meanBeatLoudness": round(mean_total, 4),
                "beatLoudnessVariation": beat_loudness_variation,
                "beatCount": int(n_beats),
            }
        }

        # Raw matrix behind debug env var only
        if os.environ.get("ASA_DEBUG_BEATS_LOUDNESS") == "1":
            result["beatsLoudness"]["rawBeatLoudness"] = [round(float(v), 4) for v in beat_loudness]
            result["beatsLoudness"]["rawLowBand"] = [round(float(v), 4) for v in low_band]
            result["beatsLoudness"]["rawHighBand"] = [round(float(v), 4) for v in high_band]

        return result
    except Exception as e:
        print(f"[warn] Beat loudness analysis failed: {e}", file=sys.stderr)
        return {"beatsLoudness": None}


def analyze_sidechain_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    rhythm_data: dict | None = None,
    beat_data: dict | None = None,
) -> dict:
    """Detect sidechain-style pumping from RMS dips aligned to kick activity."""
    try:
        if beat_data is None:
            beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)
        if beat_data is None:
            return {"sidechainDetail": None}

        beats = np.asarray(beat_data.get("beats", []), dtype=np.float64)
        low_band = np.asarray(beat_data.get("lowBand", []), dtype=np.float64)
        beat_loudness = np.asarray(beat_data.get("beatLoudness", []), dtype=np.float64)
        if beats.size < 2 or low_band.size < 2 or beat_loudness.size < 2:
            return {"sidechainDetail": None}

        mono_arr = np.asarray(mono, dtype=np.float32)
        total_samples = int(mono_arr.size)
        if total_samples < 2:
            return {"sidechainDetail": None}

        # Build a 16th-note grid from beat intervals.
        sixteenth_times = []
        for i in range(beats.size - 1):
            start = float(beats[i])
            end = float(beats[i + 1])
            if not np.isfinite(start) or not np.isfinite(end) or end <= start:
                continue
            step = (end - start) / 4.0
            sixteenth_times.extend([start + j * step for j in range(4)])

        if len(sixteenth_times) == 0:
            return {
                "sidechainDetail": {
                    "pumpingStrength": 0.0,
                    "pumpingRegularity": 0.0,
                    "pumpingRate": None,
                    "pumpingConfidence": 0.0,
                }
            }
        sixteenth_times.append(float(beats[-1]))
        sixteenth_times = np.asarray(sixteenth_times, dtype=np.float64)

        rms_algo = es.RMS()
        rms_values = []
        centers = []
        for i in range(sixteenth_times.size - 1):
            start_t = float(sixteenth_times[i])
            end_t = float(sixteenth_times[i + 1])
            if end_t <= start_t:
                continue
            start_idx = max(0, min(total_samples, int(round(start_t * sample_rate))))
            end_idx = max(
                start_idx, min(total_samples, int(round(end_t * sample_rate)))
            )
            if end_idx - start_idx < 2:
                continue
            segment = mono_arr[start_idx:end_idx]
            try:
                rms_val = float(rms_algo(segment))
            except Exception:
                rms_val = float(np.sqrt(np.mean(segment.astype(np.float64) ** 2)))
            if not np.isfinite(rms_val):
                continue
            rms_values.append(rms_val)
            centers.append((start_t + end_t) / 2.0)

        rms_values = np.asarray(rms_values, dtype=np.float64)
        centers = np.asarray(centers, dtype=np.float64)
        if rms_values.size < 4 or centers.size < 4:
            return {
                "sidechainDetail": {
                    "pumpingStrength": 0.0,
                    "pumpingRegularity": 0.0,
                    "pumpingRate": None,
                    "pumpingConfidence": 0.0,
                }
            }

        kick_series = np.interp(
            centers, beats, low_band, left=low_band[0], right=low_band[-1]
        )

        def zscore(values: np.ndarray) -> np.ndarray:
            arr = np.asarray(values, dtype=np.float64)
            std = float(np.std(arr))
            if std <= 1e-12:
                return np.zeros_like(arr)
            return (arr - float(np.mean(arr))) / std

        rms_z = zscore(rms_values)
        kick_z = zscore(kick_series)
        if np.std(rms_z) > 1e-12 and np.std(kick_z) > 1e-12:
            dip_corr = float(np.corrcoef(-rms_z, kick_z)[0, 1])
            if not np.isfinite(dip_corr):
                dip_corr = 0.0
        else:
            dip_corr = 0.0

        rms_q90 = float(np.percentile(rms_values, 90))
        rms_q10 = float(np.percentile(rms_values, 10))
        dip_depth = (rms_q90 - rms_q10) / (rms_q90 + 1e-9) if rms_q90 > 0 else 0.0
        dip_depth = float(np.clip(dip_depth, 0.0, 1.0))
        pumping_strength = float(
            np.clip(0.6 * max(0.0, dip_corr) + 0.4 * dip_depth, 0.0, 1.0)
        )

        rms_mean = float(np.mean(rms_values))
        rms_std = float(np.std(rms_values))
        kick_mean = float(np.mean(kick_series))
        dip_mask = (rms_values <= (rms_mean - 0.35 * rms_std)) & (
            kick_series >= kick_mean
        )
        dip_indices = np.where(dip_mask)[0]

        pumping_regularity = 0.0
        pumping_rate = None
        interval_steps = np.array([], dtype=np.float64)
        if dip_indices.size >= 3:
            interval_steps = np.diff(dip_indices.astype(np.float64))
            mean_step = (
                float(np.mean(interval_steps)) if interval_steps.size > 0 else 0.0
            )
            if mean_step > 0:
                pumping_regularity = float(
                    np.clip(1.0 - (np.std(interval_steps) / mean_step), 0.0, 1.0)
                )

            rate_scores = {}
            for label, target in (
                ("quarter", 4.0),
                ("eighth", 2.0),
                ("sixteenth", 1.0),
            ):
                if interval_steps.size == 0:
                    rate_scores[label] = 0.0
                    continue
                error = float(
                    np.mean(np.abs(interval_steps - target) / (target + 1e-9))
                )
                rate_scores[label] = float(np.clip(1.0 - error, 0.0, 1.0))

            best_rate = max(rate_scores, key=rate_scores.get)
            pumping_rate = best_rate if rate_scores[best_rate] >= 0.45 else None

        beat_intervals = np.diff(beats.astype(np.float64))
        mean_interval = (
            float(np.mean(beat_intervals)) if beat_intervals.size > 0 else 0.0
        )
        if mean_interval > 0:
            timing_stability = float(
                np.clip(1.0 - (np.std(beat_intervals) / mean_interval), 0.0, 1.0)
            )
        else:
            timing_stability = 0.0

        mean_total_beat_loudness = float(np.mean(beat_loudness))
        mean_kick = float(np.mean(low_band))
        kick_presence = (
            mean_kick / (mean_total_beat_loudness + 1e-9)
            if mean_total_beat_loudness > 0
            else 0.0
        )

        kick_p90 = float(np.percentile(low_band, 90))
        kick_p50 = float(np.percentile(low_band, 50))
        kick_contrast = (
            (kick_p90 - kick_p50) / (kick_p90 + 1e-9) if kick_p90 > 0 else 0.0
        )
        kick_contrast = float(np.clip(kick_contrast, 0.0, 1.0))

        confidence = float(
            np.clip(
                0.45 * max(0.0, dip_corr)
                + 0.35 * kick_contrast
                + 0.20 * timing_stability,
                0.0,
                1.0,
            )
        )
        if kick_presence < 0.12:
            confidence *= 0.6
        if dip_corr < 0.20:
            confidence *= 0.6
        if beats.size < 8:
            confidence *= 0.7
        pumping_confidence = float(np.clip(confidence, 0.0, 1.0))

        # Envelope shape: median RMS across bars at 16th-note resolution (16 values)
        envelope_shape = None
        if rms_values.size >= 16:
            n_bars = rms_values.size // 16
            if n_bars >= 1:
                bars_matrix = rms_values[:n_bars * 16].reshape(n_bars, 16)
                median_bar = np.median(bars_matrix, axis=0)
                bar_max = float(np.max(median_bar))
                if bar_max > 0:
                    normalized = median_bar / bar_max
                    envelope_shape = [round(float(v), 3) for v in normalized]

        return {
            "sidechainDetail": {
                "pumpingStrength": round(pumping_strength, 4),
                "pumpingRegularity": round(
                    float(np.clip(pumping_regularity, 0.0, 1.0)), 4
                ),
                "pumpingRate": pumping_rate,
                "pumpingConfidence": round(pumping_confidence, 4),
                "envelopeShape": envelope_shape,
            }
        }
    except Exception as e:
        print(f"[warn] Sidechain analysis failed: {e}", file=sys.stderr)
        return {"sidechainDetail": None}


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


def analyze_bass_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
) -> dict:
    """Analyze bass character: sub-bass decay time, transient ratio, fundamental Hz, swing.

    Ported from sonic-architect-app/services/bassAnalysis.ts.
    Uses Essentia LowPass for bass extraction, energy-based onset detection,
    decay measurement to -6 dB, and ZCR fundamental estimation.
    """
    try:
        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < sample_rate:
            return {"bassDetail": None}

        effective_bpm = bpm if (bpm is not None and np.isfinite(bpm) and bpm > 0) else 120.0

        # --- 1. Extract bass band: one-pole lowpass at 150 Hz ---
        fc = 150.0 / float(sample_rate)
        alpha = float(np.exp(-2.0 * np.pi * fc))
        a0 = 1.0 - alpha
        bass = np.zeros(mono_arr.size, dtype=np.float64)
        y1 = 0.0
        for i in range(mono_arr.size):
            y1 = a0 * float(mono_arr[i]) + alpha * y1
            bass[i] = y1
        bass = bass.astype(np.float32)

        # --- 2. Find bass transients (energy-based onset detection) ---
        hop_onset = max(1, int(sample_rate * 0.01))   # 10 ms hops
        frame_onset = max(1, int(sample_rate * 0.04))  # 40 ms frames
        beat_dur_s = 60.0 / effective_bpm
        min_onset_dist = int(beat_dur_s * 0.25 * sample_rate)  # ~1/16th note

        onsets: list[int] = []
        prev_energy = 0.0
        last_onset = -min_onset_dist

        i = 0
        while i + frame_onset < bass.size:
            frame_slice = bass[i : i + frame_onset]
            energy = float(np.sqrt(np.mean(frame_slice ** 2)))
            diff = energy - prev_energy
            rel_diff = diff / prev_energy if prev_energy > 0.001 else 0.0
            if rel_diff > 0.5 and energy > 0.01 and (i - last_onset) >= min_onset_dist:
                onsets.append(i)
                last_onset = i
            prev_energy = energy * 0.8 + prev_energy * 0.2
            i += hop_onset

        # --- 3. Fundamental estimation via ZCR on middle 50% ---
        start_zcr = bass.size // 4
        end_zcr = (bass.size * 3) // 4
        crossings = 0
        for j in range(start_zcr + 1, end_zcr):
            if (bass[j - 1] < 0 and bass[j] >= 0) or (bass[j - 1] >= 0 and bass[j] < 0):
                crossings += 1
        dur_zcr = float(end_zcr - start_zcr) / float(sample_rate)
        zcr = crossings / dur_zcr if dur_zcr > 0 else 0.0
        fundamental_hz = max(30.0, min(120.0, zcr / 2.0))

        if len(onsets) < 3:
            return {
                "bassDetail": {
                    "averageDecayMs": 1000,
                    "type": "sustained",
                    "transientRatio": 0.2,
                    "fundamentalHz": round(fundamental_hz),
                    "transientCount": len(onsets),
                    "swingPercent": 0,
                    "grooveType": "straight",
                }
            }

        # --- 4. Measure decay time per onset to -6 dB ---
        DECAY_THRESHOLD_DB = -6.0
        MAX_DECAY_MS = 2000.0
        decay_times: list[float] = []

        for idx in range(len(onsets) - 1):
            onset_sample = onsets[idx]
            next_onset = onsets[idx + 1]
            max_decay_samples = min(
                next_onset - onset_sample,
                int((MAX_DECAY_MS / 1000.0) * sample_rate),
            )
            # Find peak near onset (50 ms search window)
            search_end = min(onset_sample + int(sample_rate * 0.05), bass.size)
            peak_val = float(np.max(np.abs(bass[onset_sample:search_end]))) if search_end > onset_sample else 0.0
            if peak_val < 0.001:
                continue
            threshold_val = peak_val * (10.0 ** (DECAY_THRESHOLD_DB / 20.0))
            found = False
            for s in range(max_decay_samples):
                if onset_sample + s >= bass.size:
                    break
                if abs(float(bass[onset_sample + s])) < threshold_val:
                    decay_times.append((s / float(sample_rate)) * 1000.0)
                    found = True
                    break
            if not found:
                decay_times.append((max_decay_samples / float(sample_rate)) * 1000.0)

        avg_decay = float(np.mean(decay_times)) if decay_times else 800.0

        if avg_decay < 300:
            bass_type = "punchy"
        elif avg_decay < 600:
            bass_type = "medium"
        elif avg_decay < 1000:
            bass_type = "rolling"
        else:
            bass_type = "sustained"

        # --- 5. Transient ratio ---
        transient_window_samples = int(0.1 * sample_rate)  # 100 ms
        transient_energy = 0.0
        marked: set[int] = set()
        for ons in onsets:
            for s in range(ons, min(ons + transient_window_samples, bass.size)):
                if s not in marked:
                    transient_energy += float(bass[s]) ** 2
                    marked.add(s)
        total_bass_energy = float(np.sum(bass ** 2))
        transient_ratio = transient_energy / total_bass_energy if total_bass_energy > 0 else 0.0

        # --- 6. Swing detection from onset intervals ---
        swing_percent = 0
        groove_type = "straight"
        if len(onsets) >= 8:
            intervals = [float(onsets[k + 1] - onsets[k]) / float(sample_rate)
                         for k in range(len(onsets) - 1)]
            if len(intervals) >= 4:
                mean_int = float(np.mean(intervals))
                var_int = float(np.var(intervals))
                std_int = float(np.sqrt(var_int))
                cv = std_int / mean_int if mean_int > 0 else 0.0
                # Lag-1 autocorrelation for alternation detection
                if var_int > 0:
                    alt_sum = sum(
                        (intervals[j] - mean_int) * (intervals[j + 1] - mean_int)
                        for j in range(len(intervals) - 1)
                    )
                    alt_corr = alt_sum / (len(intervals) - 1) / var_int
                else:
                    alt_corr = 0.0
                if alt_corr < -0.1 and cv > 0.05:
                    swing_percent = int(min(50, max(0, cv * 400)))
                if swing_percent < 10:
                    groove_type = "straight"
                elif swing_percent < 25:
                    groove_type = "slight-swing"
                elif swing_percent < 40:
                    groove_type = "heavy-swing"
                else:
                    groove_type = "shuffle"

        return {
            "bassDetail": {
                "averageDecayMs": round(avg_decay),
                "type": bass_type,
                "transientRatio": round(float(np.clip(transient_ratio, 0.0, 1.0)), 2),
                "fundamentalHz": round(fundamental_hz),
                "transientCount": len(onsets),
                "swingPercent": swing_percent,
                "grooveType": groove_type,
            }
        }
    except Exception as e:
        print(f"[warn] Bass analysis failed: {e}", file=sys.stderr)
        return {"bassDetail": None}


def analyze_kick_detail(
    mono: np.ndarray,
    sample_rate: int = 44100,
    bpm: float | None = None,
) -> dict:
    """Analyze kick drum characteristics: onset sharpness, fundamental pitch, THD, harmonic ratio.

    Ported from sonic-architect-app/services/kickAnalysis.ts.
    Uses Essentia Spectrum + Windowing in the kick band (30-120 Hz),
    OnsetDetection for transients, per-kick THD measurement up to 10th harmonic.
    """
    try:
        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size < 4096:
            return {"kickDetail": None}

        effective_bpm = bpm if (bpm is not None and np.isfinite(bpm) and bpm > 0) else 120.0

        frame_size = 2048
        hop_size = 256
        kick_low = 30.0
        kick_high = 120.0

        window = es.Windowing(type="hann", size=frame_size)
        spectrum_algo = es.Spectrum(size=frame_size)

        freq_resolution = float(sample_rate) / float(frame_size)
        low_bin = max(1, int(kick_low / freq_resolution))
        high_bin = min(frame_size // 2 - 1, int(kick_high / freq_resolution))

        # --- 1. Build energy envelope in kick band ---
        envelope: list[float] = []
        for frame in es.FrameGenerator(mono_arr, frameSize=frame_size, hopSize=hop_size):
            spec = spectrum_algo(window(frame))
            kick_energy = 0.0
            for k in range(low_bin, high_bin + 1):
                kick_energy += float(spec[k]) ** 2
            n_bins = max(1, high_bin - low_bin + 1)
            envelope.append(float(np.sqrt(kick_energy / n_bins)))

        if len(envelope) < 5:
            return {"kickDetail": None}

        # --- 2. Detect kick transients (peaks in envelope) ---
        beat_dur_s = 60.0 / effective_bpm
        min_dist_samples = int(beat_dur_s * 0.25 * sample_rate)  # 16th note
        min_dist_frames = max(1, min_dist_samples // hop_size)

        transients: list[int] = []  # indices into envelope
        last_transient = -min_dist_frames
        for i in range(2, len(envelope) - 2):
            if (
                envelope[i] > envelope[i - 1]
                and envelope[i] > envelope[i + 1]
                and envelope[i] > 0.01
                and i - last_transient >= min_dist_frames
            ):
                transients.append(i)
                last_transient = i

        if len(transients) < 2:
            return {
                "kickDetail": {
                    "isDistorted": False,
                    "thd": 0.0,
                    "harmonicRatio": 0.0,
                    "fundamentalHz": 50.0,
                    "kickCount": len(transients),
                }
            }

        # --- 3. Per-kick THD and harmonic analysis ---
        thd_values: list[float] = []
        harmonic_ratios: list[float] = []
        fundamentals: list[float] = []

        for t_idx in transients:
            start_sample = t_idx * hop_size
            kick_frame_len = min(int(0.08 * sample_rate), frame_size)  # 80 ms
            if start_sample + frame_size > mono_arr.size:
                continue
            raw_frame = mono_arr[start_sample : start_sample + frame_size]
            spec = spectrum_algo(window(raw_frame))

            # Find fundamental (strongest peak in kick band)
            max_mag = 0.0
            fund_bin = low_bin
            for k in range(low_bin, high_bin + 1):
                mag = float(spec[k])
                if mag > max_mag:
                    max_mag = mag
                    fund_bin = k
            fund_hz = fund_bin * freq_resolution
            fund_power = max_mag ** 2

            # THD: sum of harmonic powers / fundamental power
            max_harmonic = min(10, int((sample_rate / 2.0) / fund_hz)) if fund_hz > 0 else 1
            harmonic_power = 0.0
            for h in range(2, max_harmonic + 1):
                h_bin = round(fund_bin * h)
                if 0 < h_bin < spec.size:
                    harmonic_power += float(spec[h_bin]) ** 2

            thd = float(np.sqrt(harmonic_power) / np.sqrt(fund_power)) if fund_power > 0 else 0.0

            # Harmonic vs inharmonic ratio in kick band
            harmonic_energy = 0.0
            inharmonic_energy = 0.0
            bin_width = freq_resolution
            for k in range(low_bin, min(high_bin + 1, spec.size)):
                freq = k * freq_resolution
                mag = float(spec[k])
                is_harmonic = False
                if fund_hz > 0:
                    for hh in range(1, 11):
                        if abs(freq - fund_hz * hh) < bin_width * 1.5:
                            is_harmonic = True
                            break
                if is_harmonic:
                    harmonic_energy += mag ** 2
                else:
                    inharmonic_energy += mag ** 2
            total_e = harmonic_energy + inharmonic_energy
            h_ratio = harmonic_energy / total_e if total_e > 0 else 0.0

            thd_values.append(min(1.0, thd))
            harmonic_ratios.append(h_ratio)
            fundamentals.append(fund_hz)

        if not thd_values:
            return {
                "kickDetail": {
                    "isDistorted": False,
                    "thd": 0.0,
                    "harmonicRatio": 0.0,
                    "fundamentalHz": 50.0,
                    "kickCount": len(transients),
                }
            }

        avg_thd = float(np.mean(thd_values))
        avg_harmonic_ratio = float(np.mean(harmonic_ratios))
        avg_fundamental = float(np.mean(fundamentals))
        is_distorted = avg_thd > 0.15 or avg_harmonic_ratio < 0.5

        return {
            "kickDetail": {
                "isDistorted": is_distorted,
                "thd": round(avg_thd, 2),
                "harmonicRatio": round(avg_harmonic_ratio, 2),
                "fundamentalHz": round(avg_fundamental),
                "kickCount": len(transients),
            }
        }
    except Exception as e:
        print(f"[warn] Kick analysis failed: {e}", file=sys.stderr)
        return {"kickDetail": None}


# ─────────────────────────────────────────────────────────────────────────────
# GENRE CLASSIFICATION
# Backport of genreClassifierEnhanced.ts — scores 35 electronic subgenres
# using features already computed by the other analyzers in this pipeline.
# ─────────────────────────────────────────────────────────────────────────────

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


def analyze_arrangement_detail(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Novelty timeline from Bark bands to expose structural events."""
    try:
        mono_arr = np.asarray(mono, dtype=np.float32)
        if mono_arr.ndim != 1 or mono_arr.size == 0:
            return {"arrangementDetail": None}

        frame_size = 2048
        hop_size = 1024
        if mono_arr.size < frame_size:
            mono_arr = np.pad(mono_arr, (0, frame_size - mono_arr.size))

        window = es.Windowing(type="hann", size=frame_size)
        spectrum = es.Spectrum(size=frame_size)
        bark_bands = es.BarkBands(numberBands=24, sampleRate=sample_rate)

        bark_matrix = []
        for frame in es.FrameGenerator(
            mono_arr, frameSize=frame_size, hopSize=hop_size
        ):
            spec = spectrum(window(frame))
            bands = np.asarray(bark_bands(spec), dtype=np.float32)
            if bands.size == 24 and np.all(np.isfinite(bands)):
                bark_matrix.append(bands)

        if len(bark_matrix) < 2:
            return {
                "arrangementDetail": {
                    "noveltyCurve": [],
                    "noveltyPeaks": [],
                    "noveltyMean": 0.0,
                    "noveltyStdDev": 0.0,
                }
            }

        novelty_algo = es.NoveltyCurve(
            frameRate=float(sample_rate) / float(hop_size), normalize=True
        )
        novelty = novelty_algo(np.asarray(bark_matrix, dtype=np.float32))
        novelty = np.asarray(novelty, dtype=np.float64)
        novelty = novelty[np.isfinite(novelty)]

        if novelty.size == 0:
            return {
                "arrangementDetail": {
                    "noveltyCurve": [],
                    "noveltyPeaks": [],
                    "noveltyMean": 0.0,
                    "noveltyStdDev": 0.0,
                }
            }

        max_val = float(np.max(np.abs(novelty)))
        if max_val > 0.0:
            novelty = novelty / max_val

        novelty_mean = float(np.mean(novelty))
        novelty_std = float(np.std(novelty))
        novelty_curve = _downsample_evenly(novelty, max_points=64, decimals=4)
        novelty_peaks = _pick_novelty_peaks(
            novelty,
            sample_rate=sample_rate,
            hop_size=hop_size,
            max_peaks=8,
            min_spacing_sec=2.0,
        )

        return {
            "arrangementDetail": {
                "noveltyCurve": novelty_curve,
                "noveltyPeaks": novelty_peaks,
                "noveltyMean": round(novelty_mean, 4),
                "noveltyStdDev": round(novelty_std, 4),
            }
        }
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


def analyze_structure(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Structure segmentation with SBic, returned as capped segment objects."""
    try:
        duration = float(len(mono) / sample_rate) if sample_rate > 0 else 0.0
        boundaries_seconds = None

        # Requested path: direct SBic call on mono signal.
        try:
            direct_boundaries = es.SBic()(mono)
            boundaries_seconds = np.asarray(direct_boundaries, dtype=np.float64)
        except Exception:
            boundaries_seconds = None

        # Fallback path for builds where SBic expects feature matrices and returns frame indices.
        if boundaries_seconds is None:
            frame_size = 2048
            hop_size = 1024
            window = es.Windowing(type="hann", size=frame_size)
            spectrum = es.Spectrum(size=frame_size)
            mfcc = es.MFCC(
                inputSize=frame_size // 2 + 1,
                sampleRate=sample_rate,
                numberCoefficients=13,
            )

            feature_rows = []
            for frame in es.FrameGenerator(
                mono, frameSize=frame_size, hopSize=hop_size
            ):
                spec = spectrum(window(frame))
                _bands, coeffs = mfcc(spec)
                feature_rows.append(np.asarray(coeffs, dtype=np.float64))

            if len(feature_rows) < 2:
                return {"structure": {"segments": [], "segmentCount": 0}}

            feature_matrix = np.asarray(feature_rows, dtype=np.float32).T
            boundary_frames = np.asarray(es.SBic()(feature_matrix), dtype=np.float64)
            boundaries_seconds = boundary_frames * (
                float(hop_size) / float(sample_rate)
            )

        boundaries_seconds = np.asarray(boundaries_seconds, dtype=np.float64)
        if boundaries_seconds.size == 0:
            return {"structure": {"segments": [], "segmentCount": 0}}

        # Normalize and enforce [0, duration] with sorted unique boundaries.
        boundaries_seconds = boundaries_seconds[np.isfinite(boundaries_seconds)]
        if boundaries_seconds.size == 0:
            return {"structure": {"segments": [], "segmentCount": 0}}
        boundaries_seconds = np.clip(boundaries_seconds, 0.0, duration)
        boundaries_seconds = np.unique(boundaries_seconds)
        boundaries_seconds.sort()

        if boundaries_seconds.size == 1:
            only = float(boundaries_seconds[0])
            if only > 0.0:
                boundaries_seconds = np.array([0.0, only], dtype=np.float64)
            elif duration > 0.0:
                boundaries_seconds = np.array([0.0, duration], dtype=np.float64)

        if boundaries_seconds[0] > 0.0:
            boundaries_seconds = np.insert(boundaries_seconds, 0, 0.0)
        if duration > 0.0 and boundaries_seconds[-1] < duration:
            boundaries_seconds = np.append(boundaries_seconds, duration)

        segments = []
        for i in range(len(boundaries_seconds) - 1):
            start = float(boundaries_seconds[i])
            end = float(boundaries_seconds[i + 1])
            if end <= start:
                continue
            segments.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "index": int(i),
                }
            )
            if len(segments) >= 20:
                break

        return {
            "structure": {
                "segments": segments,
                "segmentCount": len(segments),
            }
        }
    except Exception as e:
        print(f"[warn] Structure analysis failed: {e}", file=sys.stderr)
        return {"structure": None}


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

        return {
            "chordDetail": {
                "chordSequence": chord_sequence,
                "chordStrength": chord_strength,
                "progression": progression,
                "dominantChords": dominant_chords,
            }
        }
    except Exception as e:
        print(f"[warn] Chord analysis failed: {e}", file=sys.stderr)
        return {"chordDetail": None}


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


TRANSCRIPTION_CONFIDENCE_FLOOR = 0.05
TRANSCRIPTION_NOTE_CAP = 500
FULL_MIX_TRANSCRIPTION_NOTE_CAP = 200
TRANSCRIPTION_MIN_ACTIVE_WINDOW_SECONDS = 0.1
TRANSCRIPTION_NEAR_DUPLICATE_SECONDS = 0.03

from typing import Protocol, runtime_checkable


@runtime_checkable
class TranscriptionBackend(Protocol):
    """Interface for pluggable symbolic extraction backends."""

    name: str  # written to transcriptionDetail.transcriptionMethod in output

    def transcribe(
        self,
        audio_path: str,
        stem_paths: dict | None = None,
        emit_progress_markers: bool = False,
    ) -> dict:
        """Return a transcriptionDetail dict.

        Return shape must match the existing transcriptionDetail contract
        documented in JSON_SCHEMA.md. On failure, return {"transcriptionDetail": None}.
        """
        ...


def _transcription_source_paths(
    audio_path: str, stem_paths: dict | None = None
) -> list[tuple[str, str]]:
    sources = []
    if isinstance(stem_paths, dict):
        for stem_name in ("bass", "other"):
            source_path = stem_paths.get(stem_name)
            if isinstance(source_path, str) and os.path.isfile(source_path):
                sources.append((stem_name, source_path))
    if len(sources) == 0:
        return [("full_mix", audio_path)]
    return sources


def _transcription_active_end(note: dict) -> float:
    onset = float(note.get("onsetSeconds", 0.0))
    duration = float(note.get("durationSeconds", 0.0))
    return onset + max(duration, TRANSCRIPTION_MIN_ACTIVE_WINDOW_SECONDS)


def _transcription_stem_priority(note: dict) -> int:
    pitch_midi = int(note.get("pitchMidi", 0))
    return _transcription_stem_priority_for_pitch(note.get("stemSource"), pitch_midi)


def _transcription_stem_priority_for_pitch(stem_source: str | None, pitch_midi: int) -> int:
    if pitch_midi < 48:
        order = {"bass": 3, "other": 2, "full_mix": 1}
    else:
        order = {"other": 3, "bass": 2, "full_mix": 1}
    return order.get(stem_source, 0)


def _merge_transcription_notes(preferred: dict, other: dict) -> dict:
    merged = dict(preferred)
    merged["durationSeconds"] = round(
        max(
            float(preferred.get("durationSeconds", 0.0)),
            float(other.get("durationSeconds", 0.0)),
        ),
        4,
    )
    return merged


def _is_near_duplicate_pitch(note: dict, candidate: dict) -> bool:
    return (
        int(note.get("pitchMidi", 0)) == int(candidate.get("pitchMidi", 0))
        and abs(float(note.get("onsetSeconds", 0.0)) - float(candidate.get("onsetSeconds", 0.0)))
        <= TRANSCRIPTION_NEAR_DUPLICATE_SECONDS
    )


def _notes_overlap_for_dedup(note: dict, candidate: dict) -> bool:
    if abs(int(note.get("pitchMidi", 0)) - int(candidate.get("pitchMidi", 0))) > 1:
        return False
    note_start = float(note.get("onsetSeconds", 0.0))
    note_end = _transcription_active_end(note)
    candidate_start = float(candidate.get("onsetSeconds", 0.0))
    candidate_end = _transcription_active_end(candidate)
    return min(note_end, candidate_end) >= max(note_start, candidate_start)


def _select_transcription_winner(note: dict, candidate: dict, prefer_confidence_first: bool) -> dict:
    note_conf = float(note.get("confidence", 0.0))
    candidate_conf = float(candidate.get("confidence", 0.0))
    priority_pitch = min(int(note.get("pitchMidi", 0)), int(candidate.get("pitchMidi", 0)))
    note_priority = _transcription_stem_priority_for_pitch(note.get("stemSource"), priority_pitch)
    candidate_priority = _transcription_stem_priority_for_pitch(candidate.get("stemSource"), priority_pitch)

    if prefer_confidence_first:
        if note_conf != candidate_conf:
            return note if note_conf > candidate_conf else candidate
        if note_priority != candidate_priority:
            return note if note_priority > candidate_priority else candidate
    else:
        if note_priority != candidate_priority:
            return note if note_priority > candidate_priority else candidate
        if note_conf != candidate_conf:
            return note if note_conf > candidate_conf else candidate

    note_duration = float(note.get("durationSeconds", 0.0))
    candidate_duration = float(candidate.get("durationSeconds", 0.0))
    if note_duration != candidate_duration:
        return note if note_duration > candidate_duration else candidate
    return note if float(note.get("onsetSeconds", 0.0)) <= float(candidate.get("onsetSeconds", 0.0)) else candidate


def _deduplicate_transcription_notes(notes: list[dict]) -> list[dict]:
    if len(notes) <= 1:
        return [dict(note) for note in notes]

    sorted_notes = sorted(
        (dict(note) for note in notes),
        key=lambda note: (
            float(note.get("onsetSeconds", 0.0)),
            int(note.get("pitchMidi", 0)),
            -float(note.get("confidence", 0.0)),
        ),
    )
    active_heap: list[tuple[float, int, int]] = []
    active_by_pitch: dict[int, dict[int, dict]] = {}
    deduplicated: list[dict] = []
    next_active_id = 0

    def register_active(note: dict) -> None:
        nonlocal next_active_id
        note["_activeId"] = next_active_id
        note["_heapVersion"] = 1
        active_by_pitch.setdefault(int(note["pitchMidi"]), {})[next_active_id] = note
        heapq.heappush(
            active_heap,
            (_transcription_active_end(note), next_active_id, int(note["_heapVersion"])),
        )
        deduplicated.append(note)
        next_active_id += 1

    def refresh_active(note: dict) -> None:
        note["_heapVersion"] = int(note.get("_heapVersion", 0)) + 1
        heapq.heappush(
            active_heap,
            (_transcription_active_end(note), int(note["_activeId"]), int(note["_heapVersion"])),
        )

    for note in sorted_notes:
        onset = float(note.get("onsetSeconds", 0.0))
        while active_heap and active_heap[0][0] < onset:
            _end_time, active_id, heap_version = heapq.heappop(active_heap)
            active_note = None
            for bucket in active_by_pitch.values():
                active_note = bucket.get(active_id)
                if active_note is not None:
                    break
            if active_note is None or int(active_note.get("_heapVersion", 0)) != heap_version:
                continue
            pitch_bucket = active_by_pitch.get(int(active_note["pitchMidi"]))
            if pitch_bucket is not None:
                pitch_bucket.pop(active_id, None)
                if len(pitch_bucket) == 0:
                    active_by_pitch.pop(int(active_note["pitchMidi"]), None)

        matching_candidates: list[tuple[bool, float, int, dict]] = []
        for pitch_midi in range(max(0, int(note["pitchMidi"]) - 1), min(127, int(note["pitchMidi"]) + 1) + 1):
            for candidate in active_by_pitch.get(pitch_midi, {}).values():
                if candidate.get("stemSource") == note.get("stemSource"):
                    continue
                is_near_duplicate = _is_near_duplicate_pitch(note, candidate)
                if not is_near_duplicate and not _notes_overlap_for_dedup(note, candidate):
                    continue
                matching_candidates.append(
                    (
                        is_near_duplicate,
                        abs(float(candidate.get("onsetSeconds", 0.0)) - onset),
                        abs(int(candidate.get("pitchMidi", 0)) - int(note.get("pitchMidi", 0))),
                        candidate,
                    )
                )

        if len(matching_candidates) == 0:
            register_active(note)
            continue

        matching_candidates.sort(key=lambda item: (not item[0], item[1], item[2]))
        candidate = matching_candidates[0][3]
        is_near_duplicate = matching_candidates[0][0]
        winner = _select_transcription_winner(note, candidate, prefer_confidence_first=is_near_duplicate)
        loser = candidate if winner is note else note
        merged = _merge_transcription_notes(winner, loser)

        if winner is note:
            active_id = int(candidate["_activeId"])
            pitch_bucket = active_by_pitch.get(int(candidate["pitchMidi"]))
            if pitch_bucket is not None:
                pitch_bucket.pop(active_id, None)
                if len(pitch_bucket) == 0:
                    active_by_pitch.pop(int(candidate["pitchMidi"]), None)
            deduplicated = [
                merged if int(existing.get("_activeId", -1)) == active_id else existing
                for existing in deduplicated
            ]
            merged["_activeId"] = active_id
            merged["_heapVersion"] = int(candidate.get("_heapVersion", 0)) + 1
            active_by_pitch.setdefault(int(merged["pitchMidi"]), {})[active_id] = merged
            heapq.heappush(
                active_heap,
                (_transcription_active_end(merged), active_id, int(merged["_heapVersion"])),
            )
        else:
            candidate.update(merged)
            refresh_active(candidate)

    cleaned_notes = []
    for note in deduplicated:
        cleaned_note = dict(note)
        cleaned_note.pop("_activeId", None)
        cleaned_note.pop("_heapVersion", None)
        cleaned_notes.append(cleaned_note)

    return sorted(cleaned_notes, key=lambda note: note["onsetSeconds"])


TORCHCREPE_SAMPLE_RATE = 16000
TORCHCREPE_HOP_LENGTH = 160
TORCHCREPE_FMIN = 50.0
TORCHCREPE_FMAX = 1000.0
TORCHCREPE_PERIODICITY_THRESHOLD = 0.21
TORCHCREPE_MODEL = "tiny"
TORCHCREPE_MIN_NOTE_SECONDS = 0.06
TORCHCREPE_PITCH_JUMP_SPLIT_SEMITONES = 2.0
TRANSCRIPTION_BACKEND_ENV = "ASA_TRANSCRIPTION_BACKEND"


def _extract_torchcrepe_notes(
    source_path: str,
    stem_source: str,
    *,
    torch_module,
    torchcrepe_module,
    device: str,
) -> tuple[list[dict], list[int], list[float]]:
    mono = np.asarray(
        load_mono(source_path, sample_rate=TORCHCREPE_SAMPLE_RATE), dtype=np.float32
    )
    if mono.size == 0:
        return [], [], []

    with torch_module.no_grad():
        audio = torch_module.as_tensor(mono, dtype=torch_module.float32, device=device)
        if audio.ndim == 1:
            audio = audio.unsqueeze(0)

        pitch_hz, periodicity = torchcrepe_module.predict(
            audio,
            TORCHCREPE_SAMPLE_RATE,
            hop_length=TORCHCREPE_HOP_LENGTH,
            fmin=TORCHCREPE_FMIN,
            fmax=TORCHCREPE_FMAX,
            model=TORCHCREPE_MODEL,
            return_periodicity=True,
            device=device,
            pad=False,
            batch_size=512,
        )

    pitch = np.asarray(pitch_hz.squeeze(0).detach().cpu().numpy(), dtype=np.float64)
    periodicity_values = np.asarray(
        periodicity.squeeze(0).detach().cpu().numpy(), dtype=np.float64
    )
    # Free torch tensors immediately — PyTorch's CPU allocator won't
    # return memory to the OS otherwise.
    del audio, pitch_hz, periodicity
    import gc; gc.collect()
    pitch = np.nan_to_num(pitch, nan=0.0, posinf=0.0, neginf=0.0)
    periodicity_values = np.nan_to_num(
        periodicity_values, nan=0.0, posinf=0.0, neginf=0.0
    )

    voiced = (pitch > 0.0) & (periodicity_values >= TORCHCREPE_PERIODICITY_THRESHOLD)
    frame_duration = TORCHCREPE_HOP_LENGTH / float(TORCHCREPE_SAMPLE_RATE)
    notes: list[dict] = []
    midi_values: list[int] = []
    confidence_values: list[float] = []

    start_idx: int | None = None
    midi_track: list[float] = []
    confidence_track: list[float] = []
    last_midi: float | None = None

    def flush(end_idx: int) -> None:
        nonlocal start_idx, midi_track, confidence_track, last_midi
        if start_idx is None or len(midi_track) == 0:
            start_idx = None
            midi_track = []
            confidence_track = []
            last_midi = None
            return

        onset_seconds = start_idx * frame_duration
        duration_seconds = max(0.0, (end_idx - start_idx) * frame_duration)
        if duration_seconds < TORCHCREPE_MIN_NOTE_SECONDS:
            start_idx = None
            midi_track = []
            confidence_track = []
            last_midi = None
            return

        pitch_midi = int(np.clip(int(round(float(np.median(midi_track)))), 0, 127))
        confidence = _normalize_confidence(
            float(np.mean(np.asarray(confidence_track, dtype=np.float64)))
        )
        if confidence < TRANSCRIPTION_CONFIDENCE_FLOOR:
            start_idx = None
            midi_track = []
            confidence_track = []
            last_midi = None
            return

        note_obj = {
            "pitchMidi": pitch_midi,
            "pitchName": midi_to_note_name(pitch_midi),
            "onsetSeconds": round(float(onset_seconds), 4),
            "durationSeconds": round(float(duration_seconds), 4),
            "confidence": confidence,
            "stemSource": stem_source,
        }
        notes.append(note_obj)
        midi_values.append(pitch_midi)
        confidence_values.append(confidence)

        start_idx = None
        midi_track = []
        confidence_track = []
        last_midi = None

    for idx in range(len(pitch)):
        if not voiced[idx]:
            flush(idx)
            continue

        current_midi = float(69.0 + 12.0 * np.log2(max(pitch[idx], 1e-9) / 440.0))

        if start_idx is None:
            start_idx = idx
            midi_track = [current_midi]
            confidence_track = [float(periodicity_values[idx])]
            last_midi = current_midi
            continue

        if (
            last_midi is not None
            and abs(current_midi - last_midi) > TORCHCREPE_PITCH_JUMP_SPLIT_SEMITONES
        ):
            flush(idx)
            start_idx = idx
            midi_track = [current_midi]
            confidence_track = [float(periodicity_values[idx])]
            last_midi = current_midi
            continue

        midi_track.append(current_midi)
        confidence_track.append(float(periodicity_values[idx]))
        last_midi = current_midi

    flush(len(pitch))
    return notes, midi_values, confidence_values


class TorchcrepeBackend:
    """Maintained transcription backend using torchcrepe F0 tracking + segmentation."""

    name = "torchcrepe-viterbi"

    def transcribe(
        self,
        audio_path: str,
        stem_paths: dict | None = None,
        emit_progress_markers: bool = False,
    ) -> dict:
        try:
            import torch
            import torchcrepe
        except Exception as e:
            print(f"[warn] Torchcrepe import failed: {e}", file=sys.stderr)
            return {"transcriptionDetail": None}

        try:
            transcription_sources = _transcription_source_paths(audio_path, stem_paths)
            full_mix_fallback = (
                len(transcription_sources) == 1
                and transcription_sources[0][0] == "full_mix"
            )
            if full_mix_fallback:
                print(
                    "[warn] transcriptionDetail: running on full mix — quality may be low for dense material",
                    file=sys.stderr,
                )

            device = "cuda" if torch.cuda.is_available() else "cpu"
            notes: list[dict] = []
            stems_transcribed = [
                stem_source for stem_source, _source_path in transcription_sources
            ]

            for stem_source, source_path in transcription_sources:
                if emit_progress_markers:
                    transcription_mode = (
                        "stems"
                        if stem_source in ("bass", "other")
                        else "full_mix"
                    )
                    print(
                        f"@@TRANSCRIPTION_SOURCE mode={transcription_mode} source={stem_source}",
                        file=sys.stderr,
                    )

                source_notes, _source_midi_values, _source_confidence_values = (
                    _extract_torchcrepe_notes(
                        source_path,
                        stem_source,
                        torch_module=torch,
                        torchcrepe_module=torchcrepe,
                        device=device,
                    )
                )
                notes.extend(source_notes)

            notes.sort(key=lambda note: note["onsetSeconds"])
            notes = _deduplicate_transcription_notes(notes)

            stem_separation_used = any(
                stem_source in ("bass", "other") for stem_source in stems_transcribed
            )
            note_cap = (
                FULL_MIX_TRANSCRIPTION_NOTE_CAP
                if full_mix_fallback
                else TRANSCRIPTION_NOTE_CAP
            )
            if len(notes) > note_cap:
                original_count = len(notes)
                ranked_notes = sorted(
                    notes,
                    key=lambda note: (
                        -float(note.get("confidence", 0.0)),
                        -float(note.get("durationSeconds", 0.0)),
                        float(note.get("onsetSeconds", 0.0)),
                    ),
                )
                notes = sorted(
                    ranked_notes[:note_cap],
                    key=lambda note: note["onsetSeconds"],
                )
                print(
                    f"[warn] transcriptionDetail: truncated to {note_cap} notes (was {original_count})",
                    file=sys.stderr,
                )

            if len(notes) == 0:
                return {
                    "transcriptionDetail": {
                        "transcriptionMethod": self.name,
                        "noteCount": 0,
                        "averageConfidence": 0.0,
                        "dominantPitches": [],
                        "pitchRange": {
                            "minMidi": None,
                            "maxMidi": None,
                            "minName": None,
                            "maxName": None,
                        },
                        "stemSeparationUsed": stem_separation_used,
                        "fullMixFallback": full_mix_fallback,
                        "stemsTranscribed": stems_transcribed,
                        "notes": [],
                    }
                }

            midi_values = [int(note["pitchMidi"]) for note in notes]
            confidence_values = [float(note["confidence"]) for note in notes]
            dominant_pitches = [
                {
                    "pitchMidi": int(pitch_midi),
                    "pitchName": midi_to_note_name(int(pitch_midi)),
                    "count": int(count),
                }
                for pitch_midi, count in Counter(midi_values).most_common(5)
            ]

            min_midi = int(min(midi_values))
            max_midi = int(max(midi_values))
            average_confidence = round(
                float(np.mean(np.asarray(confidence_values, dtype=np.float64))), 4
            )

            return {
                "transcriptionDetail": {
                    "transcriptionMethod": self.name,
                    "noteCount": int(len(notes)),
                    "averageConfidence": average_confidence,
                    "dominantPitches": dominant_pitches,
                    "pitchRange": {
                        "minMidi": min_midi,
                        "maxMidi": max_midi,
                        "minName": midi_to_note_name(min_midi),
                        "maxName": midi_to_note_name(max_midi),
                    },
                    "stemSeparationUsed": stem_separation_used,
                    "fullMixFallback": full_mix_fallback,
                    "stemsTranscribed": stems_transcribed,
                    "notes": notes,
                }
            }
        except Exception as e:
            print(f"[warn] Torchcrepe transcription failed: {e}", file=sys.stderr)
            return {"transcriptionDetail": None}


def analyze_transcription(
    audio_path: str,
    stem_paths: dict | None = None,
    backend: TranscriptionBackend | None = None,
    emit_progress_markers: bool = False,
) -> dict:
    """Run transcription via the specified backend (torchcrepe by default)."""
    def _invoke_backend(candidate: TranscriptionBackend) -> dict:
        try:
            return candidate.transcribe(
                audio_path,
                stem_paths,
                emit_progress_markers=emit_progress_markers,
            )
        except TypeError as exc:
            if "emit_progress_markers" not in str(exc):
                raise
            return candidate.transcribe(audio_path, stem_paths)

    if backend is None:
        requested_backend = str(
            os.getenv(TRANSCRIPTION_BACKEND_ENV, "auto")
        ).strip().lower()
        if requested_backend not in ("torchcrepe", "torchcrepe-viterbi", "auto", "", "default"):
            print(
                f"[warn] Unknown {TRANSCRIPTION_BACKEND_ENV}='{requested_backend}', defaulting to torchcrepe-viterbi",
                file=sys.stderr,
            )
        backend = TorchcrepeBackend()

    return _invoke_backend(backend)


# ── Main ───────────────────────────────────────────────────────────────────


def _run_symbolic_only(audio_path: str, stem_dir: str | None = None):
    """Run symbolic extraction only and print JSON to stdout.

    Used by server.py to run symbolic work in a subprocess so that
    Demucs/torchcrepe memory is freed when the process exits.

    If --stem-dir is provided, stems are read from that directory
    (bass.wav, other.wav, etc.) instead of running Demucs again.
    """
    stem_paths = None
    if stem_dir is not None and os.path.isdir(stem_dir):
        # Look for pre-separated stems
        for name in ("bass", "other", "drums", "vocals"):
            path = os.path.join(stem_dir, f"{name}.wav")
            if os.path.isfile(path):
                if stem_paths is None:
                    stem_paths = {}
                stem_paths[name] = path

    need_separation = stem_paths is None
    temp_dir = None

    if need_separation:
        temp_dir = tempfile.mkdtemp(prefix="asa_symbolic_stems_")
        separated = separate_stems(audio_path, output_dir=temp_dir)
        if isinstance(separated, dict) and separated:
            stem_paths = separated

    try:
        result = analyze_transcription(
            audio_path,
            stem_paths=stem_paths,
        )
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: ./venv/bin/python analyze.py <audio_file> [--separate] [--fast] [--standard] [--transcribe] [--yes] [--symbolic-only] [--stem-dir DIR]",
            file=sys.stderr,
        )
        sys.exit(1)

    audio_path = sys.argv[1]
    sample_rate = 44100
    optional_args = sys.argv[2:]
    run_separation = "--separate" in optional_args
    run_fast = "--fast" in optional_args
    run_standard = "--standard" in optional_args
    run_transcribe = "--transcribe" in optional_args
    auto_yes = "--yes" in optional_args
    symbolic_only = "--symbolic-only" in optional_args

    # --symbolic-only: run separation + transcription, print JSON, exit
    if symbolic_only:
        stem_dir = None
        if "--stem-dir" in optional_args:
            idx = optional_args.index("--stem-dir")
            if idx + 1 < len(optional_args):
                stem_dir = optional_args[idx + 1]
        _run_symbolic_only(audio_path, stem_dir=stem_dir)
        sys.exit(0)
    stems = None

    analysis_estimate = get_audio_duration_seconds(audio_path)
    if analysis_estimate is not None:
        estimate = build_analysis_estimate(
            analysis_estimate, run_separation, run_transcribe
        )
        if sys.stdin.isatty():
            print_analysis_estimate(audio_path, estimate)
        if should_prompt_for_confirmation(sys.stdin.isatty(), auto_yes):
            if not prompt_to_continue():
                print("Analysis cancelled.", file=sys.stderr)
                sys.exit(0)

    # Load audio
    print(f"Loading: {audio_path}", file=sys.stderr)

    try:
        mono = load_mono(audio_path, sample_rate)
    except Exception as e:
        print(f"Error loading mono audio: {e}", file=sys.stderr)
        sys.exit(1)

    if run_fast:
        if analyze_fast is None:
            print("Error: analyze_fast module not available.", file=sys.stderr)
            sys.exit(1)
        print("Running fast analysis...", file=sys.stderr)
        result = analyze_fast(mono, sample_rate)
        fast_stereo_detail = result.get("stereoDetail")
        fast_mono_compatible = (
            fast_stereo_detail.get("subBassMono")
            if isinstance(fast_stereo_detail, dict)
            else None
        )
        fast_plr = analyze_plr(result.get("lufsIntegrated"), result.get("truePeak")).get("plr")
        output = {
            "bpm": result.get("bpm"),
            "bpmConfidence": result.get("bpmConfidence"),
            "bpmPercival": result.get("bpmPercival"),
            "bpmAgreement": result.get("bpmAgreement"),
            "bpmDoubletime": result.get("bpmDoubletime"),
            "bpmSource": result.get("bpmSource"),
            "bpmRawOriginal": result.get("bpmRawOriginal"),
            "key": result.get("key"),
            "keyConfidence": result.get("keyConfidence"),
            "timeSignature": result.get("timeSignature"),
            "durationSeconds": result.get("durationSeconds"),
            "sampleRate": result.get("sampleRate"),
            "lufsIntegrated": result.get("lufsIntegrated"),
            "lufsRange": result.get("lufsRange"),
            "truePeak": result.get("truePeak"),
            "plr": fast_plr,
            "crestFactor": result.get("crestFactor"),
            "dynamicSpread": result.get("dynamicSpread"),
            "dynamicCharacter": result.get("dynamicCharacter"),
            "stereoDetail": result.get("stereoDetail"),
            "monoCompatible": fast_mono_compatible,
            "spectralBalance": result.get("spectralBalance"),
            "spectralDetail": result.get("spectralDetail"),
            "rhythmDetail": result.get("rhythmDetail"),
            "melodyDetail": result.get("melodyDetail"),
            "transcriptionDetail": result.get("transcriptionDetail"),
            "grooveDetail": result.get("grooveDetail"),
            "sidechainDetail": result.get("sidechainDetail"),
            "acidDetail": result.get("acidDetail"),
            "reverbDetail": result.get("reverbDetail"),
            "vocalDetail": result.get("vocalDetail"),
            "supersawDetail": result.get("supersawDetail"),
            "bassDetail": result.get("bassDetail"),
            "kickDetail": result.get("kickDetail"),
            "genreDetail": result.get("genreDetail"),
            "effectsDetail": result.get("effectsDetail"),
            "synthesisCharacter": result.get("synthesisCharacter"),
            "danceability": result.get("danceability"),
            "structure": result.get("structure"),
            "arrangementDetail": result.get("arrangementDetail"),
            "segmentLoudness": result.get("segmentLoudness"),
            "segmentSpectral": result.get("segmentSpectral"),
            "segmentStereo": result.get("segmentStereo"),
            "segmentKey": result.get("segmentKey"),
            "chordDetail": result.get("chordDetail"),
            "perceptual": result.get("perceptual"),
            "essentiaFeatures": result.get("essentiaFeatures"),
        }
        print("Done.", file=sys.stderr)
        print(json.dumps(output, indent=2))
        return

    try:
        stereo, sr, num_channels = load_stereo(audio_path)
    except Exception as e:
        print(
            f"[warn] Stereo loading failed, stereo features will be null: {e}",
            file=sys.stderr,
        )
        stereo = None

    if run_separation:
        print(
            "Running source separation (this may take 30-60 seconds)...",
            file=sys.stderr,
        )
        stems = separate_stems(audio_path)
        print("@@SEPARATION_COMPLETE", file=sys.stderr)

    # Run torchcrepe pitch extraction on separated stems (if available)
    if stems is not None:
        print("Running pitch extraction (torchcrepe)...", file=sys.stderr)
        pitch_result = analyze_crepe_pitch(stems)
        print("@@PITCH_EXTRACTION_COMPLETE", file=sys.stderr)
    else:
        pitch_result = {"pitchDetail": None}

    print("Analyzing...", file=sys.stderr)

    # Run RhythmExtractor2013 once, share across BPM / time sig / rhythm detail
    rhythm_data = extract_rhythm(mono)

    # Run all analyses — each is self-contained and error-safe
    result = {}

    result.update(analyze_bpm(rhythm_data, mono, sample_rate))
    result.update(analyze_key(mono))
    result.update(analyze_time_signature(rhythm_data))
    result.update(analyze_duration_and_sr(mono, sample_rate))

    # LUFS + LRA (needs stereo)
    if stereo is not None:
        result.update(analyze_loudness(stereo))
    else:
        result["lufsIntegrated"] = None
        result["lufsRange"] = None

    # True peak (needs stereo)
    if stereo is not None:
        result.update(analyze_true_peak(stereo))
    else:
        result["truePeak"] = None

    # Dynamics
    result.update(analyze_dynamics(mono, sample_rate))
    result.update(analyze_dynamic_character(mono, sample_rate))

    # Stereo analysis
    if stereo is not None:
        result.update(analyze_stereo(stereo, sample_rate))
    else:
        result["stereoDetail"] = {
            "stereoWidth": None,
            "stereoCorrelation": None,
            "subBassCorrelation": None,
            "subBassMono": None,
        }
    stereo_detail = result.get("stereoDetail")
    result["monoCompatible"] = (
        stereo_detail.get("subBassMono") if isinstance(stereo_detail, dict) else None
    )

    # Spectral detail (also computes EnergyBand values for spectral balance in the same loop)
    spectral_result = analyze_spectral_detail(
        mono, sample_rate, _balance_bands=SPECTRAL_BALANCE_BANDS
    )
    precomputed_balance = spectral_result.pop("_spectralBalanceBands", None)
    result.update(spectral_result)

    # Spectral balance (uses precomputed band energies — no redundant frame loop)
    result.update(
        analyze_spectral_balance(mono, sample_rate, precomputed_band_energies=precomputed_balance)
    )
    result.update(analyze_plr(result.get("lufsIntegrated"), result.get("truePeak")))

    # Rhythm detail
    result.update(analyze_rhythm_detail(rhythm_data))

    # Shared beat-domain loudness data used by groove + sidechain analyses.
    beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)

    # Groove detail (Tier 2 — always run)
    result.update(analyze_groove(mono, sample_rate, rhythm_data, beat_data))
    result.update(analyze_beats_loudness(mono, sample_rate, rhythm_data, beat_data))
    result.update(analyze_sidechain_detail(mono, sample_rate, rhythm_data, beat_data))

    # Genre detail (Tier 2 — derived from other results, nearly free)
    result.update(analyze_genre_detail(result))

    # Danceability (Tier 2 — single Essentia call, fast)
    result.update(analyze_danceability(mono, sample_rate))

    # Structure + arrangement (Tier 2)
    result.update(analyze_structure(mono, sample_rate))
    result.update(analyze_arrangement_detail(mono, sample_rate))

    if run_standard:
        # Standard mode: skip Tier 3 analyses (expensive or niche).
        result["melodyDetail"] = None
        result["acidDetail"] = None
        result["reverbDetail"] = None
        result["vocalDetail"] = None
        result["supersawDetail"] = None
        result["bassDetail"] = None
        result["kickDetail"] = None
        result["effectsDetail"] = None
        result["synthesisCharacter"] = None
        result["segmentLoudness"] = None
        result["segmentSpectral"] = None
        result["segmentStereo"] = None
        result["segmentKey"] = None
        result["chordDetail"] = None
        result["perceptual"] = None
        result["essentiaFeatures"] = None

        # Stereo array no longer needed — release memory.
        del stereo
        gc.collect()
    else:
        # Full mode: run all Tier 3 analyses.

        # Melody detail (expensive: PredominantPitchMelodia hop=128)
        result.update(analyze_melody(audio_path, sample_rate, rhythm_data, stems))

        # Detection detail
        result.update(analyze_acid_detail(mono, sample_rate, bpm=result.get("bpm")))
        result.update(analyze_reverb_detail(mono, sample_rate, bpm=result.get("bpm")))
        result.update(analyze_vocal_detail(mono, sample_rate, bpm=result.get("bpm")))
        result.update(analyze_supersaw_detail(mono, sample_rate, bpm=result.get("bpm")))
        result.update(analyze_bass_detail(mono, sample_rate, bpm=result.get("bpm")))
        result.update(analyze_kick_detail(mono, sample_rate, bpm=result.get("bpm")))
        result.update(
            analyze_effects_detail(
                mono,
                sample_rate,
                rhythm_data,
                lufs_integrated=result.get("lufsIntegrated"),
            )
        )

        # Synthesis character
        result.update(analyze_synthesis_character(mono, sample_rate))

        # Segment analyses (need stereo)
        result.update(analyze_segment_stereo(result.get("structure"), stereo, sample_rate))
        result.update(
            analyze_segment_loudness(result.get("structure"), stereo, sample_rate)
        )
        result.update(
            analyze_segment_spectral(
                result.get("structure"),
                mono,
                segment_stereo_data=result.get("segmentStereo"),
                sample_rate=sample_rate,
            )
        )
        result.update(analyze_segment_key(result.get("structure"), mono, sample_rate))

        # Stereo array no longer needed — release memory.
        del stereo
        gc.collect()

        # Chords
        result.update(analyze_chords(mono, sample_rate))

        # Perceptual
        result.update(analyze_perceptual(mono, sample_rate))

        # Essentia features
        result.update(analyze_essentia_features(mono, sample_rate))

    # Optional torchcrepe transcription pass
    if run_transcribe:
        transcription_stem_paths = None
        if stems is not None:
            transcription_stem_paths = {}
            for stem_name in ("bass", "other"):
                source_path = stems.get(stem_name)
                if isinstance(source_path, str) and os.path.isfile(source_path):
                    transcription_stem_paths[stem_name] = source_path
            if len(transcription_stem_paths) == 0:
                transcription_stem_paths = None
        transcription_mode = (
            "stems" if transcription_stem_paths is not None else "full_mix"
        )
        print(f"@@TRANSCRIPTION_START mode={transcription_mode}", file=sys.stderr)
        result.update(
            analyze_transcription(
                audio_path,
                stem_paths=transcription_stem_paths,
                emit_progress_markers=True,
            )
        )
        print(f"@@TRANSCRIPTION_COMPLETE mode={transcription_mode}", file=sys.stderr)
        gc.collect()
    else:
        result["transcriptionDetail"] = None

    # Merge pitch extraction results
    result.update(pitch_result)

    # Build final output in the exact requested key order
    output = {
        "bpm": result.get("bpm"),
        "bpmConfidence": result.get("bpmConfidence"),
        "bpmPercival": result.get("bpmPercival"),
        "bpmAgreement": result.get("bpmAgreement"),
        "bpmDoubletime": result.get("bpmDoubletime"),
        "bpmSource": result.get("bpmSource"),
        "bpmRawOriginal": result.get("bpmRawOriginal"),
        "key": result.get("key"),
        "keyConfidence": result.get("keyConfidence"),
        "keyProfile": result.get("keyProfile"),
        "tuningFrequency": result.get("tuningFrequency"),
        "tuningCents": result.get("tuningCents"),
        "timeSignature": result.get("timeSignature"),
        "durationSeconds": result.get("durationSeconds"),
        "sampleRate": result.get("sampleRate"),
        "lufsIntegrated": result.get("lufsIntegrated"),
        "lufsRange": result.get("lufsRange"),
        "lufsMomentaryMax": result.get("lufsMomentaryMax"),
        "lufsShortTermMax": result.get("lufsShortTermMax"),
        "truePeak": result.get("truePeak"),
        "plr": result.get("plr"),
        "crestFactor": result.get("crestFactor"),
        "dynamicSpread": result.get("dynamicSpread"),
        "dynamicCharacter": result.get("dynamicCharacter"),
        "stereoDetail": result.get("stereoDetail"),
        "monoCompatible": result.get("monoCompatible"),
        "spectralBalance": result.get("spectralBalance"),
        "spectralDetail": result.get("spectralDetail"),
        "rhythmDetail": result.get("rhythmDetail"),
        "melodyDetail": result.get("melodyDetail"),
        "transcriptionDetail": result.get("transcriptionDetail"),
        "pitchDetail": result.get("pitchDetail"),
        "grooveDetail": result.get("grooveDetail"),
        "beatsLoudness": result.get("beatsLoudness"),
        "sidechainDetail": result.get("sidechainDetail"),
        "acidDetail": result.get("acidDetail"),
        "reverbDetail": result.get("reverbDetail"),
        "vocalDetail": result.get("vocalDetail"),
        "supersawDetail": result.get("supersawDetail"),
        "bassDetail": result.get("bassDetail"),
        "kickDetail": result.get("kickDetail"),
        "genreDetail": result.get("genreDetail"),
        "effectsDetail": result.get("effectsDetail"),
        "synthesisCharacter": result.get("synthesisCharacter"),
        "danceability": result.get("danceability"),
        "structure": result.get("structure"),
        "arrangementDetail": result.get("arrangementDetail"),
        "segmentLoudness": result.get("segmentLoudness"),
        "segmentSpectral": result.get("segmentSpectral"),
        "segmentStereo": result.get("segmentStereo"),
        "segmentKey": result.get("segmentKey"),
        "chordDetail": result.get("chordDetail"),
        "perceptual": result.get("perceptual"),
        "essentiaFeatures": result.get("essentiaFeatures"),
    }

    print("Done.", file=sys.stderr)
    print(json.dumps(output, indent=2))

    if run_separation and stems is not None:
        cleanup_stems(stems)


if __name__ == "__main__":
    main()
