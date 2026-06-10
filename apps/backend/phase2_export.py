"""Phase 2 handoff export — versioned envelope for downstream consumers.

Backs ``GET /api/analysis-runs/{run_id}/export/phase2`` and keeps the route
handler a thin lookup-and-serve (same pattern as ``csv_export.py``).

ASA's Phase 2 interpretation result is the input to downstream tooling that
lives *outside* this repo — concretely the sibling ``asa-ableton`` project
(turns the device cards into an openable Live 12 ``.als`` starter set) and the
in-repo recommendation-proof harness (``scripts/evaluate_recommendations.py
--phase2``). Until now that JSON had no export path: it exists only embedded in
the full run snapshot, with the validation warnings living in a different
subtree (attempt ``diagnostics``) and the grounding provenance in a third.
Consumers hand-extracted it, which is exactly the kind of unversioned, fragile
handoff ADR 0001 warns about.

This module freezes a single-file envelope (``phase2-export.v1``):

  - ``phase2`` — the stored ``producer_summary`` interpretation result,
    verbatim, exactly as the validator tail left it (including the additive
    ``recommendations`` field — the frozen ``recommendations.v1`` contract,
    ADR 0003).
  - ``phase1`` — the authoritative measurement payload the interpretation was
    grounded on, included so a consumer can independently verify that every
    cited ``phase1Fields`` path resolves (PURPOSE.md invariant #2) without a
    second request.
  - ``validationWarnings`` — the full warn-and-keep trail (citation-existence,
    semantic, catalogue-gate) from the attempt diagnostics, so a non-browser
    consumer sees the same chain-of-custody flags the UI renders.
  - ``provenance`` — the stored attempt provenance (interpretation schema
    version, profile, model, prompt version, grounding ids), verbatim.

Derived and read-only: the export projects stored run state and never
re-estimates or mutates anything (invariant #1). Only the ``producer_summary``
profile is exportable — it is the profile that carries device cards;
``stem_summary`` has no downstream device consumer.

See ``docs/ASA_ABLETON_BOUNDARY.md`` for the cross-repo contract this backs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

EXPORT_SCHEMA_VERSION = "phase2-export.v1"

# The device-card profile. stem_summary results carry no device cards and are
# deliberately not exportable through this envelope.
EXPORTABLE_PROFILE_ID = "producer_summary"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _producer_summary_attempt(snapshot: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The completed producer_summary attempt from a run snapshot, or ``None``.

    Reads the per-profile map rather than the stage-level ``result`` because
    the stage's preferred attempt can be a different profile (e.g.
    ``stem_summary`` finishing first).
    """
    stages = snapshot.get("stages")
    if not isinstance(stages, Mapping):
        return None
    interpretation = stages.get("interpretation")
    if not isinstance(interpretation, Mapping):
        return None
    profiles = interpretation.get("profiles")
    if not isinstance(profiles, Mapping):
        return None
    attempt = profiles.get(EXPORTABLE_PROFILE_ID)
    if not isinstance(attempt, Mapping):
        return None
    if attempt.get("status") != "completed":
        return None
    if not isinstance(attempt.get("result"), Mapping):
        # A completed attempt can carry a null result (skip path) — there is
        # nothing to hand off in that case.
        return None
    return attempt


def _validation_warnings(attempt: Mapping[str, Any]) -> list[dict[str, Any]]:
    diagnostics = attempt.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        return []
    warnings = diagnostics.get("validationWarnings")
    if not isinstance(warnings, list):
        return []
    return [warning for warning in warnings if isinstance(warning, dict)]


def build_phase2_export(
    snapshot: Mapping[str, Any],
    *,
    exported_at: str | None = None,
) -> dict[str, Any] | None:
    """Project a run snapshot into a ``phase2-export.v1`` envelope.

    Returns ``None`` when the run has no completed ``producer_summary``
    interpretation result to hand off (not requested, still running, failed,
    or completed-with-skip). Deterministic and side-effect-free.
    """
    attempt = _producer_summary_attempt(snapshot)
    if attempt is None:
        return None
    measurement = snapshot.get("stages", {}).get("measurement", {})
    measurement_result = (
        measurement.get("result") if isinstance(measurement, Mapping) else None
    )
    provenance = attempt.get("provenance")
    return {
        "schemaVersion": EXPORT_SCHEMA_VERSION,
        "runId": snapshot.get("runId"),
        "exportedAt": exported_at if exported_at is not None else _utc_now_iso(),
        "provenance": provenance if isinstance(provenance, Mapping) else None,
        "validationWarnings": _validation_warnings(attempt),
        "phase1": measurement_result if isinstance(measurement_result, Mapping) else None,
        "phase2": attempt["result"],
    }
