#!/usr/bin/env python3
"""Evaluate prescriptive loudness/dynamics recommendations.

Deterministic by default — no network, no API key. Two tiers:

* **L2 reachability** (this driver) — renders the *deterministic subset* of a
  recommendation (gain-to-target-LUFS, true-peak ceiling) and re-measures it with
  ASA's own Essentia analyzers (``loudness_rec_evaluation.measure_loudness_true_peak``).
  The analytic sub-checks run everywhere; the render sub-checks run only where
  Essentia is importable and SKIP cleanly otherwise.

* **L1 presence/consistency** of actual Gemini *output* lives in the frontend
  Vitest suite (``apps/ui/tests/services/loudnessGuardrails.test.ts`` and
  ``phase2Validator.test.ts``) because the guardrail is TypeScript. ``--include-gemini``
  here only prints how to run the live check; it does not call Gemini.

Run:  ./venv/bin/python scripts/evaluate_loudness_recs.py
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from loudness_rec_evaluation import (  # noqa: E402  (path bootstrap above)
    TRUE_PEAK_OVER_LINEAR,
    apply_gain,
    db_to_linear,
    evaluate_recommendation_reachability,
    gain_db_to_target,
    measure_loudness_true_peak,
    scale_to_true_peak_ceiling,
    synth_stereo_sine,
)

# ±0.5 LU reachability gate for the gain-to-target subset.
LUFS_TOLERANCE = 0.5
# truePeak is rounded to 1 decimal by analyze_true_peak, so the render check uses
# a coarse, unambiguous demo ceiling for "overs removed". The precise production
# ceiling (-0.3 dBFS ≈ 0.966 linear, which rounds to 1.0) is validated
# analytically instead.
RENDER_DEMO_CEILING_LINEAR = 0.7
RENDER_CEILING_ROUNDING_TOL = 0.05
# JSON_SCHEMA.md prescribes a -0.3 dB ceiling when clipping is measured.
PRODUCTION_CEILING_DBFS = -0.3

CheckResult = tuple[str, bool, str]  # (label, passed, note)


def run_analytic_checks() -> list[CheckResult]:
    """Reachability math — no audio rendered, runs everywhere."""
    results: list[CheckResult] = []

    # 1. Quiet master, modest target: pure gain reaches the target exactly.
    r = evaluate_recommendation_reachability(
        measured_lufs=-14.0, measured_true_peak_linear=0.5,
        target_lufs=-9.0, ceiling_dbfs=PRODUCTION_CEILING_DBFS,
    )
    ok = (not r.contradictory) and r.pure_gain_reaches_target and abs(r.final_lufs_estimate + 9.0) < 1e-6
    results.append(("analytic: headroom → pure gain reaches target", ok, r.note))

    # 2. Loud + nearly clipping, louder target: a peak limiter is required, but
    #    the target/ceiling pair is itself self-consistent (not contradictory).
    r = evaluate_recommendation_reachability(
        measured_lufs=-6.0, measured_true_peak_linear=0.99,
        target_lufs=-3.0, ceiling_dbfs=PRODUCTION_CEILING_DBFS,
    )
    ok = (not r.contradictory) and (not r.pure_gain_reaches_target) and r.limiting_required_db > 0.0
    results.append(("analytic: loud+over → limiter required, target self-consistent", ok, r.note))

    # 3. A ceiling above full scale would permit overs — must be flagged.
    r = evaluate_recommendation_reachability(
        measured_lufs=-9.0, measured_true_peak_linear=0.9,
        target_lufs=-9.0, ceiling_dbfs=1.0,
    )
    results.append((
        "analytic: ceiling above full scale flagged contradictory",
        r.contradictory,
        f"ceiling_linear={round(r.ceiling_linear, 3)} > full scale {TRUE_PEAK_OVER_LINEAR}",
    ))

    return results


def run_render_checks(sample_rate: int) -> list[CheckResult]:
    """Render + re-measure with the Essentia oracle. Requires Essentia."""
    results: list[CheckResult] = []

    # Gain-to-target: a quiet sine pushed toward a louder target that still has
    # headroom should land within ±0.5 LU and introduce no over.
    tone = synth_stereo_sine(peak_linear=0.25, duration_s=10.0, sample_rate=sample_rate)
    cur_lufs, _ = measure_loudness_true_peak(tone, sample_rate)
    if cur_lufs is None:
        results.append(("render: gain-to-target", False, "loudness measurement returned None"))
    else:
        target = round(cur_lufs + 6.0, 1)
        processed = apply_gain(tone, gain_db_to_target(cur_lufs, target))
        out_lufs, out_tp = measure_loudness_true_peak(processed, sample_rate)
        ok = (
            out_lufs is not None
            and abs(out_lufs - target) <= LUFS_TOLERANCE
            and out_tp is not None
            and out_tp <= TRUE_PEAK_OVER_LINEAR + 1e-9
        )
        results.append(
            (f"render: gain-to-target within ±{LUFS_TOLERANCE} LU", ok, f"got {out_lufs} LUFS vs target {target}, peak {out_tp}")
        )

    # True-peak removal: an over signal scaled to the demo ceiling has no overs.
    over = synth_stereo_sine(peak_linear=1.5, duration_s=2.0, sample_rate=sample_rate)
    _, over_tp = measure_loudness_true_peak(over, sample_rate)
    if over_tp is None:
        results.append(("render: true-peak ceiling holds", False, "true-peak measurement returned None"))
    else:
        limited = scale_to_true_peak_ceiling(over, over_tp, RENDER_DEMO_CEILING_LINEAR)
        _, lim_tp = measure_loudness_true_peak(limited, sample_rate)
        ok = (
            lim_tp is not None
            and lim_tp <= RENDER_DEMO_CEILING_LINEAR + RENDER_CEILING_ROUNDING_TOL
            and lim_tp < over_tp
        )
        results.append(
            (f"render: true-peak ceiling holds (≤ {RENDER_DEMO_CEILING_LINEAR})", ok, f"over {over_tp} → limited {lim_tp}")
        )

    return results


def _print_section(title: str, results: list[CheckResult]) -> bool:
    print(f"\n{title}")
    all_ok = True
    for label, ok, note in results:
        status = "PASS" if ok else "FAIL"
        suffix = f"  ({note})" if note else ""
        print(f"  [{status}] {label}{suffix}")
        all_ok = all_ok and ok
    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-rate", type=int, default=44_100)
    parser.add_argument(
        "--include-gemini",
        action="store_true",
        help="Print how to run the live-Gemini L1 check (does not call Gemini).",
    )
    args = parser.parse_args()

    passed = _print_section("L2 analytic reachability", run_analytic_checks())

    if importlib.util.find_spec("essentia") is not None:
        passed = _print_section("L2 render + re-measure (Essentia oracle)", run_render_checks(args.sample_rate)) and passed
    else:
        print("\nL2 render + re-measure (Essentia oracle)")
        print("  [SKIP] Essentia not importable — analytic checks above still gate reachability.")

    if args.include_gemini:
        print("\nL1 live-Gemini presence/consistency")
        print("  Deterministic L1 runs in the frontend Vitest suite:")
        print("    cd apps/ui && npx vitest run tests/services/loudnessGuardrails.test.ts tests/services/phase2Validator.test.ts")
        print("  For real Gemini output, use the live smoke path (needs GEMINI_API_KEY):")
        print("    RUN_GEMINI_LIVE_SMOKE=true npm run test:smoke")

    print(f"\n{'OK: all loudness recommendation checks passed.' if passed else 'FAIL: one or more checks failed.'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
