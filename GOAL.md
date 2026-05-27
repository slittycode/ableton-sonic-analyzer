# GOAL.md — The Recommendation-Proof Campaign

This is ASA's current **north-star goal**: a single, extended-effort objective an AI coding agent
can chase across many sessions, broken into four sequenced sub-goals. It sits below `PURPOSE.md`
(the *why*) and above `BACKLOG.md` (candidate features). When this campaign completes, the open
question it answers should be settled and the result visible in the product.

> **Authority order:** `PURPOSE.md` > `CLAUDE.md` > this file > per-app `AGENTS.md`. Nothing here
> overrides a quality invariant in `PURPOSE.md`; this campaign exists to *prove* those invariants
> hold, not to bend them.

---

## North-star goal

**Turn ASA's recommendation quality from a manual ear-test into a measurable, repeatable score —
grounded in Ableton Live 12 projects with known device settings — and use that score to prove (or
disprove) that each layer of the pipeline, Gemini included, moves recommendations closer to the
settings that actually produced the sound.**

When this is done:
1. There is a deterministic harness that scores ASA's Phase 2 recommendations against ground truth
   and runs without a human ear in the loop.
2. We have a defensible, numeric answer to *"does Gemini interpretation actually beat the
   deterministic rules?"* — the open question the project owner is currently unsure about.
3. The proof is surfaced in the product UI as per-recommendation verification, not just a CI number.

---

## The key insight (why this design)

The only trustworthy success signal the owner named is: *"I'd have to recreate it in Ableton Live 12
to know if a recommendation is right."* That sounds fatal to unattended iteration — an agent can't
recreate a track by ear. So we **invert the direction**:

> Instead of *ASA recommends → human recreates → human judges*, do
> **human authors a Live project with known settings (once) → renders it → ASA analyzes the render
> → harness checks whether ASA recovered the known settings.**

The "recreate it in Ableton to verify" step becomes a **fixture authored once per track**, not a
manual test repeated every iteration. The `.als` you built *is* the answer key. This is
simultaneously:
- the **proof** the owner wants (the chain of custody verified end-to-end against known truth),
- an **observable success signal** an unattended agent can score itself against, and
- the instrument that **settles the Gemini question** (score the deterministic path vs. the Gemini
  path on the same fixtures).

