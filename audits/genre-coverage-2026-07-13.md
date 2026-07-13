# Genre coverage audit — where the measurements are only proven on techno/house (2026-07-13)

Coverage audit for the genre-generalization program
(`plans/genre-generalization-program.md`). Maps the three genre-aware
surfaces against the priority electronic genres and names the gaps. No code
changes; every claim below carries the file it was read from.

The three surfaces:

1. **Genre classifier signatures** — `_GENRE_SIGNATURES`,
   `apps/backend/analyze_detection.py:1031` (34 signatures) plus
   `_GENRE_FAMILY_MAP` at `analyze_detection.py:1078`.
2. **Synthetic fundamentals corpus** —
   `apps/backend/scripts/build_synthetic_corpus.py` (29 clips,
   `fundamentals_eval_manifest.synthetic.json`).
3. **Mix-doctor genre profiles** — `apps/ui/src/data/genreProfiles.ts`
   (34 profiles, same id set as the backend signatures), resolved by
   `apps/ui/src/services/mixDoctor.ts` via `genreDetail.genre` →
   `genreDetail.genreFamily` → default.

Priority genres (program mandate): UK bass / garage / speed garage / 2-step;
halftime / trap / dubstep / bass; hard dance / hardstyle / gabber; IDM /
ambient / electro; plus footwork, breakbeat, downtempo.

## Summary verdict

The accuracy gates are real but narrow: the synthetic corpus proves the
pipeline on **steady kick-per-beat 4/4 material, mostly 96–140 BPM**, and
the genre surfaces enumerate house/techno lineages in depth while entire
electronic families (trap, hardstyle, gabber, footwork, electro, halftime,
2-step-as-rhythm) have **no signature, no profile, and no corpus clip**.
Nothing in the active gate set exercises a broken kick pattern, a halftime
feel, 16th-note shuffle, beatless material, or any tempo above 174.

## Surface 1 — `_GENRE_SIGNATURES` (analyze_detection.py:1031)

### What exists (34 signatures)

| Family | Signatures | BPM span |
|---|---|---|
| Ambient/downtempo | ambient-drone, ambient-techno, dub-techno, ambient | 40–125 |
| House | deep/organic/classic/tech/progressive/afro/bass-house, house | 115–132 |
| Techno | minimal/melodic/driving/industrial/hard/acid/detroit, techno | 122–160 |
| Trance | trance, psytrance | 136–148 |
| Bass | dubstep | 138–145 |
| D&B/breaks | drum-bass, neurofunk, dnb, breaks | 125–180 |
| UK garage | uk-garage, bassline, garage | 128–142 |
| Legacy broad | edm, hiphop, rock, pop, acoustic | 70–160 |

Feature axes per signature: `bpm`, `subBassDb`, `crestFactor`,
`onsetDensity`, `spectralCentroid`, `sidechainStrength`, `bassDecay`,
optional `rt60` and `kickDistortion` (kickDistortion used by exactly two:
industrial-techno, hard-techno). Weights (`analyze_detection.py:1180`):
sidechain 0.95 and bass decay 0.85 are the primary discriminators — a
**four-on-the-floor-centric assumption**, since both features encode the
kick-pumping relationship that broken-beat genres don't have.

### Priority-genre gaps

1. **trap** — nothing covers it. `hiphop` tops out at 110 BPM and assumes
   the felt (half-time) tempo; a trap track measured at its notated ~140
   BPM (see the tempo-octave trap below) lands nearest `dubstep`
   (138–145), whose sub/decay/centroid ranges then feed wrong mix advice.
2. **footwork / juke** (155–165) — falls between `hard-techno` (145–160,
   wrong character: footwork has low sidechain, sparse sub-heavy toms) and
   `dnb` (160–180, wrong rhythm). No signature.
3. **hardstyle** (150–160) — `hard-techno` will absorb it, but hardstyle's
   reverse-bass kick and much higher kick THD are a different production
   blueprint; the Phase 2 advice chain treats them identically today.
