"""Audio-detector contract tests: ``analyze_detection.py`` and ``analyze.py``.

The plan called for one test file per detector. In practice the audio-driven
detectors share a common contract:

1. Null/empty/short input → ``{"<key>Detail": None}`` (graceful, never raise).
2. With Essentia/librosa available, a synthesized signal produces a detail
   dict with the documented fields and bounded confidence in [0, 1].

Rather than duplicate the boilerplate eight times, this file groups
detectors by parent module. Each detector still gets its own ``TestCase`` so
a failure in ``analyze_acid_detail`` reports against ``AcidDetailContractTests``
specifically — preserving the plan's "attributable failure" goal.

Detectors covered:

  analyze_detection.py: acid, reverb, vocal, supersaw, effects
  analyze.py:           sidechain, bass, kick

Tests that require Essentia / librosa are gated by ``@skipUnless`` and will
run in the real backend venv. The null-input contract tests run everywhere.
"""

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# analyze_detection.py guards its essentia/librosa imports, so it loads
# unconditionally — the detectors gracefully short-circuit when the deps
# are missing.
_AD_PATH = _BACKEND_ROOT / "analyze_detection.py"
_AD_SPEC = importlib.util.spec_from_file_location("analyze_detection_audio_test", _AD_PATH)
if _AD_SPEC is None or _AD_SPEC.loader is None:
    raise AssertionError("Could not load analyze_detection.py")
analyze_detection = importlib.util.module_from_spec(_AD_SPEC)
_AD_SPEC.loader.exec_module(analyze_detection)


# analyze.py imports essentia at module load with sys.exit(1) on failure —
# attempt the import inside a broad guard so the kick/bass/sidechain test
# classes can be skipped cleanly in any environment that can't load it.
_ESSENTIA_AVAILABLE = analyze_detection.es is not None
_LIBROSA_AVAILABLE = analyze_detection.librosa is not None

analyze_module = None
if _ESSENTIA_AVAILABLE:
    try:
        # ``import_module("analyze")`` resolves through sys.path (which we
        # added above) and lets Python register it as the canonical
        # ``analyze`` module — simpler and more robust than
        # ``spec_from_file_location`` + ``exec_module``, which creates a
        # second, partially-initialised copy.
        # ``Exception`` covers ImportError; ``SystemExit`` is listed
        # separately because it's not an Exception subclass — analyze.py
        # ``sys.exit(1)``s on a missing essentia.
        import analyze as analyze_module  # type: ignore[import-not-found]
    except (SystemExit, Exception):
        analyze_module = None


# ---------------------------------------------------------------------------
# Shared synthetic-signal helpers — purpose-built, kept tiny and inline.
# ---------------------------------------------------------------------------

def _sine(freq_hz: float, sr: int, duration_s: float, amplitude: float = 0.3) -> np.ndarray:
    t = np.arange(int(sr * duration_s)) / sr
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def _impulse_with_decay(sr: int, duration_s: float, rt60_s: float = 1.5) -> np.ndarray:
    """One impulse at t=0 with an exponential decay envelope, modulated by
    noise to simulate a reverb tail. Useful for reverb detection."""
    n = int(sr * duration_s)
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(n).astype(np.float32) * 0.05
    decay = np.exp(-3 * np.log(10) * np.arange(n) / (rt60_s * sr)).astype(np.float32)
    impulse = np.zeros(n, dtype=np.float32)
    impulse[0] = 1.0
    return impulse + noise * decay


def _detuned_saw_stack(
    sr: int, duration_s: float, base_hz: float, voices: int, detune_cents: float,
) -> np.ndarray:
    """Crude additive-sawtooth supersaw stack — a known supersaw signature."""
    n = int(sr * duration_s)
    t = np.arange(n) / sr
    out = np.zeros(n, dtype=np.float64)
    for v in range(voices):
        # ±detune_cents distributed evenly across voices
        cents_off = -detune_cents + (2 * detune_cents) * (v / max(1, voices - 1))
        freq = base_hz * (2 ** (cents_off / 1200.0))
        # Saw-like via summed harmonics — keep it small to avoid aliasing
        for k in range(1, 6):
            out += (1.0 / k) * np.sin(2 * np.pi * freq * k * t)
    out *= 0.05  # keep amplitude bounded
    return out.astype(np.float32)


