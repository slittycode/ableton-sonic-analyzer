#!/usr/bin/env python3
"""Run the local musical-fundamentals evaluation gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fundamentals_evaluation import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_TRACKS_DIR,
    run_fundamentals_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local fundamentals benchmark. Missing local audio files are "
            "reported as skips; present audio must pass the declared gates."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--tracks-dir", type=Path, default=DEFAULT_TRACKS_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--fail-on-skip", action="store_true", help="Fail if any manifest track is skipped because audio is missing.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_fundamentals_evaluation(
        manifest_path=args.manifest,
        tracks_dir=args.tracks_dir,
        report_path=args.report,
        fail_on_skip=args.fail_on_skip,
    )
    summary: dict[str, Any] = {
        "summary": report["summary"],
        "reportPath": report["reportPath"],
    }
    if report["summary"]["tracksSkipped"] > 0:
        summary["note"] = (
            "Some fundamentals tracks were skipped because local audio files "
            f"were not present in {args.tracks_dir}."
        )
    print(json.dumps(summary, indent=2))
    if not report["summary"]["allPassed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