**Equivalence caveat (the central scoring risk — read before building sub-goal 2):** a track can be
validly reconstructed many ways. If you used `Compressor` and ASA recommends `Glue Compressor`, both
may be "right." Exact-match scoring is therefore wrong and brittle. Score at the level of **right
device *role/family* → right *parameter* → value in the right *direction and magnitude band***, not
byte-exact strings. The answer-key manifest must capture the *measurable intent* (e.g. "kick
fundamental ~55 Hz, heavily saturated") alongside the literal device spec, so a recommendation that
reaches the same measured outcome by a different valid route still earns credit.

---

## How to work this campaign (operating rules)

1. **Scope:** electronic music, optimized for the project owner's own production. Don't spread the
   fixture corpus across all 35 genre profiles — start with the genres the owner actually makes.
2. **Autonomy:** no hard line. You may touch prompts, the device catalog, descriptor-hook backend
   code, the Phase 1 schema, new detectors, and new UI surfaces — whatever raises the score. Honor
   every `PURPOSE.md` invariant and every tripwire in `CLAUDE.md` while doing so.
3. **Batch-and-proceed:** when you can verify an improvement with the harness, proceed and keep it.
   When a change *can't* be proven without the owner's ear or without authoring a new fixture, batch
   it into a clearly-labeled **"needs-your-listen / needs-a-fixture"** queue and keep moving on what
   you *can* prove.
4. **Gemini spend:** at the owner's discretion, not free-for-all. The deterministic recommendation
   path (`abletonDevices.ts`) costs nothing to score and is the cheap inner loop; reserve live Gemini
   runs (`RUN_GEMINI_LIVE_SMOKE=true`, needs `GEMINI_API_KEY`) for baseline comparisons and
   pre-merge confirmation, not every micro-iteration.
5. **Follow existing conventions:** new eval code mirrors the `apps/backend/scripts/evaluate_*.py`
   + `*_evaluation.py` pattern (research-only, off the product path, deletable without changing the
   product). Fixtures mirror `apps/backend/tests/fixtures/transcription_tracks/` /
   `polyphonic_tracks/` (audio + manifest + README per track).
6. **Verify before declaring a sub-goal done:** run the relevant gates (`asa-verify`, backend
   `unittest discover`, frontend `npm run verify`) and state what you checked.

---

## Sub-goal 1 — Ground-truth corpus + fixture format

**Objective:** a small corpus of electronic-genre Ableton Live 12 projects with *known* device
chains, each paired with rendered audio and a machine-readable answer key.

**Fixture authoring = fork 3 (spec-then-dial).** The agent does NOT generate `.als` files and the
owner does NOT design chains from scratch. Instead:
1. The agent writes an explicit, catalog-valid **device spec** for each fixture — exact Live 12
   devices, exact parameter names (must exist in `apps/backend/prompts/live12_device_catalog.json`),
   and exact values (e.g. "Operator → Osc A: Saw, Amp Envelope Decay: 200 ms; Saturator → Drive:
   12 dB, Freq: 4 kHz").
2. The owner builds **exactly that spec** in Live and renders it to audio. Because the spec is the
   instruction, the answer key is provably the spec — no `.als`-parsing trust gap.
3. The agent ingests the rendered audio and finalizes the fixture.

**Deliverables:**
1. A fixture schema (`manifest.json` per track) with two linked parts:
   a. **Device spec** (the answer key): ordered device chains per track-role (kick, bass, melody,
      groove, FX, stereo, master), each device/param/value catalog-valid.
   b. **Measurable intent**: the Phase 1 measurement fingerprint of the rendered audio (run ASA
      Phase 1 on the render and store it), so scoring can credit measurement-equivalent routes.
2. Corpus location: `apps/backend/tests/fixtures/recommendation_tracks/<slug>/` with `audio.*`,
   `manifest.json`, and a `README.md` per track. A top-level corpus README + manifest list.
3. A spec template + an authoring checklist the owner follows in Live (what to dial, how to render —
   match the project's 48 kHz / 24-bit default).
4. Ingest tooling that validates a render against its spec (catalog-validity, Phase 1 sanity:
   does the measured fingerprint plausibly match the declared intent?).

**Start with 5–10 fixtures.** Bias toward the owner's genres. Each fixture should isolate a few
clear, measurable design decisions rather than being a dense full mix — clean signals make scoring
honest.

**Done when:** ≥5 fixtures exist, each with a catalog-valid spec, rendered audio, and a stored Phase 1
fingerprint; the ingest tool passes on all of them; a teammate could add a new fixture by following
the checklist alone.

---

## Sub-goal 2 — The scorer (harness core)

**Objective:** given a fixture, run its audio through ASA and emit a deterministic, repeatable score
for how well the recommendations recover the known settings — no human ear required.

**Deliverables:**
1. `apps/backend/recommendation_evaluation.py` (logic) + `apps/backend/scripts/evaluate_recommendations.py`
   (CLI runner), mirroring the existing eval-harness pattern. Research-only, off the product path.
2. A scoring model implementing the **role/parameter/direction-band** rubric from the key insight
   (NOT exact string match):
   a. **Device-role recall/precision** per production domain (kick, bass, melody, groove, effects,
      stereo, mastering — invariant #5): did ASA cover the ground-truth roles, and did it avoid
      recommending devices with no ground-truth basis?
   b. **Parameter coverage** on matched devices: did it name the right parameters?
   c. **Value accuracy**: is each value within a per-unit tolerance band and in the right direction
      vs. a neutral default? Define tolerances per unit (Hz, dB, ms, ratio, %).
   d. **Chain-of-custody penalty**: reuse `phase2Validator.ts` semantics + the backend citation-path
      check — uncited cards, invalid `phase1Fields` paths, and `PURPOSE.md` invariant violations cost
      points. A high-coverage result that breaks the citation chain must not outscore a cited one.
3. A per-domain breakdown in the report (so "melody is under-covered" stays visible — it's the
   audit's known weakest surface) plus one headline aggregate.
4. An HTML/markdown report alongside the existing `*_report_html.py` harnesses.

**Watch:** scoring real Phase 2 output requires a Gemini call per fixture per run (cost). Make the
runner accept a **recommendation source** so it can score the free deterministic path
(`abletonDevices.ts`) in the cheap inner loop and the paid Gemini path on demand — this is also the
mechanism sub-goal 3 needs.

**Done when:** `evaluate_recommendations.py` runs over the corpus and produces a stable, explainable
score with a per-domain breakdown; re-running on unchanged inputs is deterministic; the score moves
in the expected direction when you deliberately inject a known-bad recommendation.

---

## Sub-goal 3 — Iterate against the score + settle the Gemini question

**Objective:** use the harness to (a) answer whether Gemini interpretation earns its place, then
(b) drive recommendation quality up with a real signal instead of vibes.

**Deliverables:**
1. **The Gemini verdict.** Score three recommendation sources on the same corpus:
   a. deterministic frontend rules (`abletonDevices.ts`) alone,
   b. full Phase 2 / Gemini interpretation,
   c. a no-op / trivial baseline.
   Report the per-domain and aggregate deltas. Deliver a written finding: *does Gemini raise the
   score, on which domains, and by how much?* This directly resolves the owner's open uncertainty
   and should feed back into `PURPOSE.md`/`asa-next-work-priorities` if the answer is surprising.
2. **Score-driven iteration.** With the signal in hand, work the audit's Tier-2/Tier-3 backlog
   (`audits/phase2-recommendation-surface-2026-05-24.md`) — prompt decision rules, catalog gaps,
   `_build_descriptor_hooks` expansion, confidence-hedging fixes — keeping only changes that raise
   the score. Each merged change cites its before/after number.
3. Guard against overfitting: hold out a fixture or two from the tuning loop, or grow the corpus as
   you tune, so you're improving recommendation *quality*, not memorizing the corpus.

**Done when:** the Gemini verdict is documented with numbers; at least one round of score-driven
prompt/catalog improvement has landed with before/after evidence; the harness is wired into a
runnable check the owner can invoke before merges.

---

## Sub-goal 4 — Surface the proof in the product

**Objective:** the owner asked for **proof *and* a richer text/UI blueprint** — make the
ground-truth verification visible to the user, not just a CI artifact.

**Deliverables:**
1. Per-recommendation verification surfacing in `AnalysisResults.tsx` (and the recommendation
   cards): a confidence/verification badge grounded in *"how often this kind of recommendation
   matched ground truth in the corpus."* Build on the existing `ui/` design-system primitives and
   tokens — no one-off styled boxes.
2. Optional: surface the closest ground-truth fixture / the measurement basis behind a card's
   verification, so the user can see *why* a recommendation is trusted.
3. Keep it honest per invariant #4: low corpus-support → hedged/low-confidence badge, never a
   confident badge on a recommendation type the corpus hasn't validated.

**Done when:** an intermediate producer looking at a result can tell which recommendations are
corpus-verified and how strongly, the UI passes `npm run verify`, and the surfacing degrades
gracefully when no corpus evidence applies to a given card.

---

## Sequencing

`1 (ground truth)` → `2 (measurement)` → `3 (iteration + Gemini verdict)` → `4 (proof in product)`.

Sub-goals 1 and 2 are the foundation and must land first — everything after depends on a trustworthy
score. 3 is the payoff (and the answer to the live open question). 4 makes the payoff a product
feature. An agent can begin 4's design while 3 iterates, but 4 ships last.

## What success looks like, in one line

A producer drops a reference track, ASA hands back a Live 12 blueprint, and **each recommendation
carries a verification grounded in tracks whose real settings we know** — and behind it, a harness
the team trusts to tell better recommendations from worse ones without anyone reaching for their ears.

---

## Implementation status (as of 2026-05-27)

This file is the north-star *spec*. A first cut of the supporting implementation — fixture schema,
five catalog-valid spec fixtures, the scorer (`recommendation_evaluation.py` + the CLI runner), the
Node deterministic-source bridge, the UI verification badge wired into `AnalysisResults.tsx`, and
the `RECOMMENDATION_VERDICT.md` write-up — was built on the local branch `worktree-goal-doc` (worktree
at `.claude/worktrees/goal-doc/`) under an explicit "continue without input" directive. It is **not**
on `main`. Landing that work is a separate, deliberate decision; in particular:

1. Sub-goal 1's renders are owner-gated — the five specs need to be dialed in Live 12 and rendered to
   48 kHz / 24-bit FLAC before the corpus is authoritative (see the worktree's
   `apps/backend/NEEDS.md` for the build-and-render checklist).
2. The Gemini-vs-deterministic verdict in the worktree was scored against numpy-proxy renders, not
   Ableton renders, so its known-settings axes (role recall, value accuracy) are provisional until
   the real renders exist.
3. Before any further sub-goal 3 prompt iteration, the worktree branch needs to be rebased on top of
   the Tier-1/2 phase2 prompt fixes that already landed on `main` (commits around `5610ca56` /
   `ade2ae5a`).

When you're ready to bring the implementation across, start from the worktree's `NEEDS.md` — it is
the living status doc for the campaign and tells you what's built, what's render-gated, and what's
next.