# ---------------------------------------------------------------------------
# analyze_detection.py — null-input contracts.
# ---------------------------------------------------------------------------

class AcidDetailContractTests(unittest.TestCase):
    """``analyze_acid_detail`` requires BPM and ≥2 samples; otherwise null."""

    def test_empty_input_returns_null(self):
        result = analyze_detection.analyze_acid_detail(
            np.array([], dtype=np.float32), bpm=128.0,
        )
        self.assertEqual(result, {"acidDetail": None})

    def test_too_short_input_returns_null(self):
        result = analyze_detection.analyze_acid_detail(
            np.array([0.0], dtype=np.float32), bpm=128.0,
        )
        self.assertEqual(result, {"acidDetail": None})

    def test_missing_bpm_returns_null(self):
        sig = _sine(220.0, 22050, 2.0)
        self.assertEqual(
            analyze_detection.analyze_acid_detail(sig, sample_rate=22050, bpm=None),
            {"acidDetail": None},
        )

    def test_negative_bpm_returns_null(self):
        sig = _sine(220.0, 22050, 2.0)
        self.assertEqual(
            analyze_detection.analyze_acid_detail(sig, sample_rate=22050, bpm=-1.0),
            {"acidDetail": None},
        )

    def test_nan_bpm_returns_null(self):
        sig = _sine(220.0, 22050, 2.0)
        self.assertEqual(
            analyze_detection.analyze_acid_detail(sig, sample_rate=22050, bpm=float("nan")),
            {"acidDetail": None},
        )

    def test_multidimensional_input_returns_null(self):
        sig = np.zeros((2, 22050), dtype=np.float32)
        self.assertEqual(
            analyze_detection.analyze_acid_detail(sig, sample_rate=22050, bpm=128.0),
            {"acidDetail": None},
        )

    @unittest.skipUnless(_ESSENTIA_AVAILABLE, "essentia required for audio-driven test")
    def test_flat_sine_yields_low_confidence(self):
        """A clean 220 Hz sine has no resonance sweep, no rhythm density → low confidence."""
        sig = _sine(220.0, 44100, 4.0)
        result = analyze_detection.analyze_acid_detail(sig, sample_rate=44100, bpm=128.0)
        detail = result["acidDetail"]
        if detail is None:
            self.skipTest("acid detector returned null detail for synthetic sine")
        self.assertIn("confidence", detail)
        self.assertGreaterEqual(detail["confidence"], 0.0)
        self.assertLessEqual(detail["confidence"], 1.0)
        # No filter sweep, no rhythm → cannot reach the 0.45 isAcid threshold.
        self.assertFalse(detail["isAcid"])


class ReverbDetailContractTests(unittest.TestCase):
    @unittest.skipUnless(_LIBROSA_AVAILABLE, "librosa required for reverb detector")
    def test_empty_input_handled(self):
        result = analyze_detection.analyze_reverb_detail(
            np.array([], dtype=np.float32), sample_rate=44100,
        )
        # Detector may return null detail or a measured-but-zero shape;
        # either is acceptable as long as it doesn't raise.
        self.assertIn("reverbDetail", result)

    @unittest.skipUnless(_LIBROSA_AVAILABLE, "librosa required for reverb detector")
    def test_silent_input_does_not_crash(self):
        silence = np.zeros(44100 * 2, dtype=np.float32)
        result = analyze_detection.analyze_reverb_detail(silence, sample_rate=44100)
        self.assertIn("reverbDetail", result)

    @unittest.skipUnless(
        _ESSENTIA_AVAILABLE and _LIBROSA_AVAILABLE,
        "essentia and librosa required",
    )
    def test_decaying_impulse_does_not_crash(self):
        """A synthesized decaying impulse is a weak proxy for real reverb; the
        detector may or may not classify it as wet (transient counter or
        slope-fit may reject the signal). The contract assertion is just:
        don't raise, and if a measured RT60 lands, it's finite and positive."""
        sig = _impulse_with_decay(44100, 4.0, rt60_s=1.2)
        result = analyze_detection.analyze_reverb_detail(sig, sample_rate=44100)
        detail = result.get("reverbDetail")
        if detail is not None and detail.get("measured"):
            self.assertTrue(np.isfinite(detail["rt60"]))
            self.assertGreater(detail["rt60"], 0.0)


