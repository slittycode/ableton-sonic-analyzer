"""Selectable Phase 1 loudness backend (WS3b, default-off experiment).

ASA's authoritative loudness is Essentia's ``LoudnessEBUR128`` (``analyze_core``).
This module lets the integrated/range/momentary-max/short-term-max **LUFS
scalars** optionally come from the ``loudness-spectro-wasm`` core (``asa-dsp``,
an openmeters-derived BS.1770 implementation) instead, selected at runtime by
``ASA_LOUDNESS_BACKEND``:

* ``essentia`` (default) — unchanged; this module is a no-op.
* ``wasm`` — override the four LUFS scalars with ``asa-dsp``'s reading.

Scope and rationale:

* **LUFS scalars only.** The WS3a parity harness validated integrated LUFS at
  ±0.1 LU; that is the EBU R128 loudness the swap is honest about. ``truePeak``
  stays on Essentia (asa-dsp's true peak diverges on broadband content — see the
  #129 parity report), and ``lufsCurve`` stays on Essentia (the asa-dsp CLI
  emits scalars, not the per-frame curves). So this is a scalar override, not a
  full engine replacement.
* **Subprocess, not pyo3.** We invoke the already-built native ``measure-cli``
  binary (source-identical to the WASM core) on a temp WAV. This sidesteps the
  workspace's ``panic = "abort"`` profile (which blocks pyo3) and the need for a
  separate Cargo workspace, and — being pure Python on this side — cannot red
  the ``loudness-wasm`` CI job. The backend has already decoded the audio, so a
  temp WAV makes the swap format-agnostic (FLAC/MP3 in, WAV to the CLI).
* **Default stays Essentia.** Per PURPOSE.md invariant #1, the authoritative
  value does not change until real-program parity is proven; the flip is the
  owner's call. Any failure here degrades gracefully back to Essentia.

The canonical loudness contract (field names, units, rounding) is unchanged.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

# The four LUFS scalar fields this backend may override. lufsCurve is
# deliberately excluded (Essentia-only; the CLI does not emit per-frame curves).
_OVERRIDABLE_FIELDS = (
    "lufsIntegrated",
    "lufsRange",
    "lufsMomentaryMax",
    "lufsShortTermMax",
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MEASURE_CLI = (
    _REPO_ROOT / "packages" / "loudness-spectro-wasm" / "target" / "release" / "measure-cli"
)


def loudness_backend_name() -> str:
    """Resolve the selected loudness backend. Unknown values fall back to essentia."""
    name = (os.environ.get("ASA_LOUDNESS_BACKEND") or "essentia").strip().lower()
    return name if name in {"essentia", "wasm"} else "essentia"


def _measure_cli_path() -> Path | None:
    """Locate the measure-cli binary (env override, then the repo build dir)."""
    override = os.environ.get("ASA_MEASURE_CLI")
    if override:
        candidate = Path(override)
        return candidate if candidate.exists() else None
    return _DEFAULT_MEASURE_CLI if _DEFAULT_MEASURE_CLI.exists() else None


def _round1(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return round(float(value), 1)
    return None


def measure_loudness_via_cli(stereo: np.ndarray, sample_rate: int) -> dict[str, Any] | None:
    """Run asa-dsp's measure-cli on the audio and return the LUFS scalars.

    Returns ``None`` (and warns on stderr) on any failure — missing binary,
    non-zero exit, unparseable output, or a null integrated reading — so the
    caller can fall back to Essentia. The diagnostics contract (stderr only) is
    preserved; this never writes to stdout.
    """
    cli = _measure_cli_path()
    if cli is None:
        print(
            "[warn] ASA_LOUDNESS_BACKEND=wasm but measure-cli is not built "
            f"(looked at {_DEFAULT_MEASURE_CLI} or $ASA_MEASURE_CLI); "
            "falling back to Essentia loudness.",
            file=sys.stderr,
        )
        return None

    tmp_path: str | None = None
    try:
        import soundfile as sf  # lazy: the essentia path needs no WAV writer

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            tmp_path = handle.name
        # Native-rate float WAV; measure-cli decodes via hound at this rate
        # (no resampling — that would break ±0.1 LU EBU conformance).
        sf.write(tmp_path, np.asarray(stereo), int(sample_rate), subtype="FLOAT")

        proc = subprocess.run(
            [str(cli), tmp_path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            print(
                f"[warn] measure-cli exited {proc.returncode}: "
                f"{proc.stderr.strip()[:200]}; falling back to Essentia loudness.",
                file=sys.stderr,
            )
            return None

        payload = json.loads(proc.stdout.strip())
        integrated = _round1(payload.get("integrated"))
        if integrated is None:
            # Null integrated (no block passed the gates / silence) — don't
            # override Essentia with a null; let Essentia's reading stand.
            print(
                "[warn] measure-cli returned null integrated loudness; "
                "falling back to Essentia loudness.",
                file=sys.stderr,
            )
            return None

        return {
            "lufsIntegrated": integrated,
            "lufsRange": _round1(payload.get("lra")),
            "lufsMomentaryMax": _round1(payload.get("momentaryMax")),
            "lufsShortTermMax": _round1(payload.get("shortTermMax")),
        }
    except Exception as exc:  # noqa: BLE001 - degrade to Essentia, never crash analysis
        print(
            f"[warn] measure-cli loudness failed ({exc}); falling back to Essentia loudness.",
            file=sys.stderr,
        )
        return None
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def apply_loudness_backend(
    loudness: dict[str, Any],
    stereo: np.ndarray | None,
    sample_rate: int,
) -> dict[str, Any]:
    """Override the LUFS scalars with the WASM backend when selected.

    No-op for the default ``essentia`` backend or when audio is unavailable.
    On any WASM failure the Essentia ``loudness`` dict is returned unchanged, so
    the analysis never degrades below the authoritative path. ``lufsCurve`` and
    every non-LUFS field pass through untouched.
    """
    if loudness_backend_name() != "wasm" or stereo is None:
        return loudness

    cli_result = measure_loudness_via_cli(stereo, sample_rate)
    if cli_result is None:
        return loudness

    merged = dict(loudness)
    for field in _OVERRIDABLE_FIELDS:
        merged[field] = cli_result.get(field)
    print(
        "[info] loudness backend: WASM (asa-dsp) overrode LUFS scalars "
        f"(integrated {merged.get('lufsIntegrated')} LUFS); "
        "truePeak and lufsCurve remain Essentia.",
        file=sys.stderr,
    )
    return merged
