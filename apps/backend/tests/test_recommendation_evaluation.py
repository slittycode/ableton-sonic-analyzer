"""Unit tests for the recommendation-quality scorer (GOAL.md sub-goal 2).

Pure-stdlib — no Essentia, no network, no rendered audio required. The scoring
logic is exercised with hand-authored fixtures + recommendation sets so the
"does the score move correctly?" gate is fully deterministic and independent of
the needs-fixture corpus audio.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import recommendation_evaluation as rev

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "recommendation_tracks"


def _spec(device: str, params: dict[str, str], family: str = "NATIVE") -> rev.SpecDevice:
    return rev.SpecDevice(
        device=device,
        family=family,
        parameters=tuple(rev.SpecParameter(name=k, value=v) for k, v in params.items()),
    )


def _make_fixture(
    device_spec: dict[str, tuple[rev.SpecDevice, ...]],
    fingerprint: dict | None = None,
) -> rev.Fixture:
    return rev.Fixture(
        slug="synthetic",
        title="synthetic test fixture",
        genre="house",
        audio_path=None,
        device_spec=device_spec,
        measurable_intent=(),
        phase1_fingerprint=fingerprint,
        render={"sampleRateHz": 48000, "bitDepth": 24},
    )


# A small Phase 1 fingerprint that the test citations resolve against.
FINGERPRINT = {
    "bpm": 124,
    "key": "A minor",
    "kickDetail": {"fundamentalHz": 55.0},
    "sidechainDetail": {"pumpingStrength": 0.6, "pumpingRate": 2.07},
    "lufsIntegrated": -9.0,
    "truePeak": 1.0,
}


class ValueParsingTests(unittest.TestCase):
    def test_units_parse(self):
        cases = {
            "4 kHz": (4000.0, "hz"),
            "3500 Hz": (3500.0, "hz"),
            "-15 dB": (-15.0, "db"),
            "200 ms": (200.0, "ms"),
            "1.8 s": (1.8, "s"),
            "3:1": (3.0, "ratio"),
            "30%": (30.0, "pct"),
            "+12st": (12.0, "st"),
            "0.6": (0.6, ""),
        }
        for text, (num, unit) in cases.items():
            pv = rev.parse_value(text)
            self.assertIsNotNone(pv, f"failed to parse {text!r}")
            self.assertAlmostEqual(pv.number, num, places=4, msg=text)
            self.assertEqual(pv.unit, unit, msg=text)

    def test_non_numeric_returns_none(self):
        for text in ("Sine", "Auto", "Lowpass", "On", ""):
            self.assertIsNone(rev.parse_value(text), text)


class ScoreValueTests(unittest.TestCase):
    def test_within_band_full_credit(self):
        self.assertEqual(
            rev.score_value(rev.parse_value("2 dB"), rev.parse_value("3 dB")), 1.0
        )

    def test_right_direction_half_credit(self):
        # Both boosts vs neutral 0 dB, but |1 - 6| = 5 > 3 dB band.
        self.assertEqual(
            rev.score_value(rev.parse_value("1 dB"), rev.parse_value("6 dB")), 0.5
        )

    def test_wrong_direction_zero(self):
        self.assertEqual(
            rev.score_value(rev.parse_value("-4 dB"), rev.parse_value("6 dB")), 0.0
        )

    def test_unit_mismatch_zero(self):
        self.assertEqual(
            rev.score_value(rev.parse_value("4 kHz"), rev.parse_value("4 dB")), 0.0
        )

    def test_hz_relative_band(self):
        # 3200 Hz vs 3500 Hz target, ±20% band = ±700 Hz -> within.
        self.assertEqual(
            rev.score_value(rev.parse_value("3200 Hz"), rev.parse_value("3500 Hz")), 1.0
        )


class DeviceEquivalenceTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(rev.devices_match("Operator", "Operator"))

    def test_equivalent_compressors_match(self):
        # The central equivalence caveat: Compressor satisfies a Glue Compressor spec.
        self.assertTrue(rev.devices_match("Compressor", "Glue Compressor"))
        self.assertTrue(rev.devices_match("Glue Compressor", "Compressor"))

    def test_equivalent_synths_match(self):
        self.assertTrue(rev.devices_match("Wavetable", "Operator"))

    def test_unrelated_devices_do_not_match(self):
        self.assertFalse(rev.devices_match("Reverb", "Operator"))
        self.assertFalse(rev.devices_match("EQ Eight", "Compressor"))


class DomainInferenceTests(unittest.TestCase):
    def test_track_context_wins(self):
        self.assertEqual(rev.infer_domain("Kick bus", "DYNAMICS"), "kick")
        self.assertEqual(rev.infer_domain("Bass", "SYNTHESIS"), "bass")
        self.assertEqual(rev.infer_domain("Pluck lead", "SYNTHESIS"), "melody")

    def test_category_fallback(self):
        self.assertEqual(rev.infer_domain(None, "STEREO"), "stereo")
        self.assertEqual(rev.infer_domain(None, "MASTERING"), "master")

    def test_unknown(self):
        self.assertEqual(rev.infer_domain(None, None), rev.UNKNOWN_DOMAIN)


class CustodyPathTests(unittest.TestCase):
    def test_collect_paths(self):
        paths = rev.collect_phase1_field_paths(FINGERPRINT)
        self.assertIn("kickDetail", paths)
        self.assertIn("kickDetail.fundamentalHz", paths)
        self.assertIn("sidechainDetail.pumpingStrength", paths)

    def test_path_covers_tracked(self):
        self.assertTrue(rev.path_covers_tracked("kickDetail", "kickDetail.fundamentalHz"))
        self.assertTrue(rev.path_covers_tracked("kickDetail.fundamentalHz", "kickDetail"))
        self.assertTrue(
            rev.path_covers_tracked("stemAnalysis.bass.reverbDetail", "stemAnalysis.*.reverbDetail")
        )
        self.assertFalse(rev.path_covers_tracked("kickDetail", "bassDetail"))


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.fixture = _make_fixture(
            {
                "kick": (_spec("Operator", {"Oscillator A Waveform": "Sine", "Amp Envelope Decay": "250 ms"}),),
                "bass": (_spec("Operator", {"Oscillator A Waveform": "Sine", "Filter Frequency": "200 Hz"}),),
                "master": (_spec("Glue Compressor", {"Threshold": "-18 dB", "Ratio": "2:1"}),),
            },
            fingerprint=FINGERPRINT,
        )

    def _good_recs(self) -> list[rev.NormalizedRec]:
        return [
            rev.NormalizedRec("kick", "Operator", "Oscillator A Waveform", "Sine", ("kickDetail.fundamentalHz",)),
            rev.NormalizedRec("kick", "Operator", "Amp Envelope Decay", "240 ms", ("kickDetail.fundamentalHz",)),
            rev.NormalizedRec("bass", "Operator", "Oscillator A Waveform", "Sine", ("sidechainDetail.pumpingStrength",)),
            rev.NormalizedRec("bass", "Operator", "Filter Frequency", "220 Hz", ("bpm",)),
            rev.NormalizedRec("master", "Glue Compressor", "Threshold", "-18 dB", ("lufsIntegrated",)),
            rev.NormalizedRec("master", "Glue Compressor", "Ratio", "2:1", ("truePeak",)),
        ]

    def test_good_recs_score_high(self):
        score = rev.score_recommendations(self.fixture, self._good_recs(), "test-good")
        self.assertGreater(score.aggregate, 0.8)
        # Every specified domain was covered.
        for domain in ("kick", "bass", "master"):
            self.assertEqual(score.domain_scores[domain].role_recall, 1.0)

    def test_known_bad_rec_lowers_score(self):
        """The core sub-goal 2 gate: injecting a known-bad rec moves the score down."""
        good = rev.score_recommendations(self.fixture, self._good_recs(), "good")
        bad_recs = [
            # Wrong device for every domain + no citations.
            rev.NormalizedRec("kick", "Reverb", "Decay Time", "2 s", ()),
            rev.NormalizedRec("bass", "EQ Eight", "Band 1 Gain", "3 dB", ()),
            rev.NormalizedRec("master", "Chorus-Ensemble", "Rate", "0.3 Hz", ()),
        ]
        bad = rev.score_recommendations(self.fixture, bad_recs, "bad")
        self.assertLess(bad.aggregate, good.aggregate)
        self.assertLess(bad.aggregate, 0.2)

    def test_equivalent_device_earns_recall(self):
        """Compressor recommended where the spec says Glue Compressor still recalls."""
        recs = [
            rev.NormalizedRec("master", "Compressor", "Threshold", "-18 dB", ("lufsIntegrated",)),
            rev.NormalizedRec("master", "Compressor", "Ratio", "2:1", ("truePeak",)),
        ]
        score = rev.score_recommendations(self.fixture, recs, "equiv")
        self.assertEqual(score.domain_scores["master"].role_recall, 1.0)

    def test_custody_penalty_applies(self):
        """Stripping citations lowers the aggregate even with full coverage."""
        cited = rev.score_recommendations(self.fixture, self._good_recs(), "cited")
        uncited_recs = [
            rev.NormalizedRec(r.domain, r.device, r.parameter, r.value, ())
            for r in self._good_recs()
        ]
        uncited = rev.score_recommendations(self.fixture, uncited_recs, "uncited")
        self.assertAlmostEqual(cited.raw_aggregate, uncited.raw_aggregate, places=6)
        self.assertLess(uncited.aggregate, cited.aggregate)
        self.assertEqual(uncited.custody.penalty, 0.0)  # nothing cited, no fingerprint credit

    def test_full_coverage_uncited_must_not_outscore_lower_coverage_cited(self):
        """GOAL.md 2.d: a high-coverage result that breaks the chain must not win."""
        # High coverage, zero citations.
        high_uncited = [
            rev.NormalizedRec(r.domain, r.device, r.parameter, r.value, ())
            for r in self._good_recs()
        ]
        # Lower coverage (kick only), but fully + validly cited.
        low_cited = [
            rev.NormalizedRec("kick", "Operator", "Oscillator A Waveform", "Sine", ("kickDetail.fundamentalHz",)),
        ]
        high = rev.score_recommendations(self.fixture, high_uncited, "high-uncited")
        low = rev.score_recommendations(self.fixture, low_cited, "low-cited")
        self.assertGreater(high.raw_aggregate, low.raw_aggregate)  # more coverage
        self.assertGreaterEqual(low.aggregate, high.aggregate)  # but custody wins

    def test_scoring_is_deterministic(self):
        """GOAL.md sub-goal 2.Done: re-running on unchanged inputs is deterministic."""
        recs = self._good_recs()
        first = rev.score_recommendations(self.fixture, recs, "det").as_dict()
        second = rev.score_recommendations(self.fixture, recs, "det").as_dict()
        self.assertEqual(first, second)

    def test_baseline_source_scores_floor(self):
        baseline = rev.score_recommendations(
            self.fixture, rev.normalize_baseline(self.fixture), "baseline"
        )
        self.assertEqual(baseline.aggregate, 0.0)

    def test_report_renders(self):
        score = rev.score_recommendations(self.fixture, self._good_recs(), "rep")
        md = rev.render_markdown_report([score])
        self.assertIn("Recommendation Evaluation Report", md)
        self.assertIn("kick", md)
        self.assertIn("Aggregate", md)


class CorpusVerificationTests(unittest.TestCase):
    """Sub-goal 4 data source: per-domain match rates + support drive the badge."""

    def _fixture(self):
        return _make_fixture(
            {
                "kick": (_spec("Operator", {"Amp Envelope Decay": "250 ms"}),),
                "master": (_spec("Glue Compressor", {"Ratio": "2:1"}),),
            },
            fingerprint=FINGERPRINT,
        )

    def test_empty_scores_degrade_gracefully(self):
        art = rev.aggregate_corpus_verification([])
        self.assertEqual(art["fixtures"], 0)
        for domain in rev.DOMAINS:
            self.assertEqual(art["perDomain"][domain]["support"], 0)
            self.assertEqual(art["perDomain"][domain]["confidence"], "NONE")

    def test_support_drives_confidence_band(self):
        fixture = self._fixture()
        recs = [
            rev.NormalizedRec("kick", "Operator", "Amp Envelope Decay", "240 ms", ("kickDetail.fundamentalHz",)),
            rev.NormalizedRec("master", "Glue Compressor", "Ratio", "2:1", ("lufsIntegrated",)),
        ]
        # Two fixtures' worth of scores -> support 2 -> LOW band (hedged).
        scores = [
            rev.score_recommendations(fixture, recs, "s"),
            rev.score_recommendations(fixture, recs, "s"),
        ]
        art = rev.aggregate_corpus_verification(scores)
        self.assertEqual(art["perDomain"]["kick"]["support"], 2)
        self.assertEqual(art["perDomain"]["kick"]["confidence"], "LOW")
        self.assertGreater(art["perDomain"]["kick"]["meanRecall"], 0.0)
        # A domain no fixture specified stays NONE.
        self.assertEqual(art["perDomain"]["groove"]["confidence"], "NONE")


class IntentCoverageTests(unittest.TestCase):
    """GOAL.md equivalence mechanism: measurableIntent paths earn credit when cited."""

    def _intent_fixture(self):
        return rev.Fixture(
            slug="intent",
            title="intent",
            genre="house",
            audio_path=None,
            device_spec={"kick": (_spec("Operator", {"Amp Envelope Decay": "250 ms"}),)},
            measurable_intent=(
                rev.IntentTarget(path="kickDetail.fundamentalHz", target=55, tolerance=15),
                rev.IntentTarget(path="lufsIntegrated", target=-9, tolerance=2),
            ),
            phase1_fingerprint=FINGERPRINT,
            render={},
        )

    def test_intent_coverage_fraction(self):
        fx = self._intent_fixture()
        recs = [rev.NormalizedRec("kick", "Saturator", "Drive", "8 dB", ("kickDetail.fundamentalHz",))]
        # 1 of 2 intent paths cited.
        self.assertAlmostEqual(rev.intent_coverage(recs, fx), 0.5)

    def test_empty_intent_is_full(self):
        fx = _make_fixture({"kick": (_spec("Operator", {"Amp Envelope Decay": "250 ms"}),)})
        self.assertEqual(rev.intent_coverage([], fx), 1.0)

    def test_intent_credit_rewards_measurement_grounded_recs(self):
        """A processing rec that cites the spec's measurable intent earns credit
        even though it names a different device than the source synth."""
        fx = self._intent_fixture()
        # Names Saturator (not the spec's Operator) but cites both intent paths.
        grounded = [
            rev.NormalizedRec("kick", "Saturator", "Drive", "8 dB",
                              ("kickDetail.fundamentalHz", "lufsIntegrated")),
        ]
        ungrounded = [
            rev.NormalizedRec("kick", "Saturator", "Drive", "8 dB", ("bpm",)),
        ]
        g = rev.score_recommendations(fx, grounded, "grounded")
        u = rev.score_recommendations(fx, ungrounded, "ungrounded")
        self.assertEqual(g.intent_coverage, 1.0)
        self.assertLess(u.intent_coverage, g.intent_coverage)
        self.assertGreater(g.aggregate, u.aggregate)


class Phase2AdapterTests(unittest.TestCase):
    def test_normalize_phase2(self):
        phase2 = {
            "abletonRecommendations": [
                {
                    "device": "Operator",
                    "trackContext": "Kick",
                    "category": "SYNTHESIS",
                    "parameter": "Amp Envelope Decay",
                    "value": "250 ms",
                    "phase1Fields": ["kickDetail.fundamentalHz"],
                },
            ],
            "mixAndMasterChain": [
                {
                    "device": "Glue Compressor",
                    "parameter": "Threshold",
                    "value": "-18 dB",
                    "phase1Fields": ["lufsIntegrated"],
                },
            ],
        }
        recs = rev.normalize_phase2(phase2)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0].domain, "kick")
        self.assertEqual(recs[0].citations, ("kickDetail.fundamentalHz",))
        self.assertEqual(recs[1].domain, "master")  # mix chain defaults to master

    def test_coerce_phase2_payload_unwraps_export_envelope(self):
        """A phase2-export.v1 file (GET .../export/phase2) feeds --phase2 directly."""
        bare = {"abletonRecommendations": [{"device": "Operator"}]}
        envelope = {
            "schemaVersion": "phase2-export.v1",
            "runId": "run-123",
            "phase1": {"bpm": 130.0},
            "phase2": bare,
        }
        self.assertEqual(rev.coerce_phase2_payload(envelope), bare)

    def test_coerce_phase2_payload_passes_bare_result_through(self):
        bare = {"abletonRecommendations": [], "schemaVersion": None}
        self.assertEqual(rev.coerce_phase2_payload(bare), bare)
        # A result that happens to carry an unrelated schemaVersion string is
        # NOT unwrapped — only the phase2-export.* envelope is.
        other = {"schemaVersion": "interpretation.v2", "phase2": {"x": 1}}
        self.assertEqual(rev.coerce_phase2_payload(other), other)


class AuthoredFixtureCatalogTests(unittest.TestCase):
    """Regression: every committed example spec is catalog-valid."""

    def test_example_fixtures_are_catalog_valid(self):
        manifests = sorted(FIXTURE_ROOT.glob("*/manifest.json"))
        self.assertGreaterEqual(len(manifests), 2, "expected >=2 example fixtures")
        corpus_domains: set[str] = set()
        for manifest in manifests:
            fixture = rev.load_fixture(manifest)
            issues = rev.validate_fixture_spec(fixture)
            self.assertEqual(
                issues, [], f"{fixture.slug} has catalog issues: {[i.message for i in issues]}"
            )
            # GOAL.md: each fixture isolates a few decisions (>=3 domains), and the
            # corpus collectively covers the full production surface (invariant #5).
            domains = set(fixture.domains_with_spec())
            self.assertGreaterEqual(
                len(domains), 3, f"{fixture.slug} should exercise at least 3 domains"
            )
            corpus_domains |= domains
        self.assertEqual(
            corpus_domains, set(rev.DOMAINS),
            f"corpus does not cover all domains; missing {set(rev.DOMAINS) - corpus_domains}",
        )

    def test_invalid_spec_is_caught(self):
        bad = _make_fixture(
            {
                "kick": (_spec("Notadevice", {"Foo": "1"}),),
                "bass": (_spec("Operator", {"Nonexistent Param": "1"}),),
            }
        )
        issues = rev.validate_fixture_spec(bad)
        messages = " ".join(i.message for i in issues)
        self.assertIn("not in catalog", messages)
        self.assertIn("not allowed", messages)


if __name__ == "__main__":
    unittest.main()