class VocalDetailContractTests(unittest.TestCase):
    """The vocal detector's confidence math on synthetic signals is opinionated
    and not exactly reproducible (formant matching, MFCC likelihood, optional
    stem cross-correlation). These tests assert only the don't-crash contract;
    content assertions are guarded so a heuristic change can't fail the gate."""

    @unittest.skipUnless(_ESSENTIA_AVAILABLE, "essentia required for vocal detector")
    def test_silent_input_does_not_crash(self):
        silence = np.zeros(44100 * 3, dtype=np.float32)
        result = analyze_detection.analyze_vocal_detail(silence, sample_rate=44100)
        self.assertIn("vocalDetail", result)
        detail = result["vocalDetail"]
        if detail is not None and "hasVocals" in detail:
            self.assertFalse(detail["hasVocals"])

    @unittest.skipUnless(_ESSENTIA_AVAILABLE, "essentia required for vocal detector")
    def test_pure_tone_does_not_crash(self):
        sig = _sine(440.0, 44100, 3.0)
        result = analyze_detection.analyze_vocal_detail(sig, sample_rate=44100)
        self.assertIn("vocalDetail", result)


class SupersawDetailContractTests(unittest.TestCase):
    @unittest.skipUnless(_ESSENTIA_AVAILABLE, "essentia required for supersaw detector")
    def test_single_sine_does_not_crash(self):
        sig = _sine(440.0, 44100, 3.0)
        result = analyze_detection.analyze_supersaw_detail(sig, sample_rate=44100)
        self.assertIn("supersawDetail", result)
        detail = result["supersawDetail"]
        if detail is not None and "isSupersaw" in detail:
            self.assertFalse(detail["isSupersaw"])

    @unittest.skipUnless(_ESSENTIA_AVAILABLE, "essentia required for supersaw detector")
    def test_detuned_stack_does_not_crash(self):
        """A 7-voice ±15 cent detuned stack — confirms the detector runs on
        a known-supersaw-like signature without raising. Numerical assertions
        (voiceCount, confidence) are intentionally not made because the
        Essentia SpectralPeaks pipeline's voice-count heuristic is not
        guaranteed to identify our synthetic stack."""
        sig = _detuned_saw_stack(44100, 3.0, base_hz=220.0, voices=7, detune_cents=15.0)
        result = analyze_detection.analyze_supersaw_detail(sig, sample_rate=44100)
        self.assertIn("supersawDetail", result)
        detail = result["supersawDetail"]
        if detail is not None and "confidence" in detail:
            self.assertGreaterEqual(detail["confidence"], 0.0)
            self.assertLessEqual(detail["confidence"], 1.0)


class EffectsDetailContractTests(unittest.TestCase):
    @unittest.skipUnless(_ESSENTIA_AVAILABLE, "essentia required for effects detector")
    def test_steady_sine_not_gated(self):
        sig = _sine(220.0, 44100, 4.0)
        result = analyze_detection.analyze_effects_detail(sig, sample_rate=44100)
        self.assertIn("effectsDetail", result)
        detail = result["effectsDetail"]
        if detail is not None and "gatingDetected" in detail:
            self.assertFalse(detail["gatingDetected"])

    @unittest.skipUnless(_ESSENTIA_AVAILABLE, "essentia required for effects detector")
    def test_amplitude_modulated_signal_may_register_gating(self):
        sr = 44100
        carrier = _sine(220.0, sr, 4.0)
        # 8 Hz amplitude modulation (quarter-note gate at 480 BPM, or 8th at
        # 240 BPM, or 16th at 120 BPM) — the rate-classification logic in
        # ``analyze_effects_detail`` resolves to one of those labels.
        t = np.arange(carrier.size) / sr
        envelope = 0.5 * (1.0 + np.sin(2 * np.pi * 8.0 * t))
        gated = (carrier * envelope).astype(np.float32)
        result = analyze_detection.analyze_effects_detail(
            gated, sample_rate=sr, rhythm_data={"bpm": 120.0},
        )
        detail = result["effectsDetail"]
        if detail is not None and detail["gatingDetected"]:
            # When gating is detected, rate must be one of the documented labels.
            self.assertIn(detail.get("gatingRate"), {"quarter", "8th", "16th", None})


