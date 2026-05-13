# Phase 1 Audit Evidence Index

This directory was created as an advisory-only workspace. No existing repo files were edited during this pass.

## Key Repo Files and Why They Matter

### Canonical runtime boundary

- `apps/backend/analysis_runtime.py`
  - `get_run()` exposes stage model and marks `measurement.authoritative = True` (`368-446`)
  - `complete_measurement()` strips `transcriptionDetail` before persistence (`496-516`)
  - `_enqueue_requested_followups()` independently queues symbolic and interpretation attempts (`1038-1086`)
  - `resolve_measurement_flags()` maps `stem_notes` to `(True, True)` (`1106-1113`)
  - `get_interpretation_grounding()` returns canonical measurement plus optional symbolic result (`330-366`)

### Measurement execution

- `apps/backend/server.py`
  - `_execute_measurement_run()` executes and persists measurement (`812-856`)
  - `_execute_reserved_measurement_job()` derives measurement flags from symbolic mode (`859-901`)
  - `_execute_symbolic_attempt()` runs symbolic extraction via `analyze_transcription()` (`953-980`)
  - `_execute_interpretation_attempt()` grounds interpretation on measurement, with symbolic optional (`1205-1267`)
  - `POST /api/analysis-runs` canonical run creation (`1341-1381`)
  - `GET /api/analysis-runs/{run_id}` canonical polling (`1384-1399`)
  - `POST /api/analyze` legacy compatibility path (`2318-2403`)
  - `POST /api/phase2` legacy interpretation compatibility path (`2405-2468`)
  - `_build_phase1()` legacy flat Phase 1 shaping (`434-488`)

- `apps/backend/analyze.py`
  - `build_analysis_estimate()` (`200-232`)
  - `extract_rhythm()` (`548+`)
  - `TranscriptionBackend` protocol (`3635-3655`)
  - `main()` monolithic measurement pipeline including optional separation and transcription (`4166-4454`)

- `apps/backend/analyze_fast.py`
  - real fast-path implementation returning sparse schema-compatible output (`16-147`)

### UI transport and product projection

- `apps/ui/src/services/analysisRunsClient.ts`
  - `projectPhase1FromRun()` merges symbolic result back into a compatibility Phase 1 view (`134-149`)
  - `parseCanonicalMeasurementResult()` strips leaked `transcriptionDetail` defensively (`245-248`)

- `apps/ui/src/services/analyzer.ts`
  - canonical `analysis-runs` creation and polling path (`161-236`)

- `apps/ui/src/App.tsx`
  - legacy estimate route still used (`259-264`)
  - main analysis path uses canonical `analyzeAudio()` and stores `measurementResult` and `symbolicResult` separately (`503-691`)
  - retry flows also use canonical endpoints (`720-849`)

- `apps/ui/src/components/analysisResultsViewModel.ts`
  - `buildMelodyInsights()` prefers symbolic notes over `melodyDetail` when symbolic exists (`387-433`)

- `apps/ui/src/services/phase2Validator.ts`
  - validates interpretation against Phase 1 for BPM, key, LUFS, genre/DSP context, and bounds (`1-240`)

- `apps/ui/src/services/fieldAnalytics.ts`
  - inventory of all Phase 1 fields used for utilization reporting; useful but partially stale (`63-161`)

### Strategy and drift docs

- `docs/ARCHITECTURE_STRATEGY.md`
  - Layer 1 / Layer 2 / Layer 3 target architecture
  - dependency verdicts for Demucs, torchcrepe, PENN

- `docs/STAGE3_REALITY_AUDIT.md`
  - states canonical measurement is authoritative and compatibility wrappers are migration debt

- `docs/field_utilization_report.md`
  - concrete evidence that many Phase 1 fields are not driving recommendations

## Tests Run

### Backend contract and compatibility tests

Command:

