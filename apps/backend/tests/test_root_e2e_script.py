import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class RootE2EScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[3]
        self.temp_dir = tempfile.TemporaryDirectory(prefix="sonic_root_e2e_script_")
        self.workspace = Path(self.temp_dir.name) / "repo"
        self.track_path = Path(self.temp_dir.name) / "reference-track.flac"
        self.track_path.write_bytes(b"fLaC")
        self.npm_log_path = Path(self.temp_dir.name) / "npm-call.log"

        (self.workspace / "bin").mkdir(parents=True, exist_ok=True)
        (self.workspace / "scripts").mkdir(parents=True, exist_ok=True)
        (self.workspace / "apps" / "backend" / "venv" / "bin").mkdir(parents=True, exist_ok=True)
        (self.workspace / "apps" / "ui").mkdir(parents=True, exist_ok=True)

        script_source = (self.repo_root / "scripts" / "test-e2e.sh").read_text(encoding="utf-8")
        _write_executable(self.workspace / "scripts" / "test-e2e.sh", script_source)
        _write_executable(
            self.workspace / "apps" / "backend" / "venv" / "bin" / "python",
            "#!/usr/bin/env bash\nexit 0\n",
        )
        _write_executable(
            self.workspace / "bin" / "python3",
            "#!/usr/bin/env bash\nexit 0\n",
        )
        _write_executable(
            self.workspace / "bin" / "npm",
            (
                "#!/usr/bin/env bash\n"
                f'printf "%s|%s" "$*" "${{VITE_ENABLE_PHASE2_GEMINI:-}}" > "{self.npm_log_path}"\n'
                "exit 0\n"
            ),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run_script(self, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(extra_env or {})
        env["PATH"] = f"{self.workspace / 'bin'}:{env.get('PATH', '')}"

        return subprocess.run(
            ["/bin/bash", str(self.workspace / "scripts" / "test-e2e.sh")],
            cwd=self.workspace,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def _copy_script_to_workspace(self, script_name: str) -> Path:
        source = self.repo_root / "scripts" / script_name
        destination = self.workspace / "scripts" / script_name
        if source.exists():
            _write_executable(destination, source.read_text(encoding="utf-8"))
        return destination

    def _run_named_script(
        self, script_name: str, extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(extra_env or {})
        env["PATH"] = f"{self.workspace / 'bin'}:{env.get('PATH', '')}"

        return subprocess.run(
            ["/bin/bash", str(self.workspace / "scripts" / script_name)],
            cwd=self.workspace,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_requires_phase2_flag_before_running(self) -> None:
        completed = self._run_script(
            {
                "TEST_FLAC_PATH": str(self.track_path),
                "GEMINI_API_KEY": "AIzaSy-valid-key",
            }
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("VITE_ENABLE_PHASE2_GEMINI must be set to true", completed.stderr)

    def test_requires_track_path_before_running(self) -> None:
        completed = self._run_script(
            {
                "VITE_ENABLE_PHASE2_GEMINI": "true",
                "GEMINI_API_KEY": "AIzaSy-valid-key",
            }
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("TEST_FLAC_PATH must point to a readable audio file", completed.stderr)

    def test_requires_non_placeholder_backend_gemini_key(self) -> None:
        completed = self._run_script(
            {
                "TEST_FLAC_PATH": str(self.track_path),
                "VITE_ENABLE_PHASE2_GEMINI": "true",
                "GEMINI_API_KEY": "your_real_key_here",
            }
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("GEMINI_API_KEY must be set to a real Gemini API key", completed.stderr)

    def test_script_verifies_canonical_analysis_run_routes(self) -> None:
        script_text = (self.workspace / "scripts" / "test-e2e.sh").read_text(encoding="utf-8")
        self.assertIn("/api/analysis-runs/estimate", script_text)
        self.assertIn("/api/analysis-runs", script_text)
        self.assertIn("/api/analysis-runs/{run_id}", script_text)

    def test_integration_script_exists_and_runs_without_live_gemini_prerequisites(self) -> None:
        integration_script = self._copy_script_to_workspace("test-e2e-integration.sh")
        self.assertTrue(
            integration_script.exists(),
            "Expected scripts/test-e2e-integration.sh to exist at the repo root.",
        )

        completed = self._run_named_script("test-e2e-integration.sh")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse("GEMINI_API_KEY must be set to a real Gemini API key" in completed.stderr)
        self.assertFalse("TEST_FLAC_PATH must point to a readable audio file" in completed.stderr)
        self.assertFalse("VITE_ENABLE_PHASE2_GEMINI must be set to true" in completed.stderr)
        self.assertEqual(
            self.npm_log_path.read_text(encoding="utf-8"),
            "run test:e2e:integration|false",
        )

    def test_integration_script_verifies_canonical_analysis_run_routes(self) -> None:
        integration_script = self._copy_script_to_workspace("test-e2e-integration.sh")
        self.assertTrue(
            integration_script.exists(),
            "Expected scripts/test-e2e-integration.sh to exist at the repo root.",
        )

        script_text = integration_script.read_text(encoding="utf-8")
        self.assertIn("/api/analysis-runs/estimate", script_text)
        self.assertIn("/api/analysis-runs", script_text)
        self.assertIn("/api/analysis-runs/{run_id}", script_text)


if __name__ == "__main__":
    unittest.main()
