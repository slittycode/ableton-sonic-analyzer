# Key-ensemble decision record (pre-registration)

**Status: DECIDED 2026-07-05 — KEEP EDMA. The vote failed both frozen bars on
GiantSteps Key (604/604 evaluable). `keyEnsemble` stays surfacing-only.** See
[Result](#result-2026-07-05).

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

## Result (2026-07-05)

Ran against the full GiantSteps Key corpus fetched locally (604 annotations,
**604/604 with audio present** via the JKU preview mirror — the 2015 Beatport
sample host is dead, all 404). Full-mode analyze so the `keyEnsemble`
cross-check is populated; the EDMA baseline and the vote are scored from the
**same** run (the fair A/B the pre-registration requires).

| Metric | EDMA (baseline) | Vote (candidate) | Δ (vote − edma) |
|---|---|---|---|
| MIREX weighted | **0.6505** | 0.6336 | **−0.0169** |
| Exact rate | **0.5762** | 0.5480 | **−0.0282** |
| Exact-or-relative | 0.6391 | — | — |

The vote flipped the label on **48 / 604** clips (the cases where temperley +
krumhansl agreed against EDMA); on net those flips were **wrong more often than
right** — unsurprising, since EDMA is the profile tuned for electronic dance
music and GiantSteps is EDM, while temperley/krumhansl are classical-corpus
profiles.

**Frozen rule applied verbatim:**
1. MIREX gain ≥ +0.02 → **FAIL** (−0.0169; the vote is *worse*).
2. Exact-rate regression ≤ 0.01 → **FAIL** (−0.0282).
3. Power ≥ 400 evaluable → PASS (604).

Both adoption conditions fail (either alone is disqualifying), so the outcome
is unambiguous: **KEEP EDMA as the shipped label.** No product change — the
shipped `key`/`keyConfidence`/`keyProfile` stay EDMA; `keyEnsemble` remains a
surfacing-only cross-check (`agreement` calibrates confidence, `alternates`
hedge the UI).

**Reproduce** (from `apps/backend/`, corpus fetched via
`scripts/fetch_giantsteps.py`):

```bash
./venv/bin/python scripts/run_key_ensemble_gate.py --jobs 8
```

Gate implementation: `key_ensemble_gate.py` (frozen constants
`MIREX_GAIN_MIN=0.02`, `EXACT_REGRESSION_TOLERANCE=0.01`, `MIN_EVALUABLE=400`);
majority-exact vote resolution + decision rule are unit-tested in
`tests/test_key_ensemble_gate.py`. Full per-clip report:
`.runtime/reports/key_ensemble_gate.json`.
