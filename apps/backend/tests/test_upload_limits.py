import json
import subprocess
import sys
import unittest
from pathlib import Path

import upload_limits


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parents[1]


class UploadLimitContractTests(unittest.TestCase):
    def test_contract_constants_match_expected_values(self) -> None:
        self.assertEqual(upload_limits.MAX_UPLOAD_SIZE_BYTES, 104_857_600)
        self.assertEqual(upload_limits.UPLOAD_REQUEST_SIZE_SLACK_BYTES, 1_048_576)
        self.assertEqual(upload_limits.MAX_UPLOAD_REQUEST_BYTES, 105_906_176)
        self.assertEqual(
            upload_limits.UPLOAD_LIMITED_POST_PATHS,
            (
                "/api/analysis-runs",
                "/api/analysis-runs/estimate",
                "/api/analyze",
                "/api/analyze/estimate",
                "/api/phase2",
            ),
        )

    def test_generator_outputs_machine_readable_json(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/render_upload_limit_contract.py",
                "--format",
                "json",
            ],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["rawAudioLimitBytes"], upload_limits.MAX_UPLOAD_SIZE_BYTES)
        self.assertEqual(payload["requestEnvelopeLimitBytes"], upload_limits.MAX_UPLOAD_REQUEST_BYTES)
        self.assertEqual(payload["protectedPostRoutes"], list(upload_limits.UPLOAD_LIMITED_POST_PATHS))

    def test_generator_outputs_plain_english_and_proxy_snippets(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/render_upload_limit_contract.py",
            ],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("Plain English", result.stdout)
        self.assertIn("nginx", result.stdout)
        self.assertIn("Caddy", result.stdout)
        self.assertIn("Traefik", result.stdout)
        self.assertIn(str(upload_limits.MAX_UPLOAD_REQUEST_BYTES), result.stdout)

    def test_docs_reference_generator_and_current_contract_values(self) -> None:
        root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        backend_readme = (BACKEND_DIR / "README.md").read_text(encoding="utf-8")
        architecture_doc = (BACKEND_DIR / "ARCHITECTURE.md").read_text(encoding="utf-8")

        expected_command = "./venv/bin/python scripts/render_upload_limit_contract.py"
        self.assertIn(expected_command, root_readme)
        self.assertIn(expected_command, backend_readme)
        self.assertIn("upload limit contract", architecture_doc.lower())

        self.assertIn(str(upload_limits.MAX_UPLOAD_REQUEST_BYTES), backend_readme)
        self.assertIn(f"{upload_limits.MAX_UPLOAD_REQUEST_BYTES:,}".replace(",", ""), backend_readme)
        self.assertIn(f"{upload_limits.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MiB", root_readme)


if __name__ == "__main__":
    unittest.main()
