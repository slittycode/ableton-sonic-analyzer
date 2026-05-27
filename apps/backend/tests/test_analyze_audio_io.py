"""Unit tests for ``analyze_audio_io`` — audio loading and stem helpers.

The full surface (``load_mono``, ``load_stereo``, ``separate_stems``,
``analyze_crepe_pitch``) depends on heavy optional dependencies: Essentia,
torchaudio, soundfile, torchcrepe. These tests focus on the **always-available
contract**: helper paths that must work without those deps, and graceful-degradation
contracts that callers (``analyze.py``) rely on.

Specifically:
- ``_write_wav_pcm16`` produces a valid PCM16 WAV with the expected channels and
  sample rate (this is the producer side of the Demucs round-trip).
- ``_load_stem_mono`` / ``_load_stem_stereo`` return ``None`` for missing /
  invalid stems instead of raising — downstream detectors rely on this.
- ``cleanup_stems`` is safe for ``None``, empty dicts, and missing files.
- ``analyze_crepe_pitch`` returns the documented null-shape envelope when no
  stems are provided.

Tests that require Essentia / torchaudio / torchcrepe are skipped when the
import fails — they will run in the real backend venv.
"""

import importlib.util
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# Import analyze_audio_io directly. It guards its essentia import with
# try/except so the module loads even when essentia is missing — the
# essentia-using helpers will fail on call rather than at import time.
_AAIO_PATH = _BACKEND_ROOT / "analyze_audio_io.py"
_AAIO_SPEC = importlib.util.spec_from_file_location("analyze_audio_io_test", _AAIO_PATH)
if _AAIO_SPEC is None or _AAIO_SPEC.loader is None:
    raise AssertionError("Could not load analyze_audio_io.py")
analyze_audio_io = importlib.util.module_from_spec(_AAIO_SPEC)
_AAIO_SPEC.loader.exec_module(analyze_audio_io)


_ESSENTIA_AVAILABLE = analyze_audio_io.es is not None


