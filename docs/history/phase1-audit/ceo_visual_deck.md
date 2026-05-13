# CEO Visual Deck

This is a picture-first deck brief. Each slide is designed to work with minimal text and strong visual hierarchy.

## Slide 1 - "What This Program Actually Does"

Purpose:
- establish the real system in one frame

Visual:
- left-to-right system hero map
- `audio in -> authoritative measurement -> optional symbolic extraction -> grounded interpretation -> producer-facing outputs`
- make measurement the brightest block
- make symbolic visually secondary

Minimal copy:
- Headline: `This product measures first, interprets second`
- Footer note: `Symbolic notes are optional and best-effort`

Evidence anchors:
- canonical measurement authority in `analysis_runtime.py`
- prompt grounding in `server.py`

## Slide 2 - "Where Truth Lives vs Where Compatibility Lives"

Purpose:
- show the split between the clean architecture and the still-live compatibility shell

Visual:
- split-screen
- left side: canonical `analysis-runs` stage model
- right side: legacy flat `phase1` blob
- draw a caution stripe over the compatibility side

Minimal copy:
- Left label: `Truth`
- Right label: `Compatibility`
- Headline: `The codebase has one authoritative path and one legacy mask`

Evidence anchors:
- `analysis_runtime.py:405-446`
- `server.py:2318-2387`
- `analysisRunsClient.ts:134-149`

## Slide 3 - "What Measurement Really Computes"

Purpose:
- show that Phase 1 is not a single detector; it is a descriptor engine

Visual:
- engine anatomy diagram
- center node: `Measurement`
- surrounding families:
  - timing and meter
  - tonal and harmonic
  - loudness and dynamics
  - stereo and spectral
  - groove and sidechain
  - sound-type detectors
  - structure and segment views

Minimal copy:
- Headline: `Phase 1 is a descriptor factory, not just tempo/key`

Evidence anchors:
- `analyze.py:4276-4437`

## Slide 4 - "Where The Pipeline Cheats"

Purpose:
- make the biggest architecture leak obvious

Visual:
- red duplicate-work loop
- measurement subprocess box shows `separation + transcription`
- canonical persistence box shows `transcription stripped`
- symbolic worker box shows `transcription run again`

Minimal copy:
- Headline: `Requested symbolic work currently leaks into measurement, then runs again later`
- Callout: `This is the most expensive fake cleanliness in the system`

Evidence anchors:
- `analysis_runtime.py:1106-1113`
- `analyze.py:4381-4398`
- `analysis_runtime.py:504-507`
- `server.py:953-980`

## Slide 5 - "What Downstream Actually Uses"

Purpose:
- distinguish valuable output from payload mass

Visual:
- usefulness heatmap
- dark green for heavily used fields
- pale gray for rarely used or uncited fields
- emphasize:
  - bpm
  - key
  - lufsIntegrated
  - spectralBalance.subBass
  - grooveDetail.kickAccent

Minimal copy:
- Headline: `A small core of Phase 1 drives most downstream value`

Evidence anchors:
- `docs/field_utilization_report.md`
- `phase2Validator.ts`
- `analysisResultsViewModel.ts`

## Slide 6 - "Why Phase 1 Is Constrained Today"

Purpose:
- show the system is real, but not cleanly finished

Visual:
- bottleneck board with five columns:
  - boundary leakage
  - dependency fragility
  - field bloat
  - weak handoffs
  - doc and contract drift

Minimal copy:
- Headline: `The bottlenecks are mostly architecture and product-shape problems, not missing DSP effort`

Evidence anchors:
- duplicate symbolic work
- legacy estimate route
- independent queueing of symbolic and interpretation
- stale `--fast` framing

## Slide 7 - "Where To Spend Resources"

Purpose:
- turn findings into budget guidance

Visual:
- 2x2 matrix:
  - `Stabilize now`
  - `Extend next`
  - `Do not expand yet`
  - `Research later`

Suggested placement:
- Stabilize now:
  - clean measurement/symbolic boundary
  - canonical estimate and UI contract
  - stem reuse
- Extend next:
  - torchcrepe backend experiment
  - Phase 1 evaluation pack
- Do not expand yet:
  - more heuristic detectors
  - more legacy wrapper features
- Research later:
  - new beat/downbeat stack
  - deeper chord/structure upgrades

Minimal copy:
- Headline: `Stabilize the contract before buying more capability`

## Slide 8 - "Executive Recommendation"

Purpose:
- end with a hard resource-allocation message

Visual:
- three stacked bands for 30 / 60 / 90 days

30 days:
- stop duplicate symbolic work
- add canonical estimate path

60 days:
- install and benchmark torchcrepe
- add stem reuse and symbolic dependency policy

90 days:
- prune or tier low-value fields
- decide whether symbolic is worth scaling further

Minimal copy:
- Headline: `Do not redesign the whole system. Clean the boundary, then run one decisive backend experiment.`

## Suggested Deck Tone

- boardroom-grade
- dark neutral base with one acid-lime accent and one cyan accent
- minimal body text
- aggressive use of hierarchy and negative space
- no decorative audio-wave cliches unless they carry actual meaning
