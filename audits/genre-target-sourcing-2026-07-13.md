# Genre-target sourcing — measured signature/profile ranges from GiantSteps (2026-07-13)

Provenance record for the PR-G7 classifier and mix-doctor changes
(`plans/genre-generalization-program.md`). Every measured number in the
new/retuned `_GENRE_SIGNATURES` entries and `genreProfiles.ts` profiles
traces to this run.

## Method

93 GiantSteps preview clips (locally staged corpus, see
`tests/fixtures/giantsteps/`), sampled per Beatport genre label, each run
through the full Phase 1 pipeline (`analyze.py --yes`, post-PR-G5 main).
Extracted per clip: the seven classifier feature axes (`bpm`, `subBass`,
`crestFactor`, `onsetRate`, `spectralCentroid`, `pumpingStrength`,
`averageDecayMs`) plus `rt60`, `kickThd`, `lufsIntegrated`, `plr`, the
seven spectral-balance bands, and `bpmOctaveEvidence.preferredBpm`.
Signature windows use ~p10–p90; profile band targets use p25/p75 with p50
optimal. Samples: hardcore-hard-techno n=17, electro-house n=15, breaks
n=15, chill-out n=15, hard-dance n=11, dubstep n=10 (control), psy-trance
n=10 (control).

**Caveats, in honesty order:**

1. **LOFI previews.** GiantSteps audio is low-bitrate; the top octave
   under-reads. New signature `spectralCentroid` windows and profile
   Highs/Brilliance `maxDb` are widened on the bright side (~+3 dB /
   +300–600 Hz). Re-source against full-quality references when a licensed
   corpus exists.
2. **2-minute previews**, not full arrangements — intro/outro-weighted
   sections are under-represented.
3. **rt60 reads 1.6–3.0 s on nearly every full mix** (detector saturates);
   excluded from all new signatures.
4. **Measured `pumpingStrength` runs 0.15–0.42 across every genre**, far
   below the 0.35–0.75 windows many ORIGINAL table entries assume. Only
   the three measured controls were retuned here; a full-table
   recalibration against real audio is a named follow-up.

## Headline findings

1. **The tempo-octave error is universal on hardcore**: all 17
   hardcore-hard-techno clips ship a halved/wrong-ratio `bpm` (84–128 for
   true 156–190). PR-G3's `bpmOctaveEvidence.preferredBpm` recovers the
   true octave on 16/17. This forced the classifier's octave-aware bpm
   axis: a gabber signature keyed on the true tempo can never fire on the
   shipped value alone. psy-trance and dubstep show the same halving on
   ~half their clips.
2. **Three control signatures never fired on real audio**: measured breaks
   (centroid 1300–2230 vs the table's 2200–5200 window), dubstep (bass
   decay 0.11–0.40 s vs the assumed 0.6–1.2 s wobble), psy-trance
   (centroid 860–1910 vs 2200–5500). All three retuned to measured ranges.

## Classifier replay — real-clip reads, old table vs new

Replayed the 93 measured feature sets through `analyze_genre_detail`
(dict-driven, no re-analysis):

| Beatport label | Old top read | New top read |
|---|---|---|
| breaks (15) | acid-techno 8 | **breaks 7** |
| chill-out (15) | hiphop 5 / acid-techno 4 | **downtempo 12** |
| dubstep (10) | hiphop 4 / trance 4 | **dubstep 4** |
| electro-house (15) | acid-techno 8 | **electro 8** |
| hard-dance (11) | hiphop 3 / techno 2 | **hardstyle 6** (+gabber 1) |
| hardcore-hard-techno (17) | hiphop 8 | **gabber 10** |
| psy-trance (10) | acid-techno 5 / hiphop 4 | **psytrance 4** |

Correct-family top-1 went from ~0/93 to 51/93. Remaining scatter is
honest: LOFI previews, heuristic features, and closely related families
(breaks/electro/two-step share the 125–140 BPM low-pumping space).

## Knowledge-based entries (no local reference audio)

`trap`, `footwork`, `two-step`, `speed-garage`, `halftime-dnb` carry
rhythm/character windows from standard genre facts — the same provenance
as the original 34-entry table — and are flagged in-line. 2015 Beatport
(the GiantSteps source) has no garage/trap/footwork sections, so these
wait on a future reference corpus for measured refinement. They get **no
mix-doctor profiles** (targets are not invented); their families fall
back via `mapLegacyToEnhanced` (trap → hiphop lineage).

## Reproduction

The batch/aggregation scripts are session scratch; method above is
sufficient to rebuild them. Raw percentiles for every genre/feature are
preserved in the PR-G7 description. Corpus staging: see
`plans/owner-actions-accuracy-program.md` (GiantSteps fetch, 2026-07-05).
