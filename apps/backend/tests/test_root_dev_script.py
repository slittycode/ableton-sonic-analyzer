import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


class RootDevScriptEnvLoadingTests(unittest.TestCase):
    def _write_temp_repo(self, env_lines: list[str]) -> Path:
        temp_root = Path(tempfile.mkdtemp(prefix="sonic-root-dev-script-"))
        self.addCleanup(lambda: shutil.rmtree(temp_root, ignore_errors=True))

        (temp_root / "scripts").mkdir(parents=True)
        (temp_root / "apps" / "ui").mkdir(parents=True)
        (temp_root / "apps" / "backend" / "venv" / "bin").mkdir(parents=True)

        source_script = Path(__file__).resolve().parents[3] / "scripts" / "dev.sh"
        shutil.copy2(source_script, temp_root / "scripts" / "dev.sh")

        (temp_root / "apps" / "ui" / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        (temp_root / "apps" / "ui" / "package.json").write_text("{}\n", encoding="utf-8")
        (temp_root / "apps" / "backend" / "server.py").write_text("print('stub')\n", encoding="utf-8")
        (temp_root / "apps" / "backend" / "venv" / "bin" / "python").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        return temp_root

    def _source_dev_script(self, repo_root: Path, command: str, extra_env: dict[str, str] | None = None) -> str:
        bash_path = shutil.which("bash")
        if bash_path is None:
            raise AssertionError("bash is required to source scripts/dev.sh in tests.")

        result = subprocess.run(
            [
                bash_path,
                "-lc",
                textwrap.dedent(
                    f"""
                    source "{repo_root / 'scripts' / 'dev.sh'}"
                    {command}
                    """
                ),
            ],
            cwd=repo_root,
            env={**os.environ, **(extra_env or {})},
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"Command failed with code {result.returncode}:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        return result.stdout.strip()

    def test_load_ui_env_file_reads_dotenv_values_when_shell_env_is_missing(self):
        repo_root = self._write_temp_repo(
            [
                'VITE_API_BASE_URL="http://127.0.0.1:9999"',
                'VITE_ENABLE_PHASE2_GEMINI="true"',
                'VITE_GEMINI_API_KEY="dotenv-key"',
                'DISABLE_HMR="true"',
            ]
        )

        output = self._source_dev_script(
            repo_root,
            'unset VITE_API_BASE_URL VITE_ENABLE_PHASE2_GEMINI VITE_GEMINI_API_KEY DISABLE_HMR; '
            'load_ui_env_file; '
            'printf "%s|%s|%s|%s" "${VITE_API_BASE_URL:-}" "${VITE_ENABLE_PHASE2_GEMINI:-}" "${VITE_GEMINI_API_KEY:-}" "${DISABLE_HMR:-}"',
        )

        self.assertEqual(output, "http://127.0.0.1:9999|true|dotenv-key|true")

    def test_load_ui_env_file_preserves_exported_values_over_dotenv(self):
        repo_root = self._write_temp_repo(
            [
                'VITE_API_BASE_URL="http://127.0.0.1:9999"',
                'VITE_ENABLE_PHASE2_GEMINI="false"',
                'VITE_GEMINI_API_KEY="dotenv-key"',
                'DISABLE_HMR="false"',
            ]
        )

        output = self._source_dev_script(
            repo_root,
            'load_ui_env_file; '
            'printf "%s|%s|%s|%s" "${VITE_API_BASE_URL:-}" "${VITE_ENABLE_PHASE2_GEMINI:-}" "${VITE_GEMINI_API_KEY:-}" "${DISABLE_HMR:-}"',
            extra_env={
                "PATH": str(Path("/usr/bin")),
                "VITE_API_BASE_URL": "http://127.0.0.1:8100",
                "VITE_ENABLE_PHASE2_GEMINI": "true",
                "VITE_GEMINI_API_KEY": "exported-key",
                "DISABLE_HMR": "true",
            },
        )

        self.assertEqual(output, "http://127.0.0.1:8100|true|exported-key|true")


if __name__ == "__main__":
    unittest.main()
