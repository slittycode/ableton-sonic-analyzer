# The ASA ↔ asa-ableton Boundary

**Status:** living contract doc. Backed by `apps/backend/phase2_export.py`,
`GET /api/analysis-runs/{run_id}/export/phase2`, the committed
`phase2-export.v1` schema and Gate alpha fixture, and the executable handoff
gate in `apps/backend/tests/test_phase2_export.py`.

## The two repos

- **ASA** (this repo, `slittycode/ableton-sonic-analyzer`) — measures a track
  deterministically (Phase 1) and produces AI device recommendations grounded in
  those measurements (Phase 2). Its product output, for downstream tooling, is a
  `producer_summary` interpretation result: device cards across
  `abletonRecommendations`, `mixAndMasterChain`, and `secretSauce.workflowSteps`,
  plus the frozen `recommendations.v1` projection (ADR 0003) attached as a
  `recommendations` field.
- **asa-ableton** (sibling repo, `slittycode/asa-ableton`) — stdlib-only Python
  that turns ASA's Phase 2 recommendations into an openable Live 12 `.als`
  starter set. It is a *consumer*: it never talks to ASA's server at runtime and
  shares no code with ASA. The boundary is a file.

The two repos are deliberately **file-coupled, not code-coupled**. asa-ableton's
fidelity gates (Gate α in its `docs/GATE_ALPHA.md`) run on a saved ASA
interpretation JSON committed as a fixture on its side. The same file shape also
feeds ASA's own recommendation-proof harness
(`apps/backend/scripts/evaluate_recommendations.py --phase2`, GOAL.md).

## The handoff artifact: `phase2-export.v1`

One HTTP call produces the complete, self-describing handoff file:

```bash
curl http://127.0.0.1:8100/api/analysis-runs/<run_id>/export/phase2 \
  -o <track>.phase2-export.json
```

(Local profile needs no auth headers; hosted mode resolves ownership from the
usual `X-ASA-User-Id` header.)

Envelope shape (key set frozen by `test_envelope_key_set_is_frozen` — additions
require a version bump):

```json
{
  "schemaVersion": "phase2-export.v1",
  "runId": "…",
  "exportedAt": "ISO-8601",
  "provenance": { "schemaVersion": "interpretation.v2", "profileId": "producer_summary", "modelName": "…", "promptVersion": "…", "groundedMeasurementRunId": "…", "…": "…" },
  "validationWarnings": [ { "code": "RECOMMENDATION_UNVERIFIED", "path": "…", "message": "…" } ],
  "phase1": { "…full authoritative Phase 1 measurement payload…" },
  "phase2": { "…producer_summary interpretation result, verbatim…" }
}
```

The CI-visible handoff gate can also be run locally:

```bash
cd apps/backend
./venv/bin/python -m unittest tests.test_phase2_export.AsaAbletonHandoffContractTests
```

It validates the committed
`tests/fixtures/phase2_export/asa_ableton_gate_alpha.phase2-export.json` against
`schemas/phase2-export.v1.schema.json` and the nested
`recommendations.v1.schema.json`. The gate fails if the top-level envelope
changes, if Gate alpha loses `device`, `parameter`, `value`, `trackContext`, or
`phase1Fields`, or if the normalized recommendation loses a dedupe key or its
`cited_measurements`. The golden fixture also locks warning and provenance
pass-through and includes the duplicate recommendation case Gate alpha must
dedupe without losing either citation trail.

Field semantics:

1. **`phase2`** — the stored interpretation result exactly as ASA's validator
   tail left it, including the additive `recommendations` field (the frozen
   `recommendations.v1` contract). Nothing is rewritten or filtered at export
   time.
2. **`phase1`** — the authoritative measurement payload the interpretation was
   grounded on. Included so a consumer can independently resolve every cited
   `phase1Fields` path (PURPOSE.md invariant #2) without a second request.
   Phase 1 values always win over anything Phase 2 says (invariant #1).
3. **`validationWarnings`** — the full warn-and-keep trail (citation-existence,
   semantic, and Live 12 catalogue-gate warnings). ASA never drops or rewrites
   a flagged card; consumers decide what to do with flagged entries.
4. **`provenance`** — interpretation schema version, profile, model, prompt
   version, and grounding IDs, verbatim from the run.

Returns 404 `PHASE2_EXPORT_NOT_AVAILABLE` until a `producer_summary`
interpretation has completed with a result. Only `producer_summary` is
exportable — `stem_summary` carries no device cards.

## Guidance for device-applying consumers (asa-ableton)

- **Prefer `phase2.recommendations.recommendations`** (the `recommendations.v1`
  entries) when you need normalized `{device, parameter, value, unit, range,
  cited_measurements[]}` records: values are parsed to numbers where possible
  and every entry is citation-gated. Fall back to the three raw card arrays for
  prose context (`reason`, `trackContext`, ordering).
- **Dedupe before counting.** The raw arrays — and therefore the flat
  `recommendations.v1` projection — can legitimately repeat a
  `(device, parameter, value)` tuple across containers (a mix-chain card and a
  workflow step may name the same move). asa-ableton's Gate α already observed
  this inflating its skip-rate accounting (~60.7% raw vs ~50% deduped).
  Deduplication is intentionally a consumer concern: ASA's contract is
  warn-and-keep, never drop.
- **Treat flagged cards as flagged, not invalid.** A
  `RECOMMENDATION_UNVERIFIED` warning means the source-extracted catalogue
  could not confirm a device/parameter spelling — the card may still be a
  correct UI-vocabulary spelling (see `UI_PARAMETER_ALIASES` in
  `apps/backend/live12_catalogue.py`).

## Relationship to other export surfaces

- **UI "Export JSON"** (`track-analysis.json` from `AnalysisResults.tsx`) is a
  looser, browser-side superset for humans: `{phase1, phase2, exportedAt}`,
  without `provenance` or `validationWarnings`, and without a schema version.
  The backend route is the canonical machine handoff; converging the UI export
  onto `phase2-export.v1` is a known follow-up.
- **`evaluate_recommendations.py --phase2`** accepts either a bare
  `Phase2Result` or a `phase2-export.v1` file
  (`recommendation_evaluation.coerce_phase2_payload`), so the downloaded export
  drops straight into a fixture dir as `phase2.json` for the GOAL.md campaign.

## Stability promise

`phase2-export.v1` follows the same policy as `recommendations.v1` (ADR 0003):
the key set above is frozen; new top-level fields require bumping the
`schemaVersion`. The *interior* of `phase1` and `phase2` is governed by their
own contracts (`phase1.v2` per ADR 0002, `interpretation.v2`/`recommendations.v1`
for Phase 2) and evolves with them — the envelope passes them through verbatim
and adds no transformation of its own.
