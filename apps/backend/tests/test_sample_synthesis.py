"""Tests for the MIDI-plan → WAV/MIDI synthesis layer.

The sine fallback path is the one exercised by these tests; the FluidSynth
path requires a system library and a soundfont, which we don't assume are
present in CI. The fallback is the everywhere-available backstop and must
stay correct.
"""

import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sample_synthesis  # noqa: E402
import sample_theory  # noqa: E402


def _single_note_plan(pitch: int = 69, bpm: float = 120.0, duration_beats: float = 4.0) -> sample_theory.ClipPlan:
    """Minimal plan: one note for `duration_beats`."""
    return sample_theory.ClipPlan(
        tempo_bpm=bpm,
        duration_beats=duration_beats,
        notes=[
            sample_theory.NoteEvent(
                pitch_midi=pitch, start_beat=0.0, duration_beats=duration_beats
            )
        ],
        program=0,
    )


class SineFallbackTests(unittest.TestCase):
    def test_render_returns_expected_shape(self) -> None:
        plan = _single_note_plan(pitch=69, bpm=120.0, duration_beats=4.0)
        result = sample_synthesis.render_clip(plan, prefer_fluidsynth=False)
        expected_samples = int(round(2.0 * sample_synthesis.SAMPLE_RATE))  # 4 beats @ 120 = 2 s
        self.assertEqual(result.samples.shape, (expected_samples,))
        self.assertEqual(result.samples.dtype, np.float32)
        self.assertEqual(result.backend, "sine_fallback")
        self.assertIsNone(result.soundfont_path)

    def test_render_contains_energy_at_target_frequency(self) -> None:
        # A4 = MIDI 69 = 440 Hz exactly.
        plan = _single_note_plan(pitch=69, bpm=120.0, duration_beats=4.0)
        result = sample_synthesis.render_clip(plan, prefer_fluidsynth=False)

        # Look at the middle of the note to avoid envelope transients.
        mid_start = result.samples.size // 4
        mid_end = result.samples.size - result.samples.size // 4
        segment = result.samples[mid_start:mid_end].astype(np.float64)
        spectrum = np.abs(np.fft.rfft(segment))
        freqs = np.fft.rfftfreq(segment.size, d=1.0 / sample_synthesis.SAMPLE_RATE)
        peak_freq = float(freqs[int(np.argmax(spectrum))])
        # Allow a few Hz of bin-resolution slop.
        self.assertAlmostEqual(peak_freq, 440.0, delta=5.0)

    def test_render_silent_when_no_notes(self) -> None:
        plan = sample_theory.ClipPlan(
            tempo_bpm=120.0, duration_beats=4.0, notes=[], program=0
        )
        result = sample_synthesis.render_clip(plan, prefer_fluidsynth=False)
        peak = float(np.max(np.abs(result.samples)))
        self.assertEqual(peak, 0.0)


class WriteWavTests(unittest.TestCase):
    def test_write_wav_round_trips(self) -> None:
        plan = _single_note_plan(pitch=60, bpm=120.0, duration_beats=2.0)
        result = sample_synthesis.render_clip(plan, prefer_fluidsynth=False)

        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "out.wav"
            sample_synthesis.write_wav(result.samples, path=wav_path)
            self.assertTrue(wav_path.is_file())
            with wave.open(str(wav_path), "rb") as wav:
                self.assertEqual(wav.getframerate(), sample_synthesis.SAMPLE_RATE)
                self.assertEqual(wav.getnchannels(), 1)
                # 16-bit subtype = 2 bytes per sample.
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertGreater(wav.getnframes(), 0)


class WriteMidiTests(unittest.TestCase):
    def test_write_midi_emits_expected_note(self) -> None:
        import pretty_midi  # local import — only test needs it

        plan = sample_theory.ClipPlan(
            tempo_bpm=120.0,
            duration_beats=4.0,
            notes=[
                sample_theory.NoteEvent(pitch_midi=60, start_beat=0.0, duration_beats=2.0),
                sample_theory.NoteEvent(pitch_midi=64, start_beat=2.0, duration_beats=2.0),
            ],
            program=0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            mid_path = Path(tmp) / "out.mid"
            sample_synthesis.write_midi(plan, path=mid_path)
            self.assertTrue(mid_path.is_file())
            pm = pretty_midi.PrettyMIDI(str(mid_path))
            self.assertEqual(len(pm.instruments), 1)
            self.assertEqual(len(pm.instruments[0].notes), 2)
            pitches = sorted(n.pitch for n in pm.instruments[0].notes)
            self.assertEqual(pitches, [60, 64])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
