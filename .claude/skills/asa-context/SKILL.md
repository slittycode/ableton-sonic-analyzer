---
name: asa-context
description: Use this skill at the start of a session working on the ASA project (Ableton Sonic Analyzer) at ~/code/projects/asa, or when the user says "load asa context", "/asa-context", "warm up on asa", "what's the asa project about", or asks for an overview of ASA's mission, architecture, or quality invariants. Loads the canonical project docs and produces a structured summary the user can scan to confirm the assistant has the right context.
version: 0.1.0
---

# ASA Context Loader

## Purpose

Bring an agent (or a fresh session) up to speed on the Ableton Sonic Analyzer project in a single, sourced summary. ASA is opinionated — read the canonical docs in order, do not paraphrase from memory.

## When to use

- Start of any session where ASA work is the focus.
- User says "load context", "/asa-context", "warm up on asa", "give me the asa overview".
- An agent has been asked to make a non-trivial change to ASA and you want a sanity check that it has internalized the quality invariants before it writes code.

## Procedure

Read the following files in this exact order. Do not skip — each one builds on the prior.

1. `~/code/projects/asa/PURPOSE.md` — **highest authority.** Mission, target user, what good output looks like, the 6 quality invariants, decision framework. Read in full.
2. `~/code/projects/asa/AGENTS.md` — root agent-facing guide. Build commands, testing strategy, key modules.
3. `~/code/projects/asa/apps/backend/AGENTS.md` — backend-specific patterns and contracts.
4. `~/code/projects/asa/apps/ui/AGENTS.md` — frontend-specific patterns and contracts.
5. `~/code/projects/asa/CLAUDE.md` — Claude Code-specific guidance for working in this repo. (Some content overlaps with AGENTS.md — read for the parts that differ.)
6. `~/code/projects/asa/BACKLOG.md` — backport candidates from `sonic-architect-app`. Read **headings only** unless the user asks about a specific item.

If `~/code/projects/asa/docs/ARCHITECTURE_STRATEGY.md` exists, also read it — it records *why* the three-layer design is shaped the way it is, and is required reading before proposing structural changes.

## Output format

After reading, produce a structured summary in this exact shape. Keep it to 10–14 lines total so it's scannable.

```
**ASA Context Summary**

Mission: <one sentence from PURPOSE.md>

Architecture (three layers):
  1. Measurement — <one phrase, name the engine>
  2. Pitch/note translation — <one phrase, name the tools>
  3. Interpretation — <one phrase, name the model>

Quality invariants (from PURPOSE.md, all six by name):
  1. Measurement authority
  2. Citation chain
  3. Ableton specificity
  4. Honest uncertainty
  5. Reconstruction completeness
  6. Intermediate accessibility

Working stack:
  - Backend: <python version, key libs>
  - Frontend: <framework + key deps>
  - Ports: UI <port>, backend <port>

Notable in-flight or recently-touched:
  - <bullet from BACKLOG.md or recent CHANGELOG, if obvious>
  - <bullet>

Pointers (read these before changing the matching surface):
  - apps/backend/prompts/phase2_system.txt — Phase 2 system prompt
  - apps/backend/JSON_SCHEMA.md — Phase 1 schema
  - docs/ARCHITECTURE_STRATEGY.md — structural decisions
```

## Quality bar for the summary

The summary is correct if:

1. **All six quality invariants are named** (by the labels above — "Measurement authority", etc.). Missing any one is a regression.
2. **The mission line is from PURPOSE.md**, not invented. Paraphrasing is fine; new claims are not.
3. **Three-layer architecture is named correctly** — Measurement / Pitch-note translation / Interpretation. Other orderings or names are wrong.
4. **Working stack mentions Python 3.11.x** (the version constraint is load-bearing — Essentia 2.1b6 wheels are 3.11-only on macOS arm64).
5. **Pointers list at least the three files above.**

If you cannot confirm a claim from a file you actually read in this session, say "not confirmed in loaded docs" instead of guessing.

## After the summary

Offer the user one of:
- "Tell me what you're working on and I'll pull in the relevant deeper docs."
- "Want me to read `docs/ARCHITECTURE_STRATEGY.md` or a specific `apps/*/AGENTS.md` more carefully before we start?"

Do not start coding until the user has confirmed direction.
