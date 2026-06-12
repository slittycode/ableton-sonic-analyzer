#!/usr/bin/env python3
"""Generate Claude-provider Phase 2 recommendations for the ground-truth corpus.

EVAL / RESEARCH ONLY (mirrors scripts/evaluate_*.py). Off the product path;
deleting this restores the product exactly.

For each fixture under ``tests/fixtures/recommendation_tracks/`` that has a
stored ``phase1_fingerprint.json``, this runs the producer_summary interpretation
through the EXACT server path (``server._run_interpretation_request``) with
``ASA_PHASE2_PROVIDER=claude`` — the text-only Claude Code CLI provider — and
writes the fully validated ``Phase2Result`` (including ``validationWarnings``
and the ``recommendations.v1`` envelope) to ``phase2.claude.json`` in the
fixture dir, where ``evaluate_recommendations.py --source claude`` picks it up.

Zero Gemini cost: the Claude provider grounds entirely on the prompt's embedded
Phase 1 JSON and never receives audio, so missing renders are fine — this is
what makes a provider comparison possible on the pre-render corpus. Needs a
logged-in Claude Code CLI (``ASA_CLAUDE_CLI``/``ASA_CLAUDE_MODEL``/
``ASA_CLAUDE_TIMEOUT_SECONDS`` are honored as usual). Expect ~6 minutes per
fixture on the CLI default model.

Examples:
  ./venv/bin/python scripts/gen_claude_phase2.py --fixture acid_303_128
  ./venv/bin/python scripts/gen_claude_phase2.py            # all fingerprinted fixtures
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The provider seam resolves at call time, but set it before importing server so
# a partially-imported Gemini path can never be selected by mistake.
os.environ["ASA_PHASE2_PROVIDER"] = "claude"
# Headless-run defaults learned from the 2026-06-11 scoring run (overridable):
# a thinking-enabled model spends the whole timeout deliberating before the
# structured output starts, and the provider's 600s default assumes no thinking.
# With thinking off, sonnet measured 300-365s per fixture.
os.environ.setdefault("MAX_THINKING_TOKENS", "0")
os.environ.setdefault("ASA_CLAUDE_TIMEOUT_SECONDS", "1800")

import server  # noqa: E402  (path bootstrap + env above)

DEFAULT_CORPUS_DIR = BACKEND_DIR / "tests" / "fixtures" / "recommendation_tracks"
OUTPUT_NAME = "phase2.claude.json"


def _card_counts(result: dict) -> str:
    recs = result.get("abletonRecommendations") or []
    chain = result.get("mixAndMasterChain") or []
    secret = (result.get("secretSauce") or {}).get("workflowSteps") or []
    warnings = result.get("validationWarnings") or []
    envelope = (result.get("recommendations") or {}).get("recommendations") or []
    return (
        f"{len(recs)} rec cards, {len(chain)} chain cards, {len(secret)} workflow steps, "
        f"{len(envelope)} envelope entries, {len(warnings)} validation warnings"
    )


def generate_for_fixture(fixture_dir: Path) -> bool:
    slug = fixture_dir.name
    fingerprint_path = fixture_dir / "phase1_fingerprint.json"
    if not fingerprint_path.exists():
        print(f"[skip] {slug}: no phase1_fingerprint.json (spec-only fixture)")
        return True
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))

    audio_path = fixture_dir / "audio.flac"
    file_size = audio_path.stat().st_size if audio_path.exists() else 0

    model_label = os.getenv("ASA_CLAUDE_MODEL", "").strip() or "(CLI default)"
    print(f"[run]  {slug}: claude provider, model {model_label} ...", flush=True)
    started = time.monotonic()
    execution = server._run_interpretation_request(
        source_path=str(audio_path),
        filename="audio.flac",
        file_size_bytes=file_size,
        profile_id="producer_summary",
        measurement_result=fingerprint,
        pitch_note_result=None,
        grounding_metadata={"profileId": "producer_summary"},
        model_name="claude-cli",
        request_id=f"claude-rec-eval-{slug}",
    )
    elapsed = time.monotonic() - started

    if not execution.get("ok"):
        print(
            f"[FAIL] {slug}: {execution.get('errorCode')}: {execution.get('message')} "
            f"({elapsed:.0f}s)"
        )
        return False
    result = execution.get("interpretationResult")
    if not isinstance(result, dict):
        print(f"[FAIL] {slug}: provider returned no interpretation result ({elapsed:.0f}s)")
        return False

    out_path = fixture_dir / OUTPUT_NAME
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"[OK]   {slug}: {_card_counts(result)} -> {out_path.name} ({elapsed:.0f}s)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fixture", help="limit to one fixture slug")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    args = parser.parse_args()

    fixture_dirs = sorted(
        path.parent for path in args.corpus_dir.glob("*/manifest.json")
        if not path.parent.name.startswith("_")
    )
    if args.fixture:
        fixture_dirs = [d for d in fixture_dirs if d.name == args.fixture]
        if not fixture_dirs:
            print(f"no fixture named {args.fixture!r} under {args.corpus_dir}")
            return 2

    ok = True
    for fixture_dir in fixture_dirs:
        ok = generate_for_fixture(fixture_dir) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
