# Owner Assessment — Is ASA Real? (2026-06-10)

Written for the project owner, in plain English, after a five-agent read-only audit of both
repos (`asa` and the sibling `~/code/projects/asa-ableton`). The question asked: *"Is this
actually going to do what it says? Is it novel or valuable, or just casual vibe coding? Can
it be honed into an ~80% legitimate analysis of a track and how to recreate it in Ableton?"*

Audit evidence: workflow run `wf_d81cbf6c-3b1` (5 parallel auditors over the DSP engine, the
Phase 2 guardrail chain, the UI, the sibling repo, and test/CI health), cross-checked against
`GOAL.md`, `apps/backend/NEEDS.md`, and `apps/backend/RECOMMENDATION_VERDICT.md`.

---

## The one-paragraph verdict

This is not casual vibe code. The measurement half of the product is already legitimate —
real, established audio-analysis engines, correctly used, locked down by a deep test suite.
The advice half is architecturally sound and genuinely novel in one specific way (every
recommendation must cite the measurement that justifies it, checked by three validator
layers), but its *quality* — "do the recommended settings actually recreate the sound?" — is
honestly unproven, and the project itself documents exactly why and what's missing. The gap
between "impressive" and "proven" is one human step: rendering five already-written fixture
specs in Ableton Live 12.

---

## What is verified real (code read, tests run, not taken on faith)

1. **Phase 1 measurements use the real engines.** BPM, key, loudness (LUFS), true peak,
   stereo and spectral balance come from Essentia (the Universitat Pompeu Fabra audio
   research library); stem separation is torchaudio's Hybrid Demucs neural network; pitch
   extraction is torchcrepe. Formulas spot-checked correct (e.g. true peak converts to dBTP
   via the right math; EBU R128 compliance is gated by tests using the official EBU test
   signals).
2. **The chain of custody is enforced, not just claimed.** A 531-line system prompt
   constrains the AI interpreter; a 57-device / 558-parameter catalogue extracted from
   Ableton's own Live 12 scripts checks device and parameter names; citation paths are
   verified against the actual measurement payload on both backend and frontend; the
   recommendation contract is a frozen, versioned JSON Schema. All of this runs on every
   interpretation and is covered by passing tests (20 citation-path tests, 30 contract
   tests, verified during this audit).
3. **The UI is a complete product surface.** Upload → analysis → results works end-to-end,
   with ~34 feature components and the full pipeline rendered (measurements, spectrograms,
   MIDI/Session Musician, recommendation cards, the consistency report, sample audition).
4. **The side program (`asa-ableton`) really works, narrowly.** It converts ASA's
   recommendations into `.als` project files that open in Live 12 **without the repair
   dialog** (verified eyes-on on Live 12.3.6 and 12.4.1), with 9/9 mapped parameters reading
   back at the recommended values. 10 devices are mapped; 16+ common devices are knowingly
   unsupported and skip-and-report rather than guess.
5. **Testing and CI are real.** ~1,180 backend test methods across 51 files, ~800 frontend
   test assertions, a green CI streak, and the important contracts are regression-gated
   (the Phase 1 schema snapshot, a golden measurement fixture, the recommendations.v1
   schema freeze, the cross-language MIME map). Heavy DSP tests skip on Linux CI and are
   covered by the macOS nightly instead — a documented, deliberate trade.

## What is real but heuristic (works, honesty enforced, accuracy unproven)

1. The **style detectors** (acid / vocal / reverb / supersaw / kick / sidechain / genre) are
   genuine signal processing — band energies, decay-slope fitting, envelope correlation —
   but their thresholds and confidence weightings are hand-tuned, not validated against a
   labeled corpus. They degrade honestly (null + low confidence rather than fake values),
   which is the right behavior, but expect misfires on material far from electronic dance
   genres.
2. The **validators warn, never block** — a deliberate choice (an earlier auto-rewrite
   produced confidently-wrong output). Bad AI output reaches the screen flagged, not
   removed. Reasonable design, worth knowing.

## What is honestly unproven (and the project says so itself)

1. **Whether the advice recovers the actual settings.** The recommendation-proof campaign
   (`GOAL.md`) built the entire scoring machine: five fixture specs with known device
   chains, a role/parameter/value-band scorer, a Gemini-vs-deterministic comparison. But the
   scored numbers so far come from **synthetic numpy proxy renders**, not Ableton renders.
   The provisional result: Gemini 0.227 aggregate vs deterministic 0.000 — Gemini wins
   decisively on citation discipline and full-surface coverage, but the
   "did-it-recover-the-real-settings" axes await real renders.
2. **A hard, documented limit:** naming the *source instrument* from finished audio is
   impossible in principle — a sampled kick and an Operator kick can measure identically
   (kick-domain role recall was 0.00 for both Gemini and the deterministic rules). The
   advice will always be stronger on *processing* (EQ, compression, saturation, space) than
   on "which synth made this."
3. **Per-recommendation verification badges** exist in the UI but render nothing until the
   corpus has real renders (all confidence bands are `NONE` — the honest pre-render state).

