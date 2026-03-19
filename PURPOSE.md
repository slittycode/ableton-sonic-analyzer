# PURPOSE.md — Why ASA Exists

This document is the highest-authority reference for what Ableton Sonic Analyzer does, who it serves, and how every change should be evaluated. It is intended for human developers and AI coding agents alike. When in doubt about whether a change is worthwhile, return here.

---

## Mission

ASA exists to answer a single question that every intermediate electronic music producer asks when they hear a track they admire:

**"How do I make something that sounds like this in Ableton Live 12?"**

No other tool answers this question with measurement-backed specificity. Spectrum analyzers give you numbers. AI chatbots give you opinions. ASA gives you both — in a chain of custody from deterministic ground truth to actionable, justified Ableton device recommendations.

---

## Core Value Proposition

ASA's unique value is the **measure-then-advise pipeline**:

1. **Measure** — Phase 1 runs a deterministic DSP engine that extracts ground-truth metrics from audio: BPM, key, LUFS, spectral balance, stereo field, groove timing, sidechain behavior, synthesis character, arrangement structure, and more. These numbers are not opinions. They are reproducible, verifiable facts about the audio signal.

2. **Advise** — Phase 2 feeds those measurements (plus the audio itself) to an AI interpreter that is constrained to treat the measurements as ground truth. The AI's job is not to re-analyze — it is to translate measurements into a reconstruction blueprint: specific Ableton Live 12 device names, specific parameter names, specific numeric values, and specific reasons tied back to the measurements that justify each recommendation.

The chain of custody — from DSP measurement to cited recommendation — is what makes ASA different. Every recommendation must trace back to a number. Every number must come from the deterministic engine. Break this chain and you break the product.

---

## Target User

ASA serves **intermediate Ableton Live 12 producers** — people who:

- Know what a compressor, EQ, and sidechain are, but may not know which specific Ableton device and parameter values would recreate the pumping they hear in a reference track.
- Can follow a step-by-step reconstruction plan if given one, but wouldn't independently derive the plan from raw spectral data.
- Use reference tracks as learning tools — not to copy, but to understand production techniques and internalize them.
- Trust numbers over vibes, but need the numbers translated into actions they can take in their DAW.

This means:

- Phase 1 output must be accurate and comprehensive enough to serve as ground truth.
- Phase 2 output must be specific enough that the user can open Ableton, create the recommended devices, dial in the recommended values, and hear something that moves toward the reference track's character.
- The UI must present results clearly enough that an intermediate producer doesn't need to be a DSP engineer to understand what they're looking at.

---

## What "Good Output" Looks Like

The ultimate quality test for any ASA feature is: **does this help the user recreate what they hear?**

### Phase 1 (Measurement) Quality

A good Phase 1 result:

- Reports BPM that matches what the user hears when they tap along. If the algorithm detects half-time or double-time, it should still surface the most musically useful tempo.
- Reports a key that matches what the user hears when they play along on a keyboard. Low-confidence keys are flagged, not hidden.
- Reports loudness, dynamics, and stereo characteristics that the user can cross-reference against their own metering plugins and find consistent.
- Extracts groove timing, sidechain behavior, and spectral balance with enough resolution that Phase 2 can make non-generic recommendations.
- Detects arrangement structure well enough that the user can map sections to their own project timeline.

A bad Phase 1 result:

- Returns numbers that don't match what the user hears. (This erodes trust in the entire pipeline.)
- Returns fields that are technically populated but too coarse or noisy to distinguish one track from another.
- Adds new fields that look impressive in the JSON but don't feed into any user-facing recommendation.

### Phase 2 (Interpretation) Quality

A good Phase 2 result:

- Names specific Ableton Live 12 devices (not generic concepts like "a compressor" — say "Glue Compressor" or "Compressor" with the specific mode).
- Specifies parameter values derived from measurements (not "set the attack to taste" — say "Attack: 10ms, informed by the measured crest factor of 8.2 dB indicating preserved transients").
- Explains WHY each recommendation fits THIS track, citing the specific measurement. A user should be able to read a recommendation and think "that makes sense given the numbers."
- Covers the full reconstruction surface: kick/drums, bass, melodic/harmonic content, groove/timing, effects/texture, stereo field, and mastering chain.
- Acknowledges uncertainty honestly. Low-confidence measurements should produce hedged recommendations, not confident-sounding guesses.

A bad Phase 2 result:

- Gives generic production advice that could apply to any track in the genre ("use sidechain compression for house music").
- Recommends devices or parameters without citing the specific measurement that justifies them.
- Ignores available measurements and relies on audio perception for things the DSP already measured.
- Pads output with filler to hit quantity targets without substance.

---

## The Agent Guardrail: The User Value Test

Before implementing any change, apply this test:

### 1. Does this change improve measurement accuracy?

If yes: it directly serves the mission. Prioritize it.

