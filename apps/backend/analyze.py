#!/usr/bin/env python3
"""
analyze.py — DSP accuracy testing tool.

Takes an audio file, runs it through Essentia's algorithms,
and prints a clean JSON result to stdout.

Usage:
    ./venv/bin/python analyze.py "path/to/track.mp3" [--separate] [--fast] [--transcribe] [--yes]
"""

import json
import math
import os
import shutil
import sys
import tempfile
import warnings
import wave
import contextlib
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


def separate_stems(audio_path: str, output_dir: str | None = None):
    """Run Demucs separation and return written source stem paths."""
    try:
        import torch
        from demucs.apply import apply_model
        from demucs.audio import AudioFile
        from demucs.pretrained import get_model
    except Exception:
        return None

    temp_dir_created = False
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="sonic_analyzer_demucs_")
        temp_dir_created = True
    else:
        os.makedirs(output_dir, exist_ok=True)

    try:
        model = get_model("htdemucs")
        model.eval()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)

        mix_np = AudioFile(audio_path).read(
            streams=0,
            samplerate=model.samplerate,
            channels=model.audio_channels,
        )
        mix = torch.tensor(mix_np, dtype=torch.float32, device=device)
        if mix.dim() == 1:
            mix = mix.unsqueeze(0)

        sources = apply_model(
            model,
            mix.unsqueeze(0),
            device=device,
            split=True,
            progress=False,
        )[0]

        source_names = list(model.sources)
        if len(source_names) == 0:
            raise RuntimeError("Demucs output does not contain any sources")

        stem_paths = {}
        for idx, source_name in enumerate(source_names):
            stem_audio = sources[idx].detach().cpu().numpy()
            stem_path = os.path.join(output_dir, f"{source_name}.wav")
            _write_wav_pcm16(stem_path, stem_audio, int(model.samplerate))
            stem_paths[source_name] = stem_path

        return stem_paths if len(stem_paths) > 0 else None
    except Exception:
        if temp_dir_created:
            shutil.rmtree(output_dir, ignore_errors=True)
        return None


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
            "Basic Pitch on bass + other stems"
            if run_separation
            else "Basic Pitch on full mix"
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

        return {
            "bpm": bpm,
            "bpmConfidence": bpm_confidence,
            "bpmPercival": bpm_percival,
            "bpmAgreement": bpm_agreement,
        }
    except Exception as e:
        print(f"[warn] BPM extraction failed: {e}", file=sys.stderr)
        return {
            "bpm": None,
            "bpmConfidence": None,
            "bpmPercival": None,
            "bpmAgreement": None,
        }


def analyze_key(mono: np.ndarray) -> dict:
    """Extract musical key and confidence using KeyExtractor."""
    try:
        extractor = es.KeyExtractor(profileType="temperley")
        key, scale, strength = extractor(mono)
        key_str = f"{key} {scale.capitalize()}"
        return {"key": key_str, "keyConfidence": round(float(strength), 2)}
    except Exception as e:
        print(f"[warn] Key extraction failed: {e}", file=sys.stderr)
        return {"key": None, "keyConfidence": None}


def analyze_loudness(stereo: np.ndarray) -> dict:
    """LUFS integrated loudness and loudness range via LoudnessEBUR128."""
    try:
        loudness = es.LoudnessEBUR128()
        momentary, short_term, integrated, loudness_range = loudness(stereo)
        return {
            "lufsIntegrated": round(float(integrated), 1),
            "lufsRange": round(float(loudness_range), 1),
        }
    except Exception as e:
        print(f"[warn] LUFS extraction failed: {e}", file=sys.stderr)
        return {"lufsIntegrated": None, "lufsRange": None}


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
                energy_band = es.EnergyBand(
                    startCutoffFrequency=lo,
                    stopCutoffFrequency=hi,
                    sampleRate=sample_rate,
                )
                energy = energy_band(spec)
                band_energies[name].append(float(energy))

        result = {}
        for name, energies in band_energies.items():
            mean_energy = np.mean(energies) if energies else 0.0
            db = 10 * np.log10(mean_energy) if mean_energy > 0 else -100.0
            result[name] = round(float(db), 1)

        return {"spectralBalance": result}
    except Exception as e:
        print(f"[warn] Spectral balance analysis failed: {e}", file=sys.stderr)
        return {"spectralBalance": None}


