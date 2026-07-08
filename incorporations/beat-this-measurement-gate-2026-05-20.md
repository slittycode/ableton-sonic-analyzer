# beat_this measurement gate — pre-registration & decision record

**Status:** GTZAN MEASURED 2026-07-05 (both measurable bars PASS) — **ASA
electronic slice still PENDING**, so the gate is NOT finalized: product
recommendation `adopt_pending_asa_slice`. See [Results](#results--gtzan-measured-2026-07-05).
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

## Results — GTZAN MEASURED (2026-07-05)

GTZAN audio (marsyas/gtzan, 1000 × 30 s WAV) + GTZAN-Rhythm beat/downbeat
annotations (TempoBeatDownbeat/gtzan_tempo_beat, 999 clips) fetched locally and
staged per `tests/fixtures/beat_tracks/README.md`. The gate is always computed
on the **asaRelevant subset** (disco/hiphop/pop, **300 clips** — clears
`MIN_CLIPS_PRIMARY=200`); `beat_this` checkpoint `final0`, `dbn=False`,
`mir_eval` metrics. Reproduce (from `apps/backend/`, eval venv):

```bash
# build the manifest from the staged corpus, then run (gate auto-restricts to asaRelevant)
./venv/bin/python scripts/build_beat_manifest.py \
  --root tests/fixtures/beat_tracks --out tests/fixtures/beat_eval_manifest.gtzan.json
./venv-eval/bin/python scripts/evaluate_beats.py \
  --manifest tests/fixtures/beat_eval_manifest.gtzan.json --html
./venv-eval/bin/python scripts/evaluate_beats.py \
  --manifest tests/fixtures/beat_eval_manifest.gtzan.json \
  --methods kick_accent --use-annotated-meter
```

(The numbers below were produced on an asaRelevant-only 300-clip manifest for
speed; the asaRelevant metrics are identical either way — the gate scores the
same 300 clips.)

| | beat F1 | downbeat F1 (strict) | downbeat F1 (phase-tol) |
|---|---|---|---|
| stride | 0.9132 | 0.2717 | 0.9021 |
| kick_accent (detected meter — SHIPPING) | 0.9132 | 0.4722 | 0.7009 |
| kick_accent (annotated meter) | 0.9132 | 0.5446 | 0.9040 |
| **beat_this** | **0.9647** | **0.9244** | **0.9427** |

Meter detection (asaRelevant): exact-match rate **0.6767** — 96/300 4/4 clips
misread as odd meters (only 1 clip is genuinely non-4/4). Meter is the weak
layer, as the synthetic baseline predicted.

**Frozen bar — the two measurable conditions PASS:**
1. `downbeatF1(beat_this) − downbeatF1(best non-neural) ≥ 0.10` → **PASS**:
   0.9244 − 0.4722 = **+0.4522** (≫ 0.10 `ADOPT_MARGIN`).
2. `beatF1(beat_this) ≥ beatF1(kick_accent) − 0.02` → **PASS**: 0.9647 ≥ 0.9132
   − 0.02 (beat_this is *better* on beats too — no regression).
3. ASA electronic slice confirms the ≥0.10 gain → **NOT RUN** (blocked on the
   one manual labeling task — see below).

Power: 300 ≥ 200 = `sufficientlyPowered: true`. `gate.productRecommendation =
adopt_pending_asa_slice`.

**Cheap-fix escape hatch does NOT trigger.** It fires only if product-faithful
kick_accent fails but annotated-meter kick_accent would pass. Feeding kick_accent
the *correct* meter lifts strict downbeat F1 only 0.4722 → 0.5446 — still 0.38
below beat_this. So fixing `analyze_time_signature` alone can't substitute; the
residual gap is phase estimation (kick_accent picks the wrong beat as bar-1:
its phase-tolerant F1 is 0.90 with annotated meter but strict is 0.54). beat_this
is genuinely the better downbeat producer.

**Verdict:** On contamination-free GTZAN electronic-adjacent audio, beat_this is
a decisive downbeat improvement (+0.45 strict F1, product-faithful) with no beat
regression, and the meter cheap-fix cannot close the gap. **Both measurable bars
pass; adoption is gated only on the ASA electronic slice** (`MIN_CLIPS_ASA=15`
hand-annotated bar-1 downbeats on modern-electronic tracks — the program's one
manual labeling task). **What would change it:** the ASA slice failing to
reproduce a ≥0.10 gain (e.g. if beat_this generalizes worse to modern electronic
than to GTZAN disco/hiphop/pop), or an unacceptable per-clip latency for the
torch model on the product path.

**Not yet measured (optional, non-blocking):** the full 10-genre GTZAN run
(only the 300-clip asaRelevant subset was run — that is the pass-bar subset);
`beat_eval_manifest.gtzan.json` (999 clips) is built and ready if the broader
per-genre / non-4/4 breakdown is wanted.
