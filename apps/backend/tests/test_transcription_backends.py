"""Transcription backend evaluation harness.

Generates synthetic audio test cases and runs TorchcrepeBackend
to verify note extraction quality.
"""

import importlib
import importlib.util
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

_TORCHCREPE_AVAILABLE = importlib.util.find_spec("torchcrepe") is not None


def _write_wav(path: str, samples: np.ndarray, sr: int = 44100) -> None:
    """Write a mono float32 array to a 16-bit WAV file."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _sine_tone(freq: float, duration: float, sr: int = 44100) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    return 0.8 * np.sin(2 * np.pi * freq * t)


@unittest.skipUnless(_TORCHCREPE_AVAILABLE, "torchcrepe not installed")
class TranscriptionBackendEvaluationTests(unittest.TestCase):
    """Synthetic audio tests for TorchcrepeBackend."""

    @classmethod
    def setUpClass(cls):
        cls.analyze = importlib.import_module("analyze")
        cls.sr = 44100

    def _run_backend(self, backend, wav_path: str) -> dict | None:
        result = backend.transcribe(wav_path, stem_paths=None)
        if isinstance(result, dict):
            return result.get("transcriptionDetail")
        return None

    def test_clean_bass_four_quarter_notes(self):
        """Four quarter notes at ~110 Hz (A2), 0.5s each with 0.1s gaps."""
        sr = self.sr
        silence = np.zeros(int(sr * 0.1), dtype=np.float32)
        notes = []
        for _ in range(4):
            notes.append(_sine_tone(110.0, 0.5, sr))
            notes.append(silence)
        audio = np.concatenate(notes)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            _write_wav(f.name, audio, sr)
            wav_path = f.name

        tc = self.analyze.TorchcrepeBackend()
        tc_result = self._run_backend(tc, wav_path)
        self.assertIsNotNone(tc_result, "TorchcrepeBackend should produce transcription")

    def test_torchcrepe_returns_notes(self):
        """TorchcrepeBackend should return at least one note for a clean tone."""
        sr = self.sr
        audio = _sine_tone(220.0, 2.0, sr)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            _write_wav(f.name, audio, sr)
            wav_path = f.name

        tc = self.analyze.TorchcrepeBackend()
        result = self._run_backend(tc, wav_path)
        self.assertIsNotNone(result)
        notes = result.get("notes", [])
        self.assertGreater(len(notes), 0, "Should detect at least one note")

    def test_polyphonic_two_simultaneous_notes(self):
        """Two simultaneous tones — tests how backend handles polyphony."""
        sr = self.sr
        a = _sine_tone(220.0, 1.0, sr)
        b = _sine_tone(330.0, 1.0, sr)
        audio = 0.5 * (a + b)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            _write_wav(f.name, audio, sr)
            wav_path = f.name

        tc = self.analyze.TorchcrepeBackend()
        tc_result = self._run_backend(tc, wav_path)
        self.assertIsNotNone(tc_result)


if __name__ == "__main__":
    unittest.main()
