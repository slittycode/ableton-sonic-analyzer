"""Tests for the Phase 2 provider abstraction, MOSS sidecar, and citation eval.

Pure-logic / contract tests — no Essentia, no GPU, no network. Run with the
product venv, or a minimal one: ``python3.11 -m venv .venv && .venv/bin/pip
install fastapi requests httpx uvicorn`` then
``.venv/bin/python -m unittest tests.test_phase2_provider`` from apps/backend.
"""

import json
import os
import unittest
from unittest import mock

import phase2_provider
import phase2_provider_evaluation as evalmod
from moss_sidecar.mock_interpreter import build_mock_phase2_result
from phase2_provider import (
    MossSidecarProvider,
    Phase2ProviderError,
    Phase2ProviderRequest,
    resolve_external_phase2_provider,
    resolve_phase2_provider_name,
)
from server_phase2 import _is_valid_phase2_shape, _validate_phase2_citation_paths


_SAMPLE_PHASE1 = {
    "bpm": 128.0,
    "key": "A Minor",
    "timeSignature": "4/4",
    "sampleRate": 48000,
    "durationSeconds": 16.0,
    "lufsIntegrated": -9.2,
    "lufsRange": 4.1,
    "truePeak": -0.8,
    "crestFactor": 11.2,
    "spectralBalance": {"subBass": 0.2, "lowMid": 0.3},
    "kickDetail": {"fundamentalHz": 55.0},
}


class ResolveProviderTests(unittest.TestCase):
    def test_defaults_to_gemini_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_phase2_provider_name(), "gemini")
            self.assertIsNone(resolve_external_phase2_provider())

    def test_unknown_value_degrades_to_gemini(self):
        with mock.patch.dict(os.environ, {"ASA_PHASE2_PROVIDER": "bogus"}, clear=True):
            self.assertEqual(resolve_phase2_provider_name(), "gemini")
            self.assertIsNone(resolve_external_phase2_provider())

    def test_moss_selected(self):
        with mock.patch.dict(os.environ, {"ASA_PHASE2_PROVIDER": "MOSS"}, clear=True):
            self.assertEqual(resolve_phase2_provider_name(), "moss")
            provider = resolve_external_phase2_provider()
            self.assertIsInstance(provider, MossSidecarProvider)
            self.assertEqual(provider.name, "moss")


class MockInterpreterContractTests(unittest.TestCase):
    def test_mock_is_schema_valid(self):
        result = build_mock_phase2_result(_SAMPLE_PHASE1)
        self.assertTrue(_is_valid_phase2_shape(result), "mock must satisfy the Phase2Result shape")

    def test_mock_citations_all_resolve(self):
        result = build_mock_phase2_result(_SAMPLE_PHASE1)
        invented = _validate_phase2_citation_paths(result, _SAMPLE_PHASE1)
        self.assertEqual(invented, [], f"mock cited non-resolving paths: {invented}")

    def test_mock_grounds_in_supplied_phase1(self):
        result = build_mock_phase2_result(_SAMPLE_PHASE1)
        self.assertEqual(result["projectSetup"]["tempoBpm"], 128.0)
        self.assertIn("A Minor", json.dumps(result))

    def test_mock_is_deterministic(self):
        a = build_mock_phase2_result(_SAMPLE_PHASE1)
        b = build_mock_phase2_result(_SAMPLE_PHASE1)
        self.assertEqual(a, b)

    def test_mock_handles_sparse_phase1(self):
        # Only bpm present — must still be schema-valid with resolving citations.
        sparse = {"bpm": 90.0}
        result = build_mock_phase2_result(sparse)
        self.assertTrue(_is_valid_phase2_shape(result))
        self.assertEqual(_validate_phase2_citation_paths(result, sparse), [])


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class MossSidecarProviderTests(unittest.TestCase):
    def _request(self):
        return Phase2ProviderRequest(
            prompt="PROMPT",
            response_schema={},
            phase1_result=_SAMPLE_PHASE1,
            model_name="moss-audio",
            request_id="req-1",
        )

    def test_success_returns_serialized_result(self):
        result = build_mock_phase2_result(_SAMPLE_PHASE1)
        provider = MossSidecarProvider(base_url="http://x:8200")
        with mock.patch(
            "requests.post",
            return_value=_FakeResponse(200, {"result": result, "provider": "moss-mock"}),
        ):
            response = provider.generate(self._request())
        self.assertIsNotNone(response.text)
        self.assertEqual(json.loads(response.text), result)

    def test_none_result_yields_skip_text(self):
        provider = MossSidecarProvider(base_url="http://x:8200")
        with mock.patch(
            "requests.post",
            return_value=_FakeResponse(200, {"result": None, "provider": "moss-mock"}),
        ):
            response = provider.generate(self._request())
        self.assertIsNone(response.text)

    def test_http_error_raises_typed_error(self):
        provider = MossSidecarProvider(base_url="http://x:8200")
        with mock.patch("requests.post", return_value=_FakeResponse(501, text="not wired")):
            with self.assertRaises(Phase2ProviderError) as ctx:
                provider.generate(self._request())
        self.assertFalse(ctx.exception.retryable)  # 4xx not retryable

    def test_network_error_raises_retryable(self):
        import requests

        provider = MossSidecarProvider(base_url="http://x:8200")
        with mock.patch("requests.post", side_effect=requests.RequestException("boom")):
            with self.assertRaises(Phase2ProviderError) as ctx:
                provider.generate(self._request())
        self.assertTrue(ctx.exception.retryable)


