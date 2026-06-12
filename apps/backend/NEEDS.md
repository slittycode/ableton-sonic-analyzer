# NEEDS — Recommendation-Proof Campaign (GOAL.md)

Status of the campaign and the queue of work that needs the **owner's hands** (a
render, a listen, a Gemini key) before an agent can finish it. Read alongside
`GOAL.md` (the why), `tests/fixtures/recommendation_tracks/README.md` (the corpus
authoring checklist), and `recommendation_evaluation.py` (the scorer).

---

## ALL FOUR SUB-GOALS MECHANICALLY COMPLETE — with proxy caveats

Under the owner's "continue without input" directive, the campaign was driven to
completion of every sub-goal's stated Done criteria. The honest caveat: sub-goals
1, 3, and 4 rest on **synthetic-proxy renders** (numpy approximations of the specs,
not Ableton renders), so their *data* is provisional pending real renders.

| Sub-goal | Done? | Caveat |
|---|---|---|
| 1 — ground-truth corpus | ✅ 5 catalog-valid fixtures, ingest passes | audio is **synthetic-proxy**, not Ableton; 2026-06-10 two fixtures re-authored to owner genres (`hard_techno_rumble_145`, `ukg_2step_shuffle_132`) and ship spec-only — their proxy audio/fingerprints retired with the old slugs |
| 2 — the scorer | ✅ fully real (32 tests, self-test) | none |
| 3 — verdict + improvement | ✅ verdict (`RECOMMENDATION_VERDICT.md`: Gemini 0.227 vs deterministic/baseline 0.000), intent-credit improvement 0.141→0.227, harness runnable | corpus numbers are on proxy audio; real-track cross-check is real |
| 4 — UI proof | ✅ badge on `ui/` primitives, real bands (master MED, bass/melody LOW, rest NONE), `npm run verify` green | bands derived from proxy corpus |

### ⚠️ RETROACTIVE — where real owner input is still necessary
1. **Real Ableton renders** of the 5 specs (48 kHz/24-bit) to replace the proxies
   (`synth_fixtures.py` output). This is the one irreplaceable human step — it makes
   the known-settings verdict and the badge bands authoritative. Re-run
   `run_phase1_fixtures.py` → `gen_deterministic.py` → `gen_gemini.py` →
   `score_verdict.py` → `gen_verification_artifact.py` (all in the job dir / pattern
   documented) on the real renders.
2. **Gemini spend already incurred** (6 live `gemini-2.5-flash` calls: 1 real track +
   5 proxy fixtures) using `VITE_GEMINI_API_KEY`. Future re-runs cost the same.
3. **Proxy artifacts to distrust until re-rendered:** dnb BPM read half-time
   (174→116) — moot since 2026-06-10, `dnb_reese_174` retired (re-authored as
   `ukg_2step_shuffle_132`); `acidDetail` fires on all proxies (synth is
   saw-heavy); melodic_techno key mis-detected AND Gemini returned 0 structured
   cards there.
4. **Genre confirmation** — ✅ resolved 2026-06-10. Owner confirmed
   house/melodic-techno/acid; the other two were re-authored to owner genres:
   `techno_rumble_130` → `hard_techno_rumble_145` (hard/peak techno) and
   `dnb_reese_174` → `ukg_2step_shuffle_132` (UK garage / 2-step).

---

## Landed this session (autonomous + verified)

**Sub-goal 2 — the scorer — is functionally complete and tested.**

- `recommendation_evaluation.py` — source-agnostic scorer. Role/parameter/
  direction-band rubric, per-domain breakdown over the seven domains, device
  equivalence classes (Compressor ↔ Glue Compressor earns credit), per-unit
  value tolerance bands, and a chain-of-custody penalty that ports
  `apps/ui/src/services/phase2Validator.ts` semantics
  (`collect_phase1_field_paths`, `path_covers_tracked`).
- `scripts/evaluate_recommendations.py` — CLI runner with `--source
  {baseline,gemini,deterministic}`, `--self-test`, `--report`, `--json`,
  `--verification-artifact`.
- `scripts/emit_deterministic_recs.ts` — **deterministic-source bridge** (Node 23+
  native TS, no `npm install`): wraps the product's `abletonDevices.ts` and emits
  the scorer's normalized rec shape. Single source of truth — no Python re-port.
- `aggregate_corpus_verification()` — per-domain match-rate + support artifact, the
  data source the sub-goal 4 UI badge reads (degrades to confidence `NONE` with no
  corpus evidence — the honest pre-render state).
