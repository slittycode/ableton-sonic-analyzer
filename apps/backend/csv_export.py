"""CSV exporters for Phase 1 time-series fields.

Patterned on the ``(time, duration, value)`` tabular shape used by Partiels
and similar Vamp-output tools (see ``docs/external-repo-review-2026-05-13.md``
Track 2 for the rationale and the rejected-alternatives discussion). Each
exporter maps one dotted JSON path inside the Phase 1 measurement payload to
a small CSV with documented columns.

The exporters are kept here, outside ``server.py``, so the route handler can
stay a thin lookup-and-serve.

Registered paths (v1):

==================================  =====================================
Path                                CSV columns
==================================  =====================================
``lufsCurve.shortTerm``             ``time, duration, lufs``  (duration=3.0)
``lufsCurve.momentary``             ``time, duration, lufs``  (duration=0.4)
``rhythmDetail.tempoCurve``         ``time, bpm``
``spectralBalanceTimeSeries``       ``time, subBass, lowBass, lowMids,``
                                    ``mids, upperMids, highs, brilliance``
==================================  =====================================

Design notes:

- The ``duration`` column on the LUFS curves reflects EBU R128's measurement
  window for that point (3.0 s short-term, 0.4 s momentary). Other curves
  do not have an intrinsic per-point duration and so omit the column.
- A field that is ``None`` or missing from the measurement payload returns
  ``None`` from :func:`export_field_to_csv`. The HTTP layer treats that
  separately from "unknown field" so users get a useful error code.
- Field paths are deliberately allowlisted: arbitrary JSONPath/nested-key
  descent on the measurement payload is not supported. Adding a new
  exportable field is a small, deliberate code change in this file.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Callable


__all__ = [
    "export_field_to_csv",
    "is_supported_field",
    "list_supported_fields",
]


# EBU R128 short-term loudness window is 3.0 s; momentary is 0.4 s.
# Each curve point reports the integrated loudness over that window
# ending at ``t``.
_LUFS_SHORT_TERM_WINDOW_S = 3.0
_LUFS_MOMENTARY_WINDOW_S = 0.4


_SPECTRAL_BANDS: tuple[str, ...] = (
    "subBass",
    "lowBass",
    "lowMids",
    "mids",
    "upperMids",
    "highs",
    "brilliance",
)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def export_field_to_csv(
    measurement_result: dict | None,
    field_path: str,
) -> str | None:
    """Look up ``field_path`` in the registry and serialize the value to CSV.

    Returns the CSV text (header row + data rows) when the field is present
    and non-empty. Returns ``None`` when any of these are true:

    - ``measurement_result`` itself is ``None``
    - the field path is not registered (caller should treat as 404 "unknown")
    - the field is missing or ``None`` in the measurement payload (caller
      should treat as 404 "not available for this run")
    - the field is present but empty (zero data points; same as above)

    The caller is responsible for distinguishing "unknown path" from
    "known path, no data" — see :func:`is_supported_field`.
    """
    if measurement_result is None:
        return None
    if field_path not in _EXPORTERS:
        return None
    field_value = _resolve_dot_path(measurement_result, field_path)
    if field_value is None:
        return None
    return _EXPORTERS[field_path](field_value)


def is_supported_field(field_path: str) -> bool:
    """Whether ``field_path`` is in the export registry.

    Independent of whether any particular run has data for it.
    """
    return field_path in _EXPORTERS


def list_supported_fields() -> list[str]:
    """All currently exportable field paths, sorted alphabetically."""
    return sorted(_EXPORTERS.keys())


# ----------------------------------------------------------------------
# Path resolution
# ----------------------------------------------------------------------


def _resolve_dot_path(payload: dict, dot_path: str) -> Any:
    """Walk ``payload`` along ``a.b.c`` and return the leaf, or ``None``.

    Returns ``None`` on any of: non-dict at an intermediate step, missing
    key at any step, or explicit ``None`` value at any step. This is a
    simple nested-key descent — *not* JSONPath syntax (no ``$``, no
    ``[*]``, no array indexing).
    """
    node: Any = payload
    for key in dot_path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
        if node is None:
            return None
    return node


# ----------------------------------------------------------------------
# Per-field serializers
# ----------------------------------------------------------------------


def _serialize_lufs_curve(
    points: Any, window_duration_s: float
) -> str | None:
    """Serialize a list of ``{t, lufs}`` points with a constant duration column."""
    if not isinstance(points, list) or len(points) == 0:
        return None
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["time", "duration", "lufs"])
    wrote_any = False
    for point in points:
        if not isinstance(point, dict):
            continue
        t = point.get("t")
        lufs = point.get("lufs")
        if t is None or lufs is None:
            continue
        writer.writerow(
            [f"{float(t):.6f}", f"{window_duration_s}", f"{float(lufs):.2f}"]
        )
        wrote_any = True
    return buf.getvalue() if wrote_any else None


def _serialize_tempo_curve(points: Any) -> str | None:
    """Serialize a list of ``{t, bpm}`` points."""
    if not isinstance(points, list) or len(points) == 0:
        return None
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["time", "bpm"])
    wrote_any = False
    for point in points:
        if not isinstance(point, dict):
            continue
        t = point.get("t")
        bpm = point.get("bpm")
        if t is None or bpm is None:
            continue
        writer.writerow([f"{float(t):.6f}", f"{float(bpm):.3f}"])
        wrote_any = True
    return buf.getvalue() if wrote_any else None


def _serialize_spectral_balance_time_series(points: Any) -> str | None:
    """Serialize a list of ``{t, subBass, ..., brilliance}`` points.

    Skips any row that is missing one of the band values rather than
    writing a partial row — keeps the CSV regular and downstream-loadable.
    """
    if not isinstance(points, list) or len(points) == 0:
        return None
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["time", *_SPECTRAL_BANDS])
    wrote_any = False
    for point in points:
        if not isinstance(point, dict):
            continue
        t = point.get("t")
        if t is None:
            continue
        band_values: list[str] = []
        skip = False
        for band in _SPECTRAL_BANDS:
            value = point.get(band)
            if value is None:
                skip = True
                break
            band_values.append(f"{float(value):.4f}")
        if skip:
            continue
        writer.writerow([f"{float(t):.6f}", *band_values])
        wrote_any = True
    return buf.getvalue() if wrote_any else None


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------


_EXPORTERS: dict[str, Callable[[Any], str | None]] = {
    "lufsCurve.shortTerm": lambda value: _serialize_lufs_curve(
        value, _LUFS_SHORT_TERM_WINDOW_S
    ),
    "lufsCurve.momentary": lambda value: _serialize_lufs_curve(
        value, _LUFS_MOMENTARY_WINDOW_S
    ),
    "rhythmDetail.tempoCurve": _serialize_tempo_curve,
    "spectralBalanceTimeSeries": _serialize_spectral_balance_time_series,
}
