#!/usr/bin/env python3
"""MSST separation runner — RUNS UNDER THE MSST VENV, not ASA's product venv.

This standalone script is invoked as a subprocess by
``apps/backend/separation_backend.py`` using the ``ASA_MSST_PYTHON`` interpreter.
It drives `SUC-DriverOld/MSST-WebUI <https://github.com/SUC-DriverOld/MSST-WebUI>`_'s
``MSSeparator`` (no PySide6 GUI) and writes canonical ``vocals/bass/drums/other``
stems as 44.1 kHz PCM16 WAVs into ``--output-dir``.

It imports ONLY MSST + numpy/soundfile/librosa/yaml (all present in the MSST
venv) — never ASA product modules (no essentia/torch-2.10 dependency), so the
two venvs stay fully isolated.

Contract (load-bearing): the **only** thing written to stdout is a single line of
JSON: ``{"stems": {name: path}, "modelType": str, "loadSeconds": float,
"inferSeconds": float, "device": str}``. Every MSST progress bar / log line is
forced to stderr (the caller captures both streams; stdout must stay pure JSON).
A non-zero exit + stderr message signals failure, on which the caller falls back
to Demucs.

Usage::

    $ASA_MSST_PYTHON scripts/msst_separate_runner.py \\
        --input track.flac --output-dir /tmp/stems \\
        --msst-root /path/to/MSST-WebUI \\
        --model-type scnet --config <cfg.yaml> --checkpoint <model.ckpt> \\
        [--device auto]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
import wave

import numpy as np

# Canonical ASA stem names + MSST aliases. Mapping is BY NAME (case-insensitive),
# never positional — MSST stem order varies by model (SCNet emits
# [drums, bass, other, vocals]).
_CANONICAL_STEMS = {"vocals", "bass", "drums", "other"}
_STEM_ALIASES = {"instrumental": "other", "instrum": "other"}

_TARGET_SAMPLE_RATE_FALLBACK = 44100


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _read_target_sample_rate(config_path: str) -> int:
    """Best-effort read of ``audio.sample_rate`` from the MSST config YAML.

    MSST configs can carry ``!!python/tuple`` tags that ``yaml.safe_load``
    rejects, so fall back to a line regex before defaulting to 44.1 kHz.
    """
    try:
        with open(config_path, "r") as handle:
            text = handle.read()
        try:
            import yaml

            config = yaml.safe_load(text)
            audio = (config or {}).get("audio", {}) if isinstance(config, dict) else {}
            sr = audio.get("sample_rate")
            if isinstance(sr, int) and sr > 0:
                return sr
        except Exception:  # noqa: BLE001 - tagged YAML; fall back to a line regex
            import re

            match = re.search(r"^\s*sample_rate:\s*(\d+)", text, re.MULTILINE)
            if match:
                return int(match.group(1))
    except Exception as exc:  # noqa: BLE001
        _eprint(f"[msst] could not read sample_rate from config ({exc}); using 44100.")
    return _TARGET_SAMPLE_RATE_FALLBACK


def _load_mix(input_path: str, target_sr: int) -> np.ndarray:
    """Load audio as channels-first stereo ``(2, N)`` float32 at ``target_sr``."""
    import soundfile as sf

    data, file_sr = sf.read(input_path, always_2d=True, dtype="float32")  # (N, C)
    mix = data.T  # (C, N)
    if mix.shape[0] == 1:
        mix = np.vstack([mix, mix])  # mono -> stereo
    elif mix.shape[0] > 2:
        mix = mix[:2]  # defensively clamp to stereo

    if file_sr != target_sr:
        import librosa

        # Resample per channel — librosa's `axis` kwarg is not reliable across the
        # 0.9.x line MSST pins, but 1-D resample works on every version.
        channels = [
            librosa.resample(np.ascontiguousarray(ch), orig_sr=file_sr, target_sr=target_sr)
            for ch in mix
        ]
        mix = np.stack(channels, axis=0)
    return np.ascontiguousarray(mix, dtype=np.float32)


def _write_wav_pcm16(path: str, audio: np.ndarray, sample_rate: int) -> None:
    """Write a channels-first ``(C, N)`` float waveform to PCM16 WAV.

    Matches ``analyze_audio_io._write_wav_pcm16`` encoding so the stems are
    byte-compatible with the Demucs path (44.1 kHz stereo PCM16).
    """
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 1:
        data = data[np.newaxis, :]
    data = np.clip(data, -1.0, 1.0)
    interleaved = (data.T * 32767.0).astype(np.int16)  # (N, C)
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(interleaved.shape[1] if interleaved.ndim == 2 else 1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(interleaved.tobytes())


def _canonical_name(stem_key: str) -> str | None:
    """Map an MSST stem key to a canonical ASA stem name, or None to skip."""
    key = str(stem_key).strip().lower()
    key = _STEM_ALIASES.get(key, key)
    return key if key in _CANONICAL_STEMS else None


def _to_channels_first(stem: np.ndarray) -> np.ndarray:
    """Coerce an MSST stem ``(N, C)`` (channels-last) to ``(C, N)``."""
    arr = np.asarray(stem, dtype=np.float32)
    if arr.ndim == 1:
        return arr[np.newaxis, :]
    # MSSeparator.separate returns channels-last (N, C); pick the channel axis as
    # the smaller dimension to be robust to either orientation.
    if arr.shape[0] <= arr.shape[1]:
        return arr  # already (C, N)
    return arr.T


def main() -> int:
    parser = argparse.ArgumentParser(description="MSST separation runner (MSST venv)")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--msst-root", required=True)
    parser.add_argument("--model-type", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    # Resolve every caller-supplied path to absolute BEFORE we chdir below, so
    # they stay valid once cwd moves into the MSST checkout.
    args.input = os.path.abspath(args.input)
    args.output_dir = os.path.abspath(args.output_dir)
    args.config = os.path.abspath(args.config)
    args.checkpoint = os.path.abspath(args.checkpoint)

    # Append (not prepend) the MSST checkout so its top-level ``utils`` /
    # ``inference`` packages don't shadow anything in this process unexpectedly.
    if args.msst_root not in sys.path:
        sys.path.append(args.msst_root)

    # MSST reads some of its own files via paths RELATIVE to the checkout root
    # (e.g. utils.constant loads ``data_backup/webui_config.json`` at import
    # time), so the import fails unless cwd is the checkout. Run from there; the
    # caller paths were just made absolute, so they survive the chdir.
    try:
        os.chdir(args.msst_root)
    except OSError as exc:
        _eprint(f"[msst] could not chdir to msst-root {args.msst_root} ({exc}).")
        return 2

    os.makedirs(args.output_dir, exist_ok=True)
    target_sr = _read_target_sample_rate(args.config)

    # Force every MSST print()/tqdm/log onto stderr — stdout is the JSON contract.
    with contextlib.redirect_stdout(sys.stderr):
        try:
            from inference.msst_infer import MSSeparator
        except Exception as exc:  # noqa: BLE001
            _eprint(f"[msst] could not import MSSeparator from {args.msst_root} ({exc}).")
            return 2

        separator = None
        try:
            load_start = time.perf_counter()
            separator = MSSeparator(
                model_type=args.model_type,
                config_path=args.config,
                model_path=args.checkpoint,
                device=args.device,
                output_format="wav",
                store_dirs="",  # we write stems ourselves; don't let MSST emit files
                # No custom logger: MSSeparator builds its own via MSST's
                # utils.logger.get_logger() (it relies on a non-stdlib
                # ``console_handler`` attribute). Its handler targets stderr and
                # the redirect_stdout above catches any stray stdout, so the
                # stdout JSON contract stays clean.
            )
            load_seconds = time.perf_counter() - load_start

            mix = _load_mix(args.input, target_sr)

            infer_start = time.perf_counter()
            separated = separator.separate(mix)  # {stem: ndarray (N, C)}
            infer_seconds = time.perf_counter() - infer_start
        except Exception as exc:  # noqa: BLE001
            _eprint(f"[msst] separation failed ({exc}).")
            return 3
        finally:
            if separator is not None:
                with contextlib.suppress(Exception):
                    separator.del_cache()

        if not isinstance(separated, dict) or not separated:
            _eprint("[msst] separator returned no stems.")
            return 4

        device = getattr(separator, "device", args.device)
        stems: dict[str, str] = {}
        for raw_name, stem_audio in separated.items():
            canonical = _canonical_name(raw_name)
            if canonical is None:
                _eprint(f"[msst] skipping unrecognized stem '{raw_name}'.")
                continue
            out_path = os.path.join(args.output_dir, f"{canonical}.wav")
            _write_wav_pcm16(out_path, _to_channels_first(stem_audio), target_sr)
            stems[canonical] = out_path

    if not stems:
        _eprint("[msst] no canonical stems written.")
        return 5

    manifest = {
        "stems": stems,
        "modelType": args.model_type,
        "loadSeconds": round(load_seconds, 3),
        "inferSeconds": round(infer_seconds, 3),
        "device": str(device),
    }
    json.dump(manifest, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
