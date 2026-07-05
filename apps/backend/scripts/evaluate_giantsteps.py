#!/usr/bin/env python3
"""Score ASA key/tempo against the GiantSteps datasets (research-only).

Corpus layout is produced by scripts/fetch_giantsteps.py (operator-run; see
tests/fixtures/giantsteps/README.md). The analyzer subprocess inherits this
process's environment, so backend experiments are scored the same way, e.g.:

    ASA_LOUDNESS_BACKEND=wasm ./venv/bin/python scripts/evaluate_giantsteps.py --subset key
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from giantsteps_evaluation import (  # noqa: E402
    DEFAULT_CORPUS_ROOT,
    DEFAULT_REPORT_DIR,
    evaluate_corpus,
    load_giantsteps_corpus,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Phase 1 key/tempo accuracy on the GiantSteps corpus."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--subset", choices=("key", "tempo"), required=True)
    parser.add_argument("--max-clips", type=int, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the full analyze pipeline instead of --fast (slower; same key/bpm fields).",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Parallel analyzer subprocesses (default 1). Scoring is identical to "
        "sequential; only wall-clock changes. 6-8 is sensible on a multi-core host.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    clips = load_giantsteps_corpus(args.root, args.subset)
    report_path = args.report or (DEFAULT_REPORT_DIR / f"giantsteps_{args.subset}.json")
    report = evaluate_corpus(
        clips,
        subset=args.subset,
        fast=not args.full,
        max_clips=args.max_clips,
        report_path=report_path,
        jobs=args.jobs,
    )
    print(json.dumps({"summary": report["summary"], "reportPath": report.get("reportPath")}, indent=2))
    if report["summary"]["status"] != "evaluated":
        print(
            f"No evaluable clips under {args.root} — fetch the corpus first "
            "(scripts/fetch_giantsteps.py; see tests/fixtures/giantsteps/README.md).",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
