# Phase 1 Definition

## Observed

Phase 1 has three live meanings in this repo:

1. Canonical runtime meaning: the authoritative `measurement` stage persisted by `AnalysisRuntime` and returned by `GET /api/analysis-runs/{runId}`. That stage is explicitly authoritative and strips `transcriptionDetail` before persistence. Evidence:
- `apps/backend/analysis_runtime.py:405-446`
- `apps/backend/analysis_runtime.py:496-516`
- `apps/ui/src/services/analysisRunsClient.ts:217-248`

2. Legacy API meaning: the old flat `phase1` blob returned by `POST /api/analyze`, built from raw analyzer payload fields and still including `transcriptionDetail` when present. Evidence:
- `apps/backend/server.py:434-488`
- `apps/backend/server.py:2318-2387`

3. Producer-visible UI meaning: a compatibility projection that starts from canonical measurement, then re-attaches symbolic output as `transcriptionDetail` so old Phase 1-shaped UI can still render. Evidence:
- `apps/ui/src/services/analysisRunsClient.ts:134-149`
- `apps/ui/src/App.tsx:503-691`
- `apps/ui/src/App.tsx:720-849`

The result is that "Phase 1" is not one thing. It is:
- a real authoritative measurement stage
- a still-live compatibility payload
- a UI projection that mixes authoritative measurement with best-effort symbolic data

## Inferred

If Phase 1 is defined strictly by the current architecture direction, then Phase 1 is meant to be Layer 1 measurement only: deterministic local DSP and descriptor extraction that downstream stages can trust. That is the direction stated in:
- `docs/ARCHITECTURE_STRATEGY.md`
- `docs/STAGE3_REALITY_AUDIT.md`
- `apps/ui/src/components/AnalysisStatusPanel.tsx`

If Phase 1 is defined by what the product currently shows the user, then it is broader than Layer 1. It effectively includes:
- measurement
- symbolic note extraction when available
- a flattened compatibility model for rendering

## Missing/unclear

What is missing is a single repo-wide statement that says:
- "Phase 1 equals canonical measurement only"
- or "Phase 1 equals the producer-visible measurement-plus-symbolic projection"

That ambiguity is not theoretical. It directly affects:
- API shape
- UI state shape
- estimate routing
- how extensions get slotted into the system

# Phase 1 Components

## Definitely exists

### Core backend runtime and transport
- `apps/backend/analysis_runtime.py`
  - `get_run()`
  - `complete_measurement()`
  - `_enqueue_requested_followups()`
  - `resolve_measurement_flags()`
  - `get_interpretation_grounding()`
- `apps/backend/server.py`
  - `POST /api/analysis-runs`
  - `GET /api/analysis-runs/{run_id}`
  - `POST /api/analysis-runs/{run_id}/symbolic-extractions`
  - `POST /api/analysis-runs/{run_id}/interpretations`
  - `POST /api/analyze` (legacy compatibility)
  - `POST /api/phase2` (legacy compatibility)
  - `_execute_measurement_run()`
  - `_execute_reserved_measurement_job()`
  - `_execute_symbolic_attempt()`
  - `_execute_interpretation_attempt()`
  - `_build_phase1()`
  - `_build_phase2_prompt()`
  - `_build_stem_summary_prompt()`
  - `_build_descriptor_hooks()`

### Measurement engine
- `apps/backend/analyze.py`
  - `main()`
  - `build_analysis_estimate()`
  - `extract_rhythm()`
  - all local descriptor analyzers used in the monolithic measurement subprocess
  - `TranscriptionBackend` protocol
  - `analyze_transcription()`
- `apps/backend/analyze_fast.py`
  - `analyze_fast()`

### UI transport and projection
- `apps/ui/src/services/analysisRunsClient.ts`
  - `createAnalysisRun()`
  - `getAnalysisRun()`
  - `projectPhase1FromRun()`
  - `projectPhase2FromRun()`
  - `parseCanonicalMeasurementResult()`
- `apps/ui/src/services/analyzer.ts`
  - `analyzeAudio()`
  - `monitorAnalysisRun()`
