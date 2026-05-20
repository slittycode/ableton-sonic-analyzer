# beat_this measurement gate — pre-registration & decision record

**Status:** PRE-REGISTERED (bar frozen) — results PENDING.
**Date opened:** 2026-05-20.
**Anchors to:** `PURPOSE.md` invariant #1 — *Phase 1 measurements are ground truth.* This gate
decides whether to change how a ground-truth measurement (downbeats) is produced, so it must itself
be decided by measurement, not preference.

## Question

ASA Phase 0 (PR #91, merged) replaced fake `beat_grid[::4]` downbeats with a real, meter-aware
**kick_accent** heuristic (`analyze_rhythm._compute_downbeat_phase`). Is the neural tracker
**CPJKU/beat_this** (ISMIR-2024, MIT-licensed) materially better at **downbeats**, enough to
justify adding a torch-model dependency to the product?

Decision space: **adopt beat_this** / **keep the heuristic** / **fix `analyze_time_signature`
instead** (cheap-fix escape hatch).

## Why this can be measured honestly

beat_this's shipped `final*`/`small*` checkpoints were **trained on all data except GTZAN**, so
GTZAN is contamination-free for it. **GTZAN-Rhythm** (Marchand/Fresnel/Peeters 2015) supplies
beat + downbeat annotations for GTZAN's 1000 clips. A small **ASA electronic slice** of
user-owned / unreleased tracks (hand-labeled for bar-1) adds modern-electronic representativeness
without contaminating beat_this.

## Method (harness: `apps/backend/beat_evaluation.py`, research-only, off the product path)

Per clip, three downbeat methods are scored against the annotation:
- `stride` — `ticks[::4]` (legacy baseline).
- `kick_accent` — the SHIPPING heuristic (reuses `extract_rhythm`, `analyze_time_signature` →
  `_parse_meter`, `_extract_beat_loudness_data`, `_compute_downbeat_phase`).
- `beat_this` — `File2Beats(checkpoint_path="final0", dbn=False)` (measured, NOT integrated).

Metrics: `mir_eval.beat` (F-measure ±70 ms, CMLt/AMLt, info-gain; trim-first-5 s) with a
hand-rolled F-measure fallback when mir_eval is unavailable. **Downbeat F1 is reported
phase-strict (primary) and phase-tolerant (diagnostic)** — the gap localizes phase error.
**Fairness:** kick_accent is measured on ASA's **own detected meter** (product-faithful); a second
run with `--use-annotated-meter` isolates the phase estimator from meter-detection error, and
meter-detection accuracy is reported separately (incl. the non-4/4 subset).

**Interpretation caveat (check before trusting absolute beat F1):** stride and kick_accent share
the *same* Essentia beat grid, so any systematic Essentia-vs-annotation timing offset depresses
both equally — the kick_accent-vs-stride downbeat comparison (does phase detection help?) is
offset-invariant and is the cleanest internal signal. beat_this uses its own grid, so before
reading too much into a beat_this-vs-DSP *beat*-F1 gap, sanity-check the median signed offset
between each method's beats and the annotation; a large systematic offset (not a tracking error)
should be normalized out or noted, since the product decision is about **downbeats**, not absolute
beat timing.

## Pre-registered pass bar (FROZEN — do not move post-results)

Evaluated on the **asaRelevant subset** (GTZAN disco/hiphop/pop), **product-faithful meter**,
**phase-strict** downbeat F1, macro-mean. Constants live in `beat_evaluation.py`.

**Adopt beat_this iff ALL:**
1. `downbeatF1(beat_this) − downbeatF1(best non-neural) ≥ 0.10` (`ADOPT_MARGIN`)
2. `beatF1(beat_this) ≥ beatF1(kick_accent) − 0.02` (`BEAT_REGRESSION_TOLERANCE`)
3. the ≥0.10 downbeat gain also holds on the ASA electronic slice

**Otherwise keep the heuristic** (any gain < 0.10 keeps the zero-dependency heuristic — this single
threshold subsumes a "within-0.03 ⇒ ship heuristic" tie rule).

**Cheap-fix escape hatch:** if product-faithful kick_accent fails but annotated-meter kick_accent
would pass → **decline beat_this, fix `analyze_time_signature`** instead, and report the expected
gain (annotated − detected downbeat F1).

**Power:** `MIN_CLIPS_PRIMARY=200` (asaRelevant), `MIN_CLIPS_ASA=15`; below → `underpowered`,
do not finalize.

## License

beat_this is **MIT** (CPJKU/beat_this) — compatible with ASA. No licensing barrier to adoption.
`dbn=False` keeps it madmom-free.

## Results — PENDING

Run (eval venv with `requirements-eval.txt`):
```
apps/backend/venv-eval/bin/python apps/backend/scripts/evaluate_beats.py \
  --manifest apps/backend/tests/fixtures/beat_eval_manifest.gtzan.json --html
# + a --use-annotated-meter diagnostic run, then the ASA slice manifest.
```
To be filled after the runs: per-method beat/downbeat F1 (full + asaRelevant + ASA slice, both
meter configs), meter-detection accuracy, the `gate.productRecommendation`, and the verdict with
"what would change it."

| | beat F1 | downbeat F1 (strict) | downbeat F1 (phase-tol) |
|---|---|---|---|
| stride | _pending_ | _pending_ | _pending_ |
| kick_accent (detected meter) | _pending_ | _pending_ | _pending_ |
| kick_accent (annotated meter) | _pending_ | _pending_ | _pending_ |
| beat_this | _pending_ | _pending_ | _pending_ |

**Verdict:** _pending the measurement._
