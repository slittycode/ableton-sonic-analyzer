#!/usr/bin/env python3
"""CLI for the beat/downbeat measurement gate (see beat_evaluation.py).

Research-only. Examples:

  # product venv, no new deps (stride vs kick_accent, hand-rolled metrics):
  ./venv/bin/python scripts/evaluate_beats.py \
      --manifest tests/fixtures/beat_eval_manifest.json --methods stride,kick_accent

  # eval venv (adds mir_eval + beat_this), full A/B + HTML:
  ./venv-eval/bin/python scripts/evaluate_beats.py \
      --manifest tests/fixtures/beat_eval_manifest.json --html

  # meter-isolation diagnostic run (feeds annotated meter to kick_accent):
  ./venv-eval/bin/python scripts/evaluate_beats.py \
      --manifest tests/fixtures/beat_eval_manifest.json --use-annotated-meter \
      --report .runtime/beat_eval/beat_eval_annotated.json
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from beat_evaluation import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REPORT_PATH,
    run_beat_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Beat/downbeat measurement gate (research-only).")
    parser.add_argument("--manifest", type=Path, required=True, help="Path to the beat-eval manifest JSON.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help="Where to write the JSON report.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Artifact output directory.")
    parser.add_argument(
        "--methods",
        type=str,
        default="stride,kick_accent,beat_this",
        help="Comma-separated subset of stride,kick_accent,beat_this.",
    )
    parser.add_argument(
        "--use-annotated-meter",
        action="store_true",
        help="Feed kick_accent the annotated meter (isolates phase from meter-detection error).",
    )
    parser.add_argument("--beat-this-checkpoint", type=str, default="final0", help="beat_this checkpoint name.")
    parser.add_argument("--html", action="store_true", help="Also render an HTML report next to the JSON.")
    args = parser.parse_args()

    methods = tuple(m.strip() for m in args.methods.split(",") if m.strip())
    report = run_beat_evaluation(
        manifest_path=args.manifest,
        report_path=args.report,
        output_dir=args.output_dir,
        methods=methods,
        use_annotated_meter=args.use_annotated_meter,
        beat_this_checkpoint=args.beat_this_checkpoint,
    )

    if args.html:
        try:
            from beat_report_html import default_html_report_path, render_beat_report

            html_path = render_beat_report(report, default_html_report_path(Path(args.output_dir)))
            report["htmlPath"] = str(html_path)
        except Exception as exc:  # noqa: BLE001 — HTML is best-effort
            print(f"[warn] HTML report failed: {exc}", file=sys.stderr)

    summary = {
        "metricsBackend": report["metricsBackend"],
        "evaluatedClipCount": report["evaluatedClipCount"],
        "asaRelevantClipCount": report["asaRelevantClipCount"],
        "gate": report["gate"],
        "reportPath": report.get("reportPath"),
        "htmlPath": report.get("htmlPath"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
