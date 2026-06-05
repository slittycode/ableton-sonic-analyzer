"""Recommendations contract v1 — frozen, versioned, schema-validated projection.

ASA's Phase 2 (interpretation) layer emits device recommendations across three
free-shaped arrays — ``abletonRecommendations``, ``mixAndMasterChain``, and
``secretSauce.workflowSteps`` — each carrying ``{device, parameter, value,
phase1Fields}`` plus prose. ``value`` is a free-text string ("10 ms", "-18 dB",
"3:1", "Sine") and there is no separate ``unit``/``range``.

This module freezes a **normalized, machine-actionable view** of those cards:
a flat list of entries shaped ``{device, parameter, value, unit, range,
cited_measurements[]}``, validated against the committed JSON Schema at
``schemas/recommendations.v1.schema.json``. The contract version string is
``recommendations.v1`` (ADR 0003).

Design properties (all load-bearing):

  1. **Derived, never authoritative.** The projection only reads Phase 2 output;
     it never overrides or re-estimates a Phase 1 measurement (PURPOSE.md
     invariant #1). It is additive — the raw Phase 2 arrays are untouched.
  2. **Citation-gated.** A card is admitted ONLY if it cites >=1 Phase 1
     measurement (invariant #2 / schema ``cited_measurements.minItems: 1``).
     Uncited cards are excluded *from this view* by design; they remain in the
     raw arrays, where the warn-and-keep catalogue gate
     (``phase2_catalogue_gates.py``) already flags them. Nothing user-facing is
     dropped — exclusion is from the normalized contract only.
  3. **Honest range.** ``range`` is a best-effort working neighborhood derived
     from a per-unit tolerance band, emitted only when the value is numeric AND
     the unit is known; otherwise ``null``. The static Live 12 catalogue carries
     no min/max (see ``data/live12_catalogue.schema.json`` extraction_notes), so
     a hard device range is deliberately NOT claimed (invariant #4).
  4. **Validated against the file, not a mirror.** ``validate_envelope`` runs the
     real JSON Schema (``jsonschema``) against the committed file — there is no
     hand-rolled structural mirror that could drift from the published schema
     (the failure mode ADR 0001 warned about).

Provenance: the value parser and per-unit tolerance bands are a faithful copy of
``recommendation_evaluation.py`` (the research-only recommendation scorer). They
are duplicated here on purpose so this product-path module carries no dependency
on the deletable research harness — the same deliberate cross-module duplication
pattern as ``audio_mime.py`` / ``audioFile.ts``. Keep the two band tables in
sync; if they ever need to diverge, that is a scoring vs. contract decision worth
a comment in both files.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import jsonschema

CONTRACT_VERSION = "recommendations.v1"

SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "recommendations.v1.schema.json"


# ---------------------------------------------------------------------------
# Value parsing + per-unit tolerance bands.
# Faithful copy of recommendation_evaluation.py — see module docstring.
# Internal unit tokens are lowercase ("hz", "db", ...); the contract maps them
# to display units ("Hz", "dB", ...) via _DISPLAY_UNIT below.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedValue:
    """A numeric magnitude extracted from a free-text value string."""

    number: float
    unit: str  # normalized: "hz", "db", "ms", "s", "ratio", "pct", "st", ""


@dataclass(frozen=True)
class UnitBand:
    abs_tol: float | None
    rel_tol: float | None
    neutral: float


# tolerance is absolute in the unit unless `rel_tol` is set (fraction of value).
UNIT_BANDS: dict[str, UnitBand] = {
    "hz": UnitBand(abs_tol=None, rel_tol=0.20, neutral=1000.0),   # +/-20%
    "db": UnitBand(abs_tol=3.0, rel_tol=None, neutral=0.0),       # +/-3 dB
    "ms": UnitBand(abs_tol=None, rel_tol=0.30, neutral=20.0),     # +/-30%
    "s": UnitBand(abs_tol=None, rel_tol=0.30, neutral=1.0),       # +/-30%
    "ratio": UnitBand(abs_tol=1.0, rel_tol=None, neutral=1.0),    # +/-1:1
    "pct": UnitBand(abs_tol=15.0, rel_tol=None, neutral=50.0),    # +/-15%
    "st": UnitBand(abs_tol=1.0, rel_tol=None, neutral=0.0),       # +/-1 semitone
    "": UnitBand(abs_tol=None, rel_tol=0.20, neutral=0.0),        # unitless: +/-20%
}

# Internal token -> display unit. "" (unitless) maps to None (absent here).
_DISPLAY_UNIT: dict[str, str] = {
    "hz": "Hz",
    "db": "dB",
    "ms": "ms",
    "s": "s",
    "ratio": "ratio",
    "pct": "%",
    "st": "st",
}

# Longer unit tokens must precede their prefixes in the alternation (`st` before
# `s`, `sec`/`semitones` before `s`, `ms` before `s`) so regex first-match wins.
_VALUE_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*"
    r"(k?hz|db|ms|sec|semitones?|st|s|%|:1|x)?",
    re.IGNORECASE,
)


def _normalize_unit(raw: str) -> str:
    if raw in ("khz", "hz"):
        return "hz"
    if raw == "db":
        return "db"
    if raw == "ms":
        return "ms"
    if raw in ("s", "sec"):
        return "s"
    if raw == "%":
        return "pct"
    if raw in ("st", "semitone", "semitones"):
        return "st"
    if raw in (":1", "x"):
        return "ratio"
    return ""


def parse_value(text: Any) -> ParsedValue | None:
    """Extract a numeric magnitude + normalized unit from a value string.

    Handles ``"4 kHz"``, ``"-15 dB"``, ``"200 ms"``, ``"3:1"``, ``"30%"``,
    ``"0.6"``, ``"+12st"``. Returns ``None`` for non-numeric values (e.g.
    ``"Sine"``, ``"Auto"``).
    """
    if text is None:
        return None
    if isinstance(text, bool):  # bool is an int subclass — exclude.
        return None
    if isinstance(text, (int, float)):
        if not math.isfinite(float(text)):
            return None
        return ParsedValue(number=float(text), unit="")
    s = str(text).strip()
    if not s:
        return None
    # Ratio form "3:1" -> 3.0 ratio.
    ratio_match = re.search(r"(-?\d+(?:\.\d+)?)\s*:\s*1\b", s)
    if ratio_match:
        return ParsedValue(number=float(ratio_match.group(1)), unit="ratio")
    match = _VALUE_RE.search(s)
    if not match:
        return None
    number = float(match.group(1))
    raw_unit = (match.group(2) or "").lower()
    unit = _normalize_unit(raw_unit)
    if unit == "hz" and raw_unit.startswith("k"):
        number *= 1000.0
    return ParsedValue(number=number, unit=unit)


def _derive_range(number: float, token: str) -> list[float] | None:
    """Suggested working range [min, max] from the per-unit tolerance band.

    Returns ``None`` for the unitless band — a range without a unit is not
    meaningful enough to publish (the contract emits ``range: null`` there).
    """
    if token not in _DISPLAY_UNIT:
        return None
    band = UNIT_BANDS.get(token)
    if band is None:
        return None
    if band.abs_tol is not None:
        tol = band.abs_tol
    else:
        tol = abs(number) * (band.rel_tol or 0.0)
    return [round(number - tol, 4), round(number + tol, 4)]


# ---------------------------------------------------------------------------
# Projection: Phase 2 result -> recommendations.v1 envelope.
# ---------------------------------------------------------------------------


def _clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _citations(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [s.strip() for s in raw if isinstance(s, str) and s.strip()]


def _project_card(card: Any) -> dict[str, Any] | None:
    """Project one Phase 2 device card into a contract entry, or ``None``.

    Returns ``None`` (card excluded from the contract) when the card lacks a
    usable device/parameter, has no usable value, or — critically — carries no
    Phase 1 citation. Exclusion here is from the normalized view only; the card
    remains in its raw Phase 2 array.
    """
    if not isinstance(card, Mapping):
        return None
    device = _clean_str(card.get("device"))
    parameter = _clean_str(card.get("parameter"))
    if not device or not parameter:
        return None
    citations = _citations(card.get("phase1Fields"))
    if not citations:  # citation-chain invariant — uncited cards are not admitted
        return None

    parsed = parse_value(card.get("value"))
    if parsed is not None:
        value: Any = parsed.number
        unit = _DISPLAY_UNIT.get(parsed.unit)  # None for the unitless token
        rng = _derive_range(parsed.number, parsed.unit) if unit is not None else None
    else:
        value = _clean_str(card.get("value"))
        if not value:  # no usable value -> cannot form a valid entry
            return None
        unit = None
        rng = None

    return {
        "device": device,
        "parameter": parameter,
        "value": value,
        "unit": unit,
        "range": rng,
        "cited_measurements": citations,
    }


# Phase 2 list-valued sources that carry device cards. secretSauce.workflowSteps
# is nested and handled separately.
_LIST_SOURCES = ("abletonRecommendations", "mixAndMasterChain")


def project_recommendations(phase2_result: Any) -> dict[str, Any]:
    """Project a Phase 2 result dict into a ``recommendations.v1`` envelope.

    Deterministic and side-effect-free. The returned envelope always validates
    against the committed schema (an empty ``recommendations`` list is valid).
    """
    recs: list[dict[str, Any]] = []
    if isinstance(phase2_result, Mapping):
        for key in _LIST_SOURCES:
            items = phase2_result.get(key)
            if isinstance(items, list):
                for item in items:
                    entry = _project_card(item)
                    if entry is not None:
                        recs.append(entry)
        secret = phase2_result.get("secretSauce")
        if isinstance(secret, Mapping):
            steps = secret.get("workflowSteps")
            if isinstance(steps, list):
                for item in steps:
                    entry = _project_card(item)
                    if entry is not None:
                        recs.append(entry)
    return {"version": CONTRACT_VERSION, "recommendations": recs}


# ---------------------------------------------------------------------------
# Validation against the committed schema FILE (not a hand-rolled mirror).
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Load and cache the committed recommendations.v1 JSON Schema."""
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _validator() -> jsonschema.protocols.Validator:
    schema = load_schema()
    validator_cls = jsonschema.validators.validator_for(schema)
    # Fail fast if the committed schema is itself malformed.
    validator_cls.check_schema(schema)
    return validator_cls(schema)


def validate_envelope(envelope: Mapping[str, Any]) -> None:
    """Validate an envelope against the committed schema. Raises on the first
    violation (``jsonschema.exceptions.ValidationError``)."""
    _validator().validate(envelope)


def iter_validation_errors(envelope: Mapping[str, Any]) -> list[str]:
    """Return human-readable messages for every schema violation (empty if
    valid). Used by tests and the runtime degrade path."""
    errors = sorted(
        _validator().iter_errors(envelope), key=lambda err: str(err.json_path)
    )
    return [f"{err.json_path}: {err.message}" for err in errors]


def build_validated_recommendations(phase2_result: Any) -> dict[str, Any] | None:
    """Project and validate in one call for runtime use.

    Returns the validated envelope, or ``None`` if projection/validation fails.
    Degrade-on-error mirrors the catalogue-gate / loudness-backend philosophy:
    a derived view must never break the response it rides on. The projection is
    deterministic, so a ``None`` here signals a genuine bug worth logging at the
    call site, not an expected outcome.
    """
    try:
        envelope = project_recommendations(phase2_result)
        validate_envelope(envelope)
        return envelope
    except Exception:  # noqa: BLE001 — additive view must not break the response
        return None
