"""Unit tests for scripts/convert_audacity_beats.py (ASA-slice annotation helper).

The converter turns an Audacity label export into the GTZAN-Rhythm `.beats`
format the beat gate consumes. Ground-truth tooling, so failure modes are hard
errors: an unanchored bar 1 or a backwards timestamp must never silently
produce a plausible-looking annotation.
"""

import unittest

from scripts.convert_audacity_beats import convert_labels


def _lines(*rows: tuple[float, str]) -> list[str]:
    return [f"{t:.3f}\t{t:.3f}\t{label}" for t, label in rows]


class ConvertLabelsTests(unittest.TestCase):
    def test_explicit_positions_pass_through(self) -> None:
        beats = convert_labels(_lines((0.5, "1"), (1.0, "2"), (1.5, "3"), (2.0, "4"), (2.5, "1")))
        self.assertEqual(beats, [(0.5, 1), (1.0, 2), (1.5, 3), (2.0, 4), (2.5, 1)])

    def test_blank_labels_cycle_from_previous(self) -> None:
        # Annotator marks only the downbeats; blanks fill 2..4 and wrap to 1... but
        # the wrap position is overridden wherever an explicit "1" appears.
        beats = convert_labels(_lines((0.0, "1"), (0.5, ""), (1.0, ""), (1.5, ""), (2.0, "1"), (2.5, "")))
        self.assertEqual(beats, [(0.0, 1), (0.5, 2), (1.0, 3), (1.5, 4), (2.0, 1), (2.5, 2)])

    def test_blank_wrap_respects_meter(self) -> None:
        beats = convert_labels(_lines((0.0, "1"), (0.5, ""), (1.0, ""), (1.5, "")), meter=3)
        self.assertEqual([pos for _, pos in beats], [1, 2, 3, 1])

    def test_first_label_must_be_explicit(self) -> None:
        with self.assertRaises(ValueError):
            convert_labels(_lines((0.0, ""), (0.5, "1")))

    def test_backwards_time_rejected(self) -> None:
        with self.assertRaises(ValueError):
            convert_labels(_lines((1.0, "1"), (0.5, "2")))

    def test_position_outside_meter_rejected(self) -> None:
        with self.assertRaises(ValueError):
            convert_labels(_lines((0.0, "5")))

    def test_comment_and_empty_lines_skipped(self) -> None:
        beats = convert_labels(["# comment", "", "0.000\t0.000\t1", "0.500\t0.500\t2"])
        self.assertEqual(beats, [(0.0, 1), (0.5, 2)])

    def test_empty_input_rejected(self) -> None:
        with self.assertRaises(ValueError):
            convert_labels(["# nothing here"])


if __name__ == "__main__":
    unittest.main()
