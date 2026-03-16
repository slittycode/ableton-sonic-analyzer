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


class BootstrapScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[3]
        self.temp_dir = tempfile.TemporaryDirectory(prefix="sonic_analyzer_bootstrap_tests_")
        self.workspace = Path(self.temp_dir.name)
        self.bin_dir = self.workspace / "bin"
        self.bin_dir.mkdir(parents=True, exist_ok=True)

        dirname_path = shutil.which("dirname")
        if dirname_path is None:
            self.fail("dirname command is required for script tests")

        os.symlink(dirname_path, self.bin_dir / "dirname")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run_script(self, script_path: Path, path_entries: list[str]) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join(path_entries)
        return subprocess.run(
            ["/bin/bash", str(script_path)],
            cwd=script_path.parent,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_root_dev_script_points_to_backend_bootstrap_when_venv_missing(self) -> None:
        workspace_root = self.workspace / "repo"
        scripts_dir = workspace_root / "scripts"
        ui_dir = workspace_root / "apps" / "ui"
        backend_dir = workspace_root / "apps" / "backend"
        backend_scripts_dir = backend_dir / "scripts"

        scripts_dir.mkdir(parents=True, exist_ok=True)
        ui_dir.mkdir(parents=True, exist_ok=True)
        backend_scripts_dir.mkdir(parents=True, exist_ok=True)

        script_source = (self.repo_root / "scripts" / "dev.sh").read_text(encoding="utf-8")
        script_path = scripts_dir / "dev.sh"
        _write_executable(script_path, script_source)

        (ui_dir / "package.json").write_text("{}", encoding="utf-8")
        (backend_dir / "server.py").write_text("print('stub')\n", encoding="utf-8")

        for command_name in ("grep", "lsof", "npm", "python3"):
            _write_executable(self.bin_dir / command_name, "#!/usr/bin/env bash\nexit 0\n")

        completed = self._run_script(script_path, [str(self.bin_dir)])

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Missing backend virtualenv", completed.stderr)
        self.assertIn("./apps/backend/scripts/bootstrap.sh", completed.stderr)

    def test_backend_bootstrap_fails_fast_without_python311(self) -> None:
        workspace_root = self.workspace / "repo"
        backend_scripts_dir = workspace_root / "apps" / "backend" / "scripts"
        backend_scripts_dir.mkdir(parents=True, exist_ok=True)

        script_source = (self.repo_root / "apps" / "backend" / "scripts" / "bootstrap.sh").read_text(
            encoding="utf-8"
        )
        script_path = backend_scripts_dir / "bootstrap.sh"
        _write_executable(script_path, script_source)

        completed = self._run_script(script_path, [str(self.bin_dir)])

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("python3.11", completed.stderr)
        self.assertIn("Install Python 3.11", completed.stderr)


if __name__ == "__main__":
    unittest.main()
