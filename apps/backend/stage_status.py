"""Public-facing collapse of the internal stage-status state machine.

ASA's run-state machine has eight internal statuses
(``queued``, ``running``, ``blocked``, ``ready``, ``completed``,
``failed``, ``interrupted``, ``not_requested``). Most of these are
runtime-scheduling concerns the client does not need to act on:

- ``blocked`` and ``ready`` are transient states between "waiting on
  a dependency" and "scheduled to run." Both look identical to a
  client polling the snapshot — there's nothing to display or do
  differently.
- ``not_requested`` means the caller did not ask for this stage to
  run (e.g. ``pitch_note_mode="off"``). Conceptually distinct from
  "queued"; the stage is simply absent from the requested pipeline.

This module exposes the five-state vocabulary intended for external
consumers and the mapping from the internal eight to that public
five. The internal ``status`` field on each stage stays untouched;
this is an *additive* collapse — the route layer attaches a parallel
``publicStatus`` field next to ``status`` on each stage.

Mapping:

==============  ===============================
Internal        Public (publicStatus)
==============  ===============================
queued          queued
running         running
blocked         queued       (transient internal)
ready           queued       (scheduled, not yet running)
completed       completed
failed          failed
interrupted     interrupted
not_requested   None         (not in the pipeline)
==============  ===============================

A ``None`` mapping is exposed in JSON as ``"publicStatus": null``.
This is deliberate — explicit ``null`` is easier for clients than
checking key presence, especially in strongly-typed languages where
optional vs missing are different shapes.

See ``docs/adr/0001-phase1-json-schema-v1.md`` for the schema-version
treatment of this field.
"""

from __future__ import annotations

from typing import Final


PUBLIC_STATUS_VALUES: Final[frozenset[str]] = frozenset(
    {"queued", "running", "completed", "failed", "interrupted"}
)


_INTERNAL_TO_PUBLIC: Final[dict[str, str | None]] = {
    "queued": "queued",
    "running": "running",
    "blocked": "queued",
    "ready": "queued",
    "completed": "completed",
    "failed": "failed",
    "interrupted": "interrupted",
    "not_requested": None,
}


def to_public_status(internal_status: str | None) -> str | None:
    """Map an internal stage status to its public-facing equivalent.

    Returns ``None`` when:
    - ``internal_status`` is ``None`` (stage exists but no status set)
    - ``internal_status`` is ``"not_requested"`` (stage is not in the pipeline)
    - ``internal_status`` is an unrecognized value (defensive — should not
      happen with the current state machine, but a forwards-compat
      guard against accidental internal-only additions leaking out)
    """
    if internal_status is None:
        return None
    return _INTERNAL_TO_PUBLIC.get(internal_status)


def public_status_values() -> frozenset[str]:
    """The complete set of non-null public status values.

    Useful for type generation, validation, and documentation.
    """
    return PUBLIC_STATUS_VALUES