4. **gabber / hardcore** (170–200+) — **no signature of any kind above
   180 BPM.** A 190 BPM gabber track's best match is `dnb`/`drum-bass`,
   which is flatly wrong (different kick, different sub, different swing).
5. **electro** (100–135, broken 808 machine funk) — no signature. The
   broken-beat + high-crest + moderate-tempo combination scores weakly
   everywhere; likely misread as `breaks` or `pop`.
6. **IDM** — no signature. Deliberately heterogeneous; the honest behavior
   is a *confident abstain* (`genreDetail: None` / low confidence), which
   the classifier already supports (`primary_score < 0.25` →
   abstain, `analyze_detection.py:1217`). The audit recommendation is to
   verify abstention on IDM-like material rather than force a signature.
7. **2-step** — `uk-garage` (128–136) exists, but its
   `sidechainStrength: (0.35, 0.65)` encodes 4×4-garage pumping; classic
   2-step has a broken kick and little sidechain, so it scores *against*
   the one signature meant to catch it. No separate 2-step signature; no
   **speed garage** signature (4×4 130–140, warehouse sub) either.
8. **halftime (D&B tempo, half feel)** — no signature; at the measured
   ~85–87 BPM (post-octave-halving) it reads as `hiphop`.
9. **breakbeat** — `breaks` (125–135) exists; adequate for nu-skool/big
   beat. The gap is *measurement-level* (downbeats on syncopated kicks),
   not signature-level.
10. **downtempo / trip-hop** (60–110 with beats) — falls in the crack
    between `ambient` (onsetDensity 0–3, i.e. nearly beatless) and
    `hiphop` (centroid ≤ 2500). No dedicated signature.

### Family-map and cross-boundary gaps

1. `_GENRE_FAMILY_MAP` (`analyze_detection.py:1078`) has **no entries for
   uk-garage, bassline, or garage** — all three fall to `"other"`, so the
   mix-doctor family fallback (`mixDoctor.ts:77`) never fires for garage.
