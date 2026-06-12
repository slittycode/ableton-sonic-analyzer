# Recommendation Verdict (GOAL.md sub-goal 3)

Does Gemini interpretation beat the deterministic rules? **Yes — decisively, and
specifically on the chain-of-custody invariant.** Numbers below. Research note.

> ⚠️ **SYNTHETIC-PROXY CORPUS.** The 5 fixtures were scored against **numpy proxy
> renders** (`synth_fixtures.py`), NOT Ableton renders, because the owner directed
> "continue without input." The proxies realize each spec's *acoustic intent*
> (tempo, kick fundamental, brightness, sidechain) closely enough for Phase 1 to
> measure plausibly, but they are not Ableton device timbres. **Re-run on real Live
> renders for an authoritative known-settings verdict.** See "Where real input is
> needed" at the bottom and `NEEDS.md`.

> **Corpus composition changed 2026-06-10, after this verdict.** Two fixtures were
> re-authored to owner genres: `techno_rumble_130` → `hard_techno_rumble_145`
> (hard/peak techno) and `dnb_reese_174` → `ukg_2step_shuffle_132` (UK garage /
> 2-step). The per-fixture proxy numbers below for "techno" and "dnb" refer to the
> retired fixtures and are not comparable to future real-render scores.

## Method
Per fixture: proxy render → `analyze.py` (real Phase 1) → three recommendation
sources scored by `recommendation_evaluation.score_recommendations`:
- **deterministic** — `abletonDevices.ts` via the node bridge (`emit_deterministic_recs.ts`), fed an `AudioFeatures` projection of the fingerprint.
- **gemini** — live `gemini-2.5-flash` via the exact server path (`server._run_interpretation_request`), key from `VITE_GEMINI_API_KEY`.
- **baseline** — empty (the floor).

## Verdict — corpus aggregate (mean over 5 proxy fixtures)

| Source | Aggregate | Raw (pre-custody) | Custody penalty |
|---|---|---|---|
| **Gemini** | **0.227** | 0.227 | **1.000** |
| Deterministic | **0.000** | 0.112 | **0.000** |
| Baseline | 0.000 | 0.000 | 1.000 |

