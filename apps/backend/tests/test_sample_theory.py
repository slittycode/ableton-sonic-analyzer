"""Tests for the Phase 3 music-theory adapter.

The MIDI numbers asserted here are the canonical Western-music values for the
given key/mode/degree combinations. Both the PyTheory and fallback paths must
agree with these reference values — if a render starts sounding out-of-key,
this is the first place to look.
"""

import sys
import unittest
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sample_theory  # noqa: E402


class ParseKeyTests(unittest.TestCase):
    def test_parses_canonical_keys(self) -> None:
        self.assertEqual(sample_theory.parse_key("C major"), (0, "major", "C"))
        self.assertEqual(sample_theory.parse_key("A minor"), (9, "minor", "A"))
        self.assertEqual(sample_theory.parse_key("F# minor"), (6, "minor", "F#"))
        self.assertEqual(sample_theory.parse_key("Bb major"), (10, "major", "Bb"))

    def test_defaults_to_major_when_mode_missing(self) -> None:
        self.assertEqual(sample_theory.parse_key("D"), (2, "major", "D"))

    def test_tolerates_parenthetical_suffix(self) -> None:
        # Phase 1 occasionally tacks on confidence qualifiers.
        self.assertEqual(
            sample_theory.parse_key("F# minor (low confidence)"),
            (6, "minor", "F#"),
        )

    def test_rejects_unknown_root(self) -> None:
        with self.assertRaises(ValueError):
            sample_theory.parse_key("H minor")

    def test_rejects_unknown_mode(self) -> None:
        with self.assertRaises(ValueError):
            sample_theory.parse_key("C ionian-augmented-fancy")

    def test_rejects_empty_input(self) -> None:
        with self.assertRaises(ValueError):
            sample_theory.parse_key("")


class BuildContextTests(unittest.TestCase):
    def test_carries_confidence_through(self) -> None:
        ctx = sample_theory.build_context(key="C major", bpm=128.0, key_confidence=0.83)
        self.assertEqual(ctx.root_pc, 0)
        self.assertEqual(ctx.mode, "major")
        self.assertEqual(ctx.root_name, "C")
        self.assertEqual(ctx.tempo_bpm, 128.0)
        self.assertEqual(ctx.key_confidence, 0.83)
        self.assertIn(ctx.backend, {"pytheory", "fallback"})


class ChordProgressionTests(unittest.TestCase):
    def test_c_major_progression_voicings(self) -> None:
        ctx = sample_theory.build_context(key="C major", bpm=120.0)
        plan = sample_theory.plan_chord_progression(ctx, bars=8, voicing_octave=4)

        # 4 chords × 3 notes each = 12 events.
        self.assertEqual(len(plan.notes), 12)

        # Chord 1 (C major): C-E-G at octave 4.
        chord_one_pitches = sorted(n.pitch_midi for n in plan.notes if n.start_beat == 0.0)
        self.assertEqual(chord_one_pitches, [60, 64, 67])

        # Chord 2 (A minor, vi): A-C-E. Starts at beat 8.
        chord_two_pitches = sorted(
            n.pitch_midi for n in plan.notes if n.start_beat == 8.0
        )
        self.assertEqual(chord_two_pitches, [57, 60, 64])

        # Chord 3 (F major, IV): F-A-C. Starts at beat 16.
        chord_three_pitches = sorted(
            n.pitch_midi for n in plan.notes if n.start_beat == 16.0
        )
        self.assertEqual(chord_three_pitches, [53, 57, 60])

        # Chord 4 (G major, V): G-B-D. Starts at beat 24.
        chord_four_pitches = sorted(
            n.pitch_midi for n in plan.notes if n.start_beat == 24.0
        )
        self.assertEqual(chord_four_pitches, [55, 59, 62])

    def test_a_minor_progression_voicings(self) -> None:
        ctx = sample_theory.build_context(key="A minor", bpm=120.0)
        plan = sample_theory.plan_chord_progression(ctx, bars=8, voicing_octave=4)

        # i (A minor) at the tonic octave: A4-C5-E5.
        chord_one_pitches = sorted(n.pitch_midi for n in plan.notes if n.start_beat == 0.0)
        self.assertEqual(chord_one_pitches, [69, 72, 76])

        # VI (F major), dropped to the octave below the tonic anchor:
        # F4-A4-C5. Distance from tonic chord: a stepwise descent in the bass.
        chord_two_pitches = sorted(
            n.pitch_midi for n in plan.notes if n.start_beat == 8.0
        )
        self.assertEqual(chord_two_pitches, [65, 69, 72])

    def test_rejects_odd_bar_counts(self) -> None:
        ctx = sample_theory.build_context(key="C major", bpm=120.0)
        with self.assertRaises(ValueError):
            sample_theory.plan_chord_progression(ctx, bars=7)


class BassRootTests(unittest.TestCase):
    def test_bass_lives_two_octaves_below_voicing(self) -> None:
        ctx = sample_theory.build_context(key="C major", bpm=120.0)
        plan = sample_theory.plan_bass_root(ctx, bars=8)
        # C at octave 2 = MIDI 36.
        for note in plan.notes:
            self.assertEqual(note.pitch_midi, 36)

    def test_bass_count_matches_bars(self) -> None:
        ctx = sample_theory.build_context(key="A minor", bpm=120.0)
        plan = sample_theory.plan_bass_root(ctx, bars=8)
        self.assertEqual(len(plan.notes), 4)  # one per two bars
        self.assertEqual(plan.duration_beats, 32.0)


class MelodyPlanTests(unittest.TestCase):
    def test_default_phrase_uses_in_key_pitches(self) -> None:
        ctx = sample_theory.build_context(key="C major", bpm=120.0)
        plan = sample_theory.plan_melody_phrase(ctx)
        self.assertIsNotNone(plan)
        assert plan is not None  # narrowing for type checkers
        # Default ascent 1-2-3-5-3-1 in C major at octave 5 -> C5 D5 E5 G5 E5 C5.
        pitches = [n.pitch_midi for n in plan.notes]
        self.assertEqual(pitches, [72, 74, 76, 79, 76, 72])

    def test_respects_supplied_hints(self) -> None:
        ctx = sample_theory.build_context(key="C major", bpm=120.0)
        plan = sample_theory.plan_melody_phrase(ctx, scale_degrees=[1, 3, 5])
        assert plan is not None
        self.assertEqual([n.pitch_midi for n in plan.notes], [72, 76, 79])

    def test_returns_none_for_empty_clean_input(self) -> None:
        ctx = sample_theory.build_context(key="C major", bpm=120.0)
        # All ineligible degrees should produce no plan rather than fabricate one.
        self.assertIsNone(sample_theory.plan_melody_phrase(ctx, scale_degrees=[0, 99]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
