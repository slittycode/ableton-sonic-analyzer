"""Citation-accuracy evaluation for Phase 2 providers (gemini vs moss).

Research-only. Scores each provider's ``Phase2Result`` on the fixed
``tests/fixtures/recommendation_tracks/`` corpus by **reusing the production
validators** — not a parallel scorer:

  - ``server_phase2._validate_phase2_citation_paths`` → invented (non-resolving)
    cited paths. Citation accuracy = (cited − invented) / cited.
  - ``server_phase2._is_valid_phase2_shape`` → schema validity (the "identical
    schema" DoD, enforced on every provider's output).
  - ``server_phase2.apply_live12_catalogue_gates`` → device/parameter catalogue
    warnings (advisory).
  - grounding coverage = fraction of recommendations that cite ≥1 Phase 1 field
    (PURPOSE.md invariant #2: every recommendation cites, never invents).

The DoD's headline "offline-good-enough vs Gemini-wins" split needs BOTH
providers producing real output on the same set. Today that live comparison is
blocked (see ``docs/PHASE2_PROVIDER.md``): no ``GEMINI_API_KEY`` locally, no audio
renders in the corpus, and MOSS is not runnable under the STEP ONE licence gate.
So this harness runs whatever providers ARE available (always the deterministic
mock; Gemini/sidecar when supplied), computes the framework, and labels the
missing legs ``BLOCKED`` rather than fabricating numbers. The mock's accuracy is
~1.0 by construction — it proves the pipeline + scorer, not model quality.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from server_phase2 import (
    _is_valid_phase2_shape,
    _validate_phase2_citation_paths,
    apply_live12_catalogue_gates,
)

# Within-this-margin-of-Gemini counts as "offline-good-enough" for the split.
OFFLINE_GOOD_ENOUGH_MARGIN = 0.05

_CITATION_RECORD_PATHS = ("mixAndMasterChain", "abletonRecommendations")


def default_corpus_dir() -> Path:
    return Path(__file__).parent / "tests" / "fixtures" / "recommendation_tracks"


@dataclass
class CorpusTrack:
    track_id: str
    manifest: dict[str, Any]
    phase1: dict[str, Any]


def load_corpus(corpus_dir: Path | None = None) -> list[CorpusTrack]:
    root = corpus_dir or default_corpus_dir()
    tracks: list[CorpusTrack] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        manifest_path = entry / "manifest.json"
        fingerprint_path = entry / "phase1_fingerprint.json"
        if not manifest_path.is_file() or not fingerprint_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        phase1 = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        tracks.append(CorpusTrack(track_id=entry.name, manifest=manifest, phase1=phase1))
    return tracks


def _count_cited_paths(result: dict[str, Any]) -> tuple[int, int, int]:
    """Return (total_cited_paths, recommendations, recommendations_with_a_citation).

    Walks the same record sets ``_validate_phase2_citation_paths`` does for the
    recommendation surfaces, so "total cited" is the denominator that pairs with
    its invented-path warnings.
    """
    total_cited = 0
    rec_count = 0
    rec_with_cite = 0
    for key in _CITATION_RECORD_PATHS:
        items = result.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rec_count += 1
            fields = item.get("phase1Fields")
            cited = [f for f in fields if isinstance(f, str)] if isinstance(fields, list) else []
            total_cited += len(cited)
            if cited:
                rec_with_cite += 1
    return total_cited, rec_count, rec_with_cite


@dataclass
class TrackScore:
    track_id: str
    available: bool
    note: str = ""
    schema_valid: bool = False
    recommendation_count: int = 0
    cited_path_total: int = 0
    invented_path_count: int = 0
    grounding_coverage: float | None = None
    citation_accuracy: float | None = None
    catalogue_warning_count: int = 0


def score_result(
    track: CorpusTrack,
    result: dict[str, Any] | None,
    *,
    available: bool,
    note: str = "",
) -> TrackScore:
    if not available or result is None:
        return TrackScore(track_id=track.track_id, available=False, note=note or "no output")

    schema_valid = _is_valid_phase2_shape(result)
    invented = _validate_phase2_citation_paths(result, track.phase1)
    total_cited, rec_count, rec_with_cite = _count_cited_paths(result)
    try:
        catalogue_warnings = apply_live12_catalogue_gates(result, request_id=track.track_id)
    except Exception:  # advisory only — never fail a score on a catalogue error
        catalogue_warnings = []

    citation_accuracy = (
        (total_cited - len(invented)) / total_cited if total_cited else None
    )
    grounding_coverage = (rec_with_cite / rec_count) if rec_count else None

    return TrackScore(
        track_id=track.track_id,
        available=True,
        note=note,
        schema_valid=schema_valid,
        recommendation_count=rec_count,
        cited_path_total=total_cited,
        invented_path_count=len(invented),
        grounding_coverage=grounding_coverage,
        citation_accuracy=citation_accuracy,
        catalogue_warning_count=len(catalogue_warnings),
    )


# A provider function maps a track to (result | None, available, note).
ProviderFn = Callable[[CorpusTrack], "tuple[dict[str, Any] | None, bool, str]"]


@dataclass
class ProviderAggregate:
    provider: str
    available: bool
    blocked_reason: str = ""
    track_scores: list[TrackScore] = field(default_factory=list)

    def _mean(self, attr: str) -> float | None:
        values = [
            getattr(s, attr)
            for s in self.track_scores
            if s.available and getattr(s, attr) is not None
        ]
        return sum(values) / len(values) if values else None

    @property
    def mean_citation_accuracy(self) -> float | None:
        return self._mean("citation_accuracy")

    @property
    def mean_grounding_coverage(self) -> float | None:
        return self._mean("grounding_coverage")

    @property
    def schema_valid_rate(self) -> float | None:
        scored = [s for s in self.track_scores if s.available]
        return sum(1 for s in scored if s.schema_valid) / len(scored) if scored else None


def evaluate_provider(
    provider: str,
    provider_fn: ProviderFn,
    tracks: list[CorpusTrack],
    *,
    blocked_reason: str = "",
) -> ProviderAggregate:
    if blocked_reason:
        return ProviderAggregate(provider=provider, available=False, blocked_reason=blocked_reason)
    scores: list[TrackScore] = []
    any_available = False
    for track in tracks:
        result, available, note = provider_fn(track)
        any_available = any_available or available
        scores.append(score_result(track, result, available=available, note=note))
    return ProviderAggregate(
        provider=provider,
        available=any_available,
        blocked_reason="" if any_available else "no tracks produced output",
        track_scores=scores,
    )


def classify_split(
    baseline: ProviderAggregate | None,
    candidate: ProviderAggregate,
) -> dict[str, Any]:
    """The 'offline-good-enough vs Gemini-wins' verdict for one candidate.

    ``baseline`` is Gemini. If it is missing/unavailable the verdict is BLOCKED —
    the framework + threshold are reported, but no comparison is invented.
    """
    if baseline is None or not baseline.available or baseline.mean_citation_accuracy is None:
        return {
            "verdict": "BLOCKED",
            "reason": (
                "No Gemini baseline available "
                f"({baseline.blocked_reason if baseline else 'baseline not run'}). "
                "Provide GEMINI_API_KEY + audio renders, or recorded Gemini outputs."
            ),
            "marginUsed": OFFLINE_GOOD_ENOUGH_MARGIN,
        }
    if candidate.mean_citation_accuracy is None:
        return {"verdict": "BLOCKED", "reason": f"{candidate.provider} produced no scores."}
    delta = candidate.mean_citation_accuracy - baseline.mean_citation_accuracy
    verdict = "OFFLINE_GOOD_ENOUGH" if delta >= -OFFLINE_GOOD_ENOUGH_MARGIN else "GEMINI_WINS"
    return {
        "verdict": verdict,
        "candidateCitationAccuracy": candidate.mean_citation_accuracy,
        "baselineCitationAccuracy": baseline.mean_citation_accuracy,
        "delta": delta,
        "marginUsed": OFFLINE_GOOD_ENOUGH_MARGIN,
    }


def build_report(aggregates: list[ProviderAggregate]) -> dict[str, Any]:
    by_name = {a.provider: a for a in aggregates}
    baseline = by_name.get("gemini")
    splits = {
        a.provider: classify_split(baseline, a)
        for a in aggregates
        if a.provider != "gemini"
    }
    return {
        "corpusNote": (
            "Fixed recommendation_tracks corpus. The mock provider's citation "
            "accuracy is ~1.0 by construction (contract fixture, not a quality "
            "proxy). Live MOSS-vs-Gemini is blocked: see docs/PHASE2_PROVIDER.md."
        ),
        "offlineGoodEnoughMargin": OFFLINE_GOOD_ENOUGH_MARGIN,
        "providers": {
            a.provider: {
                "available": a.available,
                "blockedReason": a.blocked_reason,
                "meanCitationAccuracy": a.mean_citation_accuracy,
                "meanGroundingCoverage": a.mean_grounding_coverage,
                "schemaValidRate": a.schema_valid_rate,
                "tracks": [
                    {
                        "trackId": s.track_id,
                        "available": s.available,
                        "note": s.note,
                        "schemaValid": s.schema_valid,
                        "recommendationCount": s.recommendation_count,
                        "citedPathTotal": s.cited_path_total,
                        "inventedPathCount": s.invented_path_count,
                        "citationAccuracy": s.citation_accuracy,
                        "groundingCoverage": s.grounding_coverage,
                        "catalogueWarningCount": s.catalogue_warning_count,
                    }
                    for s in a.track_scores
                ],
            }
            for a in aggregates
        },
        "splitVerdicts": splits,
    }