- `apps/ui/src/App.tsx`
  - primary analysis flow
  - legacy estimate route usage

### UI consumption
- `apps/ui/src/components/AnalysisResults.tsx`
- `apps/ui/src/components/SessionMusicianPanel.tsx`
- `apps/ui/src/components/analysisResultsViewModel.ts`
- `apps/ui/src/components/AnalysisStatusPanel.tsx`
- `apps/ui/src/services/phase2Validator.ts`
- `apps/ui/src/services/fieldAnalytics.ts`

### Tests
- `apps/backend/tests/test_analyze.py`
- `apps/backend/tests/test_analysis_runtime.py`
- `apps/backend/tests/test_server.py`
- `apps/ui/tests/services/analysisRunsClient.test.ts`
- `apps/ui/tests/services/analyzer.test.ts`
- `apps/ui/tests/services/phase2Validator.test.ts`

## Appears intended but incomplete

- A clean Layer 1 / Layer 2 / Layer 3 separation is intended, but measurement still runs symbolic work inside `analyze.py` when symbolic mode is requested.
- A canonical `analysis-runs` transport is intended, but the estimate flow still uses a legacy route in the UI.
- A pluggable symbolic backend seam is intended via `TranscriptionBackend`, but the repo still resolves effectively to Basic Pitch legacy or `auto`.
- A richer interpretation profile system exists, but the producer-facing projection still centers the old Phase 1 shape.
- Field-usage analytics exist, but the inventory is partially stale and not yet used to drive hard pruning.

## Implied but missing

- A single source of truth document for "what Phase 1 is now"
- A benchmark/evaluation harness for symbolic backend experiments
- A phase-specific quality bar for detector usefulness
- A canonical estimate endpoint attached to `analysis-runs`
- A dependency policy for whether interpretation should wait for symbolic completion
- Confidence/reliability metadata at the field level for many heuristic detectors

# Actual Pipeline

## 1. User input and run creation

Observed:
- Canonical path starts at `POST /api/analysis-runs` in `apps/backend/server.py:1341-1381`.
- UI uses that path through `createAnalysisRun()` and `analyzeAudio()`.
- Initial snapshot returns `measurement=queued`, downstream stages blocked until measurement completes.

What goes in:
- uploaded audio file
- requested symbolic mode/backend
- requested interpretation mode/profile/model

What happens:
- backend persists the source artifact
- runtime creates an analysis run row plus an initial queued measurement row

What comes out:
- a run snapshot with stage statuses and source artifact metadata

Status:
- Working

## 2. Measurement job reservation

Observed:
- Worker path uses `reserve_next_measurement_run()` and `_execute_reserved_measurement_job()`.
- Legacy `/api/analyze` bypasses the queued worker style and executes measurement immediately after creating the run.

What goes in:
- queued measurement row
- requested symbolic mode

What happens:
- runtime converts `symbolic_mode` into measurement flags through `resolve_measurement_flags()`
- today only `off` and `stem_notes` are supported

What comes out:
- measurement execution call with `run_separation`, `run_transcribe`, and `run_fast`

Status:
- Working but policy-limited

Critical observed detail:
- `resolve_measurement_flags("stem_notes") -> (True, True)` in `apps/backend/analysis_runtime.py:1106-1113`
- that means symbolic mode already changes measurement behavior before the symbolic worker runs

## 3. Measurement subprocess execution

Observed:
- `_execute_measurement_run()` calls `_run_measurement_subprocess()` and then persists or fails measurement.
- `analyze.py` is still the single monolithic measurement subprocess.

What goes in:
- source audio path
- `run_separation`
- `run_transcribe`
- `run_fast`

What happens:
- `analyze.py` loads mono
- optional fast path uses `analyze_fast()`
- full path loads stereo
- optional Demucs separation
- shared rhythm extraction
- detector pass across tempo, key, loudness, stereo, spectral, melody, groove, sidechain, acid, reverb, vocal, supersaw, bass, kick, genre, effects, synthesis character, danceability, structure, segment-level metrics, chords, perceptual, and Essentia feature blocks
- optional transcription pass runs inside `analyze.py` itself

