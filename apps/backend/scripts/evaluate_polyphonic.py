#!/usr/bin/env python3
"""Run the offline polyphonic transcription research harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from polyphonic_evaluation import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REPORT_PATH,
    run_polyphonic_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the research-only polyphonic full-track transcription harness. "
            "This does not change the production backend."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to the evaluation manifest JSON.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Path to write the report JSON (default: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for note-event and MIDI artifacts (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--mt3-command",
        type=str,
        default=None,
        help=(
            "Optional shell command template for an MT3 runner. "
            "Available placeholders: {audio_path}, {output_dir}, {midi_path}, {clip_id}."
        ),
    )
    parser.add_argument(
        "--save-demucs-diagnostics",
        action="store_true",
        help="Save Demucs stems alongside each clip for diagnostics only.",
    )
    parser.add_argument(
        "--runner-timeout-seconds",
        type=int,
        default=600,
        help="Timeout per candidate run in seconds (default: 600).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_polyphonic_evaluation(
        manifest_path=args.manifest,
        report_path=args.report,
        output_dir=args.output_dir,
        mt3_command=args.mt3_command,
        save_demucs_diagnostics=args.save_demucs_diagnostics,
        runner_timeout_seconds=max(args.runner_timeout_seconds, 1),
    )
    print(
        json.dumps(
            {
                "summary": report["summary"],
                "candidateSummaries": report["candidateSummaries"],
                "reportPath": report["reportPath"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