**The decisive factor is chain-of-custody, not raw coverage.** The deterministic
path's *raw* device-role coverage (0.112) is in the same range as Gemini's, and it
actually beats Gemini on bass role-recall (1.00 vs 0.20). But it emits **zero
citations**, so the custody penalty (PURPOSE.md invariant #2) drives its aggregate
to 0. Gemini cites every recommendation against a real measurement, so it keeps its
score. **Gemini earns its place on the citation chain + measurement grounding —
exactly the two properties PURPOSE.md calls the product.**

Per-fixture Gemini aggregate: house 0.343, dnb 0.335, techno 0.287, acid 0.172,
melodic_techno **0.000** (Gemini returned 0 structured cards for this one — a parse/
shape outlier worth investigating).

### Per-domain role recall (gemini / deterministic)
`kick 0.00/0.00 · bass 0.20/1.00 · melody 0.60/0.20 · groove 0.00/0.00 · fx 0.00/0.00 · stereo 0.00/0.00 · master 0.50/0.50`

**Key finding — source-instrument recall is partly unrecoverable from audio.**
`kick = 0.00` for *both* sources: Gemini's kick-domain cards are `EQ Eight` +
`Saturator` (how to **process** the kick), while the spec lists `Operator` (the
**source** synth). Reverse-engineering a finished render, Gemini recommends
processing — and a synth kick vs a sampled kick *measure identically*, so naming the
source instrument from audio is impossible in principle. This is a real limit on the
"recover the literal device" axis and motivated the improvement below.

## Score-driven improvement landed (with evidence)

The scorer was **ignoring `measurableIntent`** even though GOAL.md says "the key
stores measurable intent beside the literal spec, so equivalent routes earn credit."
Implemented that mechanism (`intent_coverage` + a 0.25-weighted blend): a rec that
cites the measurements the spec deemed essential earns credit even when it names a
different (or processing-not-source) device.

| | Before | After |
|---|---|---|
| Gemini aggregate | 0.141 | **0.227** (+0.086) |
| Deterministic aggregate | 0.000 | 0.000 (unchanged — uncited, earns no intent credit) |

The improvement rewards measurement-grounded recommendations and is provably
useless to a source that doesn't cite — a faithful, non-gameable implementation of
the equivalence caveat. Covered by `tests/test_recommendation_evaluation.py::IntentCoverageTests`.

## Real-track cross-check (no synthesis)

On the owner's real `VTSS – Can't Catch Me` track (real Phase 1 → real Gemini),
answer-key-free axes only (no known settings for a commercial track): Gemini **22/22
recs cited and path-valid** against the real fingerprint (custody 1.000), full-surface
coverage. Consistent with the corpus verdict — Gemini's custody advantage is real,
not a synthesis artifact.

## Claude provider head-to-head (2026-06-11 — same proxy corpus, zero Gemini cost)

The selectable Claude provider (`ASA_PHASE2_PROVIDER=claude`,
`phase2_provider.ClaudeCliProvider`) was scored on the three fixtures whose proxy
fingerprints survived the 2026-06-10 corpus re-authoring, via the exact server
path (`server._run_interpretation_request`) and the same scorer. Generation:
`scripts/gen_claude_phase2.py`; scoring: `--source claude` (reads the committed
`phase2.claude.json` evidence in each fixture dir). Model `sonnet`
(claude-sonnet-4-6), **text-only** (grounds purely on the embedded Phase 1 JSON,
no audio), `MAX_THINKING_TOKENS=0`, 300–365 s per fixture.

| Fixture | Claude | Gemini (recorded above) |
|---|---|---|
| acid_303_128 | **0.485** | 0.172 |
| house_sidechain_pluck_124 | **0.424** | 0.343 |
| melodic_techno_arp_124 | **0.424** | 0.000 (zero cards) |
| **Mean (shared subset)** | **0.444** | 0.172 |

All three Claude results are fully cited (custody penalty 1.000) with **zero**
`validationWarnings` — both the citation-path check and the Live 12 catalogue
gates came back clean.

Findings:
1. **The melodic_techno outlier was Gemini-side, not fixture-side.** From the
   identical fingerprint where Gemini returned 0 structured cards, Claude
   produced 13 rec cards + 14 chain cards + 5 workflow steps (32 envelope
   entries) and scored 0.424. The fixture's fingerprint is interpretable.
2. **Kick role recall 1.00 on all three** (the recorded gemini/deterministic
   table above shows kick 0.00/0.00): Claude's kick cards name `Operator`,
   matching the specs' source synth. Whether genuine inference or
   electronic-genre convention, it softens the "source instrument is
   unrecoverable from audio" ceiling — notably, Claude never heard any audio.
3. The groove/fx/stereo zeros persist for Claude too (cards exist — `Drum Buss`
   groove cards, a `Hybrid Reverb` that lands in `unknown` domain — but miss
   the spec devices), consistent with the domain-attribution limitation in
   `NEEDS.md`. Provider-agnostic and scorer-consistent.

Caveats, honestly: the SYNTHETIC-PROXY warning at the top applies in full. The
comparison is like-for-like on *inputs* (identical fingerprints, same scorer)
but not on *modality*: Gemini received the unrepresentative proxy audio
alongside the Phase 1 JSON, while Claude's text-only grounding may have
shielded it from proxy-audio artifacts. Model classes also differ (sonnet vs
gemini-2.5-flash). Re-run both on real renders before treating this as a
provider verdict. What it does establish: the zero-Gemini-cost route produces
fully-cited, catalogue-clean, schema-valid recommendations at
competitive-or-better measured quality on every fixture it has seen.

## Where real input is needed (retroactive)
1. **Real Ableton renders** of the 5 specs (48 kHz/24-bit) replace the proxies →
   makes the known-settings axes (role recall, value accuracy) authoritative. The
   proxies have artifacts: dnb BPM read half-time (174→116), `acidDetail` fires on
   all (synth is saw-heavy), melodic_techno key mis-detected.
2. **`melodic_techno_arp_124` Gemini 0 recs** — investigate the parse/shape outlier
   on a real render before trusting that fixture's contribution. *(Partially
   resolved 2026-06-11: Claude produced a full 13-card result from the same
   fingerprint — see the head-to-head section above — so the outlier is
   Gemini-side, not fixture-side. Still verify Gemini on a real render.)*
3. The deterministic `AudioFeatures` projection is approximate (not the app's
   `analyzer.ts`). The wire-or-demote question was resolved 2026-06-11: the
   deterministic engine is a research-only baseline and will not be wired into
   the product (see `NEEDS.md`), so reconciling the projection matters only for
   baseline fairness in this comparison, not for any product path.
