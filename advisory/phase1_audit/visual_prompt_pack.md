# Visual Prompt Pack

These prompts are designed for a designer, an image model, or a slide-builder. Each prompt is grounded in the repo findings and is intended to produce executive-grade visuals with very little explanatory text.

## Global Art Direction

Style:
- boardroom-grade systems visual design
- premium electronic-music-adjacent aesthetic, but restrained
- graphite, off-white, muted charcoal, one acid-lime accent, one cyan accent
- high contrast
- precise grid
- sparse text
- no cartoon UI
- no generic stock-business look

Visual rules:
- make authoritative measurement look stable and dense
- make symbolic output look provisional and lighter
- make legacy compatibility look faded, amber, or caution-marked
- use arrows and process framing, not random icons

## Prompt 1: System Hero Map

Goal:
- show the full product flow in one frame

Prompt:
"Create a high-end executive systems diagram for an audio-analysis product. Show a left-to-right pipeline with five major blocks: Audio Input, Authoritative Measurement, Optional Symbolic Extraction, Grounded Interpretation, Producer-Facing Output. Make Authoritative Measurement the brightest and most stable element in the composition. Show Symbolic Extraction as optional and best-effort, visually secondary. Use a dark graphite background, off-white type, cyan data lines, and acid-lime emphasis only on the authoritative layer. Minimal text, minimal ornament, very crisp grid, premium strategy-deck aesthetic, electronic-music sophistication without neon clutter."

Must show:
- measurement is first
- interpretation is grounded by measurement
- symbolic is optional

Must avoid:
- making symbolic look primary
- mixing all layers into one blob

## Prompt 2: Truth vs Compatibility Split

Goal:
- show that the codebase has a clean path and a legacy mask

Prompt:
"Design a split-screen architecture graphic. Left side: a clean canonical stage-based architecture labeled Analysis Runs, with separate blocks for Measurement, Symbolic Extraction, and Interpretation. Right side: a faded legacy flat Phase 1 blob carrying many fields in one dense panel. Use green or cyan for the canonical side, amber caution styling for the legacy side. The emotional message should be: truth exists, but compatibility still surrounds it. Minimal text, only short labels, no paragraphs."

Must show:
- canonical stage model
- compatibility blob
- explicit visual asymmetry favoring canonical

## Prompt 3: Measurement Engine Anatomy

Goal:
- show what Phase 1 actually computes

Prompt:
"Create a radial systems diagram centered on the word Measurement. Around it, place seven precise descriptor families: Tempo and Meter, Loudness and Dynamics, Stereo and Spectral, Melody and Groove, Sound-Type Detectors, Structure and Segments, Chords and Perceptual Features. Each family should feel like a measurement cluster feeding a central engine. Use crisp thin-line connectors, restrained typography, and a serious technical aesthetic suitable for a CEO who funds R&D. No gimmicks."

Must show:
- Phase 1 is broad descriptor extraction
- it is more than bpm and key

## Prompt 4: Pipeline Heatmap

Goal:
- show which stages work cleanly and which are partial or fragile

Prompt:
"Design a pipeline heatmap for a software system. Each stage should be represented as a horizontal block with a status color: green for working, yellow for partial or fragile, red for leakage or duplicate work. Stages: Upload and Run Creation, Measurement Scheduling, Measurement Subprocess, Canonical Persistence, Follow-up Queueing, Symbolic Extraction, Interpretation, UI Projection, Legacy Compatibility. Highlight one red duplicate-work loop where transcription happens inside measurement and then again in symbolic extraction. Minimal labels, very strong visual hierarchy."

Must show:
- duplicated symbolic work
- canonical persistence as a clean green stage

## Prompt 5: Output Usefulness Map

Goal:
- show that only a subset of Phase 1 outputs carry most downstream value

Prompt:
"Create an executive data-utility heatmap with Phase 1 fields on the left and downstream usage intensity on the right. Highlight bpm, key, lufsIntegrated, spectralBalance.subBass, and grooveDetail.kickAccent as the strongest-value fields. Fade confidence fields and niche detector outputs into pale low-value rows. The image should communicate payload discipline, not complexity theater. Use a minimal black, white, gray, acid-lime palette with maybe one cyan accent line."

Must show:
- value concentration
- payload excess

## Prompt 6: Bottleneck Board

Goal:
- show where resources are actually blocked

Prompt:
"Design a boardroom bottleneck board with five equal columns labeled Boundary Leakage, Dependency Fragility, Weak Handoffs, Field Bloat, and Contract Drift. In each column, represent the bottleneck as a compact systems tile, not as long text. Use red for the strongest blockers and amber for the medium blockers. This should look like an executive operating review for a technical product, not a software screenshot."

Must show:
- boundary leakage as the dominant blocker

## Prompt 7: Investment Map

Goal:
- tell the CEO where to spend money and where not to

Prompt:
"Create a 2x2 investment matrix titled Resource Allocation for Phase 1. Quadrants: Stabilize Now, Extend Next, Stop Pretending, Research Later. Place Clean Measurement Boundary, Canonical Estimate Flow, and Stem Reuse in Stabilize Now. Place Torchcrepe Backend Experiment and Phase 1 Evaluation Pack in Extend Next. Place More Legacy Wrapper Surface and More Heuristic Detector Sprawl in Stop Pretending. Place Beat/Downbeat Stack Upgrade and Chord/Structure Research in Research Later. Make the composition elegant, sparse, and forceful."

Must show:
- clear prioritization
- anti-sprawl posture

## Prompt 8: 30 / 60 / 90 Day CEO Slide

Goal:
- end with action

Prompt:
"Create a final executive roadmap slide with three horizontal bands labeled 30 Days, 60 Days, and 90 Days. Use sharp, premium typography and thin-line dividers. In 30 Days place boundary cleanup and canonical estimate flow. In 60 Days place torchcrepe benchmark and stem reuse. In 90 Days place field pruning and go/no-go decision on symbolic expansion. Make it look expensive, focused, and evidence-driven."

Must show:
- sequence
- restraint
- concrete investment direction

## Optional Motion / Animation Notes

If these visuals are built in slides or Figma:
- use one decisive wipe for pipeline arrows
- use staggered reveal only for bottlenecks and priority matrix
- avoid generic pulsing glows or floating cards
- the motion should feel like instrument signal routing, not a startup landing page
