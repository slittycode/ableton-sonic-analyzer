#!/usr/bin/env python3
"""A/B separation backends CLI — EVAL / RESEARCH ONLY.

Thin wrapper over ``separation_ab.run_ab`` (like ``scripts/evaluate_*.py`` wrap
their ``*_evaluation.py`` modules). Compares the default Demucs backend against
the optional MSST backend (``ASA_SEPARATION_BACKEND=msst``) on separation quality
and runtime, writes a JSON report, and prints a compact table.

The synthetic smoke-test always runs. The MSST column is filled only when
``ASA_MSST_PYTHON`` + ``ASA_MSST_ROOT`` are configured (otherwise reported as
``skipped_no_msst``). This is observational, not a gate — exit code is 0 for any
completed/skipped run, 1 only on a hard error.

Usage::

    ./venv/bin/python scripts/ab_separation_backends.py \\
        [-i /dir/of/real/tracks] [-o .runtime/separation_ab] [--model scnet_4stem]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

import separation_ab  # noqa: E402


def _fmt(value: object) -> str:
    return "—" if value is None else str(value)


def _print_table(report: dict) -> None:
    print("\nSeparation A/B — synthetic smoke-test (NOT a real-music quality ranking)")
    print(f"{'backend':<10} {'status':<16} {'meanSI-SDR(dB)':>15} {'runtime(s)':>11} {'device':>8}")
    synthetic = report.get("syntheticSmokeTest", {}).get("perBackend", {})
    for backend in ("demucs", "msst"):
        block = synthetic.get(backend, {})
        status = block.get("status", "—")
        quality = block.get("quality", {}) if isinstance(block.get("quality"), dict) else {}
        mean = quality.get("meanSiSdrDb")
        runtime = block.get("runtimeSeconds")
        device = block.get("device")
        print(f"{backend:<10} {status:<16} {_fmt(mean):>15} {_fmt(runtime):>11} {_fmt(device):>8}")

    real = report.get("realTracks", [])
    if real:
        print(f"\nReal-track reference-free proxies ({len(real)} track(s)):")
        for entry in real:
            print(f"  {entry.get('track')}:")
            for backend in ("demucs", "msst"):
                block = entry.get("perBackend", {}).get(backend, {})
                status = block.get("status", "—")
                runtime = block.get("runtimeSeconds")
                residual = block.get("mixReconstructionResidualDb")
                print(
                    f"    {backend:<8} status={status:<16} "
                    f"runtime={_fmt(runtime)}s reconResidual={_fmt(residual)}dB"
                )
    for caveat in report.get("caveats", []):
        print(f"\n[caveat] {caveat}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i", "--input-dir", default=None,
        help="Optional directory of real audio tracks for reference-free proxies.",
    )
    parser.add_argument(
        "-o", "--out-dir", type=Path, default=REPO_DIR / ".runtime" / "separation_ab",
        help="Report output directory. Defaults to apps/backend/.runtime/separation_ab/.",
    )
    parser.add_argument(
        "--model", default=None,
        help="MSST model registry id (sets ASA_MSST_MODEL). Defaults to scnet_4stem.",
    )
    parser.add_argument("--repeats", type=int, default=2, help="Timed runs per backend (min wins).")
    args = parser.parse_args()

    try:
        report = separation_ab.run_ab(
            input_dir=args.input_dir,
            out_dir=str(args.out_dir),
            model=args.model,
            repeats=args.repeats,
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _print_table(report)
    print(f"\nWrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
