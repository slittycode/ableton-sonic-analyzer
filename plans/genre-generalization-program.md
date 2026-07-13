# Genre-generalization program — from "passes on techno" to "passes across electronic"

Successor to the Phase A/B accuracy program (ground-truth harnesses; meter
evidence, real swing, key ensemble, stem-aware chords — all merged). The
accuracy gates currently over-index on four-on-the-floor techno/house: the
synthetic corpus is steady-kick 4/4 at mostly 96–140 BPM, and entire
electronic families have no signature, no mix-doctor profile, and no corpus
clip. The measured evidence is in
`audits/genre-coverage-2026-07-13.md` — read it first; this plan is the
PR-by-PR execution of its findings.

Priority genres: UK bass / garage / speed garage / 2-step; halftime / trap /
dubstep / bass; hard dance / hardstyle / gabber; IDM / ambient / electro;
plus footwork, breakbeat, downtempo.

## Non-negotiable discipline (how every prior PR shipped)

1. **Additive or surfacing-only, behind a pre-registered gate.** Never
   override an authoritative Phase 1 value (PURPOSE.md invariant #1). A fix
   that would change a shipped value (e.g. the octave-corrected `bpm`)
   first ships as surfaced evidence + a frozen decision doc in
   `incorporations/`, exactly like the key-ensemble gate
   (`incorporations/key-ensemble-decision-2026-07-04.md`).
2. **Every new field lands on both sides**: `analyze.py` camelCase →
   `JSON_SCHEMA.md` + `EXPECTED_TOP_LEVEL_KEYS` (and the full-only list) →
   `src/types/measurement.ts` → `backendPhase1Client.ts` reconstructor →
   `phase1FullPayload.ts` fixture → `phase1CitationContract.test.ts` if
   citable. Then re-baseline the golden deliberately:
   `UPDATE_PHASE1_GOLDEN=1 ./venv/bin/python -m unittest tests.test_phase1_golden`.
3. **Green before every push** (from repo root):
   ```bash
   cd apps/backend && ./venv/bin/python -m unittest discover -s tests
   ./venv/bin/python scripts/build_synthetic_corpus.py --check --audio-only \
     --out-dir tests/fixtures/fundamentals_tracks \
     --manifest tests/fixtures/fundamentals_eval_manifest.json
   ./venv/bin/python scripts/evaluate_fundamentals.py --fail-on-skip
   cd ../ui && npm run verify
   ```
4. **One coherent change per PR**, stacked for review — behavior changes
   are shown before merging. Honest PR bodies: what is validated
   synthetically vs. what still needs real audio.
5. New fundamentals clips that fail at baseline enter
   `_KNOWN_GAPS_BY_ID` (report-but-don't-gate), exactly like the odd-meter
   and 174 BPM entries — the gap list is the program's burn-down chart.

## PR sequence

### PR-G1 — Coverage audit (docs only) — this PR

`audits/genre-coverage-2026-07-13.md` + this plan. No behavior change.

### PR-G2 — Synthetic corpus expansion + gate promotion

Extend `scripts/build_synthetic_corpus.py` with known-truth clips spanning
the missing rhythm/tempo surface, and promote them into the active
fundamentals manifest (`fundamentals_eval_manifest.synthetic.json`):

1. **2-step broken kick** (~132 BPM): kick on 1 and the "and" of 2 (or
   equivalent classic pattern), snare on 2 and 4 — truth: bpm, 4/4,
   beatGrid, downbeats. Exercises the kick-accent downbeat phase heuristic
   off its four-on-the-floor assumption.
2. **Halftime feel** (kick 1 / snare 3) at 140 and 85 — truth pins the
   *notated* tempo; this is the deliberate tempo-octave trap.
3. **Triplet/shuffle swing** (66.7% triplet target) and **16th-note
   shuffle** clips (UKG-style) — expected initially to land in
   `knownGaps` because `compute_swing_detail` only reads the 8th grid.
4. **Breakbeat syncopation**: sampled-breaks-style pattern (syncopated
   kick, ghost snares) — beat/downbeat truth.
5. **Sparse/beatless ambient**: slow pad, no percussion — the *abstention*
   clip. Active checks assert what the pipeline should NOT claim:
   low/absent tempo confidence, `swingDetail` None or `direction:
   straight` with low confidence, meter on the assumed-4/4 fallback, key
   still correct on tonal pads.
6. **Tempo extremes**: grid clips at 85, 150, 174 (exists), 190. 190 and
   likely 150+ enter `knownGaps` at baseline (octave halving).

Every new clip kind gets `_EXPECTED_KEYS_BY_KIND` / `_THRESHOLDS_BY_KIND`
entries and deterministic-render `--check` coverage. Measured baseline
failures are registered in `_KNOWN_GAPS_BY_ID` with the owning fix PR named
in a comment. This PR changes no product code.

### PR-G3 — Tempo octave handling at extremes (surfacing first)

Surface octave evidence additively: candidate tempos (measured, ×2, ÷2 with
their supporting evidence — onset-rate consistency, beat-grid density,
genre-prior band) as a new full-mode field; never rewrite `bpm`. Gate: the
PR-G2 halftime + extreme clips flip from `knownGaps` to active passes on
the *evidence* field (does the true octave appear as a candidate with
dominant support?). Promotion of any evidence-driven correction into the
shipped `bpm` requires a frozen `incorporations/` decision doc measured on
GiantSteps tempo (staged locally, 664 clips) — same protocol as the
key-ensemble gate.

### PR-G4 — Meter/downbeats on non-4/4 and broken kicks

The measured weak layer (audit baseline 2026-07-03). Improve
`analyze_time_signature`'s discrimination (the 20% margin conservatism) and
`_compute_downbeat_phase`'s kick-on-downbeat assumption using the meter
evidence field (Phase B) plus snare/backbeat evidence. Gate: PR-G2's
2-step/breakbeat clips + the existing odd-meter knownGaps burn down without
regressing the 29 existing clips or the golden. beat_this (venv-eval,
adopt_pending_asa_slice) remains the candidate backend for the bigger jump;
its gate stays the frozen beat-this doc, not this PR.

### PR-G5 — Swing on the 16th grid (2-step shuffle)

Extend `compute_swing_detail` to detect the dominant swing grid (8th vs
16th) instead of hardwiring `"8th"` — additive: `gridResolution` already
exists as a field; new evidence lands beside it. Gate: PR-G2 shuffle/16th
clips activate; existing 8th-grid swing clips (50–66%) must not move.

### PR-G6 — Key honesty on sparse/ambient material

No algorithm change expected: the ensemble (keep-EDMA) already ships. This
PR adds the abstention/hedge checks from the PR-G2 ambient clips (key
confidence + ensemble disagreement behavior on drones/beatless pads) and
fixes only what those checks prove wrong, surfacing-only.

### PR-G7 — Genre classifier + mix-doctor widening (both sides, one PR)

Add signatures for the missing families — trap, footwork, hardstyle,
gabber/hardcore, electro, 2-step, speed garage, halftime, downtempo — and
tune uk-garage's sidechain assumption. IDM is a verified-abstain, not a
signature. Must move together (tripwire #3):

1. `_GENRE_SIGNATURES` + `_GENRE_FAMILY_MAP` (backend),
2. the `genreFamily` union in `src/types/measurement.ts:652` + the
   `validFamilies` allowlist in `backendPhase1Client.ts:1134`,
3. `genreProfiles.ts` mix-doctor profiles with *sourced* targets
   (reference-track measurements, not invented numbers),
4. golden re-baseline if any fixture's classification shifts.

Gate: classification checks on PR-G2 clips where the synthetic render is
genre-representative; for families a synthetic clip can't honestly
represent (gabber kick THD, trap 808 character), the PR body says so and
the check waits for real-audio fixtures.

## Real-audio validation (operator machine, network available)

From `plans/owner-actions-accuracy-program.md`: GiantSteps key/tempo (604 +
664 clips) and GTZAN + GTZAN-Rhythm are **already staged locally**
(2026-07-05). Remaining:

1. **Demucs weights fetch** — first `--separate` run on this machine pulls
   the torchaudio Hybrid Demucs weights, activating the stem-aware chord
   path (PR-B4) that cloud sessions could never exercise (falls back to
   full-mix without weights). Then re-run the fundamentals multi clips and
   record whether the stem path holds its ≥0.45 floor.
2. **GiantSteps tempo re-run** whenever PR-G3 surfaces octave evidence —
   the real-audio octave-error rate is the gate metric.
3. **ASA 18-clip beat slice** stays the owner's hand-annotation task (the
   one deliberately non-automatable item).

## Definition of done

The fundamentals summary gates on clips spanning broken-kick, halftime,
shuffle, breakbeat, beatless, and 85–190 BPM material — with
`_KNOWN_GAPS_BY_ID` empty or every remaining entry tied to a named,
frozen-gate decision doc — and the genre surfaces (signatures, family map,
TS union, mix-doctor profiles) cover the priority families on both sides of
the contract.