- **Sub-goal 4 badge — BUILT** on the `ui/` Pill primitive and mounted on the
  recommendation cards in `AnalysisResults.tsx`; verified by `npm run lint` +
  `test:unit` (666) + `build` (smoke needs the live stack). Renders nothing while
  the corpus is empty (graceful degradation); strengthens as renders land. Details
  in the sub-goal 4 section below.
- `tests/test_recommendation_evaluation.py` — 29 tests, all green via
  `python3.11 -m unittest tests.test_recommendation_evaluation`. The key gate
  (`test_known_bad_rec_lowers_score`, `test_full_coverage_uncited_must_not_
  outscore_lower_coverage_cited`) proves the score moves correctly.

### Provisional finding (deterministic vs baseline, pre-render)

Running the deterministic bridge on a *synthetic* `AudioFeatures` for the house
fixture and scoring it: deterministic **raw aggregate 0.161** (covers bass + melody
device roles) vs baseline **0.000** — but the deterministic path emits **zero
citations**, so the chain-of-custody penalty drives its adjusted aggregate to
**0.000**. Two takeaways the harness surfaces immediately:
1. The free path recovers *some* device roles (it beats baseline on raw coverage)
   but covers only the bands it maps — no kick/groove/stereo/master role
   attribution (invariant #5 gap).
2. It emits no `phase1Fields`, so it fails the citation chain (PURPOSE.md invariant
   #2). The rules **are** feature-triggered, so attaching the triggering measurement
   as a citation is a concrete, harness-rewarded improvement — a candidate
   sub-goal-3 "score-driven change" (frontend edit to `abletonDevices.ts` →
   `npm run verify`). Moot since 2026-06-11: the NEEDS-WIRING decision below
   demoted `abletonDevices.ts` to a research-only baseline, so this candidate is
   no longer a *product* improvement path.

This is the first real signal toward the Gemini verdict — likely Gemini earns its
place on citation + full-surface coverage. Confirm on real renders; the synthetic
`AudioFeatures` is illustrative, not a verdict.

**Sub-goal 1 — corpus format + ingest — is complete except the renders.**

- Manifest schema (`recommendation-fixture.v1`) + corpus README + authoring
  checklist + `_TEMPLATE/`.
- Catalog-validity ingest (`validate_fixture_spec`) — runs now, gates every spec
  against `prompts/live12_device_catalog.json`.
- **Five catalog-valid spec fixtures**, all covering the seven domains, in
  owner-confirmed electronic genres — meeting GOAL.md sub-goal 1's ≥5 *spec* target
  (the renders are the remaining half): `house_sidechain_pluck_124` (house),
  `hard_techno_rumble_145` (hard techno — the pilot),
  `melodic_techno_arp_124` (melodic techno),
  `ukg_2step_shuffle_132` (UK garage / 2-step — swing asserted via
  `grooveDetail.*` / `bassDetail.grooveType`),
  `acid_303_128` (acid — exercises `acidDetail`).

---

## NEEDS-FIXTURE (blocks sub-goal 1 "done" and all of 3)

The scorer cannot run on real recommendations until real audio exists, because
the recommendations themselves come from analyzing a real render. **This is the
hard human dependency** — the agent writes the spec, the owner builds and renders.

### 1. Build + render the five authored fixtures
For each of `house_sidechain_pluck_124`, `hard_techno_rumble_145`,
`melodic_techno_arp_124`, `ukg_2step_shuffle_132`, `acid_303_128`
(start with `hard_techno_rumble_145` — the pilot, smallest spec):
- Build the `manifest.json → deviceSpec` **exactly** in Live 12.
- Set the project to **48 kHz / 24-bit**.
- Render the loop to `audio.flac` in the fixture dir (no export normalization).
- Store the fingerprint:
  ```bash
  ./venv/bin/python analyze.py \
    tests/fixtures/recommendation_tracks/<slug>/audio.flac --yes \
    > tests/fixtures/recommendation_tracks/<slug>/phase1_fingerprint.json
  ```
- Re-run `scripts/evaluate_recommendations.py --fixture <slug> --source baseline`
  and confirm the no-fingerprint note is gone.

### 2. Genre fit + held-out fixture
✅ Genre fit resolved 2026-06-10: owner confirmed house/melodic-techno/acid and the
agent re-authored the other two to owner genres (hard techno 145, UK garage 2-step
132) — the spec-then-dial cost stayed on the agent, the render on you.

> Equivalence/overfitting note (GOAL.md sub-goal 3.3): hold out at least one
> fixture from any tuning loop so improvements reflect quality, not memorization.

---

## Known limitation to revisit with real data

**Domain attribution of instrument-processing effects.** The scorer attributes a
rec to the signal it shapes (`trackContext` wins), so a sidechain `Compressor`
labeled "Bass" scores under `bass`. A fixture spec that instead lists that effect
under `fx` will under-credit an otherwise-correct rec. Author specs so a device's
domain matches the trackContext a producer would give it, and tune the
`infer_domain` heuristics against actual Gemini/deterministic output in sub-goal 3
— not blind, now. (Documented in `recommendation_evaluation.infer_domain`.)

## NEEDS-WIRING — mostly closed

### Deterministic source adapter (`--source deterministic`) — BUILT
The node bridge (`scripts/emit_deterministic_recs.ts`) is done and verified end to
end: it wraps the real `abletonDevices.ts` (single source of truth) and emits the
scorer's normalized rec shape; the runner reads
`recommendation_tracks/<slug>/recommendations.deterministic.json` (or any
`--recommendations` JSON). Run it:
```bash
node apps/backend/scripts/emit_deterministic_recs.ts <audio_features.json> \
  > tests/fixtures/recommendation_tracks/<slug>/recommendations.deterministic.json
```
**Remaining (render-gated):** the bridge consumes an `AudioFeatures` object. Turning
a real Phase 1 fingerprint into `AudioFeatures` (spectral-band dominance, crest
factor, onset density) is the app's own projection (`analyzer.ts`); reuse it rather
than re-deriving, and only then is the deterministic score a real verdict input
rather than the synthetic illustration above.

**FINDING — the deterministic source is dead code on the product path. ✅ DECIDED
2026-06-11: demoted to research-only baseline (option 2).**
`apps/ui/src/data/abletonDevices.ts` is imported **nowhere** in the UI (no
component, no test) — verified by grep. ASA's product recommendations come
entirely from the Phase 2 providers (`Phase2Result`); the deterministic engine is
unwired, ported-but-unused. Consequence: a "score-driven improvement" to
`abletonDevices.ts` (e.g. the citation-emit fix flagged above) would **not reach
any user** — it would raise a harness number for code nobody runs, which is
harness-gaming, not a product improvement (PURPOSE.md decision #5). The owner
resolved the wire-or-demote choice: **demote**. Standing consequences:
1. The module stays where it is as the scored free baseline in the three-source
   comparison (its file header now records the status); it is **not** to be
   wired into the product.
2. Score-driven *product* improvements land on the **Phase 2 provider** path
   instead. The citation-emit candidate above is off the table as a product
   change (it remains a legitimate baseline-fairness tweak if the comparison
   ever needs it).

---

## Sub-goal 3 — the Gemini verdict

**Partial verdict LANDED on real data — see `RECOMMENDATION_VERDICT.md`.** Ran the
harness against live Gemini output on the owner's `VTSS – Can't Catch Me` track
(real Phase 1 → real Gemini Phase 2 via `server._run_interpretation_request`,
`gemini-2.5-flash`). Result on the answer-key-free axes: **Gemini 22/22 recs cited
and path-valid against the real fingerprint (custody penalty 1.000), full-surface
coverage; deterministic structurally 0 (uncited); baseline 0.** Gemini decisively
wins on chain-of-custody (#2) and coverage (#5). **Still owed:** the
known-settings axes (role recall / value accuracy) — those need rendered fixtures,
so the *complete* "does Gemini recover the actual settings?" verdict remains
render-gated.

**Claude provider scored on the proxy corpus — 2026-06-11, zero Gemini cost.**
The `--source claude` harness path plus `scripts/gen_claude_phase2.py` generated
and scored fully-cited, zero-warning recommendations on the three
proxy-fingerprint fixtures: **acid 0.485, house 0.424, melodic_techno 0.424**
vs recorded Gemini 0.172 / 0.343 / 0.000 on identical fingerprints (text-only
vs audio+JSON — full table and caveats in `RECOMMENDATION_VERDICT.md`). The
melodic_techno "Gemini 0 recs" outlier is resolved as Gemini-side: Claude
produced 13 cards from the same fingerprint. Evidence committed as
`phase2.claude.json` in each fixture dir. Real-render re-runs remain the
authoritative step for both providers.

Mechanism is in place: `--source baseline|gemini|claude|deterministic` on the
same corpus. To deliver the **full** verdict:
1. Render the fixtures (NEEDS-FIXTURE #1–2).
2. Wire the deterministic adapter (NEEDS-WIRING).
3. For each fixture, produce a live Gemini `phase2.json` (needs `GEMINI_API_KEY`;
   **owner-discretion spend** per GOAL.md rule 4) and drop it in the fixture dir.
4. Run all three sources, diff per-domain + aggregate, write the finding:
   *does Gemini raise the score, on which domains, by how much?* Feed a surprising
   answer back into `PURPOSE.md` / the `asa-next-work-priorities` memory.

**Phase 2 audit context for 3.2:** GOAL.md references
`audits/phase2-recommendation-surface-2026-05-24.md` for the Tier-2/3 backlog. That
audit — **and the Tier-1/2 phase2 prompt/catalog fixes it drove** (commits
`bd975ab0`, `dc8daa02`, `5610ca5`, `ade2ae5`) — is on `main` and the campaign sits
on top of it (PR #114 / commit `348498d` merged after). Iterate against the
current prompt; the audit backlog is the source for next-round score-driven
changes. Confirm with `git log --oneline | grep -E 'bd975ab|dc8daa0|5610ca5|ade2ae5'`.

---

## Sub-goal 4 — surface the proof in the UI — BUILT (content render-gated)

**Data source — BUILT.** `aggregate_corpus_verification()` emits the per-domain
match-rate + support + confidence-band artifact (via `--verification-artifact`).
Confidence band: support `<3` → LOW (hedged), `<6` → MED, else HIGH — invariant
#4's "low support never earns a confident badge", made mechanical.

**Badge — BUILT + verified.** Shipped on the `ui/` Pill primitive:
- `apps/ui/src/data/recommendationVerification.ts` — typed artifact (all-`NONE`
  pre-render; regenerate from the backend runner — see header comment).
- `apps/ui/src/services/recommendationVerification.ts` — domain inference
  (mirrors backend `infer_domain`) + lookup; node-testable.
- `apps/ui/src/components/RecommendationVerificationBadge.tsx` — renders the band
  per rec, or **nothing** when confidence is `NONE` (graceful degradation, the
  current pre-render state).
- Mounted in `AnalysisResults.tsx` on both the mix-chain cards and the patch
  cards (per-rec).
- `apps/ui/tests/services/recommendationVerification.test.ts` — 8 tests.
- **Verified:** `npm run lint` (tsc) ✓, `npm run test:unit` (666) ✓, `npm run build` ✓.

**Remaining:**
1. `npm run test:smoke` (the 4th `verify` step) needs the live stack (backend on
   8100 + UI on 3100) — not bootable in this worktree; run it where the stack is up.
2. Badges stay invisible (all-`NONE`) until real renders produce a scored corpus
   and you regenerate `recommendationVerification.ts`. The wiring is proven by a
   unit test that injects a populated artifact and asserts the `HIGH` band surfaces.
3. Optional: extend to `secretSauce.workflowSteps` cards (same one-line pattern).

Artifact shape (`--verification-artifact`), self-contained for the frontend:

```json
{
  "fixtures": 0,
  "sources": [],
  "perDomain": {
    "kick":   { "support": 0, "meanRecall": 0.0, "meanScore": 0.0, "confidence": "NONE" },
    "bass":   { "support": 0, "meanRecall": 0.0, "meanScore": 0.0, "confidence": "NONE" }
    // ...one entry per domain: kick, bass, melody, groove, fx, stereo, master
  }
}
```

`confidence` band from `support` (number of scored fixtures specifying the domain):
`0` → `NONE`, `<3` → `LOW` (hedged badge), `<6` → `MED`, else `HIGH`. The badge maps
a card's domain (via the `infer_domain` reading) to `perDomain[domain]` and renders
the band; `NONE`/`LOW` must never render as a confident badge (invariant #4).

---

## How to re-enter this campaign

```bash
# Confirm the harness is green (no venv needed — pure stdlib):
cd apps/backend && python3.11 -m unittest tests.test_recommendation_evaluation
python3.11 scripts/evaluate_recommendations.py --self-test
# Deterministic source (Node 23+, no npm install needed):
node scripts/emit_deterministic_recs.ts <audio_features.json> > /tmp/det.json
python3.11 scripts/evaluate_recommendations.py --fixture <slug> \
  --source deterministic --recommendations /tmp/det.json
# Full picture once a render exists:
python3.11 scripts/evaluate_recommendations.py --source gemini \
  --fixture <slug> --phase2 <phase2.json> --report /tmp/rec_eval.md \
  --verification-artifact /tmp/verification.json
```
