"""End-to-end audio-content tests for audition sample generation.

The other sample test modules verify the *plan* (correct MIDI numbers) and
the *primitives* (a single note renders at the right pitch; a kick lands on
its fundamental). They do not verify that the *orchestrated WAV files written
to disk* actually contain audio that reflects the Phase 1 input.

This module closes that loop. It runs the real orchestrator, loads the WAVs
it wrote, runs an FFT, and asserts on spectral content. It is the answer to
"how do we know it's generating anything of value?"

The load-bearing test is `test_different_keys_produce_different_audio`: it
proves the generator is *responsive* to its input rather than emitting a
canned clip. If sample generation ever regresses to fixed output — or stops
threading the measured key through to the render — that test fails.

Runs against the sine-additive fallback (`prefer_fluidsynth=False`) so the
assertions are deterministic and don't depend on a system soundfont.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sample_generation  # noqa: E402


# --- Spectral helpers ------------------------------------------------------- #


def _midi_to_freq(midi: int) -> float:
    """Equal-tempered frequency for a MIDI note. A4 (69) = 440 Hz."""
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def _fft_magnitude(samples: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    """Hann-windowed magnitude spectrum. Hann keeps spectral leakage low so a
    non-chord-tone band reads as genuine near-silence, not smeared neighbors."""
    mono = np.asarray(samples, dtype=np.float64)
    if mono.ndim > 1:
        mono = mono.mean(axis=1)
    window = np.hanning(mono.size)
    spectrum = np.abs(np.fft.rfft(mono * window))
    freqs = np.fft.rfftfreq(mono.size, d=1.0 / sample_rate)
    return freqs, spectrum


def _energy_near(
    samples: np.ndarray, sample_rate: int, target_hz: float, tolerance_hz: float = 6.0
) -> float:
    """Summed spectral magnitude in a narrow band around target_hz."""
    freqs, spectrum = _fft_magnitude(samples, sample_rate)
    band = (freqs >= target_hz - tolerance_hz) & (freqs <= target_hz + tolerance_hz)
    return float(np.sum(spectrum[band]))


def _dominant_freq(samples: np.ndarray, sample_rate: int) -> float:
    """Frequency of the single strongest spectral bin."""
    freqs, spectrum = _fft_magnitude(samples, sample_rate)
    return float(freqs[int(np.argmax(spectrum))])


def _load_wav(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(str(path))
    return np.asarray(audio, dtype=np.float64), int(sample_rate)


def _phase1(
    *, key: str = "C major", key_confidence: float = 0.85, kick_hz: float = 60.0
) -> dict:
    return {
        "bpm": 120.0,
        "bpmConfidence": 0.9,
        "key": key,
        "keyConfidence": key_confidence,
        "kickDetail": {
            "fundamentalHz": kick_hz,
            "decayTimeMs": 220.0,
            "confidence": 0.8,
        },
    }


def _generate(tmp: str, phase1: dict, **kwargs) -> Path:
    sample_generation.generate_samples(
        run_id="audio-content-test",
        phase1=phase1,
        phase2=None,
        output_dir=Path(tmp),
        prefer_fluidsynth=False,
        **kwargs,
    )
    return Path(tmp)


class ChordProgressionAudioTests(unittest.TestCase):
    def test_c_major_chord_audio_contains_the_triad(self) -> None:
        # The first chord of the I-vi-IV-V progression is the tonic triad,
        # occupying beats 0-8 = the first 4 s at 120 BPM. FFT a steady-state
        # window inside that span to dodge the ADSR envelope edges.
        with tempfile.TemporaryDirectory() as tmp:
            out = _generate(tmp, _phase1(key="C major"))
            audio, sr = _load_wav(out / "tonal_chord_progression.wav")
            window = audio[int(1.0 * sr) : int(3.0 * sr)]

            c4 = _energy_near(window, sr, _midi_to_freq(60))  # C4 261.6 Hz
            e4 = _energy_near(window, sr, _midi_to_freq(64))  # E4 329.6 Hz
            g4 = _energy_near(window, sr, _midi_to_freq(67))  # G4 392.0 Hz
            cs4 = _energy_near(window, sr, _midi_to_freq(61))  # C#4 — NOT in C major

            # All three chord tones carry real energy.
            self.assertGreater(c4, 0.0)
            self.assertGreater(e4, 0.0)
            self.assertGreater(g4, 0.0)
            # And the weakest chord tone still dwarfs a non-chord tone — i.e.
            # the audio is in the key, not just noise that happens to be loud.
            self.assertGreater(min(c4, e4, g4), cs4 * 20.0)

    def test_bass_root_audio_sits_on_the_tonic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = _generate(tmp, _phase1(key="C major"))
            audio, sr = _load_wav(out / "tonal_bass_root.wav")
            window = audio[int(1.0 * sr) : int(3.0 * sr)]
            # Bass root for C major is C2 = MIDI 36 ≈ 65.4 Hz.
            self.assertAlmostEqual(
                _dominant_freq(window, sr), _midi_to_freq(36), delta=4.0
            )

    def test_different_keys_produce_different_audio(self) -> None:
        # The "is it generating anything of value" test: prove the render is
        # driven by the measured key, not a fixed clip. C natural belongs to
        # the C-major triad and is absent from the F#-minor triad; F# is the
        # mirror image. Each note must be loud in its own key and near-silent
        # in the other.
        with tempfile.TemporaryDirectory() as tmp_c, tempfile.TemporaryDirectory() as tmp_fs:
            c_out = _generate(tmp_c, _phase1(key="C major"))
            fs_out = _generate(tmp_fs, _phase1(key="F# minor"))

            c_audio, sr = _load_wav(c_out / "tonal_chord_progression.wav")
            fs_audio, _ = _load_wav(fs_out / "tonal_chord_progression.wav")
            c_window = c_audio[int(1.0 * sr) : int(3.0 * sr)]
            fs_window = fs_audio[int(1.0 * sr) : int(3.0 * sr)]

            # Sanity: the two clips are not the same audio.
            self.assertNotEqual(c_audio.tobytes(), fs_audio.tobytes())

            # C natural (MIDI 60): in the C-major triad, not in F# minor's.
            c_nat_in_cmaj = _energy_near(c_window, sr, _midi_to_freq(60))
            c_nat_in_fsmin = _energy_near(fs_window, sr, _midi_to_freq(60))
            self.assertGreater(c_nat_in_cmaj, c_nat_in_fsmin * 20.0)

            # F# (MIDI 66): in the F#-minor triad, not in C major's.
            fs_in_fsmin = _energy_near(fs_window, sr, _midi_to_freq(66))
            fs_in_cmaj = _energy_near(c_window, sr, _midi_to_freq(66))
            self.assertGreater(fs_in_fsmin, fs_in_cmaj * 20.0)


class KickAudioTests(unittest.TestCase):
    def test_orchestrated_kick_lands_on_measured_fundamental(self) -> None:
        # Extends test_sample_drums (which tests synth_kick directly) through
        # the full orchestrator + disk round-trip: the kick WAV the endpoint
        # would serve actually sits on the measured kickDetail.fundamentalHz.
        with tempfile.TemporaryDirectory() as tmp:
            out = _generate(tmp, _phase1(kick_hz=72.0))
            audio, sr = _load_wav(out / "drum_kick.wav")
            # Skip the first 150 ms — the pitch envelope sweeps an octave down
            # before settling on the fundamental.
            steady = audio[int(0.15 * sr) :]
            self.assertAlmostEqual(_dominant_freq(steady, sr), 72.0, delta=20.0)

    def test_kick_fundamental_tracks_the_measurement(self) -> None:
        # Two different measured fundamentals must yield two different kicks.
        with tempfile.TemporaryDirectory() as tmp_low, tempfile.TemporaryDirectory() as tmp_high:
            low_out = _generate(tmp_low, _phase1(kick_hz=45.0))
            high_out = _generate(tmp_high, _phase1(kick_hz=95.0))
            low_audio, sr = _load_wav(low_out / "drum_kick.wav")
            high_audio, _ = _load_wav(high_out / "drum_kick.wav")
            low_peak = _dominant_freq(low_audio[int(0.15 * sr) :], sr)
            high_peak = _dominant_freq(high_audio[int(0.15 * sr) :], sr)
            # The 45 Hz kick must be audibly lower than the 95 Hz kick.
            self.assertLess(low_peak, high_peak)
            self.assertAlmostEqual(low_peak, 45.0, delta=20.0)
            self.assertAlmostEqual(high_peak, 95.0, delta=20.0)


class MelodyAudioTests(unittest.TestCase):
    def test_melody_follows_scale_degree_hints(self) -> None:
        # Hints [1, 5] in C major => scale degrees 1 then 5 => C5 then G5.
        # The rendered melody must actually play those two pitches in order.
        with tempfile.TemporaryDirectory() as tmp:
            out = _generate(tmp, _phase1(key="C major"), pitch_note_hints=[1, 5])
            audio, sr = _load_wav(out / "melody_lead.wav")

            # 2 notes over 4 bars at 120 BPM => each note gets an 8-beat (4 s)
            # slot. The 0.85 note-length gate means note 0 *sounds* ~0-3.4 s
            # and note 1 ~4-7.4 s (each followed by a short gap). Sample
            # comfortably inside each sounding span.
            first_note = audio[int(0.5 * sr) : int(3.0 * sr)]
            second_note = audio[int(4.5 * sr) : int(7.0 * sr)]

            self.assertAlmostEqual(
                _dominant_freq(first_note, sr), _midi_to_freq(72), delta=8.0
            )  # C5
            self.assertAlmostEqual(
                _dominant_freq(second_note, sr), _midi_to_freq(79), delta=10.0
            )  # G5

            # And the phrase ascends — degree 5 is above degree 1.
            self.assertLess(
                _dominant_freq(first_note, sr), _dominant_freq(second_note, sr)
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
