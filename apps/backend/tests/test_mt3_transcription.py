"""Tests for the optional MT3 polyphonic-transcription stage.

Coverage:
 1. Pure unit tests of ``Mt3Result.to_payload()`` (the camelCase
    serialization boundary) and ``_resolve_sources()`` (stems-first +
    full-mix fallback). These are sub-second and always run.
 2. Direct ``transcribe()`` call: when the MT3 extra is not installed in
    the test venv, the call must raise the typed ``Mt3NotAvailableError``
    rather than leak an ``ImportError``. Auto-skips if MT3 happens to be
    installed locally.
 3. Subprocess tests against ``analyze.py``: verify the ``ASA_ENABLE_MT3``
    gate, the "transcription key absent when flag off" contract, and the
    "MT3 failure never blocks Phase 1" contract. These run analyze.py for
    real so they exercise the actual wiring, not a mock.
 4. Slow integration test (gated on ``RUN_SLOW_TESTS=1``): real MT3
    inference against a synthetic chord fixture, asserting non-empty
    tracks and ``pretty_midi``-parseable MIDI. ASA's backend uses
    ``unittest`` rather than ``pytest``; ``RUN_SLOW_TESTS=1`` plays the
    role of ``@pytest.mark.slow`` selection. The MT3 model download is
    multi-GB and is never run in CI.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from io import BytesIO
from pathlib import Path

import numpy as np

# Import the module under test directly. mt3_transcription.py keeps all
# heavy JAX/t5x imports inside transcribe(); importing the module itself
# is stdlib + numpy only, so it's safe to do at module load.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from mt3_transcription import (  # noqa: E402
    MT3_CHECKPOINT_ID,
    Mt3NotAvailableError,
    Mt3Result,
    Mt3Track,
    _resolve_sources,
    discover_stems_dir,
    transcribe,
)


def _write_silent_wav(path: Path, sample_rate: int = 22_050, duration_seconds: float = 1.0) -> None:
    """Write a tiny mono silent WAV. Used as a placeholder fixture for tests
    that only need a path-on-disk audio file."""
    total_samples = int(sample_rate * duration_seconds)
    pcm = np.zeros(total_samples, dtype=np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def _write_chord_fixture(
    path: Path,
    *,
    sample_rate: int = 22_050,
    duration_seconds: float = 10.0,
) -> None:
    """Synthesize a polyphonic fixture for the slow MT3 integration test.

    A sustained C-major triad (C4, E4, G4) with a slow 0.5 Hz amplitude
    envelope. Real-world enough that MT3 has clean note onsets to
    transcribe, simple enough to stay deterministic across reruns.
    """
    total = int(sample_rate * duration_seconds)
    t = np.arange(total, dtype=np.float32) / sample_rate
    chord = (
        0.25 * np.sin(2 * np.pi * 261.63 * t)  # C4
        + 0.25 * np.sin(2 * np.pi * 329.63 * t)  # E4
        + 0.25 * np.sin(2 * np.pi * 392.00 * t)  # G4
    )
    envelope = np.clip(0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t), 0.0, 1.0).astype(np.float32)
    signal = (chord * envelope).astype(np.float32)
    stereo = np.stack([signal, signal], axis=1)
    pcm = np.clip(stereo, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


class Mt3ResultShapeTests(unittest.TestCase):
    """to_payload() emits the documented camelCase contract (tripwire #3)."""

    def test_to_payload_serializes_with_camelcase_keys(self) -> None:
        result = Mt3Result(
            version="mt3-py-0.1.0+test-checkpoint@0001-01-01",
            stems_used=["bass", "other"],
            tracks=[
                Mt3Track(
                    instrument="bass",
                    midi_b64="TVRoZA==",  # MThd header bytes
                    note_count=12,
                    pitch_range=(36, 60),
                ),
                Mt3Track(
                    instrument="other",
                    midi_b64="TVRoZA==",
                    note_count=24,
                    pitch_range=(48, 84),
                ),
            ],
        )
        payload = result.to_payload()
        self.assertEqual(
            set(payload.keys()),
            {"version", "stemsUsed", "tracks"},
            "Top-level keys must be camelCase (analyze.py emits camelCase "
            "directly; no conversion layer to src/types/measurement.ts).",
        )
        self.assertEqual(payload["version"], "mt3-py-0.1.0+test-checkpoint@0001-01-01")
        self.assertEqual(payload["stemsUsed"], ["bass", "other"])
        self.assertEqual(len(payload["tracks"]), 2)
        first = payload["tracks"][0]
        self.assertEqual(
            set(first.keys()),
            {"instrument", "midiB64", "noteCount", "pitchRange"},
            "Track entries must use camelCase keys.",
        )
        self.assertEqual(first["instrument"], "bass")
        self.assertEqual(first["midiB64"], "TVRoZA==")
        self.assertEqual(first["noteCount"], 12)
        self.assertEqual(first["pitchRange"], [36, 60])

    def test_to_payload_handles_empty_result(self) -> None:
        """An MT3 run that produces no usable notes still emits a valid
        envelope — the wiring in analyze.py treats this as success."""
        result = Mt3Result(
            version="mt3-py-0.1.0+test",
            stems_used=[],
            tracks=[],
        )
        payload = result.to_payload()
        self.assertEqual(payload["stemsUsed"], [])
        self.assertEqual(payload["tracks"], [])

    def test_pinned_checkpoint_id_has_documented_format(self) -> None:
        """Phase 2 reads MT3_CHECKPOINT_ID verbatim. The base identifier is
        always present; an ``@<date-or-hash>`` suffix is optional but its
        shape is constrained when operators add one (see the module docstring
        on MT3_CHECKPOINT_ID). Don't relax this regex without updating the
        module-level rationale comment."""
        self.assertRegex(
            MT3_CHECKPOINT_ID,
            r"^magenta-mt3-[a-z]+(@[A-Za-z0-9\-]+)?$",
        )


class Mt3SourceResolutionTests(unittest.TestCase):
    """_resolve_sources() falls back to full-mix when stems are missing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mt3_sources_")
        self.addCleanup(self._tmp.cleanup)
        self.audio = Path(self._tmp.name) / "mix.wav"
        _write_silent_wav(self.audio, duration_seconds=0.5)

    def test_returns_full_mix_when_stems_dir_is_none(self) -> None:
        sources = _resolve_sources(self.audio, None)
        self.assertEqual(sources, [("full_mix", self.audio)])

    def test_returns_full_mix_when_stems_dir_does_not_exist(self) -> None:
        sources = _resolve_sources(self.audio, Path(self._tmp.name) / "nope")
        self.assertEqual(sources, [("full_mix", self.audio)])

    def test_returns_full_mix_when_stems_dir_is_empty(self) -> None:
        empty = Path(self._tmp.name) / "stems_empty"
        empty.mkdir()
        sources = _resolve_sources(self.audio, empty)
        self.assertEqual(sources, [("full_mix", self.audio)])

    def test_discovers_canonical_demucs_stems_in_documented_order(self) -> None:
        stems_dir = Path(self._tmp.name) / "stems"
        stems_dir.mkdir()
        for name in ("bass", "other", "vocals"):
            (stems_dir / f"{name}.wav").write_bytes(b"\x00")
        sources = _resolve_sources(self.audio, stems_dir)
        # The order follows _DEFAULT_STEM_INSTRUMENTS so MT3 gets the same
        # iteration order across runs — load-bearing for stems_used in the
        # JSON envelope.
        self.assertEqual([name for name, _ in sources], ["bass", "other", "vocals"])

    def test_prefers_wav_over_flac_when_both_present(self) -> None:
        stems_dir = Path(self._tmp.name) / "stems"
        stems_dir.mkdir()
        (stems_dir / "bass.wav").write_bytes(b"\x00")
        (stems_dir / "bass.flac").write_bytes(b"\x00")
        sources = _resolve_sources(self.audio, stems_dir)
        self.assertEqual(sources, [("bass", stems_dir / "bass.wav")])

    def test_skips_drums_stem_by_default(self) -> None:
        """Drums are excluded by default (Phase 1 already covers them via
        kickDetail/snareDetail/hihatDetail and MT3's drum head is weaker
        than purpose-built drum trackers)."""
        stems_dir = Path(self._tmp.name) / "stems"
        stems_dir.mkdir()
        (stems_dir / "drums.wav").write_bytes(b"\x00")
        (stems_dir / "bass.wav").write_bytes(b"\x00")
        sources = _resolve_sources(self.audio, stems_dir)
        names = [name for name, _ in sources]
        self.assertNotIn("drums", names)
        self.assertIn("bass", names)


class Mt3StemsDirDiscoveryTests(unittest.TestCase):
    """discover_stems_dir() recovers the Demucs parent directory.

    This is the helper called by analyze.py's gate to translate the
    ``stems`` dict (which analyze_audio_io.separate_stems writes) into the
    parent directory ``transcribe()`` expects. Unit-tested separately
    because the subprocess pipeline test runs without ``--separate`` and
    so never exercises this branch.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mt3_discovery_")
        self.addCleanup(self._tmp.cleanup)
        self.stems_root = Path(self._tmp.name) / "stems"
        self.stems_root.mkdir()
        # Write the four Demucs canonical stems as silent WAVs.
        self.stem_files: dict[str, Path] = {}
        for name in ("drums", "bass", "other", "vocals"):
            stem_path = self.stems_root / f"{name}.wav"
            _write_silent_wav(stem_path, duration_seconds=0.1)
            self.stem_files[name] = stem_path

    def test_recovers_parent_from_full_demucs_dict(self) -> None:
        stems_dict = {name: str(path) for name, path in self.stem_files.items()}
        self.assertEqual(discover_stems_dir(stems_dict), self.stems_root)

    def test_returns_none_for_none_input(self) -> None:
        self.assertIsNone(discover_stems_dir(None))

    def test_returns_none_for_empty_dict(self) -> None:
        self.assertIsNone(discover_stems_dir({}))

    def test_returns_none_for_non_dict_input(self) -> None:
        # Defensive — analyze.py passes whatever ``stems`` happens to be.
        self.assertIsNone(discover_stems_dir([]))  # type: ignore[arg-type]
        self.assertIsNone(discover_stems_dir("not a dict"))  # type: ignore[arg-type]

    def test_returns_none_when_paths_do_not_exist(self) -> None:
        stems_dict = {
            "drums": str(self.stems_root / "missing-drums.wav"),
            "bass": str(self.stems_root / "missing-bass.wav"),
        }
        self.assertIsNone(discover_stems_dir(stems_dict))

    def test_returns_parent_of_first_existing_path(self) -> None:
        """First on-disk path wins — Demucs writes all stems to one dir,
        so any one of them recovers the directory."""
        stems_dict = {
            "drums": str(self.stems_root / "missing.wav"),
            "bass": str(self.stem_files["bass"]),  # exists
        }
        self.assertEqual(discover_stems_dir(stems_dict), self.stems_root)


def _is_mt3_extra_installed() -> bool:
    try:
        import mt3  # type: ignore  # noqa: F401
        import note_seq  # noqa: F401
        import librosa  # noqa: F401
    except ImportError:
        return False
    return True


class Mt3NotAvailableTests(unittest.TestCase):
    """When the [mt3] extra isn't installed, transcribe() raises a typed
    Mt3NotAvailableError. analyze.py relies on this contract — it catches
    Mt3NotAvailableError (alongside generic Exception) and surfaces it as a
    [warn] line without blocking the Phase 1 JSON."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mt3_unavailable_")
        self.addCleanup(self._tmp.cleanup)
        self.audio = Path(self._tmp.name) / "mix.wav"
        _write_silent_wav(self.audio, duration_seconds=0.5)

    @unittest.skipIf(
        _is_mt3_extra_installed(),
        "MT3 extra is installed locally; this test exercises the missing-deps path.",
    )
    def test_raises_mt3_not_available_when_extra_missing(self) -> None:
        with self.assertRaises(Mt3NotAvailableError):
            transcribe(self.audio, stems_dir=None)

    def test_raises_file_not_found_for_missing_audio(self) -> None:
        with self.assertRaises(FileNotFoundError):
            transcribe(Path(self._tmp.name) / "nonexistent.wav", stems_dir=None)


class AnalyzePipelineGatingTests(unittest.TestCase):
    """End-to-end: analyze.py honors the ASA_ENABLE_MT3 gate.

    These are subprocess tests that exercise the actual wiring in
    apps/backend/analyze.py. They don't need the MT3 extra installed —
    the contract under test is that the `transcription` JSON key is
    absent (not null) by default, absent when MT3 fails, and absent in
    fast mode regardless of the flag.
    """

    SAMPLE_RATE = 22_050
    DURATION = 4.0

    @classmethod
    def setUpClass(cls) -> None:
        cls.backend_dir = Path(__file__).resolve().parent.parent
        cls.analyze_path = cls.backend_dir / "analyze.py"
        cls._tmp = tempfile.TemporaryDirectory(prefix="mt3_pipeline_")
        cls.fixture = Path(cls._tmp.name) / "fixture.wav"
        _write_chord_fixture(
            cls.fixture,
            sample_rate=cls.SAMPLE_RATE,
            duration_seconds=cls.DURATION,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    @classmethod
    def _run_analyze(cls, *, env_overrides: dict[str, str], extra_args: list[str]) -> dict:
        env = os.environ.copy()
        # Strip any pre-existing flag so tests are hermetic. Override after.
        env.pop("ASA_ENABLE_MT3", None)
        env.update(env_overrides)

        venv_python = cls.backend_dir / "venv" / "bin" / "python"
        python_exe = str(venv_python) if venv_python.is_file() else sys.executable
        argv = [python_exe, str(cls.analyze_path), str(cls.fixture), "--yes", *extra_args]

        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"analyze.py exited {result.returncode}.\n"
                f"argv: {argv}\n"
                f"stdout (first 800):\n{result.stdout[:800]}\n"
                f"stderr (first 800):\n{result.stderr[:800]}"
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                "analyze.py did not emit valid JSON.\n"
                f"stdout (first 800):\n{result.stdout[:800]}\n"
                f"stderr (first 800):\n{result.stderr[:800]}"
            ) from exc

    def test_fast_mode_omits_transcription_when_flag_off(self) -> None:
        """Baseline default: no flag, no MT3 namespace. Uses --fast for speed
        because fast mode runs the same JSON-emission path that would be
        affected by an accidental ``result["transcription"] = None``."""
        payload = self._run_analyze(env_overrides={}, extra_args=["--fast"])
        self.assertNotIn(
            "transcription",
            payload,
            "transcription key must be ABSENT (not null) when ASA_ENABLE_MT3 "
            "is unset — see JSON_SCHEMA.md 'Optional MT3 Namespace'.",
        )

    def test_fast_mode_omits_transcription_when_flag_on(self) -> None:
        """Fast mode bypasses the MT3 hook entirely (analyze_fast.py builds
        its own output dict). The flag has no effect here — load-bearing
        defense-in-depth."""
        payload = self._run_analyze(
            env_overrides={"ASA_ENABLE_MT3": "1"},
            extra_args=["--fast"],
        )
        self.assertNotIn("transcription", payload)
        # Sanity-check Phase 1 still emits: fast mode should never crash on
        # the env var.
        self.assertIn("bpm", payload)

    def test_full_mode_omits_transcription_and_keeps_phase1_when_deps_missing(self) -> None:
        """Load-bearing 'never blocks Phase 1' contract: with the flag on but
        no MT3 deps installed, the hook catches Mt3NotAvailableError, logs a
        [warn], and analyze.py still emits a complete Phase 1 JSON without a
        transcription key."""
        if _is_mt3_extra_installed():
            self.skipTest(
                "MT3 extra is installed locally; this test exercises the "
                "missing-deps failure path. Run the slow integration test "
                "(RUN_SLOW_TESTS=1) instead to exercise real inference."
            )
        payload = self._run_analyze(
            env_overrides={"ASA_ENABLE_MT3": "1"},
            extra_args=[],
        )
        self.assertIn(
            "bpm",
            payload,
            "Phase 1 must still emit when MT3 fails — never block on optional stages.",
        )
        self.assertNotIn(
            "transcription",
            payload,
            "transcription key must be absent when MT3 deps are missing — "
            "the failure path is logged as [warn], never as a null key.",
        )


@unittest.skipUnless(
    os.environ.get("RUN_SLOW_TESTS") == "1",
    "Set RUN_SLOW_TESTS=1 to run the real MT3 integration test. Requires "
    "the [mt3] extra installed and the checkpoint downloaded — see "
    "apps/backend/mt3_transcription.py and apps/backend/requirements-mt3.txt. "
    "ASA's backend uses unittest, not pytest; this env-var skip plays the role "
    "of @pytest.mark.slow in the goal text.",
)
class Mt3RealInferenceTests(unittest.TestCase):
    """Live MT3 integration. Opt-in via RUN_SLOW_TESTS=1. Never runs in CI.

    Asserts the three concrete deliverables from the goal:
      1. Non-empty ``tracks``.
      2. Each ``midiB64`` parses cleanly via ``pretty_midi.PrettyMIDI``.
      3. The reported ``noteCount`` per track matches the parsed MIDI.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="mt3_slow_")
        cls.fixture = Path(cls._tmp.name) / "chord.wav"
        _write_chord_fixture(cls.fixture, sample_rate=22_050, duration_seconds=10.0)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_transcribe_returns_non_empty_parseable_midi(self) -> None:
        try:
            import pretty_midi  # noqa: F401
        except ImportError as exc:
            self.skipTest(f"pretty_midi not installed: {exc}")

        try:
            result = transcribe(self.fixture, stems_dir=None)
        except Mt3NotAvailableError as exc:
            self.skipTest(
                f"MT3 extra not available: {exc}. Install via: "
                "./apps/backend/venv/bin/pip install -r "
                "apps/backend/requirements-mt3.txt"
            )

        self.assertIsInstance(result, Mt3Result)
        self.assertTrue(result.version, "version must be a non-empty string")
        self.assertGreater(
            len(result.tracks),
            0,
            "tracks must be non-empty for a sustained chord fixture",
        )

        import pretty_midi
        for track in result.tracks:
            midi_bytes = base64.b64decode(track.midi_b64)
            parsed = pretty_midi.PrettyMIDI(BytesIO(midi_bytes))
            actual_note_count = sum(
                len(instrument.notes) for instrument in parsed.instruments
            )
            self.assertEqual(
                actual_note_count,
                track.note_count,
                f"track {track.instrument!r}: declared noteCount "
                f"{track.note_count} does not match parsed MIDI count "
                f"{actual_note_count}",
            )


if __name__ == "__main__":
    unittest.main()
