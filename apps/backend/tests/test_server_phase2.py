"""Server-side Phase 2 tests — the inline-vs-Files-API decision at 100 MiB.

The existing ``Phase2EndpointTests`` in ``test_server.py`` covers most of
the Gemini endpoint behavior (model whitelisting, API-key handling, salvage
warnings, citation paths, style-profile authoritative-measurement overrides).
The specific gap this file fills is the **upload-mode branch** in
``server._run_interpretation_request_with_profile_config``:

    if file_size_bytes <= INLINE_SIZE_LIMIT:
        flags_used.append("inline")    # base64-inline upload
    else:
        flags_used.append("files-api") # Gemini Files API upload

A regression that flips the comparison (e.g. ``>`` instead of ``<=``) would
silently route every upload through the wrong path. Until now there was no
test that asserts which branch is taken at the 100 MiB boundary.

These tests require Essentia (server.py imports analyze.py at module load,
which exits when essentia is missing). They will run in the real backend
venv and skip cleanly in environments without it.
"""

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# Attempt to import server. server.py imports analyze.py at module level,
# which ``sys.exit(1)``s if Essentia is missing.
server = None
try:
    server = importlib.import_module("server")
except (ImportError, SystemExit):
    server = None


def _valid_phase2_response() -> dict:
    """Minimal valid Phase 2 response payload — patterned after
    ``_valid_phase2_result`` in ``test_server.py`` but trimmed to just what
    the validation pipeline requires to return ok=True without warnings."""
    return {
        "trackCharacter": "Driving techno groove at 128 BPM.",
        "projectSetup": {
            "tempoBpm": 128,
            "timeSignature": "4/4",
            "sampleRate": 48000,
            "bitDepth": 24,
            "headroomTarget": "-6 dB",
            "sessionGoal": "Rebuild a tight groove from measurements.",
        },
        "trackLayout": [],
        "routingBlueprint": {
            "sidechainSource": "Kick",
            "sidechainTargets": [],
            "returns": [],
            "notes": [],
        },
        "warpGuide": {},
        "abletonRecommendations": [],
        "mixAndMasterChain": [],
        "secretSauce": {"workflowSteps": []},
    }


def _build_mock_genai(response_payload: dict):
    """Build a (mock_client, mock_genai_module, mock_genai_types) triple that
    matches what server.py expects: ``_genai.Client(api_key=...)`` returning
    a client whose ``.models.generate_content(...)`` returns a response with
    ``.text`` set to the JSON payload, and ``.files.upload(...)`` returning a
    file handle with ``.uri`` and ``.mime_type``."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(response_payload)

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response

    uploaded_file = MagicMock()
    uploaded_file.uri = "gs://files/fake-upload-id"
    uploaded_file.mime_type = "audio/mpeg"
    mock_files = MagicMock()
    mock_files.upload.return_value = uploaded_file

    mock_client = MagicMock()
    mock_client.models = mock_models
    mock_client.files = mock_files
    return mock_client


@unittest.skipUnless(server is not None, "server module requires Essentia at import")
class InlineVsFilesApiBranchTests(unittest.TestCase):
    """The branch at server.py:1535 routes uploads through inline base64
    (≤100 MiB) or the Gemini Files API (>100 MiB). Assert flags_used carries
    the correct marker for each side of the threshold."""

    def _run_interpretation(self, *, file_size_bytes: int):
        payload = _valid_phase2_response()
        mock_client = _build_mock_genai(payload)

        with tempfile.TemporaryDirectory(prefix="asa_inline_files_api_") as temp_dir:
            audio_path = Path(temp_dir) / "track.mp3"
            # Real on-disk size doesn't need to match file_size_bytes — the
            # function takes file_size_bytes as a parameter and uses it for
            # the branch decision. We just need a readable file.
            audio_path.write_bytes(b"fake-audio-bytes")

            profile_config = server._resolve_interpretation_profile_config("producer_summary")

            with (
                patch.object(server, "_GENAI_AVAILABLE", True),
                patch.dict(server.os.environ, {"GEMINI_API_KEY": "fake-key"}),
                patch.object(server, "_genai") as mock_genai,
                patch.object(server, "_genai_types") as mock_genai_types,
            ):
                mock_genai.Client.return_value = mock_client
                mock_genai_types.GenerateContentConfig.return_value = MagicMock()
                mock_genai_types.UploadFileConfig.return_value = MagicMock()

                execution = server._run_interpretation_request_with_profile_config(
                    source_path=str(audio_path),
                    filename=audio_path.name,
                    file_size_bytes=file_size_bytes,
                    profile_id="producer_summary",
                    profile_config=profile_config,
                    measurement_result={"bpm": 128},
                    pitch_note_result=None,
                    grounding_metadata={"profileId": "producer_summary"},
                    model_name="gemini-3.1-pro-preview",
                    request_id="inline-files-api-test",
                )

            return execution, mock_client

    def test_small_file_uses_inline_branch(self):
        """A 1 MiB upload must route through the inline-base64 path."""
        execution, mock_client = self._run_interpretation(file_size_bytes=1024 * 1024)
        flags = execution["diagnostics"].get("flagsUsed", [])
        self.assertIn("inline", flags)
        self.assertNotIn("files-api", flags)
        # Inline path uses ``client.models.generate_content`` directly,
        # never ``client.files.upload``.
        mock_client.files.upload.assert_not_called()

    def test_file_at_exact_threshold_uses_inline_branch(self):
        """At the 100 MiB boundary the comparison is ``<=`` — equal-size
        uploads stay inline."""
        execution, mock_client = self._run_interpretation(file_size_bytes=server.INLINE_SIZE_LIMIT)
        flags = execution["diagnostics"].get("flagsUsed", [])
        self.assertIn("inline", flags)
        mock_client.files.upload.assert_not_called()

    def test_file_above_threshold_uses_files_api_branch(self):
        """101 MiB → ``client.files.upload`` is called and the Files-API
        flag is set."""
        execution, mock_client = self._run_interpretation(
            file_size_bytes=server.INLINE_SIZE_LIMIT + 1,
        )
        flags = execution["diagnostics"].get("flagsUsed", [])
        self.assertIn("files-api", flags)
        self.assertNotIn("inline", flags)
        mock_client.files.upload.assert_called_once()


@unittest.skipUnless(server is not None, "server module requires Essentia at import")
class InlineSizeLimitConstantTests(unittest.TestCase):
    """The 100 MiB threshold is a Google-documented number, not a guess.
    Pin the constant so a refactor can't accidentally drift it."""

    def test_inline_size_limit_is_one_hundred_mebibytes(self):
        self.assertEqual(server.INLINE_SIZE_LIMIT, 104_857_600)
        self.assertEqual(server.INLINE_SIZE_LIMIT, 100 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
