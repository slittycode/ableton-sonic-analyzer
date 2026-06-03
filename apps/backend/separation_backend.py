"""Pluggable Phase 1 stem-separation backend (default-off experiment).

ASA's authoritative separation is torchaudio Hybrid Demucs
(``analyze_audio_io.separate_stems``). This module lets the separation stage
optionally run a stronger MSST / BS-RoFormer model from
`SUC-DriverOld/MSST-WebUI <https://github.com/SUC-DriverOld/MSST-WebUI>`_,
selected at runtime by ``ASA_SEPARATION_BACKEND``:

* ``demucs`` (default) — unchanged; this module delegates straight to
  ``separate_stems`` and is a no-op wrapper.
* ``msst`` — drive MSST's ``MSSeparator`` inference (no PySide6 GUI) to produce
  the same ``{stem_name: wav_path}`` contract.

Design — subprocess, not in-process import (mirrors ``loudness_backend.py``):

MSST pins older, conflicting versions of ASA's own deps (``librosa==0.9.2``,
``numpy<2``, ``demucs==4.0.0`` …) so it must live in its **own** virtualenv. We
therefore shell out to ``scripts/msst_separate_runner.py`` under
``ASA_MSST_PYTHON`` (the MSST venv interpreter) and capture its stdout. This:

* lets MSST actually run on the staged worker path (``server.py`` always invokes
  ``analyze.py`` under ``./venv/bin/python`` — an in-process import could never
  see MSST's deps),
* keeps MSST's progress bars / logging off ``analyze.py``'s stdout, which is the
  load-bearing JSON contract (tripwire #1),
* sidesteps MSST's ``utils`` / ``inference`` top-level package collision with
  ASA's ``apps/backend/utils`` package,
* and isolates MSST's torch from ASA's ``torch==2.10.0``.

Per PURPOSE.md invariant #1 the default stays Demucs and the authoritative
contract is unchanged. Any MSST failure — missing venv, missing checkout,
missing checkpoint, non-zero exit, unparseable output — degrades gracefully back
to Demucs with a ``[warn]`` on stderr.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from analyze_audio_io import separate_stems

# separation_backend.py lives at apps/backend/, so the runner is a sibling of
# this file under scripts/.
_RUNNER_SCRIPT = Path(__file__).resolve().parent / "scripts" / "msst_separate_runner.py"

# Demucs writes its stems into a tempdir prefixed ``sonic_analyzer_demucs_`` and
# ``analyze_audio_io.cleanup_stems`` only reclaims a parent dir with that exact
# prefix. The MSST path reuses the same prefix so cleanup works unchanged and no
# temp directory leaks per measurement run.
_STEM_DIR_PREFIX = "sonic_analyzer_demucs_"

# Model registry: ``ASA_MSST_MODEL`` -> the three coupled MSSeparator args.
# ``config_relpath`` / ``checkpoint_relpath`` resolve under ``ASA_MSST_MODEL_DIR``
# (default: ``ASA_MSST_ROOT``), matching MSST-WebUI's own ``configs/`` + ``pretrain/``
# layout. Checkpoints are NOT vendored — the operator downloads weights from the
# ``Sucial/MSST-WebUI`` Hugging Face repo into ``ASA_MSST_MODEL_DIR``.
_DEFAULT_MSST_MODEL = "scnet_4stem"
_MSST_MODEL_REGISTRY: dict[str, dict[str, str]] = {
    # 4-stem parity model — fills vocals/bass/drums/other, so the product path
    # (stemAnalysis overlay, pitch/note translation, MT3) behaves like Demucs.
    "scnet_4stem": {
        "model_type": "scnet",
        "config_relpath": "configs/multi_stem_models/config_musdb18_scnet.yaml",
        "checkpoint_relpath": "pretrain/multi_stem_models/model_scnet_sdr_9.3244.ckpt",
    },
    # Strong 2-stem vocal BS-RoFormer (vocals + instrumental->other). RESEARCH /
    # A-B ONLY: it leaves bass/drums absent, so pitch/note translation + MT3 fall
    # back to the full mix. Never select this as a product-path default.
    "bs_roformer_vocals": {
        "model_type": "bs_roformer",
        "config_relpath": "configs/vocal_models/config_vocals_bs_roformer.yaml",
        "checkpoint_relpath": "pretrain/vocal_models/model_bs_roformer_ep_368_sdr_12.9628.ckpt",
    },
}


def separation_backend_name() -> str:
    """Resolve the selected separation backend. Unknown values fall back to demucs."""
    name = (os.environ.get("ASA_SEPARATION_BACKEND") or "demucs").strip().lower()
    return name if name in {"demucs", "msst"} else "demucs"


def _msst_model_entry() -> dict[str, str]:
    """Resolve the MSST model registry entry. Unknown ids fall back to the default."""
    requested = (os.environ.get("ASA_MSST_MODEL") or _DEFAULT_MSST_MODEL).strip()
    entry = _MSST_MODEL_REGISTRY.get(requested)
    if entry is None:
        print(
            f"[warn] Unknown ASA_MSST_MODEL='{requested}'; valid values: "
            f"{sorted(_MSST_MODEL_REGISTRY)}. Falling back to '{_DEFAULT_MSST_MODEL}'.",
            file=sys.stderr,
        )
        entry = _MSST_MODEL_REGISTRY[_DEFAULT_MSST_MODEL]
    return entry


def separate_stems_backend(audio_path: str, output_dir: str | None = None):
    """Run the selected separation backend, returning ``{stem_name: wav_path}``.

    The return shape is identical to ``separate_stems`` (Demucs) so every
    downstream consumer — the ``stemAnalysis`` overlay, pitch/note translation,
    MT3, and ``cleanup_stems`` — is byte-compatible. For ``ASA_SEPARATION_BACKEND``
    unset/``demucs`` this is a thin pass-through to ``separate_stems``. For
    ``msst`` it drives MSST and, on any failure, degrades to Demucs.
    """
    if separation_backend_name() != "msst":
        return separate_stems(audio_path, output_dir=output_dir)

    result = _separate_via_msst_subprocess(audio_path, output_dir)
    if result is not None:
        return result

    print(
        "[warn] MSST separation unavailable; falling back to Demucs.",
        file=sys.stderr,
    )
    return separate_stems(audio_path, output_dir=output_dir)


def _separate_via_msst_subprocess(audio_path: str, output_dir: str | None):
    """Drive MSST separation via the runner subprocess under ``ASA_MSST_PYTHON``.

    Returns ``{stem_name: wav_path}`` on success, or ``None`` (warning on stderr)
    on any failure so the caller can fall back to Demucs. All MSST stdout/stderr
    is captured here and never reaches ``analyze.py``'s stdout JSON contract.
    """
    interpreter = os.environ.get("ASA_MSST_PYTHON")
    if not interpreter or not Path(interpreter).exists():
        print(
            "[warn] ASA_SEPARATION_BACKEND=msst but ASA_MSST_PYTHON is unset or "
            f"missing (got {interpreter!r}); cannot run the MSST venv.",
            file=sys.stderr,
        )
        return None

    msst_root = os.environ.get("ASA_MSST_ROOT")
    if not msst_root or not Path(msst_root).is_dir():
        print(
            "[warn] ASA_SEPARATION_BACKEND=msst but ASA_MSST_ROOT is unset or not a "
            f"directory (got {msst_root!r}); cannot find the MSST-WebUI checkout.",
            file=sys.stderr,
        )
        return None

    if not _RUNNER_SCRIPT.exists():
        print(f"[warn] MSST runner script missing at {_RUNNER_SCRIPT}.", file=sys.stderr)
        return None

    model_dir = Path(os.environ.get("ASA_MSST_MODEL_DIR") or msst_root)
    entry = _msst_model_entry()
    config_path = model_dir / entry["config_relpath"]
    checkpoint_path = model_dir / entry["checkpoint_relpath"]
    for label, candidate in (("config", config_path), ("checkpoint", checkpoint_path)):
        if not candidate.exists():
            print(
                f"[warn] MSST {label} not found at {candidate} (model "
                f"'{os.environ.get('ASA_MSST_MODEL') or _DEFAULT_MSST_MODEL}').",
                file=sys.stderr,
            )
            return None

    # Reuse the Demucs tempdir prefix so cleanup_stems reclaims the directory.
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix=_STEM_DIR_PREFIX)
    else:
        os.makedirs(output_dir, exist_ok=True)

    command = [
        interpreter,
        str(_RUNNER_SCRIPT),
        "--input",
        audio_path,
        "--output-dir",
        output_dir,
        "--msst-root",
        msst_root,
        "--model-type",
        entry["model_type"],
        "--config",
        str(config_path),
        "--checkpoint",
        str(checkpoint_path),
    ]
    device = os.environ.get("ASA_MSST_DEVICE")
    if device:
        command.extend(["--device", device])

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - degrade to Demucs, never crash analysis
        print(f"[warn] MSST runner failed to launch ({exc}).", file=sys.stderr)
        return None

    if proc.stderr:
        # Surface the runner's diagnostics on our stderr (never stdout).
        print(proc.stderr.rstrip(), file=sys.stderr)
    if proc.returncode != 0:
        print(
            f"[warn] MSST runner exited {proc.returncode}; falling back to Demucs.",
            file=sys.stderr,
        )
        return None

    return _parse_runner_manifest(proc.stdout)


def _parse_runner_manifest(stdout: str):
    """Parse the runner's single-line JSON manifest into ``{stem_name: path}``."""
    try:
        payload = json.loads(stdout.strip())
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] MSST runner produced unparseable output ({exc}).", file=sys.stderr)
        return None

    stems = payload.get("stems") if isinstance(payload, dict) else None
    if not isinstance(stems, dict) or not stems:
        print("[warn] MSST runner reported no stems.", file=sys.stderr)
        return None

    resolved: dict[str, str] = {}
    for name, path in stems.items():
        if isinstance(path, str) and os.path.isfile(path):
            resolved[name] = path
    if not resolved:
        print("[warn] MSST runner stems do not exist on disk.", file=sys.stderr)
        return None

    load_s = payload.get("loadSeconds")
    infer_s = payload.get("inferSeconds")
    device = payload.get("device")
    print(
        f"[info] separation backend: MSST ({entry_label(payload)}) produced "
        f"{sorted(resolved)} on {device} "
        f"(load {load_s}s, infer {infer_s}s).",
        file=sys.stderr,
    )
    return resolved


def entry_label(payload: dict) -> str:
    """Best-effort model label for the info line (model_type from the manifest)."""
    if isinstance(payload, dict):
        model_type = payload.get("modelType")
        if isinstance(model_type, str) and model_type:
            return model_type
    return os.environ.get("ASA_MSST_MODEL") or _DEFAULT_MSST_MODEL
