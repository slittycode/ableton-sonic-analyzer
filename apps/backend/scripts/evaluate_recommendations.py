#!/usr/bin/env python3
"""Score ASA's Phase 2 recommendations against the ground-truth corpus.

EVAL / RESEARCH ONLY (mirrors scripts/evaluate_*.py). Off the product path;
deleting this and ``recommendation_evaluation.py`` restores the product exactly.

This is the harness core of GOAL.md's recommendation-proof campaign. It loads the
fixtures under ``tests/fixtures/recommendation_tracks/``, validates each spec is
catalog-valid (the always-runnable half of ingest), pulls recommendations from a
chosen **source**, and scores how well they recover the known device settings.

The ``--source`` switch is the mechanism sub-goal 3 needs to compare three
recommendation sources on the same corpus:

  * ``baseline``      — trivial no-op source (empty rec set). Runs now, no deps.
                        The floor any real source must clear.
  * ``gemini``        — score a stored ``Phase2Result`` JSON (``--phase2`` or a
                        sibling ``phase2.json`` in the fixture dir). Either a bare
                        result or a ``phase2-export.v1`` envelope downloaded from
                        ``GET /api/analysis-runs/{run_id}/export/phase2`` works.
                        Producing it live needs GEMINI_API_KEY + rendered audio
                        (needs-fixture).
  * ``deterministic`` — score the ``abletonDevices.ts`` path. Wiring the node
                        bridge that emits normalized recs from a real Phase 1
                        fingerprint is a documented follow-on (NEEDS.md); until
                        then pass a pre-normalized rec list via ``--recommendations``.

Any source can also be fed a pre-normalized rec list (``--recommendations``) — a
JSON array of ``{domain, device, parameter, value, citations, family}`` — which
is the universal seam each adapter targets.

Examples:
  ./venv/bin/python scripts/evaluate_recommendations.py --self-test
  ./venv/bin/python scripts/evaluate_recommendations.py --source baseline
  ./venv/bin/python scripts/evaluate_recommendations.py --fixture house_sidechain_pluck_124 \\
      --source gemini --phase2 /tmp/phase2.json --report /tmp/rec_eval.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import recommendation_evaluation as rev  # noqa: E402  (path bootstrap above)

DEFAULT_CORPUS_DIR = BACKEND_DIR / "tests" / "fixtures" / "recommendation_tracks"


def _load_normalized_recs(path: Path) -> list[rev.NormalizedRec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    recs = []
    for item in raw:
        recs.append(
            rev.NormalizedRec(
                domain=item.get("domain", rev.UNKNOWN_DOMAIN),
                device=item.get("device", ""),
                parameter=item.get("parameter"),
                value=item.get("value"),
                citations=tuple(item.get("citations", [])),
                family=item.get("family"),
            )
        )
    return recs


def _resolve_recs(
    fixture: rev.Fixture,
    source: str,
    phase2_path: Path | None,
    recs_path: Path | None,
) -> tuple[list[rev.NormalizedRec] | None, str]:
    """Return (recs, note). ``recs is None`` means SKIP with the given reason."""
    if recs_path is not None:
        return _load_normalized_recs(recs_path), f"normalized recs from {recs_path.name}"

    if source == "baseline":
        return rev.normalize_baseline(fixture), "trivial baseline (empty)"

    if source == "gemini":
        candidate = phase2_path
        if candidate is None and fixture.source_path is not None:
            sibling = fixture.source_path.parent / "phase2.json"
            candidate = sibling if sibling.exists() else None
        if candidate is None or not candidate.exists():
            return None, "no Phase2Result JSON (pass --phase2 or drop phase2.json in the fixture dir)"
        phase2 = rev.coerce_phase2_payload(
            json.loads(candidate.read_text(encoding="utf-8"))
        )
        return rev.normalize_phase2(phase2), f"Phase2Result from {candidate.name}"

    if source == "deterministic":
        if fixture.source_path is not None:
            sibling = fixture.source_path.parent / "recommendations.deterministic.json"
            if sibling.exists():
                return _load_normalized_recs(sibling), f"deterministic recs from {sibling.name}"
        return None, "deterministic adapter not wired yet — see NEEDS.md (node bridge / --recommendations)"

    return None, f"unknown source '{source}'"


def _print_score(score: rev.RecommendationScore) -> None:
    print(f"  aggregate {score.aggregate:.3f}  (raw {score.raw_aggregate:.3f}, "
          f"custody penalty {score.custody.penalty:.3f})")
    for domain in rev.DOMAINS:
        ds = score.domain_scores.get(domain)
        if ds is None:
            continue
        print(
            f"    {domain:<8} recall {ds.role_recall:.2f}  prec {ds.role_precision:.2f}  "
            f"params {ds.parameter_coverage:.2f}  values {ds.value_accuracy:.2f}  "
            f"-> {ds.score:.3f}"
        )


def run_self_test() -> int:
    """Always-runnable demonstration that the score moves on a known-bad rec.

    Mirrors the synthetic gate in evaluate_phase1.py — gives a meaningful PASS/
    FAIL even with zero rendered audio in the corpus.
    """
    fixture = rev.Fixture(
        slug="self-test",
        title="self-test",
        genre="house",
        audio_path=None,
        device_spec={
            "kick": (
                rev.SpecDevice("Operator", "NATIVE",
                               (rev.SpecParameter("Amp Envelope Decay", "250 ms"),)),
            ),
            "master": (
                rev.SpecDevice("Glue Compressor", "NATIVE",
                               (rev.SpecParameter("Ratio", "2:1"),)),
            ),
        },
        measurable_intent=(),
        phase1_fingerprint={"kickDetail": {"fundamentalHz": 55.0}, "lufsIntegrated": -9.0},
        render={},
    )
    good = rev.score_recommendations(fixture, [
        rev.NormalizedRec("kick", "Operator", "Amp Envelope Decay", "240 ms", ("kickDetail.fundamentalHz",)),
        rev.NormalizedRec("master", "Compressor", "Ratio", "2:1", ("lufsIntegrated",)),
    ], "good")
    bad = rev.score_recommendations(fixture, [
        rev.NormalizedRec("kick", "Reverb", "Decay Time", "2 s", ()),
    ], "bad")

    print("Self-test: good vs known-bad recommendation set")
    print(f"  good aggregate {good.aggregate:.3f}")
    print(f"  bad  aggregate {bad.aggregate:.3f}")
    passed = good.aggregate > bad.aggregate and good.aggregate > 0.7 and bad.aggregate < 0.2
    print(f"  [{'PASS' if passed else 'FAIL'}] score moves correctly and equivalence credit holds")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["baseline", "gemini", "deterministic"],
                        default="baseline", help="recommendation source to score")
    parser.add_argument("--fixture", help="limit to one fixture slug")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--phase2", type=Path, help="Phase2Result JSON for --source gemini")
    parser.add_argument("--recommendations", type=Path,
                        help="pre-normalized rec list JSON (overrides --source resolution)")
    parser.add_argument("--report", type=Path, help="write a markdown report to this path")
    parser.add_argument("--verification-artifact", type=Path,
                        help="write the per-domain corpus-verification artifact (UI badge source) to this path")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON to stdout")
    parser.add_argument("--self-test", action="store_true",
                        help="run the synthetic good-vs-bad gate and exit")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    manifests = sorted(args.corpus_dir.glob("*/manifest.json"))
    if args.fixture:
        manifests = [m for m in manifests if m.parent.name == args.fixture]
    if not manifests:
        print(f"No fixtures found under {args.corpus_dir}", file=sys.stderr)
        return 1

    scores: list[rev.RecommendationScore] = []
    any_failure = False
    for manifest in manifests:
        fixture = rev.load_fixture(manifest)
        print(f"\n{fixture.slug}  ({fixture.genre})  source={args.source}")

        issues = rev.validate_fixture_spec(fixture)
        if issues:
            any_failure = True
            print(f"  [FAIL] spec not catalog-valid ({len(issues)} issue(s)):")
            for issue in issues:
                print(f"    - [{issue.domain}] {issue.device}/{issue.parameter}: {issue.message}")
            continue
        print("  [OK] spec catalog-valid")

        if fixture.phase1_fingerprint is None:
            print("  [note] no Phase 1 fingerprint — citation path-validity will SKIP "
                  "(render the audio and store phase1_fingerprint.json; see NEEDS.md)")

        recs, note = _resolve_recs(fixture, args.source, args.phase2, args.recommendations)
        if recs is None:
            print(f"  [SKIP] {note}")
            continue
        print(f"  scoring: {note}")
        score = rev.score_recommendations(fixture, recs, args.source)
        scores.append(score)
        _print_score(score)

    if args.report and scores:
        args.report.write_text(rev.render_markdown_report(scores), encoding="utf-8")
        print(f"\nReport written to {args.report}")

    if args.verification_artifact:
        artifact = rev.aggregate_corpus_verification(scores)
        args.verification_artifact.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print(f"Verification artifact written to {args.verification_artifact}")

    if args.json:
        print(json.dumps([s.as_dict() for s in scores], indent=2))

    return 1 if any_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