What comes out:
- one raw JSON payload shaped like the old Phase 1 contract

Evidence:
- `apps/backend/server.py:812-856`
- `apps/backend/analyze.py:4166-4447`
- `apps/backend/analyze_fast.py:16-147`

Status:
- Working, but still architecturally mixed

## 4. Measurement persistence and canonicalization

Observed:
- `complete_measurement()` copies the raw payload, removes `transcriptionDetail`, persists result, provenance, and diagnostics, then queues follow-ups.

What goes in:
- raw analyzer payload
- provenance
- diagnostics

What happens:
- `transcriptionDetail` is stripped
- measurement stage is marked completed

What comes out:
- authoritative measurement result in `measurement_outputs`

Evidence:
- `apps/backend/analysis_runtime.py:496-516`
- `apps/backend/tests/test_analysis_runtime.py:66-122`

Status:
- Working

## 5. Follow-up stage enqueueing

Observed:
- `_enqueue_requested_followups()` independently queues symbolic extraction and interpretation after measurement completion.

What goes in:
- completed run id
- requested stage configuration

What happens:
- creates a symbolic attempt if symbolic mode is not `off`
- creates an interpretation attempt if interpretation mode is not `off`

What comes out:
- queued follow-up attempt rows

Evidence:
- `apps/backend/analysis_runtime.py:1038-1086`

Status:
- Working, but with a weak handoff policy

Critical observed detail:
- interpretation is queued independently of symbolic completion
- so interpretation can run with measurement only, even when symbolic work was requested but has not completed yet

## 6. Optional symbolic extraction stage

Observed:
- `_execute_symbolic_attempt()` can materialize stems, resolve backend, call `analyze_transcription()`, and persist best-effort output.

What goes in:
- run id
- source audio
- requested symbolic backend/mode

What happens:
- if needed, backend materializes stems via Demucs and records them as artifacts
- calls `analyze_transcription()`
- stores resulting `transcriptionDetail` as `symbolicExtraction.result`

What comes out:
- best-effort symbolic result, not authoritative measurement

Evidence:
- `apps/backend/server.py:912-980`
- `apps/backend/tests/test_server.py:1781-1865`

Status:
- Working, but constrained by backend quality and duplicated work upstream

## 7. Optional interpretation stage

Observed:
- `_execute_interpretation_attempt()` always grounds on canonical measurement, optionally includes symbolic result, and marks measurement authoritative / symbolic best-effort in the prompt metadata.

What goes in:
- measurement result
- optional symbolic result
- profile and model

What happens:
- builds prompt from authoritative measurement JSON
- attaches optional symbolic JSON
- adds descriptor hooks derived from measurement
- persists interpretation result

What comes out:
- interpretation stage result

Evidence:
- `apps/backend/analysis_runtime.py:330-366`
- `apps/backend/server.py:1205-1253`
- `apps/backend/server.py:1630-1778`
- `apps/backend/tests/test_server.py:1342-1492`

Status:
- Working

## 8. Canonical transport to UI

Observed:
- UI polls `GET /api/analysis-runs/{runId}`.
- `parseCanonicalMeasurementResult()` strips leaked `transcriptionDetail` defensively.
- `projectPhase1FromRun()` re-attaches symbolic output for compatibility rendering only.

What goes in:
- run snapshot with stage snapshots

What happens:
- canonical measurement is parsed separately
- symbolic extraction result stays separate
- compatibility projection reconstructs a flat Phase 1-like object for rendering

What comes out:
- `displayPhase1`
- `displayPhase2`
- run update stream

Evidence:
- `apps/ui/src/services/analysisRunsClient.ts:134-149`
- `apps/ui/src/services/analysisRunsClient.ts:217-248`
- `apps/ui/src/services/analyzer.ts:161-236`

Status:
- Working, but compatibility-heavy

## 9. UI state and producer-facing output

Observed:
- `App.tsx` stores `measurementResult` and `symbolicResult` separately, but repeatedly reconstructs them from the compatibility projection.
- `AnalysisResults` and `SessionMusicianPanel` consume both the measurement and symbolic layers.
- `analysisResultsViewModel` explicitly prefers symbolic notes when available and falls back to `melodyDetail`.