Examples: improving BPM detection on half-time material, fixing key detection on modal content, adding a new detector that feeds into Phase 2 recommendations.

### 2. Does this change improve the quality of recommendations the user receives?

If yes: it directly serves the mission. Prioritize it.

Examples: improving the Phase 2 prompt to produce more specific device recommendations, adding a new UI panel that surfaces measurements the user couldn't previously see, improving how Phase 2 handles low-confidence data.

### 3. Does this change improve the user's ability to act on results?

If yes: it directly serves the mission. Prioritize it.

Examples: MIDI export improvements, better arrangement visualization, clearer confidence indicators, export-to-Ableton features.

### 4. Does this change improve software quality without changing what the user sees?

If yes: it's maintenance work. It has value, but it is not the mission. Do it when it unblocks user-facing work, not as an end in itself.

Examples: refactoring internal types, improving test coverage on unchanged behavior, restructuring modules, upgrading dependencies that aren't broken.

### 5. Does this change add engineering complexity without a clear path to user value?

If yes: **stop and reconsider.** This is the drift pattern that degrades ASA over time.

Examples: adding abstraction layers "for future flexibility" when no concrete future feature needs them, over-engineering error handling beyond what the user would notice, building infrastructure for hypothetical scale that doesn't exist.

---

## Quality Invariants

These are non-negotiable properties of ASA. Any change that violates one of these is a regression, regardless of what else it accomplishes.

1. **Measurement authority.** Phase 1 DSP measurements are ground truth. Phase 2 AI interpretation must never override, re-estimate, or contradict a measured value. If audio perception contradicts a measurement, the system describes the contradiction — it does not silently pick a winner.

2. **Citation chain.** Every Phase 2 recommendation must cite the specific Phase 1 measurement(s) that justify it. Recommendations without measurement justification are filler, not advice.

3. **Ableton specificity.** Recommendations must name exact Ableton Live 12 devices, exact parameter names as they appear in the Ableton UI, and specific values. "Add some compression" is not a recommendation. "Glue Compressor → Attack: 10ms, Ratio: 4:1, Threshold: -18dB (informed by crest factor 8.2 dB)" is a recommendation.

4. **Honest uncertainty.** Low-confidence measurements must propagate to hedged recommendations. The system must never present a guess with the same authority as a high-confidence measurement. The user's trust is the product's foundation.

5. **Reconstruction completeness.** Phase 2 must cover the full production surface — not just the easy parts. Kick, bass, melodic content, groove, effects, stereo, and mastering must all be addressed. Partial coverage leaves the user with an incomplete blueprint.

6. **Intermediate accessibility.** The user should not need to understand DSP theory to act on results. Numbers are translated into Ableton actions. Jargon is either avoided or explained in context.

---

## Decision Framework for New Features

When evaluating whether to add a new feature or capability:

```
                    ┌─────────────────────────────────┐
                    │ Does the user get a better       │
                    │ reconstruction blueprint?        │
                    └──────────┬──────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │        YES          │──────────► BUILD IT
                    └─────────────────────┘
                               │ NO / UNCLEAR
                    ┌──────────▼──────────────────────┐
                    │ Does it make existing features   │
                    │ more accurate or actionable?     │
                    └──────────┬──────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │        YES          │──────────► BUILD IT
                    └─────────────────────┘
                               │ NO / UNCLEAR
                    ┌──────────▼──────────────────────┐
                    │ Does it unblock something that   │
                    │ WILL improve the blueprint?      │
                    └──────────┬──────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │        YES          │──────────► BUILD IT
                    └─────────────────────┘
                               │ NO
                    ┌──────────▼──────────────────────┐
                    │ STOP. This is engineering for    │
                    │ engineering's sake. Reconsider.  │
                    └─────────────────────────────────┘
```

---

## Relationship to Other Documents

- **CLAUDE.md**: How to build and test. Commands, architecture, contracts. Read PURPOSE.md first, CLAUDE.md second.
- **ARCHITECTURE.md** (`apps/backend/`): How the backend components interact. Implementation detail.
- **JSON_SCHEMA.md** (`apps/backend/`): What Phase 1 measures and how to interpret each field. The measurement inventory.
- **BACKLOG.md**: Candidate features from a prior project. Evaluate each against this document's decision framework before porting.
- **Phase 2 system prompt** (`apps/backend/prompts/phase2_system.txt`): The operational instructions for the AI interpreter. Must remain aligned with the quality invariants defined here.

---

## Summary

ASA is not a spectrum analyzer. ASA is not an AI music chatbot. ASA is the bridge between "I hear something" and "here's how to make it in Ableton Live 12" — built on a foundation of deterministic measurements that the user and the AI can both trust.

Every line of code, every new feature, every refactor should make that bridge sturdier, more specific, and more useful to an intermediate producer sitting in front of Ableton with a reference track they want to learn from.
