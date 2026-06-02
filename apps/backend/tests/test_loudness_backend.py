"""Tests for the selectable loudness backend (WS3b).

The WASM path shells out to the native measure-cli binary, which isn't built in
the Python CI job — so these mock the subprocess and assert the
select/override/fall-back logic in pure Python.
"""

import os
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import loudness_backend as lb


_FAKE_CLI = Path("/fake/measure-cli")

# A representative Essentia loudness block (what analyze_loudness returns).
ESSENTIA_LOUDNESS = {
    "lufsIntegrated": -9.3,
    "lufsRange": 5.2,
    "lufsMomentaryMax": -7.1,
    "lufsShortTermMax": -8.0,
    "lufsCurve": {"shortTerm": [-12.0, -10.0], "momentary": [-11.0, -9.0]},
}


def _cli_proc(stdout: str, returncode: int = 0, stderr: str = "") -> mock.Mock:
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class LoudnessBackendNameTests(unittest.TestCase):
    def test_default_is_essentia(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASA_LOUDNESS_BACKEND", None)
            self.assertEqual(lb.loudness_backend_name(), "essentia")

    def test_unknown_value_falls_back_to_essentia(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_LOUDNESS_BACKEND": "bogus"}):
            self.assertEqual(lb.loudness_backend_name(), "essentia")

    def test_wasm_is_recognized_case_insensitively(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_LOUDNESS_BACKEND": "WASM"}):
            self.assertEqual(lb.loudness_backend_name(), "wasm")


class ApplyLoudnessBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        # 0.1 s of silence at 48 kHz, stereo. Real array so the (mocked) WASM
        # path can write a temp WAV without special-casing.
        self.stereo = np.zeros((4800, 2), dtype=np.float32)

    def test_essentia_default_is_a_noop(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_LOUDNESS_BACKEND": "essentia"}):
            out = lb.apply_loudness_backend(dict(ESSENTIA_LOUDNESS), self.stereo, 48_000)
        self.assertEqual(out, ESSENTIA_LOUDNESS)

    def test_none_stereo_is_a_noop_even_under_wasm(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_LOUDNESS_BACKEND": "wasm"}):
            out = lb.apply_loudness_backend(dict(ESSENTIA_LOUDNESS), None, 48_000)
        self.assertEqual(out, ESSENTIA_LOUDNESS)

    def test_wasm_overrides_lufs_scalars_keeps_curve(self) -> None:
        cli_json = (
            '{"integrated":-14.71,"momentaryMax":-12.53,'
            '"shortTermMax":-13.2,"truePeak":-1.0,"lra":6.04}'
        )
        with mock.patch.dict(os.environ, {"ASA_LOUDNESS_BACKEND": "wasm"}), \
            mock.patch.object(lb, "_measure_cli_path", return_value=_FAKE_CLI), \
            mock.patch.object(lb.subprocess, "run", return_value=_cli_proc(cli_json)):
            out = lb.apply_loudness_backend(dict(ESSENTIA_LOUDNESS), self.stereo, 48_000)

        # The four LUFS scalars are replaced (rounded to the 1-dp contract)...
        self.assertEqual(out["lufsIntegrated"], -14.7)
        self.assertEqual(out["lufsRange"], 6.0)
        self.assertEqual(out["lufsMomentaryMax"], -12.5)
        self.assertEqual(out["lufsShortTermMax"], -13.2)
        # ...while the per-frame curve (Essentia-only) passes through untouched.
        self.assertEqual(out["lufsCurve"], ESSENTIA_LOUDNESS["lufsCurve"])

    def test_wasm_missing_binary_falls_back_to_essentia(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_LOUDNESS_BACKEND": "wasm"}), \
            mock.patch.object(lb, "_measure_cli_path", return_value=None):
            out = lb.apply_loudness_backend(dict(ESSENTIA_LOUDNESS), self.stereo, 48_000)
        self.assertEqual(out, ESSENTIA_LOUDNESS)

    def test_wasm_cli_nonzero_exit_falls_back(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_LOUDNESS_BACKEND": "wasm"}), \
            mock.patch.object(lb, "_measure_cli_path", return_value=_FAKE_CLI), \
            mock.patch.object(lb.subprocess, "run", return_value=_cli_proc("", returncode=1, stderr="boom")):
            out = lb.apply_loudness_backend(dict(ESSENTIA_LOUDNESS), self.stereo, 48_000)
        self.assertEqual(out, ESSENTIA_LOUDNESS)

    def test_wasm_null_integrated_falls_back(self) -> None:
        cli_json = '{"integrated":null,"momentaryMax":null,"shortTermMax":null,"truePeak":null,"lra":null}'
        with mock.patch.dict(os.environ, {"ASA_LOUDNESS_BACKEND": "wasm"}), \
            mock.patch.object(lb, "_measure_cli_path", return_value=_FAKE_CLI), \
            mock.patch.object(lb.subprocess, "run", return_value=_cli_proc(cli_json)):
            out = lb.apply_loudness_backend(dict(ESSENTIA_LOUDNESS), self.stereo, 48_000)
        self.assertEqual(out, ESSENTIA_LOUDNESS)

    def test_wasm_unparseable_output_falls_back(self) -> None:
        with mock.patch.dict(os.environ, {"ASA_LOUDNESS_BACKEND": "wasm"}), \
            mock.patch.object(lb, "_measure_cli_path", return_value=_FAKE_CLI), \
            mock.patch.object(lb.subprocess, "run", return_value=_cli_proc("not json")):
            out = lb.apply_loudness_backend(dict(ESSENTIA_LOUDNESS), self.stereo, 48_000)
        self.assertEqual(out, ESSENTIA_LOUDNESS)


if __name__ == "__main__":
    unittest.main()