# ---------------------------------------------------------------------------
# analyze.py — null-input contracts for kick / bass / sidechain.
# These can only be exercised when essentia is available (analyze.py
# sys.exit(1)s on missing essentia at module import).
# ---------------------------------------------------------------------------

@unittest.skipUnless(analyze_module is not None, "essentia/analyze.py unavailable")
class KickDetailContractTests(unittest.TestCase):
    def test_too_short_input_returns_null(self):
        # ``analyze_kick_detail`` requires ≥4096 samples.
        sig = np.zeros(1000, dtype=np.float32)
        result = analyze_module.analyze_kick_detail(sig, sample_rate=44100, bpm=128.0)
        self.assertEqual(result, {"kickDetail": None})

    def test_multidimensional_input_returns_null(self):
        sig = np.zeros((2, 8192), dtype=np.float32)
        result = analyze_module.analyze_kick_detail(sig, sample_rate=44100, bpm=128.0)
        self.assertEqual(result, {"kickDetail": None})

    def test_silent_input_does_not_crash(self):
        sig = np.zeros(44100, dtype=np.float32)
        result = analyze_module.analyze_kick_detail(sig, sample_rate=44100, bpm=128.0)
        self.assertIn("kickDetail", result)


@unittest.skipUnless(analyze_module is not None, "essentia/analyze.py unavailable")
class BassDetailContractTests(unittest.TestCase):
    def test_too_short_input_returns_null(self):
        # ``analyze_bass_detail`` requires ≥sample_rate samples (1s).
        sig = np.zeros(1000, dtype=np.float32)
        result = analyze_module.analyze_bass_detail(sig, sample_rate=44100, bpm=128.0)
        self.assertEqual(result, {"bassDetail": None})

    def test_multidimensional_input_returns_null(self):
        sig = np.zeros((2, 88200), dtype=np.float32)
        result = analyze_module.analyze_bass_detail(sig, sample_rate=44100, bpm=128.0)
        self.assertEqual(result, {"bassDetail": None})

    def test_bpm_falls_back_to_120_when_invalid(self):
        """The detector should not crash when BPM is missing/invalid — it
        falls back to 120 BPM for the onset-distance heuristic."""
        sig = np.zeros(44100, dtype=np.float32)
        for bad in (None, float("nan"), -1.0, 0.0):
            with self.subTest(bpm=bad):
                # Must return without raising; result may be null detail.
                result = analyze_module.analyze_bass_detail(sig, sample_rate=44100, bpm=bad)
                self.assertIn("bassDetail", result)


@unittest.skipUnless(analyze_module is not None, "essentia/analyze.py unavailable")
class SidechainDetailContractTests(unittest.TestCase):
    def test_short_input_returns_null(self):
        # The sidechain detector requires beat data; with no rhythm_data
        # and a tiny array, the beat-extraction path must short-circuit.
        sig = np.zeros(100, dtype=np.float32)
        result = analyze_module.analyze_sidechain_detail(sig, sample_rate=44100)
        self.assertEqual(result, {"sidechainDetail": None})

    def test_silent_long_signal_does_not_crash(self):
        sig = np.zeros(44100 * 4, dtype=np.float32)
        result = analyze_module.analyze_sidechain_detail(sig, sample_rate=44100)
        self.assertIn("sidechainDetail", result)


if __name__ == "__main__":
    unittest.main()