2. The TS side pins `genreFamily` to a closed union of 8 values —
   `apps/ui/src/types/measurement.ts:652` and the `validFamilies` allowlist
   in `apps/ui/src/services/backendPhase1Client.ts:1134`. **Any new family
   must land on both sides** (tripwire #3) or it silently degrades to
   `"other"`.
3. The vocal boost list (`analyze_detection.py:1205`) and supersaw/acid
   boosts don't reference any of the missing genres — fine today, but new
   signatures for trap (808 + vocal) and hardstyle (kick THD) should reuse
   the existing `kickDistortion` axis rather than invent new ones.

## Surface 2 — synthetic corpus span (build_synthetic_corpus.py)

### What the 29 clips cover

| Axis | Coverage |
|---|---|
| Tempo (grid clips) | 70, 90, 110, 128, 140, 174 BPM |
| Tempo (other kinds) | chords 96–140, swing 124, multi 122/128 |
| Meter | 4/4, 3/4, 6/8, 7/8 (odd meters are registered `knownGaps`) |
| Rhythm pattern | **one pattern only: kick on every beat, accented downbeat** (`render_grid_pattern`) |
| Swing | straight-vs-swung **8th-note** hats, 50–66%, at 124 BPM only |
| Key/chords | 12 roots × major/minor, clean sine triads |
| Texture | drums-only, chords-only, bass-only, 2 multi-layer 4/4 clips |

Already-registered `knownGaps` (`_KNOWN_GAPS_BY_ID`,
`build_synthetic_corpus.py:395`): odd meters read as 4/4 (downbeats follow),
7/8 tempo smears, and **174 BPM halves to 86.9** (octave preference).

### What is absent — the priority-genre rhythm surface

1. **Broken kick patterns (2-step, breakbeat, electro).** Every grid clip
   places a kick on every beat. No active check exercises the downbeat
   heuristic (`_compute_downbeat_phase`, `analyze_rhythm.py:160` — it
   *documents* that four-on-the-floor carries no phase information) or the
   meter autocorrelation on syncopation.
2. **Halftime feel (kick 1 / snare 3).** The canonical tempo-octave trap —
   a 140 BPM halftime clip whose truth is 140, not 70 — does not exist.
   Both estimators (RhythmExtractor2013 + Percival) plus the ratio-based
   `apply_bpm_correction` (`analyze_core.py:39`, which *always* sides with
   Percival on a ~2×/1.5× ratio) are unexercised on this case.
3. **Triplet / shuffle swing and 16th-note shuffle.** Swing clips stop at
   66% on the 8th grid. UKG/2-step shuffle lives on the **16th** grid —
   which `compute_swing_detail` (`analyze_rhythm.py:191`) cannot see: it
   keeps only IOIs in 0.30–0.70 beats and hardwires
   `gridResolution: "8th"`.
4. **Sparse / beatless material.** No clip verifies honest abstention —
   tempo confidence collapsing, `swingDetail: None`, meter falling back to
   `assumed_four_four`, key ensemble hedging on drones. (The chords clips
   are beatless but only check key/chords; nothing asserts what the rhythm
   stack *should not* claim on them.)
5. **Tempo extremes 85 / 150 / 190.** 85 (halftime/trap felt tempo) and
   150 (hardstyle) are absent; 174 exists only as a knownGap; **nothing
   above 174 at all** (gabber territory, and the octave-halving failure
   is *worse* there).

## Surface 3 — mix-doctor genre profiles (genreProfiles.ts)

The 34 profile ids mirror the backend signature table one-for-one, so every
signature gap above is also a profile gap: **no trap, footwork, hardstyle,
gabber, electro, IDM, 2-step, speed garage, halftime, or downtempo
spectral/loudness targets.**

Consequence chain: a trap track misclassified as `dubstep` receives
dubstep's `spectralTargets` and LUFS/crest ranges from
`resolveMixDoctorGenreId` (`mixDoctor.ts:93`); the advice is specific,
confident, and wrong — the exact failure mode PURPOSE.md invariant #4
exists to prevent. The genre-agnostic loudness guardrails
(`loudnessGuardrails.ts`) still hold, but every genre-relative suggestion
inherits the misclassification.

Profile shape (`genreProfiles.ts:28`): crest/PLR/LUFS ranges + 7 spectral
band targets. New profiles are additive data entries; the risk is not
mechanism but **unvalidated targets** — new-genre targets must be sourced
from reference-track measurements, not invented (same discipline as the
2026-05-16 audit applied to the existing table).

## Measurement-level implications (what the fix PRs target)

| # | Measurement | Failure mode on priority genres | Evidence |
|---|---|---|---|
| 1 | Tempo octave | 174 → 86.9 measured; 190 unmeasured but same mechanism; halftime trap ambiguous by construction | `_KNOWN_GAPS_BY_ID`, `apply_bpm_correction` always prefers Percival on ratio hits |
| 2 | Meter / downbeats | odd meters read 4/4 (measured); syncopated/broken kicks unmeasured — kick-accent phase heuristic assumes kick-on-downbeat | `analyze_time_signature` 20% margin (`analyze_core.py:1292`), `_compute_downbeat_phase` |
| 3 | Swing | 16th-grid shuffle invisible; `gridResolution` hardwired `"8th"` | `compute_swing_detail` IOI window 0.30–0.70 beats |
| 4 | Key on sparse/ambient | ensemble landed (PR-B3, keep EDMA) but no abstention/hedge check exists on beatless or drone material | `_build_key_ensemble` (`analyze_core.py:159`), corpus gap #4 |
| 5 | Genre classifier | 10 priority families unrepresented or mis-tuned (see Surface 1); family map + TS union must move together | `analyze_detection.py:1031/1078`, `measurement.ts:652`, `backendPhase1Client.ts:1134` |

## Recommended sequence

See `plans/genre-generalization-program.md` for the PR-by-PR program this
audit feeds. Ordering rationale: corpus first (you can't gate what you
can't measure), then measurement fixes each behind the new clips'
pre-registered checks, classifier/profile widening last (it depends on the
measurements being right for the new material).
