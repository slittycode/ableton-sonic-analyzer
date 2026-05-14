"""Tests for the NumPy drum-synthesis layer.

The kick test is the load-bearing one: it verifies that a measured
`fundamentalHz` actually shows up as the dominant spectral energy in the
rendered audio. If this regresses, the audition lies about what the
measurement says.
"""

import sys
import unittest
from pathlib import Path

import numpy as np

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sample_drums  # noqa: E402


class KickTests(unittest.TestCase):
    def test_kick_fft_peak_lands_near_fundamental(self) -> None:
        # Use 80 Hz so the peak sits in a region with enough FFT resolution.
        kick = sample_drums.synth_kick(fundamental_hz=80.0, decay_time_ms=250.0)
        # Look at the steady-state portion (after the initial pitch sweep).
        steady_start = int(0.05 * kick.sample_rate)
        steady_segment = kick.samples[steady_start:].astype(np.float64)
        spectrum = np.abs(np.fft.rfft(steady_segment))
        freqs = np.fft.rfftfreq(steady_segment.size, d=1.0 / kick.sample_rate)
        peak_freq = float(freqs[int(np.argmax(spectrum))])
        # Generous tolerance: the pitch envelope means peak energy can sit a
        # little above the fundamental in the first ~30 ms.
        self.assertAlmostEqual(peak_freq, 80.0, delta=20.0)

    def test_kick_obeys_decay_envelope(self) -> None:
        kick = sample_drums.synth_kick(fundamental_hz=55.0, decay_time_ms=150.0)
        # Tail amplitude should be substantially lower than head amplitude.
        head_rms = float(np.sqrt(np.mean(kick.samples[:1000] ** 2)))
        tail_rms = float(
            np.sqrt(np.mean(kick.samples[-1000:] ** 2))
        )
        self.assertGreater(head_rms, tail_rms * 5.0)

    def test_kick_rejects_negative_fundamental(self) -> None:
        with self.assertRaises(ValueError):
            sample_drums.synth_kick(fundamental_hz=-1.0)


class SnareTests(unittest.TestCase):
    def test_snare_is_well_formed(self) -> None:
        snare = sample_drums.synth_snare()
        self.assertEqual(snare.sample_rate, sample_drums.SAMPLE_RATE)
        self.assertEqual(snare.samples.dtype, np.float32)
        # Within [-1, 1] after normalization.
        self.assertLessEqual(float(np.max(np.abs(snare.samples))), 1.0)
        # Non-silent.
        self.assertGreater(
            float(np.sqrt(np.mean(snare.samples.astype(np.float64) ** 2))), 0.01
        )


class HatTests(unittest.TestCase):
    def test_hat_is_short_and_non_silent(self) -> None:
        hat = sample_drums.synth_hat()
        self.assertLess(hat.duration_seconds, 0.3)
        self.assertGreater(
            float(np.sqrt(np.mean(hat.samples.astype(np.float64) ** 2))), 0.005
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
