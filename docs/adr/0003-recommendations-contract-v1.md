# ADR 0003 — Recommendations Contract v1

**Status:** Accepted
**Date:** 2026-06-05
**Supersedes:** —
**Anchor:** [PURPOSE.md](../../PURPOSE.md) quality invariants #1 (measurement authority) and #2 (citation chain).

## Context

ASA's Phase 2 (interpretation) layer emits device recommendations across three
free-shaped arrays in the `Phase2Result` payload:

1. `abletonRecommendations[]` — general device cards, carry `category` + `trackContext`.
2. `mixAndMasterChain[]` — the ordered mastering pipeline.
3. `secretSauce.workflowSteps[]` — the signature-technique steps.

Each card carries `{device, parameter, value, …, phase1Fields[]}` plus prose
(`reason`, `instruction`, `measurementJustification`). Two properties make this
shape awkward as a stable API surface:

1. **`value` is free text.** Gemini emits `"10 ms"`, `"-18 dB"`, `"3:1"`,
   `"Sine"` — a single string with the magnitude, unit, and sometimes shape all
   fused. There is no separate `unit`, no `range`, and the citation is named
   `phase1Fields`, not the producer-facing `cited_measurements`.
2. **There is no machine-checkable freeze.** The Phase 2 shape is typed on the
   frontend (`interpretation.ts`) and guarded at runtime by `phase2Validator.ts`
   and the backend catalogue/citation gates, but no committed JSON Schema
   declares a versioned recommendation contract an external consumer (a REAPER
   script, a Max patch, a downstream pipeline, or ASA's own UI) can validate
   against — the same gap ADR 0001 closed for Phase 1's *measurements*, now for
   Phase 2's *recommendations*.

The campaign goal is to **freeze a versioned `recommendations` JSON contract** —
each entry `{device, parameter, value, unit, range, cited_measurements[]}`, every
recommendation citing the Phase 1 measurement(s) that justify it and never
overriding them — with a semver'd JSON Schema, CI validation of Phase 2 output
against it, and a round-trip test.

## Decision

Declare the **Recommendations Contract v1**, version string `"recommendations.v1"`.

The contract is a **deterministic, server-side projection** of the existing
Phase 2 cards into a normalized envelope. It is additive: it never overrides a
Phase 1 measurement (invariant #1) and never mutates the raw Phase 2 arrays — it
only *reads* them.

**Envelope:**

```json
{ "version": "recommendations.v1", "recommendations": [ <entry>, … ] }
```

**Entry** (exactly six fields, `additionalProperties: false`):

| Field | Type | Meaning |
| --- | --- | --- |
| `device` | `string` (non-empty) | Live 12 device name as recommended, trimmed. Not catalogue-rewritten. |
| `parameter` | `string` (non-empty) | Device parameter name as recommended. Not catalogue-rewritten. |
| `value` | `string \| number` | The magnitude when one was parsed from the value string (`"10 ms"`→`10`, `"3:1"`→`3`); else the original non-numeric string (`"Sine"`). |
| `unit` | enum \| `null` | One of `Hz, dB, ms, s, ratio, %, st`, or `null` when the value is non-numeric/unitless. `ratio` denotes a compression-style ratio (`3` ≡ `3:1`). |
| `range` | `[number, number] \| null` | Best-effort suggested working range, derived from a per-unit tolerance band around `value`. `null` when no band applies. **Not** a device hard-limit (see *Honest range* below). |
| `cited_measurements` | `string[]` (`minItems: 1`) | Dotted Phase 1 measurement paths justifying the recommendation, projected from `phase1Fields`. |

**Authoritative artifacts:**

- Schema: [`apps/backend/schemas/recommendations.v1.schema.json`](../../apps/backend/schemas/recommendations.v1.schema.json) (Draft 2020-12).
- Projection + validation: [`apps/backend/recommendations_contract.py`](../../apps/backend/recommendations_contract.py)
  (`project_recommendations`, `validate_envelope`, `build_validated_recommendations`).
- TypeScript mirror: `RecommendationContractEntry` / `RecommendationsContract` in
  [`apps/ui/src/types/interpretation.ts`](../../apps/ui/src/types/interpretation.ts).

**API exposure:** the validated envelope is attached additively to the
interpretation stage result as `recommendations` (alongside the existing rich
Phase 2 fields), so the normalized contract travels in the live
`GET /api/analysis-runs/{run_id}` snapshot, not just in tests.

## Why a projection, not a change to Gemini's emission

Reshaping Gemini's structured output to emit these six fields directly was
rejected: it is unverifiable without a live Gemini call, touches the prompt, the
response schema, every existing validator, the UI, and all stored older results
— the opposite of a surgical change. The projection is additive, deterministic,
testable in the cheap inner loop with no Gemini spend, and reuses the proven
value-parsing logic from the recommendation scorer
(`recommendation_evaluation.py`). It honors invariant #1 by construction: a view
derived from Phase 2 output cannot override a Phase 1 measurement.

## Citation-gating (invariant #2)

The schema requires `cited_measurements` with `minItems: 1`. The projection
admits a card **only if it cites ≥1 Phase 1 measurement**; uncited cards are
**excluded from this normalized view by design**.

This is *not* a violation of the warn-and-keep contract
(`phase2_catalogue_gates.py`): nothing user-facing is dropped. Uncited cards
remain in the raw Phase 2 arrays, where the existing warn-and-keep gate already
flags them with `RECOMMENDATION_UNVERIFIED` / `citation_missing`. The exclusion
is from the *contract* only, and it is surfaced (the gate warning), not silent.
`minItems: 1` is therefore honest: every entry that *is* in the contract carries
a citation. It is **not** a runtime hard-fail against live Gemini — Phase 1 stays
authoritative, and a missing citation degrades to a warning, never a rejection.

## Honest range (invariant #4)

`range` is a **measurement-informed neighborhood**, not a Live device limit. The
static Live 12 catalogue carries no `min`/`max` (see
[`data/live12_catalogue.schema.json`](../../data/live12_catalogue.schema.json)
`extraction_notes` — those live on runtime `Live.DeviceParameter` objects), so a
true device range cannot be supplied here. The contract derives `range` from the
same per-unit tolerance bands the recommendation scorer uses for value accuracy
(`±20%` for Hz, `±3 dB`, `±30%` for ms/s, `±1` for ratio/st, `±15%`), and emits
it **only** when the value is numeric *and* the unit is known — otherwise `null`.
This keeps the contract from pretending a precise range exists where it does not.

## Validation is against the file, not a mirror

`validate_envelope` runs the real `jsonschema` validator against the **committed
schema file**. There is deliberately **no** hand-rolled structural validator that
"matches" the schema — that is exactly the drift failure mode ADR 0001 called out
(a payload validated against a function that *resembles* the schema is not
validated against the schema). The `live12_catalogue.py` precedent avoided a
`jsonschema` dependency because it had no consumer mandating schema-as-gate; this
contract's whole point is the CI gate, so the dependency (`jsonschema==4.26.0`,
pure-Python) is earned.

## Compatibility policy

`version: "recommendations.v1"` identifies the **major** version; the committed
`recommendations.v1.schema.json` is the current v1 contract. With
`additionalProperties: false`, evolution classifies as:

| Change | Class | Allowed in v1? |
| --- | --- | --- |
| Add a new **optional** entry field | Additive (minor) | **Yes** — add to `properties` (not `required`), keep `additionalProperties: false`, keep the `version` const. Consumers must validate against the *current* v1 schema; payloads emitted before the addition still validate. |
| Add a new value to the `unit` enum | Additive (minor) | **Yes** — extend the enum and `_DISPLAY_UNIT` / `UNIT_BANDS`. |
| Make an existing optional field required | Breaking (major) | **No** — bump to `recommendations.v2`. |
| Rename / remove / retype a field | Breaking (major) | **No** — v2. |
| Change `value`/`unit`/`range` semantics or a tolerance band | Breaking (major) | **No** — v2. |
| Loosen `additionalProperties` to `true` | Breaking (major) | **No** — it changes the validation contract; v2. |

A v2 bump means a new `recommendations.v2.schema.json`, a new `version` const,
and a new ADR — mirroring ADR 0002's `phase1.v2` precedent.

## Where v1 is enforced

| Layer | Enforcement | If you break v1 here |
| --- | --- | --- |
| Schema validity | `test_recommendations_contract.SchemaIsValidTests` runs `check_schema` on the file | Test fails; CI red. |
| Phase 2 output conforms | `test_recommendations_contract.ProjectionValidatesTests` projects a representative Phase 2 result and validates each entry against the file | Test fails; CI red. |
| Round-trip stability | `test_recommendations_contract.RoundTripTests` | Test fails; CI red. |
| Frozen entry shape | `test_recommendations_contract.SchemaFreezeTests` (additionalProperties, minItems, required, enum, version const) | Test fails; CI red. |
| Attached to the interpretation result | `test_server.…test_run_interpretation_request_attaches_recommendations_contract` | Test fails; CI red. |
| Survives into the run snapshot | `test_analysis_runtime.test_run_snapshot_surfaces_recommendations_contract_verbatim` (the payload behind `GET /api/analysis-runs/{run_id}`) | Test fails; CI red. |
| TS ↔ Python agreement | `RecommendationContractEntry` in `interpretation.ts` | UI type-check (`npm run lint`) fails. |

CI runs these via `python -m unittest discover -s tests` in the backend job
([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)).

## What this ADR does *not* do

- **Does not change Gemini's emission.** The raw Phase 2 arrays and the prompt
  are untouched; `recommendations` is a derived sibling field.
- **Does not deduplicate.** A device/parameter appearing in more than one source
  array yields more than one entry. Dedup is deferrable to a minor revision if a
  consumer needs it.
- **Does not rewrite devices/parameters against the catalogue.** Catalogue
  verification stays warn-and-keep on the raw arrays (`phase2_catalogue_gates.py`).
- **Does not guarantee a non-empty contract.** A track that yields no cited cards
  produces `{"version": "recommendations.v1", "recommendations": []}`, which is
  valid.

## Consequences

- External consumers and the UI gain a stable, citation-first recommendation
  shape they can validate against, independent of the prose-heavy Phase 2 fields.
- Adding an optional entry field or a unit enum value is low-friction (update the
  schema file + the projection + the freeze tests). Renaming/removing/retyping
  requires a v2 schema and a new ADR.
- The contract makes the citation chain (invariant #2) a *validated* property of
  the recommendation surface, not just a runtime guardrail.

## Alternatives considered

- **Reshape Gemini's structured output to emit the six fields directly.**
  Rejected — unverifiable without live Gemini, large blast radius, violates the
  surgical-change principle.
- **Hand-rolled stdlib validator (the `live12_catalogue.py` pattern).** Rejected
  — reintroduces the schema/validator drift ADR 0001 warned about and makes
  "validate against the schema" a fiction. The `jsonschema` dependency is earned
  by the CI-gate mandate.
- **Include uncited cards with an empty `cited_measurements`.** Rejected — it
  would make `minItems: 1` impossible and dilute the contract's promise that
  every entry is measurement-justified. Uncited cards stay in the raw arrays.
