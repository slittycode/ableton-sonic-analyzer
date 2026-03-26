from __future__ import annotations

import gc
import json
import os
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from analyze import BasicPitchBackend, TorchcrepeBackend, analyze_transcription, separate_stems


def _emit_progress(step_key: str, message: str, fraction: float | None = None) -> None:
    payload: dict[str, Any] = {
        "stepKey": step_key,
        "message": message,
    }
    if isinstance(fraction, (int, float)):
        payload["fraction"] = min(max(float(fraction), 0.0), 1.0)
    print(f"@@ASA_PROGRESS {json.dumps(payload)}", file=sys.stderr, flush=True)


def _max_rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(usage)
    return int(usage * 1024)


def _emit_memory(stage_key: str) -> None:
    print(
        f"@@ASA_MEMORY {json.dumps({'stageKey': stage_key, 'rssBytes': _max_rss_bytes()})}",
        file=sys.stderr,
        flush=True,
    )


def _cleanup_torch_cache() -> None:
    try:
        import torch
    except Exception:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        return


def _resolve_backend(backend_id: str) -> Any:
    if backend_id in ("", "auto", "default", "transcription-backend:auto"):
        return None
    if backend_id in (
        "torchcrepe",
        "torchcrepe-viterbi",
        "transcription-backend:torchcrepe-viterbi",
    ):
        return TorchcrepeBackend()
    if backend_id in (
        "basic-pitch",
        "basic-pitch-legacy",
        "transcription-backend:basic-pitch-legacy",
    ):
        return BasicPitchBackend()
    raise RuntimeError(f"Unsupported symbolic backend '{backend_id}'.")


def _parse_optional_path(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    path = raw_value.strip()
    if not path:
        return None
    return path


def _parse_args(argv: list[str]) -> dict[str, Any]:
    if len(argv) < 2:
        raise RuntimeError(
            "Usage: ./venv/bin/python symbolic_extract.py <audio_path> "
            "[--mode stem_notes] [--backend auto] [--stem-bass-path path] [--stem-other-path path]"
        )

    audio_path = argv[1]
    mode = "stem_notes"
    backend = "auto"
    stem_bass_path: str | None = None
    stem_other_path: str | None = None

    index = 2
    while index < len(argv):
        arg = argv[index]
        if arg == "--mode" and index + 1 < len(argv):
            mode = argv[index + 1]
            index += 2
            continue
        if arg == "--backend" and index + 1 < len(argv):
            backend = argv[index + 1]
            index += 2
            continue
        if arg == "--stem-bass-path" and index + 1 < len(argv):
            stem_bass_path = _parse_optional_path(argv[index + 1])
            index += 2
            continue
        if arg == "--stem-other-path" and index + 1 < len(argv):
            stem_other_path = _parse_optional_path(argv[index + 1])
            index += 2
            continue
        raise RuntimeError(f"Unknown argument '{arg}'.")

    return {
        "audio_path": audio_path,
        "mode": mode,
        "backend": backend,
        "stem_bass_path": stem_bass_path,
        "stem_other_path": stem_other_path,
    }


def main() -> None:
    started_at = time.perf_counter()
    temp_dir: str | None = None
    created_stem_paths: dict[str, str] | None = None

    try:
        args = _parse_args(sys.argv)
        audio_path = str(args["audio_path"])
        mode = str(args["mode"])
        backend_id = str(args["backend"])
        stem_paths = {
            stem_name: stem_path
            for stem_name, stem_path in (
                ("bass", args.get("stem_bass_path")),
                ("other", args.get("stem_other_path")),
            )
            if isinstance(stem_path, str) and os.path.isfile(stem_path)
        }

        _emit_progress("prepare", "Preparing symbolic extraction inputs.", 0.05)
        _emit_memory("start")

        if mode == "stem_notes" and len(stem_paths) == 0:
            temp_dir = tempfile.mkdtemp(prefix="asa_symbolic_")
            _emit_progress("separating_stems", "Separating bass and other stems.", 0.2)
            _emit_memory("separation_start")
            separated = separate_stems(audio_path, output_dir=temp_dir)
            if isinstance(separated, dict) and separated:
                stem_paths = {
                    stem_name: stem_path
                    for stem_name, stem_path in separated.items()
                    if stem_name in {"bass", "other"}
                    and isinstance(stem_path, str)
                    and os.path.isfile(stem_path)
                }
                created_stem_paths = dict(stem_paths) if stem_paths else None
            _cleanup_torch_cache()
            gc.collect()
            _emit_memory("separation_done")

        backend = _resolve_backend(backend_id)
        _emit_progress(
            "transcribing_symbolic",
            "Running best-effort symbolic transcription.",
            0.65,
        )
        _emit_memory("transcription_start")
        symbolic_payload = analyze_transcription(
            audio_path,
            stem_paths=stem_paths if stem_paths else None,
            backend=backend,
            emit_progress_markers=True,
        )
        transcription_detail = (
            symbolic_payload.get("transcriptionDetail")
            if isinstance(symbolic_payload, dict)
            else None
        )

        _cleanup_torch_cache()
        gc.collect()
        _emit_memory("transcription_done")

        diagnostics = {
            "backendDurationMs": round((time.perf_counter() - started_at) * 1000.0, 2),
            "stemSeparationUsed": bool(stem_paths),
            "peakRssBytes": _max_rss_bytes(),
        }
        provenance = {
            "schemaVersion": "symbolic.v1",
            "backendId": backend_id,
            "mode": mode,
        }
        if isinstance(transcription_detail, dict):
            provenance["resolvedBackendId"] = transcription_detail.get(
                "transcriptionMethod"
            )

        _emit_progress("complete", "Symbolic extraction complete.", 1.0)
        print(
            json.dumps(
                {
                    "transcriptionDetail": (
                        transcription_detail
                        if isinstance(transcription_detail, dict)
                        else None
                    ),
                    "provenance": provenance,
                    "diagnostics": diagnostics,
                    "stemPaths": created_stem_paths,
                }
            )
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    finally:
        if temp_dir and not created_stem_paths:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
