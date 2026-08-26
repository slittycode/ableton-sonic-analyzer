#!/usr/bin/env python3
"""Offline Demucs vs RoFormer stem probe — research only.

Does not change product separation defaults. Writes per-backend stem folders
and a manifest for ear A/B. See docs/SEPARATION_ROFORMER_PROBE.md.

Usage (from apps/backend):

  # Product venv has Demucs; put RoFormer CLIs on PATH from a separate eval venv
  export PATH="/tmp/asa-roformer-eval/bin:$PATH"
  ./venv/bin/python scripts/probe_roformer_separation.py /path/to/track.wav \\
    --backends demucs,bs_roformer,melband_vocals \\
    --out .runtime/separation_probe

Backends:
  demucs          — ASA Hybrid Demucs (analyze_audio_io.separate_stems)
  bs_roformer     — bs-roformer-infer CLI (multi-stem default model)
  melband_vocals  — melband-roformer-infer CLI (Kim vocals default)
  audio_separator — audio-separator CLI (optional; default BS-RoFormer Viperx-ish)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


REPO_BACKEND = Path(__file__).resolve().parents[1]
if str(REPO_BACKEND) not in sys.path:
    sys.path.insert(0, str(REPO_BACKEND))


def _which(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print(f"[probe] $ {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None)


def _copy_wavs(src_dir: Path, dest_dir: Path) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for path in sorted(src_dir.rglob("*")):
        if path.suffix.lower() not in {".wav", ".flac", ".mp3", ".ogg"}:
            continue
        if not path.is_file():
            continue
        target = dest_dir / path.name
        # Avoid collisions if nested
        if target.exists():
            target = dest_dir / f"{path.parent.name}_{path.name}"
        shutil.copy2(path, target)
        written.append(target.name)
    return written


def run_demucs(audio: Path, out_dir: Path) -> dict:
    from analyze_audio_io import separate_stems

    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    stems = separate_stems(str(audio), output_dir=str(out_dir))
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    if not stems:
        return {
            "ok": False,
            "error": "separate_stems returned None (torchaudio/Demucs unavailable?)",
            "elapsedMs": elapsed_ms,
            "files": [],
        }
    # separate_stems already writes into out_dir
    files = sorted(Path(p).name for p in stems.values())
    return {
        "ok": True,
        "elapsedMs": elapsed_ms,
        "files": files,
        "stemMap": {k: Path(v).name for k, v in stems.items()},
        "note": "ASA product Hybrid Demucs (HDEMUCS_HIGH_MUSDB_PLUS)",
    }


def run_bs_roformer(audio: Path, out_dir: Path) -> dict:
    cli = _which("bs-roformer-infer")
    if not cli:
        return {
            "ok": False,
            "error": "bs-roformer-infer not on PATH (pip install bs-roformer-infer in eval venv)",
            "files": [],
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    # CLI expects a folder of inputs; stage single file
    stage = out_dir / "_input"
    stage.mkdir(parents=True, exist_ok=True)
    staged = stage / audio.name
    if not staged.exists():
        shutil.copy2(audio, staged)
    store = out_dir / "_raw"
    store.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        _run(
            [
                cli,
                "--input_folder",
                str(stage),
                "--store_dir",
                str(store),
            ]
        )
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": f"bs-roformer-infer failed: {exc}",
            "elapsedMs": round((time.perf_counter() - started) * 1000.0, 1),
            "files": [],
        }
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    files = _copy_wavs(store, out_dir)
    return {
        "ok": bool(files),
        "elapsedMs": elapsed_ms,
        "files": files,
        "note": "default multi-stem BS-RoFormer-SW (see bs-roformer-download --list-models)",
    }


def run_melband_vocals(audio: Path, out_dir: Path) -> dict:
    cli = _which("melband-roformer-infer")
    if not cli:
        return {
            "ok": False,
            "error": "melband-roformer-infer not on PATH (pip install melband-roformer-infer in eval venv)",
            "files": [],
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = out_dir / "_input"
    stage.mkdir(parents=True, exist_ok=True)
    staged = stage / audio.name
    if not staged.exists():
        shutil.copy2(audio, staged)
    store = out_dir / "_raw"
    store.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        _run(
            [
                cli,
                "--input_folder",
                str(stage),
                "--store_dir",
                str(store),
            ]
        )
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": f"melband-roformer-infer failed: {exc}",
            "elapsedMs": round((time.perf_counter() - started) * 1000.0, 1),
            "files": [],
        }
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    files = _copy_wavs(store, out_dir)
    return {
        "ok": bool(files),
        "elapsedMs": elapsed_ms,
        "files": files,
        "note": "default MelBand Kim vocals (+ residual). Best first bet for ASA vocal isolation pain.",
    }


def run_audio_separator(audio: Path, out_dir: Path, model: str | None) -> dict:
    cli = _which("audio-separator")
    if not cli:
        return {
            "ok": False,
            "error": "audio-separator not on PATH (optional: pip install 'audio-separator[cpu]')",
            "files": [],
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    # Default model is a strong BS-RoFormer vocals pair in recent audio-separator
    model_filename = model or "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
    started = time.perf_counter()
    try:
        _run(
            [
                cli,
                str(audio),
                "--model_filename",
                model_filename,
                "--output_dir",
                str(out_dir),
                "--output_format",
                "WAV",
                "--use_soundfile",
            ]
        )
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": f"audio-separator failed: {exc}",
            "elapsedMs": round((time.perf_counter() - started) * 1000.0, 1),
            "files": [],
            "model": model_filename,
        }
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    files = [p.name for p in sorted(out_dir.glob("*")) if p.is_file() and p.suffix.lower() == ".wav"]
    return {
        "ok": bool(files),
        "elapsedMs": elapsed_ms,
        "files": files,
        "model": model_filename,
        "note": "audio-separator model zoo; try MelBand Kim via --audio-separator-model vocals_mel_band_roformer.ckpt",
    }


BACKENDS = {
    "demucs": lambda audio, out, args: run_demucs(audio, out),
    "bs_roformer": lambda audio, out, args: run_bs_roformer(audio, out),
    "melband_vocals": lambda audio, out, args: run_melband_vocals(audio, out),
    "audio_separator": lambda audio, out, args: run_audio_separator(
        audio, out, args.audio_separator_model
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="Input audio file")
    parser.add_argument(
        "--backends",
        default="demucs,bs_roformer,melband_vocals",
        help=f"Comma-separated: {','.join(BACKENDS)}",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_BACKEND / ".runtime" / "separation_probe",
        help="Output root (default: apps/backend/.runtime/separation_probe)",
    )
    parser.add_argument(
        "--audio-separator-model",
        default=None,
        help="Optional audio-separator --model_filename override",
    )
    args = parser.parse_args()

    audio = args.audio.expanduser().resolve()
    if not audio.is_file():
        print(f"error: audio not found: {audio}", file=sys.stderr)
        return 2

    track_key = audio.stem.replace(" ", "_")[:80]
    root = args.out.expanduser().resolve() / track_key
    root.mkdir(parents=True, exist_ok=True)

    wanted = [b.strip() for b in args.backends.split(",") if b.strip()]
    unknown = [b for b in wanted if b not in BACKENDS]
    if unknown:
        print(f"error: unknown backends {unknown}; choose from {list(BACKENDS)}", file=sys.stderr)
        return 2

    results: dict[str, dict] = {}
    for name in wanted:
        backend_dir = root / name
        print(f"[probe] === {name} → {backend_dir}", file=sys.stderr)
        try:
            results[name] = BACKENDS[name](audio, backend_dir, args)
        except Exception as exc:  # noqa: BLE001 — research probe; surface full error
            results[name] = {"ok": False, "error": str(exc), "files": []}
        status = "ok" if results[name].get("ok") else f"FAIL: {results[name].get('error')}"
        print(f"[probe] {name}: {status}", file=sys.stderr)

    manifest = {
        "audio": str(audio),
        "trackKey": track_key,
        "outDir": str(root),
        "backends": results,
        "listenChecklist": [
            "Vocal track: solo demucs/vocals vs melband_vocals/*vocals* — bleed?",
            "Vocal track: demucs/other still has lead?",
            "Instrumental: demucs/vocals ghost energy vs melband residual?",
            "Multi-stem: bs_roformer drums/bass vs demucs kick/bass definition?",
            "Would vocalDetail.hasVocals / confidence change if we swapped vocals stem only?",
        ],
        "productDefault": "demucs (analyze_audio_io.separate_stems) — do not flip without corpus evidence",
        "docs": "docs/SEPARATION_ROFORMER_PROBE.md",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "ok": all(r.get("ok") for r in results.values())}, indent=2))
    # Non-zero if any requested backend failed (so scripts can detect missing CLIs)
    return 0 if any(r.get("ok") for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