class CitationEvalTests(unittest.TestCase):
    def _track(self):
        return evalmod.CorpusTrack(track_id="t1", manifest={}, phase1=_SAMPLE_PHASE1)

    def test_mock_scores_perfect_citation_accuracy(self):
        track = self._track()
        result = build_mock_phase2_result(_SAMPLE_PHASE1)
        score = evalmod.score_result(track, result, available=True, note="mock")
        self.assertTrue(score.schema_valid)
        self.assertEqual(score.citation_accuracy, 1.0)
        self.assertEqual(score.grounding_coverage, 1.0)
        self.assertGreater(score.cited_path_total, 0)

    def test_invented_path_lowers_accuracy(self):
        track = self._track()
        result = build_mock_phase2_result(_SAMPLE_PHASE1)
        # Inject one invented citation into the first recommendation.
        result["abletonRecommendations"][0]["phase1Fields"] = ["totallyMadeUpField"]
        score = evalmod.score_result(track, result, available=True)
        self.assertIsNotNone(score.citation_accuracy)
        self.assertLess(score.citation_accuracy, 1.0)
        self.assertGreaterEqual(score.invented_path_count, 1)

    def test_unavailable_provider_scores_blocked(self):
        track = self._track()
        score = evalmod.score_result(track, None, available=False, note="no key")
        self.assertFalse(score.available)
        self.assertFalse(score.schema_valid)

    def test_split_blocked_without_gemini_baseline(self):
        tracks = [self._track()]
        mock_agg = evalmod.evaluate_provider(
            "moss-mock",
            lambda t: (build_mock_phase2_result(t.phase1), True, "mock"),
            tracks,
        )
        gemini_agg = evalmod.evaluate_provider(
            "gemini", lambda t: (None, False, "blocked"), tracks, blocked_reason="no key"
        )
        report = evalmod.build_report([mock_agg, gemini_agg])
        self.assertEqual(report["splitVerdicts"]["moss-mock"]["verdict"], "BLOCKED")
        self.assertAlmostEqual(report["providers"]["moss-mock"]["meanCitationAccuracy"], 1.0)