```bash
cd apps/backend && ./venv/bin/python -m unittest \
  tests.test_analyze.AnalyzeStructuralSnapshotTests.test_output_contains_expected_raw_top_level_fields \
  tests.test_analyze.AnalyzeFastStructuralSnapshotTests.test_output_schema_matches_full_mode \
  tests.test_server.AnalysisRunCompatibilityTests.test_analyze_returns_analysis_run_id_and_persists_measurement \
  tests.test_server.AnalysisRunCompatibilityTests.test_analyze_can_return_legacy_transcription_detail_without_contaminating_canonical_measurement \
  tests.test_server.StageWorkerTests.test_symbolic_worker_uses_analyze_transcription_protocol_entry_point \
  tests.test_server.StageWorkerTests.test_reserved_measurement_job_uses_runtime_symbolic_mode_resolution
```

Result:

```text
Ran 6 tests in 3.195s
OK
```

Notable signals:
- canonical measurement persistence is covered
- legacy `/api/analyze` compatibility behavior is covered
- symbolic worker protocol entry point is covered
- measurement flag resolution from symbolic mode is covered

### UI type-check

Command:

```bash
cd apps/ui && npm run lint
```

Result:

```text
> sonic-analyzer-ui@1.6.0 lint
> tsc --noEmit
```

Status: passed

## Additional Test Files Read for Evidence

- `apps/backend/tests/test_analysis_runtime.py:66-122`
  - proves canonical measurement strips `transcriptionDetail` and queues symbolic

- `apps/backend/tests/test_server.py:1342-1492`
  - proves legacy `/api/phase2` ignores client Phase 1 JSON and uses server-owned measurement
  - proves dedicated `stem_summary` prompt path exists

- `apps/backend/tests/test_server.py:1560-1865`
  - proves `/api/analyze` returns `analysisRunId` and persists measurement
  - proves legacy `phase1.transcriptionDetail` can exist while canonical measurement excludes it
  - proves symbolic worker uses `analyze_transcription()` protocol entry point

- `apps/ui/tests/services/analysisRunsClient.test.ts:189-345`
  - proves canonical run projection strips leaked measurement `transcriptionDetail`
  - proves symbolic retry and interpretation retry use canonical endpoints

## Primary-Source Web Research

These were read only to evaluate realistic extension options.

- [Essentia](https://github.com/MTG/essentia)
  - broad MIR/DSP feature library, active releases, AGPL

- [Demucs](https://github.com/facebookresearch/demucs)
  - official repo states it is no longer maintained by Meta; fork is bug-fix only

- [Basic Pitch](https://github.com/spotify/basic-pitch)
  - polyphonic AMT, downmixes stereo to mono, works best on one instrument at a time, Mac M1 note for Python 3.10

- [torchcrepe](https://github.com/maxrmorrison/torchcrepe)
  - PyTorch CREPE, periodicity output, Viterbi decoding, MIT

- [PENN](https://github.com/interactiveaudiolab/penn)
  - pitch plus periodicity, decoders including Viterbi and pYIN-style options, MIT

- [madmom](https://github.com/CPJKU/madmom)
  - MIR library with beat/downbeat tooling, model/data licensing caveat for commercial products

- [librosa](https://librosa.org/doc/latest/index.html)
  - broad MIR building blocks, not a drop-in authoritative detector stack

- [aubio](https://aubio.org/)
  - lightweight onset/pitch/beat library, GPL

## Command Log Summary

Representative non-mutating commands used during the audit:

```bash
pwd
git rev-parse --show-toplevel
git status -sb
rg -n "..." apps/backend/analysis_runtime.py
rg -n "..." apps/backend/server.py
rg -n "..." apps/ui/src
nl -ba <file> | sed -n '<range>p'
cd apps/backend && ./venv/bin/python -m unittest ...
cd apps/ui && npm run lint
```

## Read-Only Compliance Notes

- Existing repo files: read only
- Tests: non-mutating unit tests and type-check only
- New files: created only under `advisory/phase1_audit/`
- No formatter, migration, config, schema, or source-code edits were applied outside this advisory directory
