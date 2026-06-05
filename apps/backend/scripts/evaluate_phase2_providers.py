#!/usr/bin/env python3
"""Citation-accuracy eval: Phase 2 providers (gemini vs moss) on the fixed corpus.

Research-only harness for the Phase2Provider goal's DoD. Wraps
``phase2_provider_evaluation.py`` (which reuses the production validators). Runs
the always-available deterministic mock, plus Gemini and/or a live MOSS sidecar
when you supply them, and prints the "offline-good-enough vs Gemini-wins" split
(labelled BLOCKED for any leg that can't run — never fabricated).

Examples:
    # Mock only (always works; proves the pipeline + scorer):
    ./venv/bin/python scripts/evaluate_phase2_providers.py

    # Score a live MOSS sidecar (start it first, see moss_sidecar/README.md):
    ./venv/bin/python scripts/evaluate_phase2_providers.py --sidecar-url http://127.0.0.1:8200

    # Compare against recorded Gemini outputs (one <track_id>.json per track):
    ./venv/bin/python scripts/evaluate_phase2_providers.py --recorded-gemini-dir /path/to/gemini_outputs

    # Write the full JSON report:
    ./venv/bin/python scripts/evaluate_phase2_providers.py --out .runtime/phase2_providers_report.json

See docs/PHASE2_PROVIDER.md for why the live MOSS-vs-Gemini numbers are currently
blocked (licence gate, no Gemini key, no audio renders).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from moss_sidecar.mock_interpreter import build_mock_phase2_result  # noqa: E402
from phase2_provider_evaluation import (  # noqa: E402
    CorpusTrack,
    build_report,
    evaluate_provider,
    load_corpus,
)


def _mock_provider(track: CorpusTrack):
    return build_mock_phase2_result(track.phase1), True, "deterministic mock"


def _recorded_gemini_provider_factory(recorded_dir: Path):
    def _fn(track: CorpusTrack):
        path = recorded_dir / f"{track.track_id}.json"
        if not path.is_file():
            return None, False, f"no recorded output at {path.name}"
        try:
            return json.loads(path.read_text(encoding="utf-8")), True, "recorded"
        except (ValueError, OSError) as exc:
            return None, False, f"unreadable recorded output: {exc}"

    return _fn


def _sidecar_provider_factory(sidecar_url: str):
    import requests

    def _fn(track: CorpusTrack):
        try:
            response = requests.post(
                f"{sidecar_url.rstrip('/')}/v1/phase2",
                json={
                    "prompt": "",
                    "response_schema": {},
                    "phase1": track.phase1,
                    "model": "moss-audio",
                    "audio": None,
                },
                timeout=180,
            )
        except requests.RequestException as exc:
            return None, False, f"sidecar unreachable: {exc}"
        if response.status_code != 200:
            return None, False, f"sidecar HTTP {response.status_code}"
        result = response.json().get("result")
        return result, result is not None, "live sidecar"

    return _fn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=None)
    parser.add_argument(
        "--recorded-gemini-dir",
        type=Path,
        default=None,
        help="Directory with one <track_id>.json recorded Gemini Phase2Result per track.",
    )
    parser.add_argument(
        "--sidecar-url",
        type=str,
        default=None,
        help="Base URL of a running MOSS sidecar to score (e.g. http://127.0.0.1:8200).",
    )
    parser.add_argument("--out", type=Path, default=None, help="Write the full JSON report here.")
    args = parser.parse_args(argv)

    tracks = load_corpus(args.corpus_dir)
    if not tracks:
        print("No corpus tracks found.", file=sys.stderr)
        return 1

    aggregates = [evaluate_provider("moss-mock", _mock_provider, tracks)]

    # Gemini baseline: recorded outputs if provided, else BLOCKED with the reason.
    if args.recorded_gemini_dir is not None:
        aggregates.append(
            evaluate_provider(
                "gemini",
                _recorded_gemini_provider_factory(args.recorded_gemini_dir),
                tracks,
            )
        )
    else:
        reason = (
            "no --recorded-gemini-dir and live Gemini not run by this harness"
            + ("" if os.getenv("GEMINI_API_KEY") else "; GEMINI_API_KEY unset")
            + "; corpus has no audio renders"
        )
        aggregates.append(
            evaluate_provider("gemini", _mock_provider, tracks, blocked_reason=reason)
        )

    if args.sidecar_url:
        aggregates.append(
            evaluate_provider(
                "moss-sidecar", _sidecar_provider_factory(args.sidecar_url), tracks
            )
        )

    report = build_report(aggregates)

    print(f"\nPhase 2 provider eval — {len(tracks)} tracks\n" + "=" * 52)
    for name, data in report["providers"].items():
        if not data["available"]:
            print(f"  {name:<13} BLOCKED — {data['blockedReason']}")
            continue
        acc = data["meanCitationAccuracy"]
        cov = data["meanGroundingCoverage"]
        valid = data["schemaValidRate"]
        print(
            f"  {name:<13} schemaValid={_pct(valid)}  "
            f"citationAccuracy={_pct(acc)}  groundingCoverage={_pct(cov)}"
        )
    print("\nSplit verdicts (offline-good-enough vs Gemini-wins):")
    for name, verdict in report["splitVerdicts"].items():
        print(f"  {name:<13} {verdict['verdict']}"
              + (f" — {verdict['reason']}" if verdict.get("reason") else ""))

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nFull report → {args.out}")
    return 0


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


if __name__ == "__main__":
    raise SystemExit(main())
