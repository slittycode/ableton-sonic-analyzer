"""Tests for the MIDI-plan → WAV/MIDI synthesis layer.

The sine fallback path is the one exercised by audio-level tests; the
FluidSynth and symusic.Synthesizer paths require a system soundfont, which
we don't assume is present in CI. The fallback is the everywhere-available
backstop and must stay correct.

BackendResolutionTests covers the env-flag dispatch logic in pure isolation —
no synthesis, no soundfont, just verifying that
``_resolve_backend`` picks the right path under each combination of env
override + soundfont availability + ``allow_soundfont_backends`` flag.
"""

import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

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
        # Round-trips via symusic itself (pretty_midi was dropped in PR-G).
        # The parity contract here is weaker than cross-library — it proves
        # symusic can read its own output — but it still verifies the file
        # is a valid Standard MIDI file and the notes survive the trip.
        from symusic import Score

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
            loaded = Score(mid_path).to("Second")
            self.assertEqual(len(loaded.tracks), 1)
            notes = sorted(loaded.tracks[0].notes, key=lambda n: n.time)
            self.assertEqual(len(notes), 2)
            self.assertEqual([int(n.pitch) for n in notes], [60, 64])
            # Onsets at beats 0 and 2 → 0.0 s and 1.0 s at 120 BPM.
            self.assertAlmostEqual(float(notes[0].time), 0.0, places=3)
            self.assertAlmostEqual(float(notes[1].time), 1.0, places=3)
            # Both notes last 2 beats → 1.0 s at 120 BPM.
            self.assertAlmostEqual(float(notes[0].duration), 1.0, places=3)
            self.assertAlmostEqual(float(notes[1].duration), 1.0, places=3)


class BackendResolutionTests(unittest.TestCase):
    """Pure-logic tests for `_resolve_backend` — no synthesis, no soundfont."""

    def _resolve(
        self,
        *,
        env: str | None = None,
        soundfont_path: Path | None = None,
        allow_soundfont_backends: bool = True,
    ) -> str:
        env_dict = {} if env is None else {sample_synthesis._BACKEND_ENV_VAR: env}
        with patch.dict(os.environ, env_dict, clear=False):
            if env is None:
                os.environ.pop(sample_synthesis._BACKEND_ENV_VAR, None)
            return sample_synthesis._resolve_backend(
                soundfont_path=soundfont_path,
                allow_soundfont_backends=allow_soundfont_backends,
            )

    def test_auto_with_soundfont_prefers_symusic(self) -> None:
        # symusic outranks FluidSynth in auto mode — same MIDI library used
        # everywhere else on the backend.
        result = self._resolve(env="auto", soundfont_path=Path("/tmp/fake.sf2"))
        self.assertEqual(result, "symusic")

    def test_auto_without_soundfont_falls_through_to_sine(self) -> None:
        result = self._resolve(env="auto", soundfont_path=None)
        self.assertEqual(result, "sine_fallback")

    def test_explicit_sine_always_wins(self) -> None:
        # Even with a soundfont, ``ASA_SAMPLE_SYNTH_BACKEND=sine`` forces the
        # deterministic path — the documented escape hatch.
        result = self._resolve(env="sine", soundfont_path=Path("/tmp/fake.sf2"))
        self.assertEqual(result, "sine_fallback")

    def test_explicit_symusic_with_soundfont(self) -> None:
        result = self._resolve(env="symusic", soundfont_path=Path("/tmp/fake.sf2"))
        self.assertEqual(result, "symusic")

    def test_explicit_symusic_without_soundfont_degrades(self) -> None:
        # Refusing to auto-download a built-in SF3 is deliberate — that's a
        # network call on the request path and could silently fail in
        # hosted-mode workers.
        result = self._resolve(env="symusic", soundfont_path=None)
        self.assertEqual(result, "sine_fallback")

    def test_explicit_fluidsynth_requires_both_binding_and_soundfont(self) -> None:
        with patch.object(sample_synthesis, "_FLUIDSYNTH_IMPORTABLE", False):
            result = self._resolve(
                env="fluidsynth", soundfont_path=Path("/tmp/fake.sf2")
            )
        self.assertEqual(result, "sine_fallback")

        with patch.object(sample_synthesis, "_FLUIDSYNTH_IMPORTABLE", True):
            result = self._resolve(
                env="fluidsynth", soundfont_path=Path("/tmp/fake.sf2")
            )
            self.assertEqual(result, "fluidsynth")

    def test_allow_soundfont_false_forces_sine(self) -> None:
        # The ``prefer_fluidsynth=False`` kwarg path that the existing tests
        # rely on — even with a soundfont and a hardcoded env override, the
        # caller can force the deterministic sine backend.
        result = self._resolve(
            env="symusic",
            soundfont_path=Path("/tmp/fake.sf2"),
            allow_soundfont_backends=False,
        )
        self.assertEqual(result, "sine_fallback")

    def test_unknown_env_value_falls_back_to_auto(self) -> None:
        # Robustness: a typo or misconfiguration shouldn't break rendering.
        # The module logs a warning and treats the value as "auto".
        result = self._resolve(env="bogus", soundfont_path=Path("/tmp/fake.sf2"))
        self.assertEqual(result, "symusic")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
