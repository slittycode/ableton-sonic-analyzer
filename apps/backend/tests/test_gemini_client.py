"""Unit tests for _build_gemini_client (Vertex AI + ADC vs AI Studio key).

Selection matrix + error paths. No network, no real ADC.

Run:
  ./venv/bin/python -m unittest tests.test_gemini_client
"""

import os
import unittest
from unittest import mock

import server


class GeminiClientBuilderMatrixTests(unittest.TestCase):
    def test_no_project_no_key_raises_not_configured(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(server, "_genai") as _mock_genai,
        ):
            with self.assertRaises(server.GeminiClientBuildError) as ctx:
                server._build_gemini_client()
            self.assertEqual(ctx.exception.error_code, "GEMINI_NOT_CONFIGURED")

    def test_project_only_auto_selects_vertex(self) -> None:
        env = {"GOOGLE_CLOUD_PROJECT": "asa-test-proj"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as mock_genai,
        ):
            mock_client = mock.MagicMock()
            mock_genai.Client.return_value = mock_client
            client, flags = server._build_gemini_client()
            self.assertIs(client, mock_client)
            call = mock_genai.Client.call_args
            self.assertTrue(call.kwargs.get("vertexai"))
            self.assertEqual(call.kwargs.get("project"), "asa-test-proj")
            self.assertEqual(call.kwargs.get("location"), "global")
            self.assertEqual(flags, ["vertex:global"])

    def test_key_only_auto_selects_apistudio(self) -> None:
        env = {"GEMINI_API_KEY": "AIzaSy-test-key"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as mock_genai,
        ):
            mock_client = mock.MagicMock()
            mock_genai.Client.return_value = mock_client
            client, flags = server._build_gemini_client()
            self.assertIs(client, mock_client)
            call = mock_genai.Client.call_args
            self.assertEqual(call.kwargs.get("api_key"), "AIzaSy-test-key")
            self.assertNotIn("vertexai", call.kwargs)
            self.assertEqual(flags, ["apistudio"])

    def test_project_wins_over_key_when_no_override(self) -> None:
        env = {
            "GOOGLE_CLOUD_PROJECT": "proj-wins",
            "GEMINI_API_KEY": "key-loses",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock.MagicMock()
            _, flags = server._build_gemini_client()
            self.assertEqual(flags, ["vertex:global"])

    def test_explicit_vertex_forces_vertex(self) -> None:
        env = {
            "ASA_GEMINI_BACKEND": "vertex",
            "GOOGLE_CLOUD_PROJECT": "forced-vertex",
            "GEMINI_API_KEY": "should-be-ignored",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock.MagicMock()
            _, flags = server._build_gemini_client()
            call = mock_genai.Client.call_args
            self.assertTrue(call.kwargs["vertexai"])
            self.assertEqual(flags, ["vertex:global"])

    def test_explicit_apistudio_forces_apistudio(self) -> None:
        env = {
            "ASA_GEMINI_BACKEND": "apistudio",
            "GEMINI_API_KEY": "forced-key",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock.MagicMock()
            _, flags = server._build_gemini_client()
            call = mock_genai.Client.call_args
            self.assertEqual(call.kwargs["api_key"], "forced-key")
            self.assertEqual(flags, ["apistudio"])

    def test_asa_gcp_project_alias_works(self) -> None:
        env = {"ASA_GCP_PROJECT": "alias-proj"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock.MagicMock()
            _, flags = server._build_gemini_client()
            self.assertEqual(flags, ["vertex:global"])
            call = mock_genai.Client.call_args
            self.assertEqual(call.kwargs.get("project"), "alias-proj")

    def test_location_override_via_google_cloud_location(self) -> None:
        env = {
            "GOOGLE_CLOUD_PROJECT": "loc-proj",
            "GOOGLE_CLOUD_LOCATION": "europe-west1",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock.MagicMock()
            _, flags = server._build_gemini_client()
            self.assertEqual(flags, ["vertex:europe-west1"])

    def test_location_override_via_asa_gcp_location(self) -> None:
        env = {
            "ASA_GCP_PROJECT": "loc-proj",
            "ASA_GCP_LOCATION": "asia-northeast1",
        }
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as mock_genai,
        ):
            mock_genai.Client.return_value = mock.MagicMock()
            _, flags = server._build_gemini_client()
            self.assertEqual(flags, ["vertex:asia-northeast1"])

    def test_explicit_vertex_without_project_raises(self) -> None:
        env = {"ASA_GEMINI_BACKEND": "vertex"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as _mock_genai,
        ):
            with self.assertRaises(server.GeminiClientBuildError) as ctx:
                server._build_gemini_client()
            self.assertEqual(ctx.exception.error_code, "GEMINI_VERTEX_NOT_CONFIGURED")

    def test_explicit_apistudio_without_key_raises(self) -> None:
        env = {"ASA_GEMINI_BACKEND": "apistudio"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as _mock_genai,
        ):
            with self.assertRaises(server.GeminiClientBuildError) as ctx:
                server._build_gemini_client()
            self.assertEqual(ctx.exception.error_code, "GEMINI_NOT_CONFIGURED")

    def test_unknown_backend_value_raises(self) -> None:
        env = {"ASA_GEMINI_BACKEND": "bogus", "GEMINI_API_KEY": "k"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server, "_genai") as _mock_genai,
        ):
            with self.assertRaises(server.GeminiClientBuildError) as ctx:
                server._build_gemini_client()
            self.assertEqual(ctx.exception.error_code, "GEMINI_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
