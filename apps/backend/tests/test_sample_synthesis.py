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
        result = sample_synthesis.render_clip(plan, allow_soundfont_backends=False)
        expected_samples = int(round(2.0 * sample_synthesis.SAMPLE_RATE))  # 4 beats @ 120 = 2 s
        self.assertEqual(result.samples.shape, (expected_samples,))
        self.assertEqual(result.samples.dtype, np.float32)
        self.assertEqual(result.backend, "sine_fallback")
        self.assertIsNone(result.soundfont_path)

    def test_render_contains_energy_at_target_frequency(self) -> None:
        # A4 = MIDI 69 = 440 Hz exactly.
        plan = _single_note_plan(pitch=69, bpm=120.0, duration_beats=4.0)
        result = sample_synthesis.render_clip(plan, allow_soundfont_backends=False)

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
        result = sample_synthesis.render_clip(plan, allow_soundfont_backends=False)
        peak = float(np.max(np.abs(result.samples)))
        self.assertEqual(peak, 0.0)


class WriteWavTests(unittest.TestCase):
    def test_write_wav_round_trips(self) -> None:
        plan = _single_note_plan(pitch=60, bpm=120.0, duration_beats=2.0)
        result = sample_synthesis.render_clip(plan, allow_soundfont_backends=False)

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
        # Parity is layered:
        #   1. Library-independent: the bytes must start with a valid MThd
        #      header and contain at least one MTrk chunk. This catches the
        #      "writer emits something only its own reader can parse" failure
        #      mode that worried us when pretty_midi was dropped as the
        #      independent reader.
        #   2. Within-library: symusic.Score must read the file back as the
        #      same notes (pitch, onset, duration). Weaker than cross-library
        #      but still a real round-trip.
        import struct

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

            # Layer 1 — library-independent structural check.
            raw = mid_path.read_bytes()
            self.assertEqual(raw[:4], b"MThd", "Should start with MThd chunk")
            mthd_length = struct.unpack(">I", raw[4:8])[0]
            self.assertEqual(
                mthd_length, 6, "MThd content must be exactly 6 bytes per the MIDI spec"
            )
            self.assertIn(
                b"MTrk", raw, "Should contain at least one MTrk chunk"
            )

            # Layer 2 — symusic round-trip on the same bytes.
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
    """Pure-logic tests for `_resolve_backend` — no synthesis, no soundfont.

    Precedence under ``auto`` is *deliberately conservative*: FluidSynth wins
    when both importable and a soundfont is reachable, because operators with
    existing FluidSynth setups already have proven audio output and we don't
    have cross-backend parity evidence yet. Symusic is the auto fallback only
    when FluidSynth isn't importable; operators opt in explicitly via
    ``ASA_SAMPLE_SYNTH_BACKEND=symusic`` to get the faster Prestosynth path.
    """

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

    def test_auto_with_soundfont_and_fluidsynth_prefers_fluidsynth(self) -> None:
        # The conservative default — operators with a working FluidSynth keep
        # getting the same engine they had pre-campaign.
        with patch.object(sample_synthesis, "_FLUIDSYNTH_IMPORTABLE", True):
            result = self._resolve(env="auto", soundfont_path=Path("/tmp/fake.sf2"))
        self.assertEqual(result, "fluidsynth")

    def test_auto_with_soundfont_no_fluidsynth_uses_symusic(self) -> None:
        # Symusic backstops in auto only when FluidSynth isn't importable —
        # the new capability that wasn't reachable before this campaign.
        with patch.object(sample_synthesis, "_FLUIDSYNTH_IMPORTABLE", False):
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

    def test_explicit_symusic_overrides_fluidsynth_preference(self) -> None:
        # Explicit opt-in: operator has measured parity locally and wants the
        # faster Prestosynth path even when FluidSynth would otherwise win.
        with patch.object(sample_synthesis, "_FLUIDSYNTH_IMPORTABLE", True):
            result = self._resolve(
                env="symusic", soundfont_path=Path("/tmp/fake.sf2")
            )
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
        # The caller-side escape hatch (used by tests) — even with a
        # soundfont and a hardcoded env override, ``allow_soundfont_backends
        # =False`` forces the deterministic sine backend.
        result = self._resolve(
            env="symusic",
            soundfont_path=Path("/tmp/fake.sf2"),
            allow_soundfont_backends=False,
        )
        self.assertEqual(result, "sine_fallback")

    def test_unknown_env_value_falls_back_to_auto(self) -> None:
        # Robustness: a typo or misconfiguration shouldn't break rendering.
        # The module logs a warning and treats the value as "auto", which
        # then resolves to FluidSynth-first when both backends could run.
        with patch.object(sample_synthesis, "_FLUIDSYNTH_IMPORTABLE", True):
            result = self._resolve(env="bogus", soundfont_path=Path("/tmp/fake.sf2"))
        self.assertEqual(result, "fluidsynth")


