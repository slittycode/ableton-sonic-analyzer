"""Pre-registered key-ensemble decision gate (accuracy program PR-B3).

Implements the frozen decision rule in
``incorporations/key-ensemble-decision-2026-07-04.md``: run the full analyze
pipeline over GiantSteps Key, score the shipped EDMA label (baseline) against a
three-profile majority vote resolved from the full-only ``keyEnsemble`` field,
and apply the pre-registered rule for whether the vote should become the
shipped label.

Research-only — not on the product path. Driven by
``scripts/run_key_ensemble_gate.py``; corpus fetched locally by the operator
via ``scripts/fetch_giantsteps.py`` (audio is Beatport's and never committed).

The vote is evaluated from the same full-mode analyze pass that produces the
EDMA baseline, so the two labels are scored against identical measurement
conditions — the fair A/B the pre-registration requires.
"""

from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from giantsteps_evaluation import (
    DEFAULT_REPORT_DIR,
    GiantstepsClip,
    Runner,
    _run_analyze,
    mirex_key_score,
)

# --- Frozen decision-rule constants (see the pre-registration doc) ---------
# Adopt the vote as the shipped label iff BOTH hold:
MIREX_GAIN_MIN = 0.02            # mirexWeighted(vote) - mirexWeighted(edma) >= +0.02
EXACT_REGRESSION_TOLERANCE = 0.01  # keyExactRate(vote) >= keyExactRate(edma) - 0.01
# Power floor: below this many evaluable clips the run is underpowered and must
# not be finalised (GiantSteps Key ships ~604 clips).
MIN_EVALUABLE = 400


def resolve_vote(profiles: list[dict[str, Any]], edma_key: str | None) -> str | None:
    """Resolve the candidate label from the ensemble profiles.

    Frozen rule: majority-exact wins; no majority -> EDMA stays. With the three
    shipped profiles (edma, temperley, krumhansl) a majority is >= 2 exact
    agreements; ties or all-distinct reads keep the EDMA label.
    """
    keys = [p.get("key") for p in profiles if isinstance(p.get("key"), str)]
    if not keys:
        return edma_key
    top_key, top_count = Counter(keys).most_common(1)[0]
    return top_key if top_count * 2 > len(keys) else edma_key


def _score_labels(pairs: list[tuple[str, str | None]]) -> dict[str, float]:
    """MIREX weighted score + exact rate over (expected, label) pairs."""
    scores = [mirex_key_score(expected, label) for expected, label in pairs]
    n = len(scores)
    if n == 0:
        return {"mirexWeighted": 0.0, "keyExactRate": 0.0, "count": 0}
    return {
        "mirexWeighted": round(sum(scores) / n, 4),
        "keyExactRate": round(sum(1 for s in scores if s == 1.0) / n, 4),
        "count": n,
    }


def apply_decision_rule(edma: dict[str, float], vote: dict[str, float], evaluable: int) -> dict[str, Any]:
    """Apply the frozen rule; returns the decision block."""
    mirex_gain = round(vote["mirexWeighted"] - edma["mirexWeighted"], 4)
    exact_delta = round(vote["keyExactRate"] - edma["keyExactRate"], 4)
    gain_ok = mirex_gain >= MIREX_GAIN_MIN
    no_regression = vote["keyExactRate"] >= edma["keyExactRate"] - EXACT_REGRESSION_TOLERANCE
    underpowered = evaluable < MIN_EVALUABLE
    adopt = gain_ok and no_regression and not underpowered
    if underpowered:
        decision = "underpowered"
    elif adopt:
        decision = "adopt_vote"
    else:
        decision = "keep_edma"
    return {
        "decision": decision,
        "adopt": adopt,
        "underpowered": underpowered,
        "mirexGain": mirex_gain,
        "mirexGainRequired": MIREX_GAIN_MIN,
        "mirexGainMet": gain_ok,
        "exactDelta": exact_delta,
        "exactRegressionTolerance": EXACT_REGRESSION_TOLERANCE,
        "exactNoRegression": no_regression,
        "evaluable": evaluable,
        "minEvaluable": MIN_EVALUABLE,
    }


