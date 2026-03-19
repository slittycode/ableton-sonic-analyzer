# Phase 1 Pipeline Map

This file describes the actual pipeline as it exists today, not the idealized one.

## Stage 1: Upload and run creation

Input:
- audio file
- requested symbolic mode/backend
- requested interpretation mode/profile/model

Code:
- `apps/backend/server.py:1341-1381`
- `apps/ui/src/services/analyzer.ts:161-179`

Behavior:
- UI posts the file to `POST /api/analysis-runs`
- backend stores the source artifact and creates a queued measurement job
- returned snapshot marks downstream stages blocked until measurement completes

Output:
- `runId`
- stage snapshot with `measurement=queued`

Status:
- working

## Stage 2: Measurement scheduling

Input:
- queued measurement row
- requested symbolic mode

Code:
- `apps/backend/analysis_runtime.py:464-494`
- `apps/backend/server.py:859-901`

Behavior:
- worker reserves the next queued run
- runtime converts symbolic mode into measurement flags
- today:
  - `off -> (False, False)`
  - `stem_notes -> (True, True)`

Output:
- measurement execution call arguments

Status:
- working, but policy is narrow and architecturally leaky

## Stage 3: Measurement subprocess

Input:
- source audio path
- `run_separation`
- `run_transcribe`
- `run_fast`

Code:
- `apps/backend/server.py:812-856`
- `apps/backend/analyze.py:4166-4454`
- `apps/backend/analyze_fast.py:16-147`

Behavior:
- normal path:
  - load mono
  - optional stereo load
  - optional Demucs separation
  - shared rhythm extraction
  - broad detector pass
  - optional transcription pass
- fast path:
  - computes a smaller core measurement set
  - preserves full schema shape with many `None` fields

Output:
- raw JSON payload in old Phase 1 shape

Status:
- working

Fragility:
- monolithic
- symbolic work can already happen here

## Stage 4: Canonical measurement persistence

Input:
- raw analyzer payload
- provenance
- diagnostics

Code:
- `apps/backend/analysis_runtime.py:496-516`

Behavior:
- copies payload
- strips `transcriptionDetail`
- persists authoritative measurement

Output:
- `stages.measurement.result`

Status:
- working

Important note:
- this is where the authoritative Layer 1 boundary is enforced today
- it is enforced after the subprocess, not inside the subprocess design

## Stage 5: Follow-up queueing

Input:
- completed measurement run

Code:
- `apps/backend/analysis_runtime.py:1038-1086`

Behavior:
- queues symbolic extraction if requested
- queues interpretation if requested

Output:
- attempt rows for follow-up stages

Status:
- working

Fragility:
- interpretation does not wait for symbolic completion

## Stage 6: Symbolic extraction

Input:
- source audio path
- optional stem paths
- backend id

Code:
- `apps/backend/server.py:912-980`
- `apps/backend/analyze.py:3635-4160`

Behavior:
- materializes stems if needed
- resolves backend
- calls `analyze_transcription()`
- stores result as best-effort symbolic output

Output:
- `stages.symbolicExtraction.result`

Status:
- working

Fragility:
- when measurement already ran with `run_transcribe=True`, this is duplicate symbolic work
- when measurement already ran with separation, this can still rematerialize stems later

## Stage 7: Interpretation

Input:
- authoritative measurement
- optional symbolic result
- profile and model

Code:
- `apps/backend/analysis_runtime.py:330-366`
- `apps/backend/server.py:1205-1778`

Behavior:
- loads grounded measurement and symbolic state
- builds prompt with:
  - authoritative measurement JSON
  - optional symbolic extraction JSON
  - grounding metadata
  - measurement-derived hooks
- persists interpretation result

Output:
- `stages.interpretation.result`

Status:
- working

Fragility:
- may run before symbolic is complete
- therefore symbolic is additive, not guaranteed

## Stage 8: Canonical transport to UI

Input:
- run snapshot from `GET /api/analysis-runs/{runId}`

Code:
- `apps/ui/src/services/analysisRunsClient.ts:134-149`
- `apps/ui/src/services/analysisRunsClient.ts:217-248`
- `apps/ui/src/services/analyzer.ts:185-236`

Behavior:
- parses measurement separately
- defensively strips leaked `transcriptionDetail`
- projects a legacy-shaped Phase 1 display object by merging symbolic result back in

Output:
- `displayPhase1`
- `displayPhase2`

Status:
- working

Fragility:
- this re-blurs the measurement/symbolic boundary for product rendering

## Stage 9: Producer-facing UI

Input:
- projected Phase 1 display object
- interpretation result

Code:
- `apps/ui/src/App.tsx:503-691`
- `apps/ui/src/components/analysisResultsViewModel.ts:387-433`
- `apps/ui/src/components/SessionMusicianPanel.tsx`

Behavior:
- UI stores `measurementResult` and `symbolicResult` separately
- melody-related views prefer symbolic notes when present
- detector cards and musician views render both measurement and symbolic information

Output:
- producer-visible Phase 1 experience

Status:
- working

Fragility:
- user-facing "Phase 1" still looks broader than authoritative measurement

## Stage 10: Legacy compatibility routes

Input:
- audio file and old Phase 1/Phase 2 style client expectations

Code:
- `apps/backend/server.py:434-488`
- `apps/backend/server.py:2318-2403`
- `apps/backend/server.py:2405-2468`

Behavior:
- `/api/analyze` still returns a flat `phase1` response
- `/api/phase2` still exists, but resolves server-owned measurement instead of trusting client payload

Output:
- deprecated compatibility responses

Status:
- working, but compatibility-only

## What fully flows today

- Audio upload -> canonical run creation -> measurement execution -> authoritative measurement persistence -> polling -> UI rendering
- Audio upload -> canonical run creation -> measurement execution -> interpretation grounding -> interpretation result -> UI rendering

## What only partially flows today

- Symbolic request -> clean Layer 2-only symbolic execution

Reason:
- measurement still performs symbolic work when `stem_notes` is requested
- symbolic stage then exists as a second pass, not the only pass

## Where the product still has dead weight

- legacy `/api/analyze` payload shaping
- legacy estimate route
- Phase 1 compatibility projection as a long-term state shape
- large numbers of fields with unclear downstream value
