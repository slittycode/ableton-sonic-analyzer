# Phase 2 Recommendation-Surface Audit — 2026-05-24

**Scope:** The Phase 2 recommendation surface — `apps/backend/prompts/phase2_system.txt` and
`apps/backend/prompts/live12_device_catalog.json` — plus the chain-of-custody validators
(`apps/ui/src/services/phase2Validator.ts`, `apps/backend/server_phase2.py`) and the frontend
deterministic device rules (`apps/ui/src/data/abletonDevices.ts`).

**Why:** `PURPOSE.md` names the recommendation surface as *the product*, yet the Phase 2 prompt and
device catalog had been untouched for ~50 commits while measurement/validation/eval infra kept
growing (see the `asa-next-work-priorities` note). This is the Priority-1 reinvestment.

**Method:** 11 parallel read-only audit agents, one per production-surface domain (kick, bass,
melody/harmony, groove/sidechain, effects, stereo, mastering) plus four cross-cutting reviews
(confidence-hedging #4, citation/chain-of-custody #1/#2, Live 12 device-name accuracy #3, and a
program-wide health review). Findings cross-validated where multiple agents converged. Every field
path and device/parameter name below was verified against `JSON_SCHEMA.md` / the catalog / (for the
device-name agent) the official Ableton Live 12 manual before being trusted.

---

## Tier 1 — Verified bugs (APPLIED in this pass)

All 11 are concrete, reproduced against the source files, and shipped. Gates run after: backend
`test_phase2_citation_paths` + `test_phase2_grammar_fix` (32 tests OK), frontend
`phase2Validator.test.ts` (65 tests OK), `tsc --noEmit` clean, catalog JSON valid (57 devices).

| # | File / line | Bug | Fix |
|---|---|---|---|
| 1 | `phase2_system.txt:456` | Example card cites `bassDetail.decayTime` — field does not exist | → `bassDetail.averageDecayMs` (`analyze_detection.py:1139`, `JSON_SCHEMA.md:753`) |
| 2 | `phase2_system.txt:158` | Hint says "Auto Pan" — renamed in Live 12 | → "Auto Pan-Tremolo" |
| 3 | `phase2_system.txt:171` | "Damping parameter" — no Reverb/Hybrid Reverb param named Damping | → "High Cut (the damping control)" |
| 4 | `phase2_system.txt:173` | "Hall reverb with damping set high" | → "High Cut lowered for more damping" |
| 5 | `phase2_system.txt:190` | Teaches `stemAnalysis.drums.spectralDetail.spectralFlatness` ("both exist") — server renames it to `spectralFlatnessMean`, so the example fails its own validator | → corrected to `spectralFlatnessMean` + explicit warning |
| 6 | `phase2_system.txt:95` | Rename caveat listed only `spectralCentroid` | → all four (`spectralCentroid/Rolloff/Bandwidth/Flatness` → `*Mean`, top-level AND per-stem) |
| 7 | `live12_device_catalog.json:464` (Saturator) | Param `"Frequency"` — Live UI label is `"Freq"` | → `"Freq"` |
| 8 | `live12_device_catalog.json:810-811` (Arpeggiator) | `"Tranpose Steps"/"Tranpose Distance"` — misspelled + wrong names | → `"Steps"/"Distance"` (per Ableton manual) |
| 9 | `phase2Validator.ts` CONFIDENCE_PAIRS | `sidechainDetail.envelopeShape32` (the *preferred* citation) had no confidence pair → hedge check silently no-ops | added `envelopeShape32 → pumpingConfidence` |
| 10 | `abletonDevices.ts:187` | Deterministic FX rule recommends "Ableton Exciter" — not a Live 12 device (chain-of-custody break) | → Saturator (Color, Freq ~4kHz) |
| 11 | `phase2_system.txt:458` | Mastering example sets only `Ceiling` — passes `validateLoudnessActionPresence` but never enables inter-sample peak limiting, so `truePeak > 1.0` overs persist on lossy export | `advancedTip` now instructs enabling `True Peak: On` (catalog Limiter has the param) |