def run_gate(
    clips: list[GiantstepsClip],
    *,
    runner: Runner | None = None,
    max_clips: int | None = None,
    report_path: Path | None = None,
    jobs: int = 1,
) -> dict[str, Any]:
    """Run the full-mode analyze pass and evaluate the pre-registered gate.

    ``jobs`` parallelises the per-clip full analyze across a thread pool (the
    work runs in the analyzer subprocesses); scoring stays sequential and in
    corpus order, so the decision is identical to ``jobs=1``. Full mode over the
    120 s GiantSteps previews is otherwise multi-hour.
    """
    if runner is None:
        runner = _run_analyze

    selected = clips[:max_clips] if max_clips else clips

    def _run_one(clip: GiantstepsClip) -> tuple[GiantstepsClip, str, Any]:
        if not clip.expected_key:
            return clip, "no_annotation", None
        if not clip.audio_path.exists():
            return clip, "missing_audio", None
        try:
            return clip, "ok", runner(clip.audio_path, None)  # full mode -> keyEnsemble
        except Exception as exc:  # noqa: BLE001 — record and continue
            return clip, "analyze_failed", str(exc)[-300:]

    if jobs and jobs > 1:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            outcomes = list(pool.map(_run_one, selected))
    else:
        outcomes = [_run_one(clip) for clip in selected]

    edma_pairs: list[tuple[str, str | None]] = []
    vote_pairs: list[tuple[str, str | None]] = []
    per_clip: list[dict[str, Any]] = []
    missing_audio = 0
    analyze_failed = 0
    no_ensemble = 0
    vote_flips = 0

    for clip, status, data in outcomes:
        if status == "no_annotation":
            per_clip.append({"id": clip.clip_id, "status": "no_annotation"})
            continue
        if status == "missing_audio":
            missing_audio += 1
            per_clip.append({"id": clip.clip_id, "status": "missing_audio"})
            continue
        if status == "analyze_failed":
            analyze_failed += 1
            per_clip.append({"id": clip.clip_id, "status": "analyze_failed", "error": data})
            continue
        payload = data

        edma_label = payload.get("key") if isinstance(payload.get("key"), str) else None
        ensemble = payload.get("keyEnsemble")
        profiles = ensemble.get("profiles", []) if isinstance(ensemble, dict) else []
        if not profiles:
            no_ensemble += 1
        vote_label = resolve_vote(profiles, edma_label)

        edma_pairs.append((clip.expected_key, edma_label))
        vote_pairs.append((clip.expected_key, vote_label))
        flipped = vote_label != edma_label
        vote_flips += int(flipped)
        per_clip.append(
            {
                "id": clip.clip_id,
                "status": "evaluated",
                "expectedKey": clip.expected_key,
                "edmaKey": edma_label,
                "voteKey": vote_label,
                "voteFlipped": flipped,
                "edmaMirex": mirex_key_score(clip.expected_key, edma_label),
                "voteMirex": mirex_key_score(clip.expected_key, vote_label),
            }
        )

    evaluable = len(edma_pairs)
    edma_scores = _score_labels(edma_pairs)
    vote_scores = _score_labels(vote_pairs)
    decision = apply_decision_rule(edma_scores, vote_scores, evaluable)

    summary = {
        "subset": "key",
        "clipsListed": len(selected),
        "clipsEvaluable": evaluable,
        "clipsMissingAudio": missing_audio,
        "clipsAnalyzeFailed": analyze_failed,
        "clipsNoEnsemble": no_ensemble,
        "voteFlips": vote_flips,
        "edma": edma_scores,
        "vote": vote_scores,
        **decision,
    }
    report = {
        "schemaVersion": "key-ensemble-gate-report.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "clips": per_clip,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["reportPath"] = str(report_path)
    return report


DEFAULT_GATE_REPORT = DEFAULT_REPORT_DIR / "key_ensemble_gate.json"