What goes in:
- projected Phase 1 display object
- interpretation output

What happens:
- UI renders detector cards, measurement summaries, musician/piano-roll views, and interpretation content

What comes out:
- producer-visible Phase 1 experience

Evidence:
- `apps/ui/src/App.tsx:503-691`
- `apps/ui/src/components/analysisResultsViewModel.ts:387-433`
- `apps/ui/src/components/SessionMusicianPanel.tsx`

Status:
- Working

## 10. Legacy compatibility path

Observed:
- `/api/analyze` still exists, logs itself as legacy, returns deprecation headers, and flattens the raw payload into `phase1`.
- `/api/phase2` ignores client-provided `phase1_json` and resolves server-owned measurement instead.

What goes in:
- uploaded audio and old flags

What happens:
- legacy route creates a canonical run behind the scenes
- then returns a legacy-shaped response

What comes out:
- legacy `phase1`
- deprecation headers

Evidence:
- `apps/backend/server.py:2318-2403`
- `apps/backend/server.py:2405-2468`
- `apps/backend/tests/test_server.py:1560-1719`

Status:
- Working, but compatibility debt

# Pipeline Gaps and Failure Points

## 1. The canonical boundary exists, but the measurement subprocess still performs Layer 2 work

Observed:
- when symbolic mode is `stem_notes`, measurement is launched with `run_transcribe=True`
- `analyze.py` then runs transcription inside the measurement subprocess
- `complete_measurement()` strips that output
- symbolic extraction later runs again through the symbolic worker

Evidence:
- `apps/backend/analysis_runtime.py:1106-1113`
- `apps/backend/analyze.py:4381-4398`
- `apps/backend/analysis_runtime.py:504-507`
- `apps/backend/server.py:953-980`

Impact:
- duplicate work
- blurred measurement/symbolic boundary
- wasted latency and compute

Judgment:
- real architectural gap, not a fake problem

## 2. Symbolic and interpretation are auto-queued independently, so interpretation can outrun symbolic

Observed:
- `_enqueue_requested_followups()` queues both stages immediately after measurement
- `_execute_interpretation_attempt()` accepts `symbolicResult=None`

Impact:
- producer-summary output may be grounded only on measurement even when symbolic was requested
- stage ordering is not semantically enforced

Judgment:
- weak handoff, not a hard limitation of the architecture

## 3. Phase 1 still has no single product contract

Observed:
- runtime says measurement is authoritative
- legacy API still returns flat Phase 1
- UI re-projects symbolic into Phase 1 for display

Impact:
- extensions can land in the wrong layer
- UI and docs can keep reintroducing symbolic-as-measurement confusion

Judgment:
- implementation and migration gap

## 4. The estimate path is still legacy and not aligned with actual execution variants

Observed:
- `App.tsx` still uses `estimatePhase1WithBackend()` through the legacy estimate route
- `build_analysis_estimate()` accepts `run_fast` in signature but current call path and estimate logic do not appear to differentiate fast mode meaningfully

Evidence:
- `apps/ui/src/App.tsx:259-264`
- `apps/backend/analyze.py:200-232`
- `apps/backend/analyze.py:4183-4187`

Impact:
- estimate UX is disconnected from the canonical API
- fast mode can be described inaccurately

Judgment:
- implementation gap

## 5. Fast mode is real, but docs still misdescribe it

Observed:
- `analyze_fast.py` returns a sparse but real schema-compatible payload
- repo docs and agent guidance still contain drift around `--fast`

Impact:
- operator confusion
- wrong product assumptions

Judgment:
- fake limit caused by stale documentation, not by missing implementation

## 6. Many emitted Phase 1 fields are not clearly paying for themselves

Observed:
- field utilization report shows a narrow set of Phase 1 fields driving most recommendations
- field analytics inventory contains stale or mismatched field names

Evidence:
- `docs/field_utilization_report.md:7-40`
- `apps/ui/src/services/fieldAnalytics.ts:63-161`

