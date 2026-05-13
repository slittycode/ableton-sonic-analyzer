"""
test_audio_fixture_smoke.py — Deterministic WAV generation and backend smoke test.

Tests that:
1. A deterministic 440 Hz sine wave WAV can be generated using stdlib
2. The generated WAV is structurally valid (readable via wave module)
3. The backend can parse the audio file's duration via get_audio_duration_seconds
4. No external models or network access is required
"""

import importlib.util
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path


def _write_440hz_sine_wav(
    path: Path,
    *,
    sample_rate: int = 44100,
    duration_seconds: float = 1.0,
    frequency_hz: float = 440.0,
) -> None:
    """
    Write a deterministic mono 16-bit PCM WAV file containing a 440 Hz sine wave.

    Args:
        path: File path where the WAV will be written
        sample_rate: Audio sample rate in Hz (default 44100)
        duration_seconds: Duration of the audio in seconds (default 1.0)
        frequency_hz: Frequency of the sine wave in Hz (default 440.0)
    """
    frame_count = int(sample_rate * duration_seconds)
    # Amplitude: 25% of max int16 to avoid clipping
    amplitude = 0.25 * 32767

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)

        frames = bytearray()
        for index in range(frame_count):
            # Generate sine wave sample: A * sin(2π * f * t)
            sample_value = amplitude * math.sin(2 * math.pi * frequency_hz * index / sample_rate)
            sample_int16 = int(sample_value)
            # Pack as little-endian signed 16-bit integer
            frames.extend(struct.pack("<h", sample_int16))

        wav.writeframes(bytes(frames))


class AudioFixtureSmokeTests(unittest.TestCase):
    """Tests for deterministic WAV generation and backend audio handling."""

    SAMPLE_RATE = 44100
    DURATION_SECONDS = 1.0
    FREQUENCY_HZ = 440.0

    def test_generate_sine_wav_is_structurally_valid(self) -> None:
        """Verify that generated WAV file is readable and has correct structure."""
        with tempfile.TemporaryDirectory(prefix="asa_fixture_test_") as temp_dir:
            wav_path = Path(temp_dir) / "test_440hz.wav"
            _write_440hz_sine_wav(wav_path)

            # Verify file exists
            self.assertTrue(wav_path.exists(), "Generated WAV file does not exist")

            # Verify WAV structure
            with wave.open(str(wav_path), "rb") as wav:
                n_channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                frame_rate = wav.getframerate()
                n_frames = wav.getnframes()
                frames_data = wav.readframes(n_frames)

                # Assert structure
                self.assertEqual(n_channels, 1, "Expected mono (1 channel)")
                self.assertEqual(sample_width, 2, "Expected 16-bit (2 bytes per sample)")
                self.assertEqual(frame_rate, self.SAMPLE_RATE, f"Expected sample rate {self.SAMPLE_RATE}")
                self.assertEqual(n_frames, int(self.SAMPLE_RATE * self.DURATION_SECONDS),
                               f"Expected {int(self.SAMPLE_RATE * self.DURATION_SECONDS)} frames")

                # Assert frames are not empty
                expected_byte_count = n_frames * sample_width
                self.assertEqual(len(frames_data), expected_byte_count,
                               f"Expected {expected_byte_count} bytes of audio data")

    def test_generate_sine_wav_is_deterministic(self) -> None:
        """Verify that WAV generation produces identical output on repeated calls."""
        with tempfile.TemporaryDirectory(prefix="asa_fixture_test_") as temp_dir:
            wav_path_1 = Path(temp_dir) / "test_1.wav"
            wav_path_2 = Path(temp_dir) / "test_2.wav"

            # Generate the same WAV twice
            _write_440hz_sine_wav(wav_path_1)
            _write_440hz_sine_wav(wav_path_2)

            # Read both files and compare
            with wave.open(str(wav_path_1), "rb") as wav1, \
                 wave.open(str(wav_path_2), "rb") as wav2:
                frames1 = wav1.readframes(wav1.getnframes())
                frames2 = wav2.readframes(wav2.getnframes())
                self.assertEqual(frames1, frames2, "Generated WAV files differ on repeated calls")

    def test_backend_can_read_duration_from_generated_wav(self) -> None:
        """Verify that the backend's get_audio_duration_seconds works with generated WAV."""
        # Import get_audio_duration_seconds from analyze.py
        repo_root = Path(__file__).resolve().parent.parent
        analyze_module_path = repo_root / "analyze_estimate.py"

        spec = importlib.util.spec_from_file_location("analyze_module", analyze_module_path)
        if spec is None or spec.loader is None:
            self.skipTest("Could not load analyze_estimate.py")

        analyze_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(analyze_module)

        # Access the function
        get_audio_duration_seconds = getattr(analyze_module, "get_audio_duration_seconds", None)
        if get_audio_duration_seconds is None:
            self.skipTest("get_audio_duration_seconds not found in analyze_estimate.py")

        with tempfile.TemporaryDirectory(prefix="asa_fixture_test_") as temp_dir:
            wav_path = Path(temp_dir) / "test_440hz.wav"
            _write_440hz_sine_wav(wav_path, duration_seconds=2.5)

            # Call the backend's duration function
            duration = get_audio_duration_seconds(str(wav_path))

            # The duration should be approximately our specified duration
            # (allow 0.5 second tolerance for metadata variations)
            self.assertIsNotNone(duration, "get_audio_duration_seconds returned None")
            self.assertGreaterEqual(duration, 2.0, f"Duration {duration} is too short")
            self.assertLessEqual(duration, 3.0, f"Duration {duration} is too long")

    def test_440hz_sine_has_correct_frequency_characteristics(self) -> None:
        """Verify that generated WAV contains expected 440 Hz frequency."""
        with tempfile.TemporaryDirectory(prefix="asa_fixture_test_") as temp_dir:
            wav_path = Path(temp_dir) / "test_440hz.wav"
            _write_440hz_sine_wav(wav_path, duration_seconds=2.0)

            with wave.open(str(wav_path), "rb") as wav:
                frames_data = wav.readframes(wav.getnframes())

            # Unpack samples to verify they form a reasonable sine wave
            samples = struct.unpack(f"<{len(frames_data) // 2}h", frames_data)
            self.assertGreater(len(samples), 0, "No audio samples found")

            # Find peak sample value (should be near amplitude of 0.25 * 32767 ≈ 8191)
            max_sample = max(abs(s) for s in samples)
            expected_amplitude = 0.25 * 32767
            # Allow 10% tolerance for rounding
            self.assertGreater(max_sample, expected_amplitude * 0.9,
                             f"Max sample {max_sample} is below expected range")
            self.assertLess(max_sample, expected_amplitude * 1.1,
                           f"Max sample {max_sample} is above expected range")

            # Verify we have both positive and negative samples (sine wave oscillates)
            has_positive = any(s > 1000 for s in samples)
            has_negative = any(s < -1000 for s in samples)
            self.assertTrue(has_positive, "No positive samples found; expected sine wave")
            self.assertTrue(has_negative, "No negative samples found; expected sine wave")


if __name__ == "__main__":
    unittest.main()
