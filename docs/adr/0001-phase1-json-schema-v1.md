# ADR 0001 — Phase 1 JSON Schema v1

**Status:** Accepted
**Date:** 2026-05-13
**Supersedes:** —
**Anchor:** [PURPOSE.md](../../PURPOSE.md) quality invariant #2 (citation chain).

## Context

ASA's HTTP contract has two layers that matter to external consumers:

1. **The raw analyzer output** — what `apps/backend/analyze.py` writes to stdout. Documented in [`apps/backend/JSON_SCHEMA.md`](../../apps/backend/JSON_SCHEMA.md). The top-level key set is enforced by `EXPECTED_TOP_LEVEL_KEYS` in [`apps/backend/tests/test_analyze.py`](../../apps/backend/tests/test_analyze.py).
2. **The `phase1` HTTP envelope** — what `GET /api/analysis-runs/{run_id}` returns under `stages.measurement.result`. Typed on the frontend by `Phase1Result` in [`apps/ui/src/types/measurement.ts`](../../apps/ui/src/types/measurement.ts).

These two layers share the same field shape — Python emits camelCase JSON directly; there is no rename layer between them ([CLAUDE.md tripwire #3](../../CLAUDE.md)). That coupling has served ASA well, but it carries no explicit version or compatibility promise. Until this ADR, "Phase 1 schema v1" was implicit in `EXPECTED_TOP_LEVEL_KEYS` and `Phase1Result` — provable from code but not stated as a contract.

The external-repo review at [`docs/history/external-repo-review-2026-05-13.md`](../history/external-repo-review-2026-05-13.md) flagged this gap as Track 2 work. Partiels exports a documented schema (CSV/JSON/SDIF), and consumers of ASA's output (REAPER scripts, Max patches, downstream pipelines) need a stable shape to write against.

## Decision

The Phase 1 measurement payload — as captured by `EXPECTED_TOP_LEVEL_KEYS` and documented in `JSON_SCHEMA.md` on the date of this ADR — is hereby declared **Phase 1 JSON Schema v1**.

The contract is the union of:

- The current set of top-level keys in `apps/backend/tests/test_analyze.py:EXPECTED_TOP_LEVEL_KEYS`.
- Their semantic meaning as documented in `apps/backend/JSON_SCHEMA.md`.
- The per-detail-object shapes as typed in `apps/ui/src/types/measurement.ts`.

The combination is the schema. There is no separate JSON Schema artifact (yet). Generation of a machine-readable schema is deferred to v2 if and when an external consumer needs it for validation.

## Compatibility policy

A future change to the Phase 1 payload is classified as follows:

| Change | Class | Allowed in v1? |
| --- | --- | --- |
| Add a new top-level key | Additive (minor) | **Yes**, must update `EXPECTED_TOP_LEVEL_KEYS`, `JSON_SCHEMA.md`, and `Phase1Result`. |
| Add a new nested key inside an existing detail object | Additive (minor) | **Yes**, must update the detail interface in `types/measurement.ts`. |
| Add a new value to an existing string enum (e.g. `keyProfile`, `dynamicCharacter`) | Additive (minor) | **Yes**, must update the TypeScript union. Consumers should treat unknown values defensively. |
| Rename an existing key | Breaking (major) | **No** under v1. Requires a v2 bump. |
| Remove an existing key | Breaking (major) | **No** under v1. |
| Change a key's type (e.g. `number` → `number | null`, scalar → object) | Breaking (major) | **No** under v1. |
| Change the units of a value (e.g. dB → LUFS, seconds → milliseconds) | Breaking (major) | **No** under v1. |
| Tighten or loosen a value range (e.g. confidence was `[0, 1]`, now `[0, 100]`) | Breaking (major) | **No** under v1. |
| Change the shape of a detail object's elements (e.g. `{t, lufs}` → `{time, value}`) | Breaking (major) | **No** under v1. |

**Versioning identifier:** the schema version is the string `"phase1.v1"`. The CSV export endpoint (`GET /api/analysis-runs/{run_id}/export/csv/{field_path}`) does **not** carry a version because its CSV column names mirror the v1 field names; if a breaking schema change ever bumps to v2, the export contract must be re-evaluated at the same time.

## Time-series field shapes (v1 reference)

The following nested shapes are the load-bearing time-series fields exported via the CSV endpoint introduced alongside this ADR. They are pinned by v1.

| Field | Element shape | CSV columns |
| --- | --- | --- |
| `lufsCurve.shortTerm` | `{t: number, lufs: number}` | `time, duration, lufs` (duration=3.0) |
| `lufsCurve.momentary` | `{t: number, lufs: number}` | `time, duration, lufs` (duration=0.4) |
| `rhythmDetail.tempoCurve` | `{t: number, bpm: number}` | `time, bpm` |
| `spectralBalanceTimeSeries` | `{t, subBass, lowBass, lowMids, mids, upperMids, highs, brilliance}` | `time, subBass, lowBass, lowMids, mids, upperMids, highs, brilliance` |

Adding a new exportable time-series field is an additive change: register a serializer in [`apps/backend/csv_export.py`](../../apps/backend/csv_export.py), update the test in `apps/backend/tests/test_csv_export.py`, and document the CSV columns in the table above.

## Stage status field — `status` (internal) + `publicStatus` (additive)

Every stage object inside the run snapshot (`stages.measurement`, `stages.pitchNoteTranslation`, `stages.interpretation`) carries two status fields:

- **`status`** (8-state, internal vocabulary): `queued | running | blocked | ready | completed | failed | interrupted | not_requested`. This is the runtime's scheduling vocabulary and reflects internal state-machine transitions. Stable.
- **`publicStatus`** (5-state collapse + null): `queued | running | completed | failed | interrupted | null`. Added in Track 3.4 of the external-repo incorporation work. Maps `blocked`/`ready` → `queued`, `not_requested` → `null`, everything else 1:1. Stable.

The collapse exists so external consumers who don't care about the distinction between internal scheduling states (e.g. blocked-waiting-for-dependency vs queued-and-ready) can read one field with a smaller vocabulary. The internal `status` is preserved for tools that need to debug or inspect runtime behavior.

Source of truth for the mapping: [`apps/backend/stage_status.py`](../../apps/backend/stage_status.py). TypeScript mirror: `PublicStageStatus` in [`apps/ui/src/types/backend.ts`](../../apps/ui/src/types/backend.ts).

## Where v1 is enforced

| Layer | Enforcement | If you break v1 here |
| --- | --- | --- |
| Top-level keys | `EXPECTED_TOP_LEVEL_KEYS` snapshot in `test_analyze.py` | Test fails; CI red. |
| Detail shapes | `Phase1Result` typing in `apps/ui/src/types/measurement.ts` | TypeScript type-check fails on the UI side. |
| HTTP envelope | `_normalize_run_snapshot` in `apps/backend/server.py` | Existing route tests in `test_server.py` fail. |
| CSV column contract | `apps/backend/tests/test_csv_export.py` | Per-field tests assert exact column names and order. |

There is no single "phase1.v1.json" file. The schema is the four-test-suite intersection. This is deliberate — generating a JSON Schema artifact would add a new failure mode (the artifact drifting from the runtime contract) without a current consumer.

## What this ADR does *not* do

- **Does not generate a machine-readable JSON Schema.** No `phase1.v1.schema.json` is committed. If a future external consumer requires one, that's a v2-era task or a separate ADR.
- **Does not add an HTTP version header.** The `phase1` envelope is implicitly v1 by virtue of the route shape; if/when v2 lands, the canonical move is a new top-level field `phase1Version` rather than HTTP header negotiation.
- **Does not freeze SDIF or LAB export.** Both were considered in the review and deferred. This ADR scopes v1 to JSON + CSV.

## Consequences

- Future PRs that add fields are routine and low-friction; the checklist is in [CLAUDE.md](../../CLAUDE.md) under "Where to Make the Change."
- Future PRs that rename, remove, or retype fields require a new ADR and either a v2 envelope or a deprecation cycle. Neither is in scope for v1.
- ASA-side consumers (the UI) are tightly coupled to v1 by construction. External-side consumers (REAPER, Max, downstream scripts) gain a stable column contract from the CSV exporter.

## Alternatives considered

- **Mirror Partiels' export schema verbatim.** Rejected in [external-repo-review-2026-05-13.md](../history/external-repo-review-2026-05-13.md). Partiels' CSV is `time, duration, label/value` per Vamp track — too flat for ASA's domain-named measurements. Would have collapsed the citation chain (Quality Invariant #2).
- **Generate a JSON Schema artifact.** Deferred. No current consumer needs it; the test-snapshot enforcement already prevents drift.
- **Version the schema via HTTP `Accept` header.** Overkill for one runtime. Re-evaluate at v2.