def analyze_spectral_detail(mono: np.ndarray, sample_rate: int = 44100) -> dict:
    """Frame-by-frame SpectralCentroid, SpectralRolloff, MFCC, and HPCP (Chroma)."""
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

        return {
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

        ticks = rhythm_data["ticks"]

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

        # Beat positions (first 16)
        beat_positions = [round(float(t), 3) for t in ticks[:16]]

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

        return {
            "rhythmDetail": {
                "onsetRate": round(onset_rate, 2),
                "beatPositions": beat_positions,
                "grooveAmount": round(groove, 4),
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

        return {
            "sidechainDetail": {
                "pumpingStrength": round(pumping_strength, 4),
                "pumpingRegularity": round(
                    float(np.clip(pumping_regularity, 0.0, 1.0)), 4
                ),
                "pumpingRate": pumping_rate,
                "pumpingConfidence": round(pumping_confidence, 4),
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

        key_extractor = es.KeyExtractor(profileType="temperley")
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


def _extract_basic_pitch_notes(
    source_path: str,
    stem_source: str,
    predict,
    model_path,
) -> tuple[list[dict], list[int], list[float]]:
    with contextlib.redirect_stdout(sys.stderr):
        _model_output, _midi_data, raw_note_events = predict(source_path, model_path)

    notes = []
    midi_values = []
    confidence_values = []

    for raw_event in raw_note_events or []:
        pitch_raw = None
        onset_raw = None
        duration_raw = None
        end_raw = None
        confidence_raw = None

        if isinstance(raw_event, dict):
            pitch_raw = raw_event.get(
                "pitchMidi",
                raw_event.get(
                    "pitch_midi",
                    raw_event.get(
                        "pitch", raw_event.get("midi", raw_event.get("note"))
                    ),
                ),
            )
            onset_raw = raw_event.get(
                "onsetSeconds",
                raw_event.get(
                    "onset_seconds",
                    raw_event.get(
                        "onset",
                        raw_event.get(
                            "startSeconds",
                            raw_event.get("start_seconds", raw_event.get("start")),
                        ),
                    ),
                ),
            )
            duration_raw = raw_event.get(
                "durationSeconds",
                raw_event.get("duration_seconds", raw_event.get("duration")),
            )
            end_raw = raw_event.get(
                "offsetSeconds",
                raw_event.get(
                    "offset_seconds",
                    raw_event.get(
                        "offset",
                        raw_event.get(
                            "endSeconds",
                            raw_event.get("end_seconds", raw_event.get("end")),
                        ),
                    ),
                ),
            )
            confidence_raw = raw_event.get(
                "confidence",
                raw_event.get(
                    "amplitude", raw_event.get("velocity", raw_event.get("probability"))
                ),
            )
        elif isinstance(raw_event, (tuple, list)):
            if len(raw_event) >= 3:
                onset_raw = raw_event[0]
                duration_raw = raw_event[1]
                pitch_raw = raw_event[2]
            if len(raw_event) >= 4:
                confidence_raw = raw_event[3]
        else:
            pitch_raw = getattr(raw_event, "pitchMidi", None)
            if pitch_raw is None:
                pitch_raw = getattr(raw_event, "pitch_midi", None)
            if pitch_raw is None:
                pitch_raw = getattr(raw_event, "pitch", None)
            onset_raw = (
                getattr(raw_event, "onsetSeconds", None)
                or getattr(raw_event, "onset_seconds", None)
                or getattr(raw_event, "onset", None)
                or getattr(raw_event, "start", None)
            )
            duration_raw = (
                getattr(raw_event, "durationSeconds", None)
                or getattr(raw_event, "duration_seconds", None)
                or getattr(raw_event, "duration", None)
            )
            end_raw = (
                getattr(raw_event, "offsetSeconds", None)
                or getattr(raw_event, "offset_seconds", None)
                or getattr(raw_event, "offset", None)
                or getattr(raw_event, "end", None)
            )
            confidence_raw = (
                getattr(raw_event, "confidence", None)
                or getattr(raw_event, "amplitude", None)
                or getattr(raw_event, "velocity", None)
            )

        onset_seconds = _to_finite_float(onset_raw, None)
        second_value = _to_finite_float(duration_raw, None)
        duration_seconds = None
        if onset_seconds is not None and second_value is not None:
            duration_seconds = (
                second_value - onset_seconds
                if second_value >= onset_seconds
                else second_value
            )
        if (
            (duration_seconds is None or duration_seconds <= 0)
            and onset_seconds is not None
            and end_raw is not None
        ):
            end_seconds = _to_finite_float(end_raw, None)
            if end_seconds is not None:
                duration_seconds = end_seconds - onset_seconds

        pitch_midi = _to_finite_float(pitch_raw, None)
        if pitch_midi is None or onset_seconds is None or duration_seconds is None:
            continue
        if onset_seconds < 0 or duration_seconds <= 0:
            continue

        pitch_midi_int = int(np.clip(int(round(pitch_midi)), 0, 127))
        confidence = _normalize_confidence(confidence_raw)

        note_obj = {
            "pitchMidi": pitch_midi_int,
            "pitchName": midi_to_note_name(pitch_midi_int),
            "onsetSeconds": round(float(onset_seconds), 4),
            "durationSeconds": round(float(duration_seconds), 4),
            "confidence": confidence,
            "stemSource": stem_source,
        }
        notes.append(note_obj)
        midi_values.append(pitch_midi_int)
        confidence_values.append(confidence)

    return notes, midi_values, confidence_values


def analyze_transcription_basic_pitch(
    audio_path: str, stem_paths: dict | None = None
) -> dict:
    try:
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH
    except Exception as e:
        print(f"[warn] Basic Pitch import failed: {e}", file=sys.stderr)
        return {"transcriptionDetail": None}

    try:
        transcription_sources = _transcription_source_paths(audio_path, stem_paths)
        notes = []
        midi_values = []
        confidence_values = []
        stems_transcribed = [
            stem_source for stem_source, _source_path in transcription_sources
        ]

        for stem_source, source_path in transcription_sources:
            source_notes, source_midi_values, source_confidence_values = (
                _extract_basic_pitch_notes(
                    source_path,
                    stem_source,
                    predict,
                    ICASSP_2022_MODEL_PATH,
                )
            )
            notes.extend(source_notes)
            midi_values.extend(source_midi_values)
            confidence_values.extend(source_confidence_values)

        notes.sort(key=lambda note: note["onsetSeconds"])
        stem_separation_used = any(
            stem_source in ("bass", "other") for stem_source in stems_transcribed
        )

        if len(notes) == 0:
            return {
                "transcriptionDetail": {
                    "transcriptionMethod": "basic-pitch",
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
                    "stemsTranscribed": stems_transcribed,
                    "notes": [],
                }
            }

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
                "transcriptionMethod": "basic-pitch",
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
                "stemsTranscribed": stems_transcribed,
                "notes": notes,
            }
        }
    except Exception as e:
        print(f"[warn] Basic Pitch transcription failed: {e}", file=sys.stderr)
        return {"transcriptionDetail": None}


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: ./venv/bin/python analyze.py <audio_file> [--separate] [--fast] [--transcribe] [--yes]",
            file=sys.stderr,
        )
        sys.exit(1)

    audio_path = sys.argv[1]
    sample_rate = 44100
    optional_args = sys.argv[2:]
    run_separation = "--separate" in optional_args
    run_fast = "--fast" in optional_args
    run_transcribe = "--transcribe" in optional_args
    auto_yes = "--yes" in optional_args
    # TODO: When enabled, use hopSize=4096 for frame-based algorithms except BPM/key.
    _ = run_fast
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

    # Spectral balance
    result.update(analyze_spectral_balance(mono, sample_rate))

    # Spectral detail
    result.update(analyze_spectral_detail(mono, sample_rate))

    # Rhythm detail
    result.update(analyze_rhythm_detail(rhythm_data))

    # Shared beat-domain loudness data used by groove + sidechain analyses.
    beat_data = _extract_beat_loudness_data(mono, sample_rate, rhythm_data)

    # Melody detail
    result.update(analyze_melody(audio_path, sample_rate, rhythm_data, stems))

    # Groove detail
    result.update(analyze_groove(mono, sample_rate, rhythm_data, beat_data))
    result.update(analyze_sidechain_detail(mono, sample_rate, rhythm_data, beat_data))
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

    # Danceability
    result.update(analyze_danceability(mono, sample_rate))

    # Structure
    result.update(analyze_structure(mono, sample_rate))
    result.update(analyze_arrangement_detail(mono, sample_rate))
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

    # Chords
    result.update(analyze_chords(mono, sample_rate))

    # Perceptual
    result.update(analyze_perceptual(mono, sample_rate))

    # Essentia features
    result.update(analyze_essentia_features(mono))

    # Optional Basic Pitch transcription pass
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
        result.update(
            analyze_transcription_basic_pitch(
                audio_path, stem_paths=transcription_stem_paths
            )
        )
    else:
        result["transcriptionDetail"] = None

    # Build final output in the exact requested key order
    output = {
        "bpm": result.get("bpm"),
        "bpmConfidence": result.get("bpmConfidence"),
        "bpmPercival": result.get("bpmPercival"),
        "bpmAgreement": result.get("bpmAgreement"),
        "key": result.get("key"),
        "keyConfidence": result.get("keyConfidence"),
        "timeSignature": result.get("timeSignature"),
        "durationSeconds": result.get("durationSeconds"),
        "sampleRate": result.get("sampleRate"),
        "lufsIntegrated": result.get("lufsIntegrated"),
        "lufsRange": result.get("lufsRange"),
        "truePeak": result.get("truePeak"),
        "crestFactor": result.get("crestFactor"),
        "dynamicSpread": result.get("dynamicSpread"),
        "dynamicCharacter": result.get("dynamicCharacter"),
        "stereoDetail": result.get("stereoDetail"),
        "spectralBalance": result.get("spectralBalance"),
        "spectralDetail": result.get("spectralDetail"),
        "rhythmDetail": result.get("rhythmDetail"),
        "melodyDetail": result.get("melodyDetail"),
        "transcriptionDetail": result.get("transcriptionDetail"),
        "grooveDetail": result.get("grooveDetail"),
        "sidechainDetail": result.get("sidechainDetail"),
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
