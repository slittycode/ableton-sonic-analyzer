#!/usr/bin/env python3
"""Run the Phase 1 evaluation harness and emit a JSON report artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from phase1_evaluation import (
    DEFAULT_BENCH_TRACKS_DIR,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_TRANSCRIPTION_TRACKS_DIR,
    run_phase1_evaluation,
)
from phase1_report_html import default_html_report_path, render_html_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Phase 1 evaluation harness. By default runs only the synthetic-"
            "fixture gate (safe for CI). Pass --include-real to also evaluate "
            "real reference tracks from the local bench when present."
        )
    )
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
    parser.add_argument(
        "--include-real",
        action="store_true",
        help=(
            "Opt in to evaluating real reference tracks listed under "
            "manifest.realTracks. Missing audio files are skipped with a clear "
            "notice rather than failing the run."
        ),
    )
    parser.add_argument(
        "--real-tracks-dir",
        type=Path,
        default=DEFAULT_BENCH_TRACKS_DIR,
        help=(
            f"Directory holding local real reference tracks "
            f"(default: {DEFAULT_BENCH_TRACKS_DIR})"
        ),
    )
    parser.add_argument(
        "--include-transcription",
        action="store_true",
        help=(
            "Opt in to evaluating Layer 2 (torchcrepe) transcription against "
            "manifest.transcriptionTracks. Always runs the stepped-sine self-"
            "test even when the corpus is empty. Missing audio files are "
            "skipped with a clear notice rather than failing the run."
        ),
    )
    parser.add_argument(
        "--transcription-tracks-dir",
        type=Path,
        default=DEFAULT_TRANSCRIPTION_TRACKS_DIR,
        help=(
            f"Directory holding local transcription reference tracks "
            f"(default: {DEFAULT_TRANSCRIPTION_TRACKS_DIR})"
        ),
    )
    parser.add_argument(
        "--html-report",
        type=Path,
        default=None,
        help=(
            "Also render an HTML accuracy report. Pass an explicit path or leave "
            "blank to use the dated default at .runtime/reports/accuracy_<stamp>.html. "
            "Use 'auto' to opt in with the default path explicitly."
        ),
        nargs="?",
        const="auto",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_phase1_evaluation(
        manifest_path=args.manifest,
        report_path=args.report,
        runs_per_fixture=max(args.runs, 1),
        include_real=args.include_real,
        real_tracks_dir=args.real_tracks_dir,
        include_transcription=args.include_transcription,
        transcription_tracks_dir=args.transcription_tracks_dir,
    )
    summary_line: dict[str, Any] = {
        "summary": report["summary"],
        "reportPath": report["reportPath"],
    }
    notes: list[str] = []
    if args.include_real and report["summary"]["realTracksSkipped"] > 0:
        notes.append(
            "Some real tracks were skipped because audio files were not present "
            f"in {args.real_tracks_dir}. See report for per-track skipReason."
        )
    if (
        args.include_transcription
        and report["summary"]["transcriptionTracksSkipped"] > 0
    ):
        notes.append(
            "Some transcription tracks were skipped because audio files were "
            f"not present in {args.transcription_tracks_dir}. See report for "
            "per-track skipReason."
        )
    if notes:
        summary_line["note"] = " ".join(notes)

    if args.html_report is not None:
        if isinstance(args.html_report, Path):
            html_path = args.html_report
        else:
            # const="auto" sentinel — use the dated default location alongside the JSON report.
            html_path = default_html_report_path(args.report.parent)
        html_written = render_html_report(report, html_path)
        summary_line["htmlReportPath"] = str(html_written)

    print(json.dumps(summary_line, indent=2))
    if not report["summary"]["allPassed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
