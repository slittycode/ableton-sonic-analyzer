---
name: asa-verify-device
description: Use this skill when working on ASA and you need to verify that an Ableton Live 12 device name (or parameter name) is spelled exactly right and actually exists. Triggered by edits to apps/ui/src/data/abletonDevices.ts, edits to the Phase 2 system prompt at apps/backend/prompts/phase2_system.txt that reference devices, questions like "does Live 12 have a Glue Compressor", "is 'Drum Bus' a real device", "verify <device-name>", or any time Phase 2 output is being reviewed for device-spelling correctness against the LIVE_12_DEVICE_CATALOG_JSON contract.
version: 0.1.0
---

# ASA Device Verifier

## Purpose

The Phase 2 system prompt (`apps/backend/prompts/phase2_system.txt`, lines 22–24) requires recommendations to use *exact* device and parameter spellings from `LIVE_12_DEVICE_CATALOG_JSON`. Rule #6 of the prompt's ABSOLUTE RULES forbids third-party devices entirely — only NATIVE and MAX_FOR_LIVE are allowed.

This skill is the verification step those rules rely on. It confirms a device exists in Live 12, returns its canonical spelling and parameter list, and flags non-existent or third-party names.

## When to use

- The user is editing `apps/ui/src/data/abletonDevices.ts` (the spectral-band → device mapping table).
- The user is editing `apps/backend/prompts/phase2_system.txt` and references devices.
- The user is reviewing a Phase 2 output and wants to confirm every emitted `device` field is real.
- The user asks directly: "verify <device>", "does Live 12 have <device>", "is <name> the real spelling".

## Procedure

### Step 1 — Identify the device candidate(s)

Pull the exact strings the user wants verified. If they paste a Phase 2 output, extract every distinct `device` value from `abletonRecommendations`, `mixAndMasterChain`, and `secretSauce.workflowSteps`.

### Step 2 — Search the Live manual

For each candidate, call:

```
mcp__Ableton_Knowledge__search_live_manual
  question: "<device-name> device in Ableton Live 12"
  num_results: 5
```

Look for results where the title or top match contains the device name as a heading or section reference. The manual is the source of truth.

### Step 3 — Fall back to the knowledge base

If `search_live_manual` returns no clear match, call:

```
mcp__Ableton_Knowledge__search_knowledge_base
  question: "<device-name> Ableton Live"
```

Knowledge base articles often cover newer devices and naming changes between Live versions.

### Step 4 — Classify the device

Categorize into one of:

- **NATIVE (Live 12 stock)** — exists in the manual and ships with Live 12. Examples: Glue Compressor, EQ Eight, Operator, Wavetable, Drum Rack, Utility.
- **MAX_FOR_LIVE** — ships in Live 12 Suite via Max for Live. The manual lists Max for Live devices separately; if the device appears in those sections, label it MAX_FOR_LIVE.
- **LIVE 11 ONLY or RENAMED** — if the device exists in Live 11 manual results but not Live 12, or has been renamed (e.g., classic instrument renamed/replaced), call this out.
- **NOT FOUND** — no clear match in the manual. The candidate is likely a third-party plugin, a hallucination, or a misspelling. Suggest the closest plausible Live 12 name(s) from the search results.

The Phase 2 prompt forbids third-party devices, so a NOT FOUND result on a Phase 2 emission is a violation worth surfacing loudly.

### Step 5 — Extract the parameter list

When the device is NATIVE or MAX_FOR_LIVE, capture its parameter names *exactly as they appear in the Live UI*. The Phase 2 prompt requires parameter spellings to match too — "Attack" not "attack", "Threshold" not "threshold dB".

If the search result snippet doesn't surface enough parameters, do one targeted follow-up:

```
mcp__Ableton_Knowledge__search_live_manual
  question: "<device-name> parameters Attack Release Threshold"
  num_results: 3
```

### Step 6 — Report

Use this exact format. One block per candidate.

```
**Device:** `<as-typed-by-user>`
**Status:** NATIVE | MAX_FOR_LIVE | LIVE 11 ONLY | NOT FOUND
**Canonical spelling:** `<exact name as it appears in Live 12 manual>`
**Family:** <Instrument | Audio Effect | MIDI Effect | Utility | Drum / Sampler | Other>

**One-line description:** <from the manual snippet>

**Parameters (exact UI spelling):**
  - <Parameter Name 1> — <brief role, if obvious from the snippet>
  - <Parameter Name 2>
  - <Parameter Name 3>
  ...

**Manual reference:** <article title and URL from MCP result>
```

If status is NOT FOUND, replace the body with:

```
**Status:** NOT FOUND
**Closest plausible Live 12 alternatives:**
  - <suggestion 1> (from search result <snippet>)
  - <suggestion 2>
**Recommendation:** <one sentence — "rename to X", "this looks like a third-party plugin (forbidden by Phase 2 rule #6)", or "verify with the user">.
```

### Step 7 — When verifying multiple devices, end with a summary table

```
| Candidate              | Status         | Canonical spelling      | Issue                  |
| ---------------------- | -------------- | ----------------------- | ---------------------- |
| Glue Compressor        | NATIVE         | Glue Compressor         | —                      |
| Drum Buss              | NATIVE         | Drum Bus                | misspelled (one 's')   |
| Pro-Q 3                | NOT FOUND      | —                       | third-party (forbidden)|
```

## Quality bar

The verification is correct if:

1. Every device classified NATIVE/MAX_FOR_LIVE has a manual reference URL or article title from an actual MCP result, not from memory.
2. Parameter names use the exact capitalization from the manual snippet (do not lowercase or paraphrase).
3. NOT FOUND results include at least one suggested alternative when the search returned anything relevant.
4. If the user pasted a Phase 2 output, every distinct device value in that output appears in the summary table.

Do not classify a device as NATIVE without a manual reference. "I'm pretty sure it exists" is not acceptable — the entire point of this skill is to remove that guesswork.

## Common cases worth knowing

- "Glue Compressor" and "Compressor" are distinct devices in Live 12; both are NATIVE. Confirm which one the user means.
- "Drum Bus" is one word in the canonical spelling, but "Drum Buss" (with double-s) is a common typo.
- "Hybrid Reverb" was added in Live 11 — confirm it's documented for Live 12 in the manual results before classifying.
- "Echo" exists; "Echo Delay" does not — make sure that distinction is preserved.
- Third-party plugins to watch for (Phase 2 violations): Pro-Q, FabFilter, Soothe2, Waves, Vital, Serum, Massive, Diva. Any of these → NOT FOUND + Phase 2 violation.

## After the report

If the user is editing `abletonDevices.ts`, offer to surface the exact rename/diff. If they're reviewing Phase 2 output, offer to also run a parameter-level verification (next step in the `asa-citation-auditor` workflow, which is on the Tier 2 backlog).