---

## Tier 2 — High-leverage decision rules (RECOMMENDED; warrant live Gemini smoke before shipping)

The recurring through-line across every domain: **the prompt routes fields correctly (the FIELD
CITATION MAP is good) but lacks the *decision rules* that convert a measured value into a specific
device parameter** — i.e. invariants #3 (exact device/param/value) and #5 (full surface). These are
ready to apply but should be validated with `RUN_GEMINI_LIVE_SMOKE=true` on a known track, because
unit tests do not exercise prompt quality and adding bulk prose risks degrading model adherence.

**Guardrail-grade:**
1. **Kick 50 Hz sentinel guard.** `analyze_kick_detail` returns hardcoded `fundamentalHz: 50.0,
   thd: 0.0` when <2 transients are found — byte-identical to a real clean 50 Hz kick. Add a prompt
   rule: if `kickDetail.kickCount < 2 AND fundamentalHz == 50.0 AND thd == 0.0`, emit NO kick-specific
   recommendation; note the kick is unmeasured. (invariant #4) *(The other guardrail-grade item —
   the Limiter True-Peak example — was promoted to Tier 1 #11 and applied.)*

**Per-domain decision rules (one tight block each, in the prompt's existing voice):**
3. **Kick** — `kickDetail` per-field table mirroring the existing SNARE/HI-HAT block: `fundamentalHz`
   → Drum Buss Boom Frequency / Operator Osc A Coarse; `thd` → Saturator Drive ranges; `harmonicRatio`
   → Drum Buss Crunch; `isDistorted` veto (don't stack Saturator).
4. **Bass** — sub-vs-mid architecture from `spectralBalance.subBass`/`lowBass`; `averageDecayMs`/`type`
   → Glue Compressor Release; Utility Bass Mono from `stereoDetail.subBassCorrelation`.
5. **Mastering** — surface `plr` (forwarded but uncited anywhere) with a PLR→device threshold table;
   Multiband Dynamics selection logic; `headroomTarget` derivation.
6. **Stereo** — MUST rule for negative `stereoCorrelation` (mono cancellation — currently no required
   action); `stereoWidth`→Utility % mapping; EQ Eight M/S mode (the primary freq-selective stereo tool,
   currently invisible to the prompt).
7. **Effects** — Delay/Echo BPM-sync section (no measurement anchor today); `acidDetail` → Auto Filter
   (Resonance/Envelope/LFO); `textureCharacter`/`perceptual` → Erosion/Dynamic Tube.
8. **Groove/sidechain** — sidechain Threshold/Ratio from `pumpingStrength`; `effectsDetail.gating*` →
   Beat Repeat (measured, device in catalog, bridge unbuilt); `bassDetail.swingPercent` (only
   concrete swing %, currently orphaned — converged finding from bass + groove agents).
9. **Melody/harmony** — the most under-covered surface (~5 of ~37 fields cited): Scale / Arpeggiator /
   Auto Shift / Chord MIDI devices are never used as directives; `tuningCents` → Osc Fine;
   `oddToEvenRatio` → oscillator type; vibrato fields → LFO/vibrato.
10. **Confidence hedging (#4)** — a condensed CONFIDENCE-GATED HEDGING block: most `*Confidence`
    fields have no hedging rule today (only `saturationLikely` is handled well). Add thresholds for
    `keyConfidence`, `downbeatConfidence` (replace vague "≈0" at line 140 with `< 0.4`),
    `pitchConfidence` mid-tier (0.15–0.35), `genreDetail.confidence`, and the specialty detectors.

---

## Tier 3 — Validator / catalog structural items (need design + tests, not one-line fixes)

1. **`bpmConfidence` scale bug** *(converged: confidence + citation agents)*. `bpmConfidence` is
   unbounded (~1.0–4.0) but `phase2Validator.ts` `LOW_CONFIDENCE_THRESHOLD = 0.4` is applied
   uniformly, so the BPM hedge **never fires**. Fix needs per-field thresholds (e.g. bpm hedge at
   `< 1.0`). Touch `phase2Validator.ts` + tests.
2. **`reverbDetail.confidence` dead reference.** CONFIDENCE_PAIRS maps `reverbDetail` →
   `reverbDetail.confidence`, which doesn't exist → reverb hedge check silently no-ops. Reverb quality
   is the boolean `reverbDetail.measured`, which doesn't fit the numeric check — needs a small design
   decision (left in place this pass to avoid churning validator semantics blind).
3. **`trackLayout.grounding.phase1Fields` is unvalidated.** The prompt cites it as the citation
   exemplar, but neither validator re-checks its paths — invented paths there go uncaught.
4. **Catalog completeness.** Stock devices absent from the catalog that Phase 2 may legitimately emit:
   **Drum Sampler** (promised in catalog `_meta`, missing from `devices[]`), Redux, Grain Delay,
   Resonators, Overdrive, Vinyl Distortion, Vocoder, Convolution Reverb. **Flanger** is Legacy as of
   Live 12.2 — prefer Phaser-Flanger (consider a `_notes` steer).
5. **Catalog `_notes` / `parameterValueHints`.** The catalog is name-only today. Several agents want
   per-device notes (e.g. Utility "Bass Mono" is a ~200 Hz toggle, not a free frequency; Glue
   Compressor Attack is a stepped selector). Adding these is a catalog schema-shape change — verify
   the loader/validator tolerate new keys before adding.
6. **Groove Pool citability.** `bassDetail.swingPercent` / `grooveDetail.perDrumSwing` justify a
   Groove Pool move, but Groove Pool is a session feature, not a device, so it can't be emitted under
   the NATIVE+M4L device policy. Decide: special-case it, or document the limitation.

---

## Verification status

- **Applied (Tier 1):** verified green — backend `test_phase2_citation_paths`+`test_phase2_grammar_fix`
  (32), frontend `phase2Validator.test.ts` (65), `tsc --noEmit`, catalog JSON load.
- **Not yet run:** the live Gemini smoke (`RUN_GEMINI_LIVE_SMOKE=true` on a known track) — requires
  `GEMINI_API_KEY`. This is the only gate that tests recommendation *quality*; run it before shipping
  any Tier 2 prompt additions.
- The catalog *replay* validator (`scripts/replay_catalog_validation.py`) needs saved Gemini snapshots
  in `/tmp` (none present); it is a budget-saving replay, not a unit gate.

---

## Program-wide health review (cross-cutting agent)

Confirms the allocation-drift hypothesis with hard numbers and surfaces adjacent risks beyond the
prompt/catalog. These extend Tier 3.

**Allocation drift (quantified):** `phase2_system.txt` has **10 lifetime commits**, the catalog **2**;
the last substantive prompt rewrite was commit #41 (`a901996d`, 2026-05-14) — ~65 commits ago. In
that window the measurement/test/eval/UI surfaces moved constantly; the recommendation surface got two
one-paragraph additions (#91 downbeats line, #95 the clipping MUST rule). Phase 1 fields emitted and
passed to Gemini in the raw JSON but **absent from the FIELD CITATION MAP with specific paths**:
`genreDetail`, `effectsDetail`, `synthesisCharacter.*` (sub-paths), `textureCharacter.*`, `perceptual`,
`danceability`, `keyProfile`, `tuningCents`, `tuningFrequency`. Gemini must guess how to use them.

**Highest-leverage, code-free items (fastest mission value):**
- Teach the prompt to cite `genreDetail` (genre/confidence → sessionGoal/genreContext) and
  `effectsDetail.gating*` (→ Beat Repeat / Gate / LFO gating).
- Add named sub-paths for `synthesisCharacter.*` / `textureCharacter.*` to the citation map (today the
  parent key is cited, which the path-shape validator can't verify).
- Add worked example cards for the output sections that lack them (only MASTERING has one) — LLMs learn
  format from examples; GROOVE / SYNTHESIS / REVERB / STEM have none.
- Add a `Drum Sampler` catalog entry (named in `_meta`, missing from `devices[]`).

**Grounding code (not just prompt):** `server_phase2.py:_build_descriptor_hooks()` pre-digests Phase 1
for Gemini but only handles segmentLoudness / groove accents / sidechain / vibrato — **not** snareDetail,
hihatDetail, transientDensityDetail, reverbDetail, or the chord timeline (the most specific
reconstruction data). Expanding it is high-leverage and complements the prompt work.

**Contract-safety / reliability gaps (defensive backstops):**
- `_normalize_spectral_detail()` (`server_phase1.py`) — the `spectralCentroid → spectralCentroidMean`
  rename (the exact thing bug #5/#6 above stem from) has **no unit test**. A 5-line test would lock it.
- `_build_descriptor_hooks()` — untested; null groove/sidechain (the common case) could silently emit
  empties.
- `worker.py` (hosted worker entry) — **zero test coverage**; import/API drift fails silently in local,
  catastrophically in hosted.
- Live Gemini smoke asserts only completion, **not** that cards carry `phase1Fields`/`reason` — i.e. it
  does not test the chain-of-custody invariants it's best positioned to catch.
- `url_ingest.py` SSRF guard has integration coverage but no unit tests for the IP-range logic.

**Governance:** `packages/loudness-spectro-wasm/` still has zero imports yet runs a `loudness-wasm` CI
job on every PR (`.github/workflows/ci.yml`). Decision overdue since #88: wire it in at proven Essentia
parity, or shelve it + drop the CI job. (Matches Priority 2 in `asa-next-work-priorities`.)

---

## Live verification — VTSS – Can't Catch Me (2026-05-24)

Ran the real track through measurement + Phase 2 (Gemini 2.5 Flash, inline path, Demucs skipped)
via the canonical `/api/analysis-runs` flow. Phase 1: 144.9 BPM, C Minor, psytrance (conf 1.0),
kick 800 hits / 76 Hz / THD 0.68 / distorted. Phase 2 produced **25 measurement-cited cards**.

**Confirmed working in real Gemini output:**
- Tier-1 #11 Limiter True-Peak: emitted `Limiter | True Peak = On` citing `truePeak`.
- Tier-2 kick rules: `Drum Buss | Boom Frequency = 76 Hz` ← `kickDetail.fundamentalHz`; Drum Buss
  Drive ← `kickDetail.isDistorted`/`thd`. Sentinel guard correctly inert (kickCount=800).
- `sidechainDetail.envelopeShape32` cited (now covered by the validator confidence pair).

**Validator caught (both non-fatal — the chain-of-custody surface working as designed):**
- `UNKNOWN_PARAMETER` `EQ Eight | High Cut` — model over-generalized the Damping→High Cut fix
  (the *Reverb* card used High Cut correctly). Fixed by the High-Cut clarification (commit
  697b0e0a). Warrants a confirming re-run.
- `UNRESOLVED_CITATION_PATH` `arrangementOverview.segments` — pre-existing Phase-2 self-citation
  tendency the prompt already warns against (~line 213); candidate for descriptor-hook / worked-
  example reinforcement.

**Not exercised on this track (correctly):** `effectsDetail.gating*` (no gating present),
`genreDetail.*` (context, not card citations), `synthesisCharacter`/`textureCharacter` (strong
kick/acid/supersaw signals dominated). Adding these to the citation map alone did NOT drive
citation usage — validating the program review's point that **worked examples**, not just map
entries, drive field adoption. Use that for the next Tier-2 batch.
