"""Audio loading, stem separation, and pitch extraction utilities."""

import gc
import os
import shutil
import sys
import tempfile
import wave

import numpy as np

try:
    import essentia.standard as es
except ImportError:
    es = None


def load_mono(path: str, sample_rate: int = 44100) -> np.ndarray:
    """Load audio as mono via MonoLoader."""
    loader = es.MonoLoader(filename=path, sampleRate=sample_rate)
    return loader()


def load_stereo(path: str):
    """Load audio with AudioLoader to preserve stereo channels."""
    loader = es.AudioLoader(filename=path)
    audio, sr, num_channels, md5, bit_rate, codec = loader()
    return audio, sr, num_channels


def _load_stem_mono(
    stems: dict | None,
    stem_name: str,
    sample_rate: int = 44100,
) -> np.ndarray | None:
    """Load a preferred stem as mono when it exists."""
    if not isinstance(stems, dict):
        return None

    stem_path = stems.get(stem_name)
    if not isinstance(stem_path, str) or not os.path.isfile(stem_path):
        return None

    try:
        return load_mono(stem_path, sample_rate=sample_rate)
    except Exception:
        return None


def _load_stem_stereo(
    stems: dict | None,
    stem_name: str,
) -> np.ndarray | None:
    """Load a Demucs-produced stem as a (N, 2) stereo array.

    Demucs writes stems as 44.1 kHz stereo PCM16 WAV via `_write_wav_pcm16`
    above. The stereo path is what `analyze_loudness` (LoudnessEBUR128) and
    `analyze_stereo` consume. Returns None when the stem is missing or
    unreadable.
    """
    if not isinstance(stems, dict):
        return None

    stem_path = stems.get(stem_name)
    if not isinstance(stem_path, str) or not os.path.isfile(stem_path):
        return None

    try:
        audio, _sr, _channels = load_stereo(stem_path)
        if audio is None:
            return None
        return audio
    except Exception:
        return None


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
