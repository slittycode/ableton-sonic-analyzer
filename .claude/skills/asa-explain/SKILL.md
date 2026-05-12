---
name: asa-explain
description: Use this skill when the user asks what a Phase 1 measurement field in the ASA project means, hands you a dotted field path like "kickDetail.fundamentalHz" or "spectralBalance.subBass", says "/asa-explain <field>", or asks "what does crest factor mean in ASA", "where does this number come from", or "how should I interpret this measurement". Looks up the field in the canonical ASA schema docs and grounds it against Ableton Live 12 concepts via the Ableton Knowledge MCP.
version: 0.1.0
---

# ASA Measurement Field Explainer

## Purpose

Translate a Phase 1 measurement field into a producer-grounded answer: what it measures, what range to expect, why it matters for the reconstruction blueprint, and which Live 12 device(s) surface or shape it.

Inputs the user might hand you:
- A dotted path: `kickDetail.fundamentalHz`, `spectralBalance.subBass`, `sidechainDetail.pumpingStrength`
- A concept name: "crest factor", "the BPM agreement field", "spectral flatness"
- A measurement value in context: "ASA says my track has spectralCentroid 4200 Hz — what does that mean?"

## Procedure

### Step 1 — Normalize the request to a dotted path

If the user gives you a concept name, identify the matching field path. Common mappings:

- "crest factor" → `crestFactor` (root scalar)
- "BPM" → `bpm` + `bpmConfidence`; mention `bpmDoubletime` if half/double-time correction is relevant
- "key" → `key` + `keyConfidence`
- "stereo width" → `stereoDetail.stereoWidth`
- "spectral centroid" → `spectralDetail.spectralCentroidMean` (the post-normalization name — the field uses `Mean` suffix after server normalization; this is documented in the Phase 2 prompt as a common mistake to avoid)

If you cannot map the request to a known field, say so and ask the user to clarify before proceeding.

### Step 2 — Look up the field in the canonical schema

Read the relevant section(s) of `~/code/projects/asa/apps/backend/JSON_SCHEMA.md`. The doc is grep-friendly:

```bash
grep -n "^### \`<containerName>\`" apps/backend/JSON_SCHEMA.md
```

The file is organized as `## Section Name` → `### \`containerName\`` → bullet points per field. Section index includes:
- Core Metrics (root scalars: `bpm`, `key`, `lufsIntegrated`, `crestFactor`, etc.)
- Loudness & Dynamics (`lufsCurve`, `dynamicCharacter`, `textureCharacter`)
- Stereo (`stereoDetail`)
- Spectral Balance (`spectralBalance`, `spectralBalanceTimeSeries`, `spectralDetail`)
- Rhythm (`rhythmDetail`, `grooveDetail`, `beatsLoudness`, `rhythmTimeline`, `sidechainDetail`, `effectsDetail`)
- Melody (`melodyDetail`, `transcriptionDetail`)
- Pitch Detail (`pitchDetail`)
- Harmony (`chordDetail`, `segmentKey`)
- Synthesis Character (`synthesisCharacter`, `perceptual`, `essentiaFeatures`)
- Structure (`structure`, `arrangementDetail`, `segmentLoudness`, `segmentSpectral`, `segmentStereo`)

Capture: the field's definition, type/range, and any caveats the schema doc calls out.

### Step 3 — Confirm against the TypeScript type

Read the corresponding type definition. Phase 1 types live in `~/code/projects/asa/apps/ui/src/types/measurement.ts` (re-exported via `apps/ui/src/types/index.ts`). Confirm:
- The field name is spelled the same as in the schema.
- The optional/nullable status matches (the schema doc says "feature functions return `null` on failure" — this is real, downstream consumers must handle nulls).

If the schema doc and the TS type disagree, **flag the drift in your output**. This is a real bug class.

### Step 4 — Ground it in Ableton Live 12

Call `mcp__Ableton_Knowledge__search_live_manual` with a query oriented around the *Live device or concept* that this measurement informs, not the measurement name itself. Examples:

| Measurement | Good search query |
|---|---|
| `crestFactor` | "Compressor transient handling Glue Compressor attack" |
| `spectralBalance.subBass` | "EQ Eight low shelf sub bass band" |
| `sidechainDetail.pumpingStrength` | "sidechain compression Compressor external sidechain" |
| `kickDetail.fundamentalHz` | "Operator Drum Rack kick fundamental tuning" |
| `stereoDetail.stereoCorrelation` | "Utility width mono compatibility" |
| `melodyDetail.vibratoExtent` | "pitch modulation LFO vibrato in instruments" |

For root-level rhythm/timing fields (`bpm`, `key`, `timeSignature`), search for the Live concept that uses them — warp modes, time-signature handling, key signature.

If `search_live_manual` returns weak results, fall back to `mcp__Ableton_Knowledge__search_knowledge_base` for help-article-level context. Skip videos (`search_videos`) for this skill — the goal is a precise definition, not a tutorial.

### Step 5 — Compose the answer

Use this exact structure. Keep each section to 1–3 sentences.

```
**Field:** `<dotted.path>`  (alias: <human name> if applicable)

**What it measures:**
<plain-English definition. If the schema gives units, include them.>

**Typical range / interpretation:**
<expected range; what "high" vs "low" means in practice.>

**Why it matters for the reconstruction blueprint:**
<which Phase 2 recommendations cite this, or which kind of decision it enables. Tie to the citation contract if relevant.>

**Related Live 12 device(s) / concept(s):**
<1–3 specific devices/parameters from the Ableton Knowledge MCP results, with exact spelling.>

**Sources:**
- `apps/backend/JSON_SCHEMA.md` § <section name>
- `apps/ui/src/types/measurement.ts` (line range)
- Live 12 manual: <article title from MCP result, with URL if returned>
```

### Step 6 — Flag drift, hedges, and gotchas

After the structured answer, surface:

1. **Documented gotchas** from `apps/backend/prompts/phase2_system.txt` lines 93–97 — if the user's path is one of the historically-typoed ones, name the correct spelling:
   - `monoCompatible` is top-level, **not** `stereoDetail.monoCompatible`.
   - Spectral mean fields use the `Mean` suffix after server normalization — use `spectralDetail.spectralCentroidMean`, **not** `spectralDetail.spectralCentroid`.
   - Sidechain fields live under `sidechainDetail`, **not** `pumpingDetail`.
2. **Confidence pairing** — if the field has a sibling `<field>Confidence` (e.g., `bpm` ↔ `bpmConfidence`), say so and remind that low-confidence measurements must produce hedged recommendations (Quality Invariant #4).
3. **Drift between schema and type** — if you spotted any in Step 3.

## Quality bar

The answer is correct if:

1. The field path is one that actually appears in `apps/backend/JSON_SCHEMA.md` (or is explicitly called out as not present and renamed).
2. The Live 12 device/concept named comes from the MCP result, not from memory.
3. The "Sources" section cites real files and a real MCP-returned manual article.
4. Any documented gotcha that applies to this field is flagged.

Do not invent ranges. If the schema doesn't state a range, say so and offer a typical-music range as a separate, labeled annotation.

## After the answer

Offer one follow-up:
- "Want me to also explain a related field?" (suggest one based on the section the user's field lives in)
- "Want to see how this field is cited in `phase2Validator.ts` or `phase2_system.txt`?"

Don't volunteer a redesign or refactor unless asked — this skill is an explainer, not a code-changer.