## Notable dead code

`apps/ui/src/data/abletonDevices.ts` — a 309-line deterministic recommendation engine — is
imported nowhere. The product's recommendations come entirely from the AI interpreter. The
campaign docs already flag this (improve-it-or-call-it-a-baseline decision pending).

## Is it novel / valuable?

**The novelty is the chain of custody, and it's real.** Spectrum analyzers give numbers
without advice; AI chatbots give advice without numbers; commercial assistants (mastering
services, mix analyzers) don't name exact Ableton Live 12 devices with parameter values tied
to measurements of *your reference track*. ASA's specific combination — deterministic
measurement → cited, catalogue-checked, schema-frozen device recommendations → optional
`.als` export — does not exist as a mainstream product. The market risk isn't "this is
nothing"; it's that the advice layer's quality ceiling is unproven (see above) and the
maintenance surface is large for a single owner.

## The "80% legitimate" question

Split it in two:

1. **Analysis: already there.** The measurement layer is as legitimate as the established
   open-source state of the art, because it *is* the established open-source state of the
   art, correctly assembled and regression-locked. Tempo, key, loudness, dynamics, stereo,
   spectral balance, structure: trustworthy today (key detection on harmonically ambiguous
   electronic material is the usual weak spot industry-wide; ASA flags low confidence).
2. **Recreation guidance: plausibly 60–80% useful today on processing-related advice,
   unproven on exact values.** Every recommendation is at least grounded in real
   measurements and checked against a real device catalogue — the live VTSS run scored
   22/22 recommendations with valid citations. What's missing is the loop that proves the
   recommended *values* move a reconstruction toward the reference. That machinery is built
   and idle, waiting on the five Ableton renders.

## Shortest path to proof (in priority order)

1. **Render the five fixture specs in Live 12** (48 kHz / 24-bit FLAC, checklist in
   `apps/backend/tests/fixtures/recommendation_tracks/README.md`). This single session of
   Ableton work converts the provisional verdict and the UI badges from proxy to
   authoritative. Nothing else on the list substitutes for it.
2. **Use the new no-Gemini interpreter** (`ASA_PHASE2_PROVIDER=claude`, added 2026-06-10 —
   see the addendum below and `docs/PHASE2_PROVIDER.md`) for free iteration: it produces
   real Phase 2 JSON from measurements alone via the local Claude Code CLI, with no API
   credits.
3. **Clear asa-ableton's two gates** — Gate α needs exactly one real Phase 2 JSON (item 2
   now provides this for free); Gate β is a 15-minute eyes-on check of Auto Filter's
   Cutoff in Live. Then push the unpushed `feat/track-ii-gate-tooling` branch.
4. Longer-term: validate or retire the weakest detectors against the corpus as it grows,
   and decide the fate of the dead deterministic engine.

---

## Addendum: live result — Claude-as-interpreter on a real track (2026-06-10)

`ASA_PHASE2_PROVIDER=claude` ran end-to-end on `VTSS – Can't Catch Me` (run
`094c2a14`, backend on 8100, **no `GEMINI_API_KEY` set**): real Phase 1 measurement →
the same 238k-character prompt the Gemini path builds → the local Claude Code CLI
(sandboxed: `--safe-mode`, no tools, schema-enforced via `--json-schema`) → the same
parse/citation/catalogue/recommendations.v1 validator tail.

Scored by ASA's own guardrails, against the documented Gemini bar on this same track
(22/22 recs cited, custody 1.000 — `RECOMMENDATION_VERDICT.md`):

1. **26/26 device cards cited, zero invented citation paths** (the citation-existence
   validator raised nothing). The measurements-only interpreter met the chain-of-custody
   bar Gemini set — supporting the design's claim that grounding comes from Phase 1
   JSON, not from listening to the audio.
2. **6 warn-and-keep catalogue annotations** (`RECOMMENDATION_UNVERIFIED` ×5,
   `UNKNOWN_PARAMETER` ×1) — Operator/Scale/EQ-Eight parameter-name spellings outside
   the curated catalogue. The guardrails surfaced them and kept the cards, exactly as
   designed.
3. **recommendations.v1 envelope: 26 schema-valid entries.** Full production surface
   covered (kick, acid bass, supersaw lead, drum bus/groove, FX returns, stereo,
   master); all seven `sonicElements` populated; `authoritativeMeasurements` echoed
   Phase 1 exactly (144.9 BPM, C Minor).
4. Interpretation latency ≈ 6.5 minutes on the CLI's default model (hence the 600 s
   provider timeout default).

**Bonus proof:** the same output was fed to the sibling repo's Gate α fidelity harness
(`asa-ableton verify`) — its first-ever real (non-synthetic) input, previously blocked
on Gemini credits. Result: **11/11 applied parameters landed in a structurally valid
`.als`, 0 mismatched; real skip-rate 60.7%** (≈50% excluding cross-container duplicate
cards), driven by the 10-device fragment library (Operator and Echo are the top
coverage gaps). Recorded in `asa-ableton/docs/GATE_ALPHA.md` with the source JSON
committed as a fixture.
