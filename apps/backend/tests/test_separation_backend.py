"""Tests for the pluggable separation backend (Demucs <-> MSST).

The MSST path shells out to a runner under a separate venv that isn't installed
in CI — so these mock the subprocess and the env wiring and assert the
select / dispatch / fall-back logic in pure Python. No MSST install required.
"""

import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import separation_backend as sb


def _load_runner_module():
    """Load the MSST runner from scripts/ by path (it is not on sys.path)."""
    runner_path = Path(__file__).resolve().parent.parent / "scripts" / "msst_separate_runner.py"
    spec = importlib.util.spec_from_file_location("msst_separate_runner", runner_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_runner = _load_runner_module()


_SENTINEL_STEMS = {"vocals": "/tmp/v.wav", "bass": "/tmp/b.wav"}


def _runner_proc(stdout: str, returncode: int = 0, stderr: str = "") -> mock.Mock:
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class SeparationBackendNameTests(unittest.TestCase):
    def test_default_is_demucs(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASA_SEPARATION_BACKEND", None)
            self.assertEqual(sb.separation_backend_name(), "demucs")

    def test_unknown_value_falls_back_to_demucs(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_SEPARATION_BACKEND": "bogus"}):
            self.assertEqual(sb.separation_backend_name(), "demucs")

    def test_msst_is_recognized_case_insensitively(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_SEPARATION_BACKEND": "MSST"}):
            self.assertEqual(sb.separation_backend_name(), "msst")


class ModelRegistryTests(unittest.TestCase):
    def test_default_model_resolves(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASA_MSST_MODEL", None)
            entry = sb._msst_model_entry()
        self.assertEqual(entry["model_type"], "scnet")
        self.assertIn("checkpoint_relpath", entry)

    def test_unknown_model_falls_back_to_default(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_MSST_MODEL": "does_not_exist"}):
            entry = sb._msst_model_entry()
        self.assertEqual(entry, sb._MSST_MODEL_REGISTRY[sb._DEFAULT_MSST_MODEL])

    def test_two_stem_entry_is_not_the_default(self) -> None:
        # Guard: the contract-incomplete 2-stem entry must never be the default.
        self.assertNotEqual(sb._DEFAULT_MSST_MODEL, "bs_roformer_vocals")
        self.assertIn("bs_roformer_vocals", sb._MSST_MODEL_REGISTRY)


class DispatchTests(unittest.TestCase):
    def test_demucs_default_delegates_to_separate_stems(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASA_SEPARATION_BACKEND", None)
            with mock.patch.object(
                sb, "separate_stems", return_value=_SENTINEL_STEMS
            ) as demucs:
                out = sb.separate_stems_backend("/tmp/track.flac", output_dir="/tmp/out")
        demucs.assert_called_once_with("/tmp/track.flac", output_dir="/tmp/out")
        self.assertEqual(out, _SENTINEL_STEMS)

    def test_msst_without_python_env_falls_back_to_demucs(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_SEPARATION_BACKEND": "msst"}, clear=False):
            os.environ.pop("ASA_MSST_PYTHON", None)
            with mock.patch.object(
                sb, "separate_stems", return_value=_SENTINEL_STEMS
            ) as demucs:
                out = sb.separate_stems_backend("/tmp/track.flac")
        demucs.assert_called_once()
        self.assertEqual(out, _SENTINEL_STEMS)

    def test_msst_happy_path_returns_runner_stems(self) -> None:
        # Full chain: separate_stems_backend -> _separate_via_msst_subprocess ->
        # subprocess exits 0 with a valid manifest -> stems returned (no fallback).
        env = {
            "ASA_SEPARATION_BACKEND": "msst",
            "ASA_MSST_PYTHON": __file__,
            "ASA_MSST_ROOT": str(Path(__file__).parent),
        }
        manifest = json.dumps(
            {
                "stems": {
                    "vocals": "/tmp/v.wav",
                    "bass": "/tmp/b.wav",
                    "drums": "/tmp/d.wav",
                    "other": "/tmp/o.wav",
                },
                "modelType": "scnet",
                "loadSeconds": 3.2,
                "inferSeconds": 5.1,
                "device": "cpu",
            }
        )
        with mock.patch.dict(os.environ, env, clear=False), \
            mock.patch.object(Path, "exists", return_value=True), \
            mock.patch.object(Path, "is_dir", return_value=True), \
            mock.patch("separation_backend.os.makedirs"), \
            mock.patch("separation_backend.os.path.isfile", return_value=True), \
            mock.patch("separation_backend.subprocess.run",
                       return_value=_runner_proc(manifest, returncode=0)), \
            mock.patch.object(sb, "separate_stems") as demucs:
            out = sb.separate_stems_backend("/tmp/track.flac", output_dir="/tmp/out")
        demucs.assert_not_called()  # MSST succeeded — no Demucs fallback
        self.assertEqual(
            out,
            {
                "vocals": "/tmp/v.wav",
                "bass": "/tmp/b.wav",
                "drums": "/tmp/d.wav",
                "other": "/tmp/o.wav",
            },
        )

    def test_msst_runner_nonzero_exit_falls_back_to_demucs(self) -> None:
        env = {
            "ASA_SEPARATION_BACKEND": "msst",
            "ASA_MSST_PYTHON": __file__,  # any existing file path
            "ASA_MSST_ROOT": str(Path(__file__).parent),  # any existing dir
        }
        with mock.patch.dict(os.environ, env, clear=False), \
            mock.patch.object(Path, "exists", return_value=True), \
            mock.patch("separation_backend.subprocess.run",
                       return_value=_runner_proc("", returncode=3, stderr="boom")), \
            mock.patch.object(sb, "separate_stems", return_value=_SENTINEL_STEMS) as demucs:
            out = sb.separate_stems_backend("/tmp/track.flac", output_dir="/tmp/out")
        demucs.assert_called_once()
        self.assertEqual(out, _SENTINEL_STEMS)


class RunnerManifestParseTests(unittest.TestCase):
    def test_valid_manifest_returns_existing_stems(self) -> None:
        manifest = json.dumps(
            {
                "stems": {"vocals": "/tmp/v.wav", "bass": "/tmp/b.wav"},
                "modelType": "scnet",
                "loadSeconds": 1.0,
                "inferSeconds": 2.0,
                "device": "cpu",
            }
        )
        with mock.patch("separation_backend.os.path.isfile", return_value=True):
            out = sb._parse_runner_manifest(manifest)
        self.assertEqual(out, {"vocals": "/tmp/v.wav", "bass": "/tmp/b.wav"})

    def test_unparseable_output_returns_none(self) -> None:
        self.assertIsNone(sb._parse_runner_manifest("not json"))

    def test_missing_files_on_disk_returns_none(self) -> None:
        manifest = json.dumps({"stems": {"vocals": "/nope/v.wav"}})
        with mock.patch("separation_backend.os.path.isfile", return_value=False):
            self.assertIsNone(sb._parse_runner_manifest(manifest))


class RunnerHelperTests(unittest.TestCase):
    def test_canonical_name_maps_by_name_not_position(self) -> None:
        # SCNet emits [drums, bass, other, vocals]; mapping is by name.
        self.assertEqual(_runner._canonical_name("Vocals"), "vocals")
        self.assertEqual(_runner._canonical_name("BASS"), "bass")
        self.assertEqual(_runner._canonical_name("instrumental"), "other")
        self.assertIsNone(_runner._canonical_name("piano"))

    def test_to_channels_first_transposes_channels_last(self) -> None:
        # MSSeparator.separate returns channels-last (N, C); writer needs (C, N).
        stem = np.zeros((44100, 2), dtype=np.float32)
        out = _runner._to_channels_first(stem)
        self.assertEqual(out.shape, (2, 44100))

    def test_to_channels_first_keeps_channels_first(self) -> None:
        stem = np.zeros((2, 44100), dtype=np.float32)
        out = _runner._to_channels_first(stem)
        self.assertEqual(out.shape, (2, 44100))

    def test_write_wav_pcm16_roundtrip(self) -> None:
        import tempfile
        import wave

        audio = np.stack([np.linspace(-0.5, 0.5, 100), np.linspace(0.5, -0.5, 100)])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "stem.wav")
            _runner._write_wav_pcm16(path, audio, 44100)
            with wave.open(path, "rb") as handle:
                self.assertEqual(handle.getnchannels(), 2)
                self.assertEqual(handle.getframerate(), 44100)
                self.assertEqual(handle.getnframes(), 100)


class ToggleGatingTests(unittest.TestCase):
    """The NonCommercial-gated, per-user toggle helpers."""

    # A real file + real dir so msst_available()'s existence checks pass.
    _REAL_PY = os.path.realpath(__file__)  # any existing file
    _REAL_DIR = os.path.dirname(os.path.realpath(__file__))  # any existing dir

    def test_msst_available_false_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASA_MSST_PYTHON", None)
            os.environ.pop("ASA_MSST_ROOT", None)
            self.assertFalse(sb.msst_available())

    def test_msst_available_true_when_configured(self):
        with mock.patch.dict(
            os.environ, {"ASA_MSST_PYTHON": self._REAL_PY, "ASA_MSST_ROOT": self._REAL_DIR}
        ):
            self.assertTrue(sb.msst_available())

    def test_msst_available_false_when_paths_missing(self):
        with mock.patch.dict(
            os.environ,
            {"ASA_MSST_PYTHON": "/nope/python", "ASA_MSST_ROOT": "/nope/root"},
        ):
            self.assertFalse(sb.msst_available())

    def test_toggle_requires_both_flag_and_install(self):
        configured = {"ASA_MSST_PYTHON": self._REAL_PY, "ASA_MSST_ROOT": self._REAL_DIR}
        # Flag on + installed -> enabled.
        with mock.patch.dict(os.environ, {**configured, "ASA_ALLOW_MSST_TOGGLE": "1"}):
            self.assertTrue(sb.msst_user_toggle_enabled())
        # Flag on but NOT installed -> disabled.
        with mock.patch.dict(os.environ, {"ASA_ALLOW_MSST_TOGGLE": "true"}, clear=False):
            os.environ.pop("ASA_MSST_PYTHON", None)
            os.environ.pop("ASA_MSST_ROOT", None)
            self.assertFalse(sb.msst_user_toggle_enabled())
        # Installed but flag off -> disabled.
        with mock.patch.dict(os.environ, configured, clear=False):
            os.environ.pop("ASA_ALLOW_MSST_TOGGLE", None)
            self.assertFalse(sb.msst_user_toggle_enabled())

    def test_normalize_forces_demucs_unless_msst_permitted(self):
        # msst only survives when explicitly permitted.
        self.assertEqual(sb.normalize_separation_backend("msst", toggle_enabled=True), "msst")
        self.assertEqual(sb.normalize_separation_backend("MSST", toggle_enabled=True), "msst")
        self.assertEqual(sb.normalize_separation_backend("msst", toggle_enabled=False), "demucs")
        # everything else collapses to the safe default.
        for value in ("demucs", "Demucs", "bogus", "", None, 123):
            self.assertEqual(
                sb.normalize_separation_backend(value, toggle_enabled=True), "demucs"
            )


if __name__ == "__main__":
    unittest.main()