Impact:
- payload bloat
- slow extension discussions because everything looks equally important

Judgment:
- mixed: partly a usefulness problem, partly an observability problem

# Current Limits

## Technical limits

- Monolithic measurement subprocess. `analyze.py` still owns a very large amount of DSP, optional separation, and optional transcription in one execution path.
- Duplicate symbolic work when symbolic mode is enabled. Measurement can transcribe and symbolic can transcribe again.
- Fast mode preserves the full schema shape but mostly returns `None`, so contract compatibility hides meaningful capability loss.
- Runtime is local-file plus sqlite plus worker-loop based. Fine for local/dev, weak for larger throughput or distributed execution.
- Stem materialization can happen after measurement via a second Demucs pass because measurement-time stem outputs are not retained for reuse.

## Architectural limits

- Phase 1 has three active definitions.
- Canonical and compatibility surfaces still coexist in user-visible flows.
- Interpretation does not depend on symbolic completion even when symbolic was requested.
- Estimate flow is still not canonicalized into `analysis-runs`.
- Measurement remains authoritative only after a defensive strip step, not because upstream execution is cleanly measurement-only.

## Model / analysis limits

- Symbolic backend is still effectively Basic Pitch legacy by default path. That backend downmixes to mono and explicitly works best on one instrument at a time.
- The repo does not yet contain an installed, validated torchcrepe or PENN backend despite strategy docs pointing there.
- Many detector outputs are heuristic and repo-grounded, but not backed by an evaluation pack in this repo.
- Segment, chord, and structure outputs are useful but still coarse; they are not obviously calibrated for DAW-grade editing decisions.

## UX / product limits

- User-visible "Phase 1" still mixes authoritative measurement and best-effort symbolic output.
- The estimate route, legacy route, and canonical route tell slightly different stories about the same stage.
- The UI does separate `measurementResult` and `symbolicResult` in state, but it keeps reconstructing both from a Phase 1-shaped projection.
- Rich detector output does not automatically translate into richer user value; many outputs remain descriptive activity more than decision leverage.

## Data quality / extraction limits

- Basic Pitch path is fragile on supported macOS setups and awkward on macOS arm64 Python versioning.
- Symbolic note extraction on dense electronic full mixes is intrinsically approximate even with separation.
- Some field-usage infrastructure is stale relative to the current payload shape.
- There is no clearly checked-in golden dataset for Phase 1 regression quality.

# Are These Real Limits?

## Real limits

- Full-mix symbolic truth is fundamentally hard. The system cannot make polyphonic note extraction from dense mixes "authoritative" just by changing plumbing.
- Separation quality and transcription quality will remain approximate on complex electronic material even with better backends.
- Dependency maintenance and licensing are real constraints:
  - Demucs upstream is no longer maintained at Meta.
  - Essentia is AGPL.
  - madmom model/data licensing is non-commercial.
  - aubio is GPL.

## Fake limits

- "Fast mode does nothing." False. The code implements a real sparse fast path.
- "Phase 1 cannot be authoritative yet." False. Canonical measurement is already persisted as authoritative and tested as such.
- "Interpretation still depends on client Phase 1 JSON." False. Legacy `/api/phase2` resolves server-owned measurement and ignores client-provided measurement JSON.

## Temporary or implementation-gap limits

- Duplicate measurement-plus-symbolic work
- legacy estimate route
- lack of symbolic completion dependency before interpretation
- stale docs and stale analytics inventory
- missing experiment harness for torchcrepe and PENN
- over-large Phase 1 field surface with weak usefulness ranking

## Bottom line

The biggest current constraints are not fundamental DSP impossibilities. They are mostly:
- stage-boundary leakage
- migration debt
- under-instrumented usefulness
- not-yet-run backend experiments

# Extension Opportunities

## Ranked by value

### 1. Stop doing symbolic work inside measurement, then doing it again later

What it adds:
- cleaner Layer 1 boundary
- lower latency and lower wasted compute
- much clearer semantics for Phase 1

Type:
- incremental architecturally
- high leverage operationally

