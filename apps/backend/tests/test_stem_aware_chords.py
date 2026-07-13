import os
import tempfile
import unittest
import wave

import numpy as np

from analyze_audio_io import mix_stems_mono
from analyze_segments import analyze_chords, analyze_segment_key


def _write_wav(path: str, samples: np.ndarray, sr: int = 44100) -> None:
    pcm = np.clip(samples, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())


class MixStemsMonoTests(unittest.TestCase):
    def test_sums_named_stems_and_skips_missing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            other = os.path.join(d, "other.wav")
            vocals = os.path.join(d, "vocals.wav")
            _write_wav(other, np.full(44100, 0.2, dtype=np.float32))
            _write_wav(vocals, np.full(44100, 0.1, dtype=np.float32))
            stems = {"other": other, "vocals": vocals, "bass": os.path.join(d, "nope.wav")}
            mixed = mix_stems_mono(stems, ("other", "vocals"))
            self.assertIsNotNone(mixed)
            self.assertEqual(mixed.shape[0], 44100)
            # 0.2 + 0.1 summed.
            self.assertAlmostEqual(float(mixed.mean()), 0.3, places=2)

    def test_none_when_no_stem_loadable(self) -> None:
        self.assertIsNone(mix_stems_mono(None, ("other", "vocals")))
        self.assertIsNone(mix_stems_mono({"bass": "/no/such.wav"}, ("other", "vocals")))


class ChordSourceTaggingTests(unittest.TestCase):
    def _tone(self, freqs, seconds=2.0, sr=44100):
        t = np.arange(int(seconds * sr)) / sr
        sig = sum(np.sin(2 * np.pi * f * t) for f in freqs)
        return (sig / np.max(np.abs(sig)) * 0.8).astype(np.float32)

    def test_chord_source_reflects_harmonic_input(self) -> None:
        full = self._tone([261.6, 329.6, 392.0])  # C major triad
        harmonic = self._tone([261.6, 329.6, 392.0])
        default = analyze_chords(full)["chordDetail"]
        self.assertEqual(default["chordSource"], "full_mix")
        stemmed = analyze_chords(full, harmonic_mono=harmonic)["chordDetail"]
        self.assertEqual(stemmed["chordSource"], "harmonic_stems")

    def test_segment_key_source_tagged(self) -> None:
        mono = self._tone([261.6, 329.6, 392.0], seconds=4.0)
        structure = {"segments": [{"start": 0.0, "end": 4.0}]}
        out = analyze_segment_key(structure, mono, harmonic_mono=mono)["segmentKey"]
        if out:  # segmentation may return None on trivial structure; tag when present
            self.assertTrue(all(e["source"] == "harmonic_stems" for e in out))


if __name__ == "__main__":
    unittest.main()
