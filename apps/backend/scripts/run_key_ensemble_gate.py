#!/usr/bin/env python3
"""Run the pre-registered key-ensemble decision gate (accuracy PR-B3).

Scores the shipped EDMA key label against a three-profile majority vote over
GiantSteps Key and applies the frozen rule in
``incorporations/key-ensemble-decision-2026-07-04.md``. Runs the *full* analyze
pipeline (the ``keyEnsemble`` cross-check is full-mode only), so it is slower
than the fast key eval; expect a few seconds per clip.

    ./venv/bin/python scripts/run_key_ensemble_gate.py
    ./venv/bin/python scripts/run_key_ensemble_gate.py --max-clips 50   # smoke

Exits non-zero when the run is underpowered (< 400 evaluable clips) so it can
never be finalised on a vacuous corpus.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from giantsteps_evaluation import DEFAULT_CORPUS_ROOT, load_giantsteps_corpus  # noqa: E402
from key_ensemble_gate import DEFAULT_GATE_REPORT, run_gate  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the pre-registered key-ensemble gate.")
    parser.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--max-clips", type=int, default=None)
    parser.add_argument("--report", type=Path, default=DEFAULT_GATE_REPORT)
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Parallel analyzer subprocesses (default 1). Decision is identical to "
        "sequential; only wall-clock changes. 6-8 is sensible on a multi-core host.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    clips = load_giantsteps_corpus(args.root, "key")
    report = run_gate(clips, max_clips=args.max_clips, report_path=args.report, jobs=args.jobs)
    print(json.dumps({"summary": report["summary"], "reportPath": report.get("reportPath")}, indent=2))
    if report["summary"]["decision"] == "underpowered":
        print(
            f"Underpowered: only {report['summary']['clipsEvaluable']} evaluable clips "
            f"(need >= {report['summary']['minEvaluable']}). Fetch more of the corpus "
            "(scripts/fetch_giantsteps.py) before finalising the gate.",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
