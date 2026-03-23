# Stage 3 Reality Audit

**Date:** 2026-03-18  
**Purpose:** Compare the current repo state to the Stage 3 framing in `docs/ARCHITECTURE_STRATEGY.md` and the attached research inputs:

- `deep-research-report.md`
- `deep-research-report (1).md`
- `deep-research-report (2).md`

This audit is intentionally repo-grounded. It records where the code already matches the Layer 1 / Layer 2 / Layer 3 theory, where old terminology survives only as compatibility debt, and where the product framing still over-promises.

## Stage 3 Product Question

Stage 3 is not “find the next Basic Pitch.” The product question is:

> What producer-facing outputs are honest and useful now, given separated stems, deterministic measurements, and current-model limits?

The current repo should be judged against two intended outputs:

- **Output A — Local pitch/note notes**
  - Purpose: import and clean up
  - Layer: 2
  - Nature: local, stem-based, confidence-aware, best-effort
- **Output B — AI musical stem summary**
  - Purpose: understand what’s happening
  - Layer: 3
  - Nature: grounded, editorial, uncertainty-aware, not pitch/note truth

## Audit Matrix

| Area | Current state | Classification | Notes |
| --- | --- | --- | --- |
| Canonical runtime model | `apps/backend/analysis_runtime.py` separates measurement, pitch/note translation, and interpretation with distinct tables and attempt histories. | `Aligned` | This is the structural foundation the Stage 3 plan needs. |
| Canonical transport boundary | `apps/ui/src/services/analysisRunsClient.ts` parses canonical measurement separately and only reconstructs `transcriptionDetail` in `projectPhase1FromRun()`. | `Aligned` | This is the correct compatibility edge. |
| Pitch/note translation worker integration point | `apps/backend/server.py` pitch/note translation worker calls `analyze_transcription()` rather than importing Basic Pitch directly. | `Aligned` | The `TranscriptionBackend` slot is real. |
| Measurement authority | Canonical measurement strips `transcriptionDetail` before persistence. | `Aligned` | Layer 1 is no longer silently polluted by Layer 2 output. |
| Legacy wrappers | `/api/analyze`, `/api/phase2`, `Phase1Result.transcriptionDetail`, and display projections still preserve the old flat blob. | `Misaligned but compatibility-only` | Acceptable during migration. Do not expand this surface. |
| Session Musician UI wording | The panel existed in a “MIDI transcription / polyphonic vs monophonic” frame. | `Misaligned and needs migration` | Updated in this pass toward pitch/note notes vs melody guide wording. |
| Producer-summary Gemini prompt | `apps/backend/prompts/phase2_system.txt` still treated `transcriptionDetail` as polyphonic truth and blurred pitch/note vs measurement authority. | `Misaligned and needs migration` | Updated in this pass. |
| Basic Pitch framing | Core docs and runtime strings still presented Basic Pitch as a normal/default backend. | `Misaligned and needs migration` | Updated in this pass to `legacy` framing. |
| Experiment B profile | No dedicated `stem_summary` interpretation profile existed. | `Misaligned and needs migration` | Added in this pass as a distinct Layer 3 profile. |
| Descriptor hooks for experiments | Measurement had the raw data (`rhythmDetail.downbeats`, `segmentLoudness`, `sidechainDetail`) but no explicit experiment-oriented hook bundle. | `Misaligned and needs migration` | Added in this pass through prompt grounding hooks, not a broad MIR expansion. |
| Torchcrepe readiness | Strategy doc implied torchcrepe was effectively ready; the backend venv currently does **not** have `torchcrepe` or `penn` installed. | `Misaligned and needs migration` | This is a hard repo-state mismatch, not a theoretical one. |
| Experiment A evaluation pack | No checked-in Vtss bass stem or equivalent three-case evaluation pack is present in the repo. | `Misaligned and needs migration` | The experiment rubric exists in strategy, but the asset pack does not. |
| Ableton / blueprint horizon | The repo does not implement a reconstruction blueprint system. | `Aligned` | This is correct; report `(2)` should remain horizon guidance only. |