class SymusicRenderPathTests(unittest.TestCase):
    """Coverage for ``_render_with_symusic_synth`` itself, not just dispatch.

    The mocked tests verify the function builds the right Score and dispatches
    to ``symusic.Synthesizer`` with the documented arguments — runs everywhere.
    The integration test actually invokes the Prestosynth render; it's skipped
    when no SF2/SF3 is reachable so CI without a system soundfont stays green.
    """

    def test_render_with_symusic_synth_builds_score_and_returns_mono_float32(self) -> None:
        plan = _single_note_plan(pitch=60, bpm=120.0, duration_beats=2.0)
        sf_path = Path("/tmp/fake.sf2")
        expected_samples = int(round(2 * 60 / 120 * sample_synthesis.SAMPLE_RATE))
        mock_synth = unittest.mock.MagicMock()
        mock_synth.render.return_value = np.zeros(expected_samples, dtype=np.float32)

        with patch.object(
            sample_synthesis, "Synthesizer", return_value=mock_synth
        ) as mock_factory:
            result = sample_synthesis._render_with_symusic_synth(plan, sf_path)

        # The factory must receive the soundfont path + the canonical sample
        # rate. quality=0 is the documented default but pinned here so a
        # silent drift in the call surface still fails the test.
        mock_factory.assert_called_once()
        call = mock_factory.call_args
        self.assertEqual(call.args[0], str(sf_path))
        self.assertEqual(call.kwargs.get("sample_rate"), sample_synthesis.SAMPLE_RATE)
        self.assertEqual(call.kwargs.get("quality"), 0)

        # render() receives the built Score positionally; stereo=False is the
        # contract that yields a 1D buffer (no axis-reduction guesswork).
        mock_synth.render.assert_called_once()
        render_call = mock_synth.render.call_args
        score_arg = render_call.args[0]
        self.assertEqual(len(score_arg.tracks), 1)
        self.assertEqual(len(score_arg.tracks[0].notes), 1)
        self.assertEqual(int(score_arg.tracks[0].notes[0].pitch), 60)
        self.assertEqual(render_call.kwargs.get("stereo"), False)

        # Result shape — float32 mono at the canonical sample rate.
        self.assertEqual(result.backend, "symusic")
        self.assertEqual(result.sample_rate, sample_synthesis.SAMPLE_RATE)
        self.assertEqual(result.samples.dtype, np.float32)
        self.assertEqual(result.samples.ndim, 1)
        self.assertEqual(result.samples.shape[0], expected_samples)
        self.assertEqual(result.soundfont_path, str(sf_path))

    def test_render_with_symusic_synth_reduces_stereo_to_mono(self) -> None:
        # Defensive path: if a future symusic version returns 2D (stereo),
        # the wrapper still hands the caller a 1D mono float32.
        plan = _single_note_plan(pitch=60, bpm=120.0, duration_beats=1.0)
        sf_path = Path("/tmp/fake.sf2")
        expected_samples = int(round(1 * 60 / 120 * sample_synthesis.SAMPLE_RATE))
        # Shape (channels=2, samples) — typical interleaved-then-deinterleaved
        # layout. Both channels carry the same signal so the mono should match.
        stereo_buffer = np.full((2, expected_samples), 0.25, dtype=np.float32)
        mock_synth = unittest.mock.MagicMock()
        mock_synth.render.return_value = stereo_buffer

        with patch.object(sample_synthesis, "Synthesizer", return_value=mock_synth):
            result = sample_synthesis._render_with_symusic_synth(plan, sf_path)

        self.assertEqual(result.samples.ndim, 1)
        self.assertEqual(result.samples.shape[0], expected_samples)
        self.assertTrue(np.allclose(result.samples, 0.25))

    @unittest.skipUnless(
        sample_synthesis.locate_soundfont() is not None,
        "No SF2/SF3 soundfont reachable; set SONIC_ANALYZER_SOUNDFONT to enable.",
    )
    def test_symusic_synth_produces_nonzero_audio_with_real_soundfont(self) -> None:
        # Integration: the only assertion the audible-output story rests on
        # in actual practice. Skipped when no soundfont is on disk; runs
        # locally for any maintainer with SONIC_ANALYZER_SOUNDFONT set.
        plan = _single_note_plan(pitch=60, bpm=120.0, duration_beats=1.0)
        sf_path = sample_synthesis.locate_soundfont()
        assert sf_path is not None  # narrowing for type-checkers

        result = sample_synthesis._render_with_symusic_synth(plan, sf_path)
        self.assertEqual(result.backend, "symusic")
        self.assertEqual(result.sample_rate, sample_synthesis.SAMPLE_RATE)
        self.assertEqual(result.samples.dtype, np.float32)
        self.assertEqual(result.samples.ndim, 1)
        rms = float(np.sqrt(np.mean(result.samples**2)))
        self.assertGreater(
            rms, 1e-4, "A single sustained note should produce nonzero RMS"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