Difficulty:
- medium

Dependency risk:
- low

Belongs in:
- Phase 1 now

### 2. Persist and reuse stems across measurement and symbolic extraction

What it adds:
- removes duplicate Demucs passes
- makes symbolic retry cheaper
- gives a stable artifact seam for future backends

Type:
- incremental

Difficulty:
- medium

Dependency risk:
- low to medium

Belongs in:
- Phase 1 now

### 3. Install one maintained symbolic backend behind `TranscriptionBackend` and benchmark it

What it adds:
- honest answer to whether Phase 1-adjacent symbolic extraction can move beyond Basic Pitch legacy
- real data for product decisions

Type:
- transformative for symbolic usefulness, not for measurement itself

Difficulty:
- medium

Dependency risk:
- medium

Belongs in:
- Phase 1-adjacent, but should be done now because it currently distorts Phase 1 expectations

### 4. Canonicalize estimate and monitoring around `analysis-runs`

What it adds:
- one transport model
- clearer UX
- easier future deprecation of legacy endpoints

Type:
- incremental

Difficulty:
- medium

Dependency risk:
- low

Belongs in:
- Phase 1 now

### 5. Make interpretation wait for symbolic completion only when a profile truly depends on symbolic

What it adds:
- cleaner handoff contracts
- fewer silent "measurement-only even though symbolic was requested" interpretations

Type:
- incremental

Difficulty:
- low to medium

Dependency risk:
- low

Belongs in:
- Phase 1 / Phase 3 boundary now

### 6. Split Phase 1 outputs into core, optional, and experimental tiers

What it adds:
- payload discipline
- easier product storytelling
- clearer extension roadmap

Type:
- incremental, but strategically important

Difficulty:
- medium

Dependency risk:
- low

Belongs in:
- Phase 1 now

### 7. Add a Phase 1 evaluation pack

What it adds:
- objective regression checking for tempo, key, sectioning, and symbolic note experiments
- stops opinion-driven architecture arguments

Type:
- transformative for decision quality

Difficulty:
- medium to high

Dependency risk:
- low

Belongs in:
- Phase 1 now

### 8. Upgrade rhythm/downbeat or structure using external MIR tooling

What it adds:
- potentially better section boundaries and bar grids

Type:
- incremental to medium

Difficulty:
- medium

Dependency risk:
- medium to high

Belongs in:
- after boundary cleanup, not before

# Best Existing Tools / Methods Worth Considering

## Keep using

### Essentia

Why it matters:
- it is already the backbone of local measurement
- broad descriptor coverage
- mature MIR/DSP building blocks

Why consider it "best":
- it already matches the repo's strongest capability: deterministic local measurement

Caution:
- AGPL licensing matters for product strategy

## Keep, but do not overinvest in as the strategic differentiator

### Demucs

What it adds:
- high quality stem separation for bass/other style routing

Why it matters:
- symbolic extraction and some melody analysis benefit from stem-aware paths

Caution:
- upstream Meta repo is not maintained anymore and the fork is bug-fix only
- this argues for operational containment, not aggressive platform expansion around it

## Best fit for the next symbolic experiment

### torchcrepe

What it adds:
- maintained PyTorch CREPE implementation
- periodicity output
- built-in Viterbi decoding and threshold/filter tools

Why it fits this repo:
- the repo strategy already points toward monophonic stem-note extraction rather than broad polyphonic full-mix truth
- Viterbi plus periodicity is a good fit for bass or dominant-line stem work

Caution:
- not currently installed in the backend environment

## Strong fallback candidate

### PENN

What it adds:
- neural pitch plus periodicity
- multiple decoders including Viterbi and pYIN-style paths

Why it matters:
- gives another monophonic stem-note path if torchcrepe quality is insufficient

Caution:
- more moving parts
- runtime/model integration still needs repo work

## Useful for beat/downbeat experiments, but watch licensing

### madmom

What it adds:
- strong beat/downbeat tracking lineage
- packaged DBNBeatTracker-style tooling

Why it matters:
- could improve bar-grid reliability and section timing

