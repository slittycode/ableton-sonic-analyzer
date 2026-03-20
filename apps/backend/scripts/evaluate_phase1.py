#!/usr/bin/env python3
"""Run the Phase 1 evaluation harness and emit a JSON report artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from phase1_evaluation import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_REPORT_PATH,
    run_phase1_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 1 evaluation harness.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help=f"Path to evaluation manifest (default: {DEFAULT_MANIFEST_PATH})",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Path to write report JSON (default: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="Number of repeated analyze runs per fixture (default: 2)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_phase1_evaluation(
        manifest_path=args.manifest,
        report_path=args.report,
        runs_per_fixture=max(args.runs, 1),
    )
    print(json.dumps({"summary": report["summary"], "reportPath": report["reportPath"]}, indent=2))
    if not report["summary"]["allPassed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
