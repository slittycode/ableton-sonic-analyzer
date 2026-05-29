#!/usr/bin/env python3
"""FluidSynth vs symusic.Synthesizer parity probe.

The PR-F audio-backend swap (`apps/backend/sample_synthesis.py`) wires symusic
as an optional audition-sample renderer behind ``ASA_SAMPLE_SYNTH_BACKEND``.
This script gives a maintainer the cheapest possible way to verify the two
backends produce comparable audio on the same SoundFont before flipping the
auto default away from FluidSynth.

What it does:

1. Builds a deterministic ``ClipPlan`` (a single-octave C-major triad
   sustained over 4 beats at 120 BPM — short enough to render quickly, rich
   enough that any voice-leveling or pitching drift between backends shows
   up in the spectrum).
2. Renders the same plan through both backends with the same soundfont.
3. Compares mono float32 buffers along three axes: RMS (overall loudness),
   peak (clipping headroom), and spectral centroid (timbral character).
4. Emits a JSON report at ``apps/backend/.runtime/parity/synth_parity.json``
   with the deltas and a pass/fail verdict using the documented tolerances.

The script is intentionally **non-prescriptive about adoption**. Passing
parity does not flip the auto default — that's a separate code change. A
failing run is just evidence the engines diverge enough that the default
swap would be audible.

Skip behaviour:

  * pyfluidsynth missing → exit 0, status ``skipped_no_fluidsynth``.
  * No SF2/SF3 reachable via ``SONIC_ANALYZER_SOUNDFONT`` or the known
    candidate paths → exit 0, status ``skipped_no_soundfont``.
  * symusic should always be importable (it's a hard dep); if absent, the
    script raises rather than skips because that's a deeper integrity issue.

Usage:

    ./venv/bin/python scripts/parity_probe_synth_backends.py \\
        [--soundfont /path/to/font.sf2] \\
        [--out-dir .runtime/parity]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

REPO_DIR = Path(__file__).resolve().parent.parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

import sample_synthesis  # noqa: E402
from sample_theory import ClipPlan, NoteEvent  # noqa: E402

# Tolerance bands. These are loose by design — soundfont-driven synths
# legitimately differ in voice rendering, envelope shapes, and reverb tails.
# The intent is "audible parity at typical monitor levels", not "bit-exact".
RMS_DB_TOLERANCE = 1.0
PEAK_DB_TOLERANCE = 2.0
CENTROID_HZ_TOLERANCE = 200.0


@dataclass(frozen=True)
class BufferStats:
    rms_dbfs: float
    peak_dbfs: float
    spectral_centroid_hz: float
    nonzero: bool


def _build_probe_plan() -> ClipPlan:
    """Single-octave C-major triad sustained for 4 beats at 120 BPM (2 s)."""
    return ClipPlan(
        tempo_bpm=120.0,
        duration_beats=4.0,
        notes=[
            NoteEvent(pitch_midi=60, start_beat=0.0, duration_beats=4.0, velocity=100),
            NoteEvent(pitch_midi=64, start_beat=0.0, duration_beats=4.0, velocity=100),
            NoteEvent(pitch_midi=67, start_beat=0.0, duration_beats=4.0, velocity=100),
        ],
        program=0,  # Acoustic Grand Piano — a stable preset across SF banks.
    )


def _compute_buffer_stats(samples: np.ndarray, sample_rate: int) -> BufferStats:
    mono = np.asarray(samples, dtype=np.float64).reshape(-1)
    if mono.size == 0:
        return BufferStats(
            rms_dbfs=-float("inf"),
            peak_dbfs=-float("inf"),
            spectral_centroid_hz=0.0,
            nonzero=False,
        )

    rms = float(np.sqrt(np.mean(mono * mono)))
    peak = float(np.max(np.abs(mono)))
    if peak <= 0:
        return BufferStats(
            rms_dbfs=-float("inf"),
            peak_dbfs=-float("inf"),
            spectral_centroid_hz=0.0,
            nonzero=False,
        )

    # FFT on the steady-state portion (skip the attack edge) for a stable
    # centroid even when one backend has a sharper transient than the other.
    skip_samples = min(int(0.1 * sample_rate), mono.size // 4)
    window = mono[skip_samples:]
    if window.size == 0:
        window = mono
    hann = np.hanning(window.size)
    spectrum = np.abs(np.fft.rfft(window * hann))
    freqs = np.fft.rfftfreq(window.size, d=1.0 / sample_rate)
    spectrum_sum = float(spectrum.sum())
    centroid = (
        float((freqs * spectrum).sum() / spectrum_sum)
        if spectrum_sum > 0
        else 0.0
    )

    return BufferStats(
        rms_dbfs=20.0 * float(np.log10(max(rms, 1e-12))),
        peak_dbfs=20.0 * float(np.log10(max(peak, 1e-12))),
        spectral_centroid_hz=centroid,
        nonzero=True,
    )


def _stats_to_dict(stats: BufferStats) -> dict[str, Any]:
    return {
        "rmsDbfs": round(stats.rms_dbfs, 3),
        "peakDbfs": round(stats.peak_dbfs, 3),
        "spectralCentroidHz": round(stats.spectral_centroid_hz, 2),
        "nonzero": stats.nonzero,
    }


def _verdict(
    fluidsynth: BufferStats, symusic: BufferStats
) -> dict[str, Any]:
    """Apply the tolerance bands and emit a pass/fail per axis."""
    rms_delta_db = abs(fluidsynth.rms_dbfs - symusic.rms_dbfs)
    peak_delta_db = abs(fluidsynth.peak_dbfs - symusic.peak_dbfs)
    centroid_delta_hz = abs(
        fluidsynth.spectral_centroid_hz - symusic.spectral_centroid_hz
    )

    axes = {
        "rms": {
            "deltaDb": round(rms_delta_db, 3),
            "toleranceDb": RMS_DB_TOLERANCE,
            "pass": rms_delta_db <= RMS_DB_TOLERANCE,
        },
        "peak": {
            "deltaDb": round(peak_delta_db, 3),
            "toleranceDb": PEAK_DB_TOLERANCE,
            "pass": peak_delta_db <= PEAK_DB_TOLERANCE,
        },
        "spectralCentroid": {
            "deltaHz": round(centroid_delta_hz, 2),
            "toleranceHz": CENTROID_HZ_TOLERANCE,
            "pass": centroid_delta_hz <= CENTROID_HZ_TOLERANCE,
        },
    }
    return {
        "axes": axes,
        "overallPass": all(axis["pass"] for axis in axes.values()),
    }


def _render_with_backend(
    backend: sample_synthesis.Backend,
    plan: ClipPlan,
    soundfont: Path,
) -> sample_synthesis.RenderResult:
    if backend == "fluidsynth":
        return sample_synthesis._render_with_fluidsynth(plan, soundfont)
    if backend == "symusic":
        return sample_synthesis._render_with_symusic_synth(plan, soundfont)
    raise ValueError(f"Unknown backend for parity probe: {backend!r}")


def _emit_report(report: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--soundfont",
        type=Path,
        default=None,
        help="Explicit SF2/SF3 path. Overrides SONIC_ANALYZER_SOUNDFONT and the candidate-paths fallback.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_DIR / ".runtime" / "parity",
        help="Directory to write synth_parity.json. Defaults to apps/backend/.runtime/parity/.",
    )
    args = parser.parse_args()

    report: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "probe": "fluidsynth_vs_symusic",
        "soundfontPath": None,
        "fluidsynth": None,
        "symusic": None,
        "verdict": None,
        "status": "pending",
        "tolerances": {
            "rmsDb": RMS_DB_TOLERANCE,
            "peakDb": PEAK_DB_TOLERANCE,
            "centroidHz": CENTROID_HZ_TOLERANCE,
        },
    }

    if not sample_synthesis._FLUIDSYNTH_IMPORTABLE:
        report["status"] = "skipped_no_fluidsynth"
        report["reason"] = (
            "pyfluidsynth is not importable in this venv; cannot measure parity "
            "without both backends running side-by-side."
        )
        _emit_report(report, args.out_dir / "synth_parity.json")
        print(json.dumps(report, indent=2))
        return 0

    soundfont = sample_synthesis.locate_soundfont(args.soundfont)
    if soundfont is None:
        report["status"] = "skipped_no_soundfont"
        report["reason"] = (
            "No SF2/SF3 reachable. Set SONIC_ANALYZER_SOUNDFONT or pass "
            "--soundfont to enable the probe."
        )
        _emit_report(report, args.out_dir / "synth_parity.json")
        print(json.dumps(report, indent=2))
        return 0

    report["soundfontPath"] = str(soundfont)
    plan = _build_probe_plan()

    try:
        fluidsynth_result = _render_with_backend("fluidsynth", plan, soundfont)
        symusic_result = _render_with_backend("symusic", plan, soundfont)
    except Exception as exc:
        report["status"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"
        _emit_report(report, args.out_dir / "synth_parity.json")
        print(json.dumps(report, indent=2))
        return 1

    fluidsynth_stats = _compute_buffer_stats(
        fluidsynth_result.samples, fluidsynth_result.sample_rate
    )
    symusic_stats = _compute_buffer_stats(
        symusic_result.samples, symusic_result.sample_rate
    )

    report["fluidsynth"] = {
        "sampleRate": fluidsynth_result.sample_rate,
        "durationSeconds": round(fluidsynth_result.duration_seconds, 3),
        "stats": _stats_to_dict(fluidsynth_stats),
    }
    report["symusic"] = {
        "sampleRate": symusic_result.sample_rate,
        "durationSeconds": round(symusic_result.duration_seconds, 3),
        "stats": _stats_to_dict(symusic_stats),
    }

    if not (fluidsynth_stats.nonzero and symusic_stats.nonzero):
        report["status"] = "error"
        report["error"] = (
            "One or both backends returned silent audio — check soundfont preset "
            "loading and program-select wiring."
        )
        _emit_report(report, args.out_dir / "synth_parity.json")
        print(json.dumps(report, indent=2))
        return 1

    verdict = _verdict(fluidsynth_stats, symusic_stats)
    report["verdict"] = verdict
    report["status"] = "completed_pass" if verdict["overallPass"] else "completed_fail"

    _emit_report(report, args.out_dir / "synth_parity.json")
    print(json.dumps(report, indent=2))
    return 0 if verdict["overallPass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
