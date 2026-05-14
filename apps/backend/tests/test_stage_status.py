"""Unit tests for stage_status — the 8 → 5 public-status collapse.

The collapse is the documented contract for ``publicStatus`` on every
stage object in the run snapshot. Tests here pin the mapping cell-by-cell
so a quiet edit to the lookup table is caught.
"""

import sys
import unittest
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


import stage_status  # noqa: E402 — load after sys.path is set


class PublicStatusValuesTests(unittest.TestCase):
    """The five public-facing values, exhaustively."""

    def test_exact_five_values(self):
        self.assertEqual(
            stage_status.PUBLIC_STATUS_VALUES,
            frozenset({"queued", "running", "completed", "failed", "interrupted"}),
        )

    def test_helper_returns_same_set(self):
        self.assertEqual(
            stage_status.public_status_values(),
            stage_status.PUBLIC_STATUS_VALUES,
        )


class ToPublicStatusTests(unittest.TestCase):
    """Cell-by-cell mapping pins for the eight internal states."""

    def test_queued_maps_to_queued(self):
        self.assertEqual(stage_status.to_public_status("queued"), "queued")

    def test_running_maps_to_running(self):
        self.assertEqual(stage_status.to_public_status("running"), "running")

    def test_blocked_maps_to_queued(self):
        """``blocked`` is transient internal scheduling; clients see it
        the same as ``queued``."""
        self.assertEqual(stage_status.to_public_status("blocked"), "queued")

    def test_ready_maps_to_queued(self):
        """``ready`` means scheduled but not yet started; same as queued
        from the client's perspective."""
        self.assertEqual(stage_status.to_public_status("ready"), "queued")

    def test_completed_maps_to_completed(self):
        self.assertEqual(stage_status.to_public_status("completed"), "completed")

    def test_failed_maps_to_failed(self):
        self.assertEqual(stage_status.to_public_status("failed"), "failed")

    def test_interrupted_maps_to_interrupted(self):
        self.assertEqual(
            stage_status.to_public_status("interrupted"), "interrupted"
        )

    def test_not_requested_maps_to_none(self):
        """``not_requested`` means the caller didn't ask for this stage;
        conceptually distinct from queued. Exposed as ``null`` in JSON."""
        self.assertIsNone(stage_status.to_public_status("not_requested"))


class ToPublicStatusDefensiveTests(unittest.TestCase):
    """Defensive cases: nones, unknowns, and the empty string."""

    def test_none_returns_none(self):
        self.assertIsNone(stage_status.to_public_status(None))

    def test_unknown_internal_status_returns_none(self):
        """A new internal-only state added without a public mapping
        should fall through as None rather than leak through. This is
        the forwards-compat guard."""
        self.assertIsNone(stage_status.to_public_status("does_not_exist"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(stage_status.to_public_status(""))

    def test_case_sensitive(self):
        """The internal vocabulary is lowercase. Uppercase shouldn't
        match — the mapping table is case-sensitive by design."""
        self.assertIsNone(stage_status.to_public_status("QUEUED"))
        self.assertIsNone(stage_status.to_public_status("Running"))


class MappingCompletenessTests(unittest.TestCase):
    """Pins the set of internal states the mapping covers.

    If a new internal status is added without a corresponding entry
    here, this test fails. If an old one is removed, this test fails.
    Either way, the developer must make a deliberate choice about the
    public mapping rather than silently drift.
    """

    EXPECTED_INTERNAL_STATES = frozenset(
        {
            "queued",
            "running",
            "blocked",
            "ready",
            "completed",
            "failed",
            "interrupted",
            "not_requested",
        }
    )

    def test_internal_states_unchanged(self):
        actual = frozenset(stage_status._INTERNAL_TO_PUBLIC.keys())
        self.assertEqual(actual, self.EXPECTED_INTERNAL_STATES)

    def test_all_non_null_mappings_are_public_values(self):
        """Every non-None target of the mapping must be in
        PUBLIC_STATUS_VALUES — no smuggling new public states in via
        the mapping table without updating the canonical set."""
        for internal, public in stage_status._INTERNAL_TO_PUBLIC.items():
            if public is None:
                continue
            self.assertIn(
                public,
                stage_status.PUBLIC_STATUS_VALUES,
                msg=(
                    f"{internal!r} maps to {public!r}, which is not in "
                    f"PUBLIC_STATUS_VALUES. Either add it to the public "
                    f"set or change the mapping."
                ),
            )


if __name__ == "__main__":
    unittest.main()