class WriteWavPcm16Tests(unittest.TestCase):
    """``_write_wav_pcm16`` is the writer Demucs uses to persist separated
    stems. Downstream loaders depend on the exact PCM16 format. A regression
    here breaks the whole Demucs round-trip."""

    def test_mono_signal_writes_mono_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mono.wav")
            sr = 44100
            sig = 0.3 * np.sin(2 * np.pi * 440 * np.arange(sr) / sr).astype(np.float32)
            analyze_audio_io._write_wav_pcm16(path, sig, sr)
            with wave.open(path, "rb") as wf:
                self.assertEqual(wf.getnchannels(), 1)
                self.assertEqual(wf.getsampwidth(), 2)  # PCM16
                self.assertEqual(wf.getframerate(), sr)
                self.assertEqual(wf.getnframes(), sr)

    def test_stereo_signal_writes_two_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "stereo.wav")
            sr = 44100
            n = sr // 2
            t = np.arange(n) / sr
            left = 0.3 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
            right = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
            stereo = np.stack([left, right])  # shape (2, N)
            analyze_audio_io._write_wav_pcm16(path, stereo, sr)
            with wave.open(path, "rb") as wf:
                self.assertEqual(wf.getnchannels(), 2)
                self.assertEqual(wf.getnframes(), n)

    def test_writes_to_specified_sample_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            for sr in (44100, 48000, 22050):
                path = os.path.join(tmp, f"sr_{sr}.wav")
                sig = np.zeros(100, dtype=np.float32)
                analyze_audio_io._write_wav_pcm16(path, sig, sr)
                with wave.open(path, "rb") as wf:
                    self.assertEqual(wf.getframerate(), sr)

    def test_clips_out_of_range_amplitude(self):
        """``_write_wav_pcm16`` clips to [-1, 1] before scaling — feeding it a
        signal that exceeds full-scale must not wrap or NaN-out the output."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "clip.wav")
            sr = 44100
            # +3.0 must clip to +1.0, then scale to int16 max (~32767).
            sig = np.full(sr, 3.0, dtype=np.float32)
            analyze_audio_io._write_wav_pcm16(path, sig, sr)
            with wave.open(path, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16)
            # All samples should be saturated at +32767 (the int16 max).
            self.assertEqual(int(samples.max()), 32767)
            self.assertEqual(int(samples.min()), 32767)


class LoadStemMonoTests(unittest.TestCase):
    """``_load_stem_mono`` is called by every per-stem detector. It must
    return ``None`` gracefully when the stem is unavailable rather than
    raising — the detector path treats ``None`` as 'no stem' and falls back
    to the full mix."""

    def test_returns_none_for_none_stems(self):
        self.assertIsNone(analyze_audio_io._load_stem_mono(None, "drums"))

    def test_returns_none_for_non_dict_stems(self):
        self.assertIsNone(analyze_audio_io._load_stem_mono("not-a-dict", "drums"))  # type: ignore[arg-type]
        self.assertIsNone(analyze_audio_io._load_stem_mono([], "drums"))  # type: ignore[arg-type]

    def test_returns_none_for_missing_stem_name(self):
        stems = {"vocals": "/some/path.wav"}
        self.assertIsNone(analyze_audio_io._load_stem_mono(stems, "drums"))

    def test_returns_none_when_path_is_not_string(self):
        stems = {"drums": 123}  # type: ignore[dict-item]
        self.assertIsNone(analyze_audio_io._load_stem_mono(stems, "drums"))

    def test_returns_none_when_file_does_not_exist(self):
        stems = {"drums": "/nonexistent/path/to/drums.wav"}
        self.assertIsNone(analyze_audio_io._load_stem_mono(stems, "drums"))


class LoadStemStereoTests(unittest.TestCase):
    """``_load_stem_stereo`` mirrors the mono variant — same null-safe
    contract for stereo loudness / stereo-width detectors."""

    def test_returns_none_for_none_stems(self):
        self.assertIsNone(analyze_audio_io._load_stem_stereo(None, "drums"))

    def test_returns_none_for_non_dict_stems(self):
        self.assertIsNone(analyze_audio_io._load_stem_stereo([], "vocals"))  # type: ignore[arg-type]

    def test_returns_none_when_path_invalid_or_missing(self):
        self.assertIsNone(analyze_audio_io._load_stem_stereo({"vocals": ""}, "vocals"))
        self.assertIsNone(
            analyze_audio_io._load_stem_stereo({"vocals": "/no/such/file.wav"}, "vocals"),
        )


class CleanupStemsTests(unittest.TestCase):
    def test_none_input_is_safe(self):
        analyze_audio_io.cleanup_stems(None)  # must not raise

    def test_empty_dict_is_safe(self):
        analyze_audio_io.cleanup_stems({})  # must not raise

    def test_non_string_paths_are_skipped(self):
        # Non-string values must not raise — the comprehension filters them.
        analyze_audio_io.cleanup_stems({"vocals": None, "drums": 123})  # type: ignore[dict-item]

    def test_removes_existing_stem_files(self):
        with tempfile.TemporaryDirectory(prefix="sonic_analyzer_demucs_") as tmp:
            vocal_path = os.path.join(tmp, "vocals.wav")
            drum_path = os.path.join(tmp, "drums.wav")
            for p in (vocal_path, drum_path):
                Path(p).write_bytes(b"fake-wav")
                self.assertTrue(os.path.exists(p))

            analyze_audio_io.cleanup_stems({"vocals": vocal_path, "drums": drum_path})

            # Both files removed, and since the parent dir matched the
            # ``sonic_analyzer_demucs_`` prefix, the dir itself is gone too.
            self.assertFalse(os.path.exists(vocal_path))
            self.assertFalse(os.path.exists(drum_path))

    def test_leaves_unmanaged_parent_dir_alone(self):
        """If the parent directory doesn't have the ``sonic_analyzer_demucs_``
        prefix, ``cleanup_stems`` must not delete it — it could be user data."""
        with tempfile.TemporaryDirectory(prefix="user_data_") as tmp:
            stem_path = os.path.join(tmp, "vocals.wav")
            Path(stem_path).write_bytes(b"fake-wav")

            analyze_audio_io.cleanup_stems({"vocals": stem_path})

            # The file is gone, but the parent dir survives.
            self.assertFalse(os.path.exists(stem_path))
            self.assertTrue(os.path.isdir(tmp))


class AnalyzeCrepePitchTests(unittest.TestCase):
    """When stems are absent, ``analyze_crepe_pitch`` must return the
    documented null envelope ``{"pitchDetail": None}`` rather than raising
    or returning an empty dict — downstream callers rely on this exact shape."""

    def test_none_stems_returns_null_pitch_detail(self):
        result = analyze_audio_io.analyze_crepe_pitch(None)
        self.assertEqual(result, {"pitchDetail": None})

    def test_empty_stems_returns_null_pitch_detail_when_torchcrepe_missing(self):
        """If torchcrepe is unavailable, an empty stems dict still yields
        the null envelope. With torchcrepe available, the function would
        proceed but find no readable stems and still return the null shape."""
        # With or without torchcrepe, an empty input must produce the null shape.
        result = analyze_audio_io.analyze_crepe_pitch({})
        self.assertEqual(result, {"pitchDetail": None})


@unittest.skipUnless(_ESSENTIA_AVAILABLE, "essentia not installed in this env")
class LoadMonoTests(unittest.TestCase):
    """End-to-end load_mono via Essentia's MonoLoader. Requires essentia;
    skipped when the dep is missing (test env without the backend venv)."""

    def test_load_mono_returns_numpy_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tone.wav")
            sr = 44100
            sig = (0.3 * np.sin(2 * np.pi * 440 * np.arange(sr) / sr)).astype(np.float32)
            analyze_audio_io._write_wav_pcm16(path, sig, sr)

            loaded = analyze_audio_io.load_mono(path, sample_rate=sr)
            self.assertIsInstance(loaded, np.ndarray)
            self.assertEqual(loaded.ndim, 1)
            # MonoLoader may pad/resample slightly; tolerate ±2 samples.
            self.assertAlmostEqual(loaded.size, sr, delta=2)

    def test_load_mono_resamples_to_target_sample_rate(self):
        """A 48 kHz WAV loaded at sample_rate=44100 must resample to
        approximately 44100 samples per second."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tone_48k.wav")
            src_sr = 48000
            sig = (0.3 * np.sin(2 * np.pi * 440 * np.arange(src_sr) / src_sr)).astype(np.float32)
            analyze_audio_io._write_wav_pcm16(path, sig, src_sr)

            loaded = analyze_audio_io.load_mono(path, sample_rate=44100)
            # 1 second of 48 kHz → ~44100 samples at 44.1 kHz.
            self.assertAlmostEqual(loaded.size, 44100, delta=100)


if __name__ == "__main__":
    unittest.main()