Caution:
- model/data licensing is non-commercial
- good experiment tool, not a free product default

## Useful as prototyping glue, not as the main answer

### librosa

What it adds:
- segmentation, onset, beat, chroma, sequence utilities

Why it matters:
- good for prototyping structure and feature post-processing

Caution:
- it is a toolkit, not a drop-in authoritative detector stack

### aubio

What it adds:
- lightweight onset, pitch, beat, tempo, MFCC, transient/steady-state tools

Why it matters:
- fast prototyping and real-time leaning utilities

Caution:
- GPL
- likely lower ceiling than the maintained neural pitch candidates for the specific symbolic role here

# Highest-Leverage Improvements

## 1. Purify the Phase 1 boundary

Do this:
- stop letting `symbolic_mode=stem_notes` force measurement-time transcription
- keep measurement authoritative and deterministic
- move symbolic extraction fully into the symbolic stage
- persist or reuse stems so separation is not repeated

Why first:
- it removes duplicated work
- clarifies what Phase 1 actually is
- reduces the chance of future architecture drift

## 2. Canonicalize the product flow around `analysis-runs`

Do this:
- add a canonical estimate path
- stop using legacy estimate as the main UX path
- keep symbolic projection explicitly compatibility-only
- de-emphasize `/api/analyze` and `/api/phase2` in user-facing flows

Why second:
- it aligns the runtime truth with the UI truth
- it makes future extension work cheaper

## 3. Run one real symbolic backend experiment with a repo-local scorecard

Do this:
- implement a `torchcrepe` backend behind `TranscriptionBackend`
- compare it against Basic Pitch legacy on a small, curated stem set
- score note usefulness, octave stability, confidence usefulness, and producer value

Why third:
- it answers whether Phase 1-adjacent symbolic work is worth extending
- it turns strategy-doc intent into measurable repo reality

# Risks and Blind Spots

## 1. Counting detectors instead of value

Risk:
- the code emits a lot of Phase 1 material, but downstream value clusters around a much smaller subset

Why this matters:
- the team can mistake payload breadth for product depth

Evidence:
- `docs/field_utilization_report.md:7-40`
- `apps/ui/src/services/fieldAnalytics.ts:67-161`

## 2. Confusing symbolic plausibility with measurement truth

Risk:
- the UI and compatibility surface still make it easy to treat `transcriptionDetail` as part of Phase 1 truth

Why this matters:
- it distorts user trust and engineering prioritization

Evidence:
- `apps/ui/src/services/analysisRunsClient.ts:134-149`
- `apps/ui/src/App.tsx:540-542`
- `apps/ui/src/components/analysisResultsViewModel.ts:387-433`

## 3. Extending before evaluating

Risk:
- new backends or new detector families can be added without a repo-local quality bar

Why this matters:
- the system can grow in complexity without improving producer usefulness

Evidence:
- strategy docs reference torchcrepe and PENN, but repo state still lacks a checked-in evaluation harness and installed experiment path

# Final Verdict

Verdict: **Phase 1 is only partially realized**

Why:
- the authoritative measurement stage is real, tested, persisted, and used downstream
- the UI and interpretation stack do consume it meaningfully
- but the actual Phase 1 boundary is still muddied by legacy compatibility, duplicated symbolic work, and an unresolved product definition

More direct version:
- Layer 1 measurement exists and works
- "Phase 1" as a clean, finished product phase does not yet fully exist

If Phase 1 were frozen today, it would be extendable, but not yet clean enough to scale extension work without first fixing the boundary and contract issues above.

## If I were continuing this project tomorrow

1. Remove measurement-time transcription from the canonical symbolic-request path and make stem reuse explicit.
2. Add a canonical estimate flow to `analysis-runs` and stop relying on the legacy estimate route in the main UI.
3. Implement a `torchcrepe` backend behind `TranscriptionBackend` and evaluate it on a small stem-based benchmark against Basic Pitch legacy.
4. Add a hard distinction in the UI between authoritative measurement and optional symbolic notes.
5. Use field-usage evidence to cut or tier low-value Phase 1 outputs before adding more detectors.