class MossBranchIntegrationTests(unittest.TestCase):
    """Executes the modified server.py function through the MOSS branch.

    This is the test that proves the abstraction is *in-path* (not dead code):
    it calls ``_run_interpretation_request_with_profile_config`` with
    ``ASA_PHASE2_PROVIDER=moss`` and a mocked sidecar HTTP, and asserts the
    result flows through the SAME shared parse/validate tail as Gemini. Requires
    the full backend venv (``import server`` pulls numpy/Essentia); self-skips in
    the lightweight env so the rest of this module still runs.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import server  # noqa: F401
        except Exception as exc:  # pragma: no cover - env-dependent
            raise unittest.SkipTest(f"server import unavailable (needs full venv): {exc}")

    def test_moss_provider_flows_through_shared_tail(self):
        import server

        result = build_mock_phase2_result(_SAMPLE_PHASE1)
        fake = _FakeResponse(200, {"result": result, "provider": "moss-mock"})
        profile_config = server._resolve_interpretation_profile_config("producer_summary")
        with mock.patch.dict(os.environ, {"ASA_PHASE2_PROVIDER": "moss"}, clear=False), \
                mock.patch("requests.post", return_value=fake):
            execution = server._run_interpretation_request_with_profile_config(
                source_path=__file__,  # any real file; mock sidecar ignores content
                filename="loop.flac",
                file_size_bytes=123,
                profile_id="producer_summary",
                profile_config=profile_config,
                measurement_result=_SAMPLE_PHASE1,
                pitch_note_result=None,
                grounding_metadata={},
                model_name="gemini-2.5-flash",
                request_id="itest-moss-1",
            )
        self.assertTrue(execution["ok"], execution)
        self.assertIsNotNone(execution["interpretationResult"])
        self.assertTrue(_is_valid_phase2_shape(execution["interpretationResult"]))

    def test_gemini_default_does_not_touch_sidecar(self):
        import server

        # With the default provider, requests.post must never be called (the
        # native Gemini path is taken). We don't need a key: the GEMINI_NOT_CONFIGURED
        # early-return proves the Gemini branch ran, and the sidecar was untouched.
        with mock.patch.dict(os.environ, {"ASA_PHASE2_PROVIDER": "gemini", "GEMINI_API_KEY": ""},
                             clear=False), \
                mock.patch("requests.post") as posted:
            execution = server._run_interpretation_request_with_profile_config(
                source_path=__file__,
                filename="loop.flac",
                file_size_bytes=123,
                profile_id="producer_summary",
                profile_config=server._resolve_interpretation_profile_config("producer_summary"),
                measurement_result=_SAMPLE_PHASE1,
                pitch_note_result=None,
                grounding_metadata={},
                model_name="gemini-2.5-flash",
                request_id="itest-gem-1",
            )
        posted.assert_not_called()
        self.assertFalse(execution["ok"])
        self.assertEqual(execution["errorCode"], "GEMINI_NOT_CONFIGURED")


class ClassifySplitTests(unittest.TestCase):
    """The DoD's 'offline-good-enough vs Gemini-wins' threshold logic."""

    def _agg(self, name: str, accuracy: float | None) -> evalmod.ProviderAggregate:
        scores = (
            [evalmod.TrackScore(track_id="t", available=True, schema_valid=True,
                                citation_accuracy=accuracy)]
            if accuracy is not None
            else []
        )
        return evalmod.ProviderAggregate(
            provider=name, available=accuracy is not None, track_scores=scores
        )

    def test_candidate_within_margin_is_offline_good_enough(self):
        # Clearly inside the margin (avoid the exact float boundary).
        baseline = self._agg("gemini", 0.90)
        candidate = self._agg("moss", 0.90 - evalmod.OFFLINE_GOOD_ENOUGH_MARGIN + 0.01)
        verdict = evalmod.classify_split(baseline, candidate)
        self.assertEqual(verdict["verdict"], "OFFLINE_GOOD_ENOUGH")

    def test_candidate_outside_margin_is_gemini_wins(self):
        # Clearly outside the margin.
        baseline = self._agg("gemini", 0.90)
        candidate = self._agg("moss", 0.90 - evalmod.OFFLINE_GOOD_ENOUGH_MARGIN - 0.01)
        verdict = evalmod.classify_split(baseline, candidate)
        self.assertEqual(verdict["verdict"], "GEMINI_WINS")
        self.assertLess(verdict["delta"], 0)

    def test_candidate_better_than_baseline_is_offline_good_enough(self):
        baseline = self._agg("gemini", 0.80)
        candidate = self._agg("moss", 0.95)
        verdict = evalmod.classify_split(baseline, candidate)
        self.assertEqual(verdict["verdict"], "OFFLINE_GOOD_ENOUGH")
        self.assertGreater(verdict["delta"], 0)

    def test_missing_baseline_is_blocked(self):
        candidate = self._agg("moss", 0.95)
        verdict = evalmod.classify_split(self._agg("gemini", None), candidate)
        self.assertEqual(verdict["verdict"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
