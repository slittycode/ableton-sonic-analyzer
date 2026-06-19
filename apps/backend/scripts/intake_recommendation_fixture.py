#!/usr/bin/env python3
"""Ingest one real recommendation fixture and refresh all proof artifacts.

The hard-techno pilot is the default, so the complete pilot workflow is one
command from ``apps/backend``:

  ./venv/bin/python scripts/intake_recommendation_fixture.py

The command validates the render, regenerates canonical Phase 1 evidence,
checks measurable intent, generates Claude and deterministic recommendations,
scores Claude/deterministic/baseline, and refreshes the UI verification data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from recommendation_fixture_intake import run_fixture_intake  # noqa: E402


DEFAULT_CORPUS_DIR = BACKEND_DIR / "tests" / "fixtures" / "recommendation_tracks"
DEFAULT_FIXTURE = "hard_techno_rumble_145"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        default=DEFAULT_FIXTURE,
        help=f"fixture slug (default: {DEFAULT_FIXTURE})",
    )
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    args = parser.parse_args()

    result = run_fixture_intake(args.corpus_dir / args.fixture)
    print(f"[{'PASS' if result.passed else 'FAIL'}] {result.message}")
    if result.scores:
        for score in result.scores:
            print(
                f"  {score['source']:<13} aggregate {score['aggregate']:.3f} "
                f"(raw {score['rawAggregate']:.3f}, custody {score['custody']['penalty']:.3f})"
            )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