## Specific Layer-Bleed Findings

### `transcriptionDetail` still acts too central in a few places

- `apps/ui/src/components/analysisResultsViewModel.ts`
- `apps/ui/src/services/fieldAnalytics.ts`
- legacy `Phase1Result` parsing in `apps/ui/src/services/backendPhase1Client.ts`
- documentation in `apps/backend/README.md`, `apps/backend/ARCHITECTURE.md`, and `apps/backend/JSON_SCHEMA.md`

Status:
- compatibility-only in the transport and view-model layer
- needs continued migration in wording and product framing

### Basic Pitch was still framed as the default future path

Before this pass, that appeared in:

- `apps/backend/analyze.py`
- `apps/backend/README.md`
- `apps/backend/ARCHITECTURE.md`
- `apps/backend/JSON_SCHEMA.md`
- `apps/ui/src/components/SessionMusicianPanel.tsx`
- `apps/ui/README.md`

Status:
- now reframed as `basic-pitch-legacy` in runtime metadata and core docs
- still present historically in changelogs, which is acceptable

### Gemini prompting still blurred measurement and interpretation

Before this pass:

- `apps/backend/prompts/phase2_system.txt` referred to `transcriptionDetail` as polyphonic truth
- there was no dedicated stem-listening profile

Status:
- producer-summary prompt updated
- new `stem_summary` profile added

## Research Inputs Bent Into Repo Reality

### `deep-research-report.md`

Relevant to this repo now:

- torchcrepe and PENN are the right Layer 2 experiment set
- Gemini stem listening is a Layer 3 interpretation path, not a transcription backend
- polyphonic electronic-music transcription remains the wrong bet

Repo consequence:
- keep `TranscriptionBackend`
- quarantine Basic Pitch
- add `stem_summary` as a separate interpretation profile

### `deep-research-report (1).md`

Relevant to this repo now:

- producer-facing legibility needs a bar grid, energy evolution, and pumping/modulation cues more than a wider descriptor backlog

Repo consequence:
- expose only three prompt-grounding hooks for Stage 3:
  - stable bar grid
  - beat-synchronous energy/loudness curve
  - pumping/modulation descriptor

### `deep-research-report (2).md`

Relevant to this repo now:

- useful as horizon guidance for producer workflows and future reconstruction ideas

Repo consequence:
- do **not** turn Stage 3 into a reconstruction-blueprint build

## Immediate Next Steps After This Audit

1. Run Experiment A with a real evaluation pack:
   - one clean bass stem
   - one glide-heavy bass stem
   - one ambiguous melodic/other stem
2. Install and test `torchcrepe` before discussing output quality.
3. Try `PENN` only if torchcrepe fails the quality bar.
4. Keep `BasicPitchBackend` available only as a legacy comparison backend during the experiment window.
5. Evaluate `stem_summary` independently of local MIDI quality.

## Decision Gates

### Local pitch/note notes ship only if:

- at least 2 of 3 evaluation cases are `Green`
- the result is importable after light cleanup
- the output is not dominated by octave spam, segmentation noise, or misleading note clutter

### Gemini stem summary ships only if:

- it stays bar-aligned to measured structure
- uncertainty is explicit
- it does not re-estimate BPM, key, or meter
- a producer would still find it useful when note accuracy is only approximate

## Bottom Line

The runtime architecture is ahead of the product language. The repo already has the right Stage 3 skeleton:

- authoritative measurement
- pluggable pitch/note translation slot
- grounded interpretation slot

What it lacked was honesty at the edges:

- Basic Pitch still looked current instead of legacy
- Session Musician still implied a stronger transcription promise than the strategy supports
- Gemini had no distinct stem-listening profile
- the experiment inputs described in strategy were not actually present in the repo

This pass fixes the language, the interpretation profile boundary, and the audit trail. The next pass should be a real backend bakeoff, not more theory.
