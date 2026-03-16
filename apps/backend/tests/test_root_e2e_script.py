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

        (self.workspace / "scripts").mkdir(parents=True, exist_ok=True)
        (self.workspace / "apps" / "backend" / "venv" / "bin").mkdir(parents=True, exist_ok=True)
        (self.workspace / "apps" / "ui").mkdir(parents=True, exist_ok=True)

        script_source = (self.repo_root / "scripts" / "test-e2e.sh").read_text(encoding="utf-8")
        _write_executable(self.workspace / "scripts" / "test-e2e.sh", script_source)
        _write_executable(
            self.workspace / "apps" / "backend" / "venv" / "bin" / "python",
            "#!/usr/bin/env bash\nexit 0\n",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run_script(self, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(extra_env or {})

        return subprocess.run(
            ["/bin/bash", str(self.workspace / "scripts" / "test-e2e.sh")],
            cwd=self.workspace,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_requires_phase2_flag_before_running(self) -> None:
        completed = self._run_script(
            {
                "VITE_GEMINI_API_KEY": "AIzaSy-valid-key",
            }
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("VITE_ENABLE_PHASE2_GEMINI must be set to true", completed.stderr)

    def test_requires_non_placeholder_gemini_key(self) -> None:
        completed = self._run_script(
            {
                "VITE_ENABLE_PHASE2_GEMINI": "true",
                "VITE_GEMINI_API_KEY": "your_real_key_here",
            }
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("VITE_GEMINI_API_KEY must be set to a real Gemini API key", completed.stderr)


if __name__ == "__main__":
    unittest.main()
