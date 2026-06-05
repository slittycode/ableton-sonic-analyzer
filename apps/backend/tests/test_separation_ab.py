"""Focused tests for the ground-truth reference-set logic in separation_ab.

Research-only harness, but the new SI-SDR aggregation math and the on-disk
MUSDB-style loader carry real logic worth pinning. These tests need only numpy +
the stdlib ``wave`` writer the harness already uses — no torch, no Demucs, no
MSST install.
"""

from __future__ import annotations

import os
import tempfile
import unittest

import numpy as np

import separation_ab as sab


def _write_wav(path: str, mono: np.ndarray) -> None:
    sab._write_stereo_wav(path, np.asarray(mono, dtype=np.float32))


class LoadReferenceTrackTests(unittest.TestCase):
    def test_loads_mixture_and_present_stems(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            track = os.path.join(root, "Some - Track")
            os.makedirs(track)
            n = sab.SAMPLE_RATE  # 1 second
            _write_wav(os.path.join(track, "mixture.wav"), np.zeros(n))
            _write_wav(os.path.join(track, "vocals.wav"), 0.3 * np.ones(n))
            _write_wav(os.path.join(track, "bass.wav"), -0.2 * np.ones(n))
            # drums/other deliberately absent — must be skipped, not invented.

            loaded = sab._load_reference_track(track)
            self.assertIsNotNone(loaded)
            mixture_path, known = loaded
            self.assertTrue(mixture_path.endswith("mixture.wav"))
            self.assertEqual(set(known), {"vocals", "bass"})
            self.assertEqual(len(known["vocals"]), n)

    def test_returns_none_without_mixture(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            track = os.path.join(root, "no_mix")
            os.makedirs(track)
            _write_wav(os.path.join(track, "vocals.wav"), np.ones(sab.SAMPLE_RATE))
            self.assertIsNone(sab._load_reference_track(track))

    def test_returns_none_without_any_stems(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            track = os.path.join(root, "mix_only")
            os.makedirs(track)
            _write_wav(os.path.join(track, "mixture.wav"), np.ones(sab.SAMPLE_RATE))
            self.assertIsNone(sab._load_reference_track(track))


class AggregateReferenceTests(unittest.TestCase):
    def test_means_over_completed_tracks_only(self) -> None:
        tracks = [
            {
                "track": "t1",
                "perBackend": {
                    "demucs": {
                        "status": "completed",
                        "runtimeSeconds": 10.0,
                        "quality": {
                            "vocals": {"siSdrDb": 6.0, "present": True},
                            "bass": {"siSdrDb": 4.0, "present": True},
                            "meanSiSdrDb": 5.0,
                        },
                    },
                    "msst": {"status": "skipped_no_msst"},
                },
            },
            {
                "track": "t2",
                "perBackend": {
                    "demucs": {
                        "status": "completed",
                        "runtimeSeconds": 20.0,
                        "quality": {
                            "vocals": {"siSdrDb": 8.0, "present": True},
                            "bass": {"siSdrDb": 6.0, "present": True},
                            "meanSiSdrDb": 7.0,
                        },
                    },
                    "msst": {"status": "error", "error": "boom"},
                },
            },
        ]
        agg = sab._aggregate_reference(tracks)
        self.assertEqual(agg["demucs"]["meanSiSdrDb"], 6.0)  # mean(5,7)
        self.assertEqual(agg["demucs"]["meanRuntimeSeconds"], 15.0)  # mean(10,20)
        self.assertEqual(agg["demucs"]["tracksScored"], 2)
        self.assertEqual(agg["demucs"]["perStemMeanSiSdrDb"]["vocals"], 7.0)  # mean(6,8)
        self.assertEqual(agg["demucs"]["perStemMeanSiSdrDb"]["bass"], 5.0)  # mean(4,6)
        self.assertIsNone(agg["demucs"]["perStemMeanSiSdrDb"]["drums"])  # never scored
        # MSST never completed → all-None aggregate, zero tracksScored.
        self.assertIsNone(agg["msst"]["meanSiSdrDb"])
        self.assertEqual(agg["msst"]["tracksScored"], 0)

    def test_perfect_estimate_scores_high_sdr(self) -> None:
        # Sanity: scoring a stem against itself yields a high (finite or inf) SI-SDR.
        ref = np.sin(np.linspace(0, 50, sab.SAMPLE_RATE)).astype(np.float32)
        self.assertGreater(sab.si_sdr(ref, ref), 100.0)


if __name__ == "__main__":
    unittest.main()
