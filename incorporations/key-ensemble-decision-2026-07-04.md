# Key-ensemble decision record (pre-registration)

**Status: PENDING — gate not yet run (awaiting GiantSteps Key audio).**

Accuracy program PR-B3. Records — *before* the deciding run — the rule for
whether ASA's shipped key label should switch from EDMA-alone to a
multi-profile vote. Pre-registered so the outcome can't be rationalised after
seeing the numbers.

## What shipped in PR-B3 (surfacing-only)

`analyze_key` now runs `KeyExtractor` for three profiles — `edma`,
`temperley`, `krumhansl` — in full mode and emits an additive, full-only
`keyEnsemble` field: `{method: "profile_vote.v1", agreement, profiles[],
alternates[]}`. **The shipped `key`/`keyConfidence`/`keyProfile` are
unchanged — still EDMA.** The vote is evidence only until this gate passes.

## The measurement

Run `scripts/evaluate_giantsteps.py --subset key` (GiantSteps Key: ~600
expert-annotated Beatport clips) twice:

1. **Baseline** — the shipped EDMA label.
2. **Vote** — a candidate rule that resolves the label from the three
   profiles: majority-exact wins; no majority → EDMA stays.

Metrics: MIREX weighted key score (`giantsteps_evaluation.mirex_key_score`),
exact rate, exact-or-relative rate.

## Frozen decision rule

**Adopt the vote as the shipped label iff BOTH:**

1. `mirexWeighted(vote) − mirexWeighted(edma) ≥ +0.02` (a real ≥2-point gain
   on the 0–1 MIREX scale), AND
2. `keyExactRate(vote) ≥ keyExactRate(edma) − 0.01` (no exact-match
   regression beyond noise).

Otherwise **keep EDMA** as the shipped label; `keyEnsemble` stays a
surfacing-only cross-check (still useful: `agreement` calibrates confidence,
`alternates` hedge the UI).

**Power:** GiantSteps Key has ~604 clips; require ≥ 400 evaluable (audio
present) or the run is `underpowered` and must not be finalised.

## If adopted

Switch the shipped `key` to the vote result, set `keyProfile` to the winning
profile (or `"profile_vote.v1"`), recalibrate `keyConfidence` from
`(agreement, winning strength)`, re-baseline the golden (curated value), and
sync the frontend parity fixture. Record the numbers here.
