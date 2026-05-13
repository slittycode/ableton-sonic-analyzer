# Resource Priority Matrix

## Ranking Criteria

- Payoff: likely impact on Phase 1 usefulness and clarity
- Difficulty: implementation effort inside this repo
- Dependency risk: external fragility, licensing, maintenance, or environment risk
- Phase fit: whether the work belongs inside Phase 1 now or should wait

| Rank | Opportunity | Bucket | What it adds | Incremental or transformative | Difficulty | Dependency risk | Likely payoff | Phase fit | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Remove measurement-time transcription from symbolic-requested runs | Existing in repo, underused seam | Makes Phase 1 boundary real, cuts duplicate work | Incremental with large strategic payoff | Medium | Low | Very high | Phase 1 now | `analysis_runtime.py:1106-1113`, `analyze.py:4381-4398` |
| 2 | Persist and reuse stems across measurement and symbolic | Existing in repo, custom extension | Avoids repeated Demucs work and makes symbolic retries cheaper | Incremental | Medium | Low to medium | Very high | Phase 1 now | `server.py:912-950` |
| 3 | Canonicalize estimate into `analysis-runs` | Existing in repo, underused | Aligns UI truth with runtime truth, removes legacy estimate dependence | Incremental | Medium | Low | High | Phase 1 now | `App.tsx:259-264`, `server.py:1537-1585` |
| 4 | Add one maintained symbolic backend through `TranscriptionBackend` | Existing seam plus external tool | Turns symbolic from legacy-only into an actual experiment path | Transformative for symbolic usefulness | Medium | Medium | High | Phase 1-adjacent now | `analyze.py:3635-3655` |
| 5 | Build a small Phase 1 evaluation pack | New custom capability | Gives objective basis for tempo/key/section/note quality decisions | Transformative for product truth | Medium to high | Low | High | Phase 1 now | No checked-in harness found; strategy docs imply the need |
| 6 | Make interpretation optionally wait for symbolic completion | Existing in repo, underused | Removes a weak handoff when a profile depends on symbolic | Incremental | Low to medium | Low | Medium to high | Phase 1 / Phase 3 boundary now | `analysis_runtime.py:1038-1086`, `server.py:1205-1233` |
| 7 | Tier Phase 1 fields into core / optional / experimental | Existing in repo, custom product discipline | Reduces payload bloat and improves product clarity | Incremental | Medium | Low | Medium to high | Phase 1 now | `docs/field_utilization_report.md`, `fieldAnalytics.ts` |
| 8 | Torchcrepe experiment | Wider-world tool | Better monophonic stem-note candidate with periodicity and Viterbi | Transformative for symbolic quality if it works | Medium | Medium | Medium to high | Phase 1-adjacent now | Strategy doc plus upstream repo |
| 9 | PENN experiment | Wider-world tool | Alternative pitch plus periodicity candidate | Transformative if torchcrepe disappoints | Medium | Medium | Medium | Later than torchcrepe | Strategy doc plus upstream repo |
| 10 | Beat/downbeat upgrade with madmom-style methods | Wider-world tool | Potentially better bar grid and structure timing | Incremental to medium | Medium | Medium to high | Medium | Later | `madmom` licensing and integration caution |
| 11 | Structure/chord prototyping with librosa utilities | Wider-world tool | Faster experimentation around segmentation/chroma pipelines | Incremental | Low to medium | Low | Medium | Later | `librosa` is useful glue, not the authoritative stack |
| 12 | Lightweight realtime experiments with aubio | Wider-world tool | Cheap onset/pitch/tempo prototyping | Incremental | Low | High for licensing | Low to medium | Later or side-path only | GPL limits product fit |

## Recommended Resource Split

### Fund immediately

- boundary cleanup
- stem reuse
- canonical estimate path

### Fund as the first true extension bet

- `torchcrepe` backend experiment
- small evaluation pack

### Do not fund yet

- more detector families
- more legacy wrapper work
- broad UI polishing around a still-ambiguous contract

### Research after stabilization

- better beat/downbeat stack
- richer chord and section modeling
- additional symbolic backends beyond the first serious experiment
