"""Tests for the one-command recommendation-fixture render intake."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import recommendation_fixture_intake as intake


class MeasurableIntentTests(unittest.TestCase):
    def test_checks_exact_numeric_string_and_directional_targets(self):
        intent = {
            "bpm": {"target": 145, "tolerance": 1, "direction": "exact"},
            "key": {"target": "F minor"},
            "lufsIntegrated": {"target": -7, "tolerance": 2},
            "sidechainDetail.pumpingStrength": {
                "target": 0.5,
                "tolerance": 0.05,
                "direction": "min",
            },
        }
        fingerprint = {
            "bpm": 144.6,
            "key": "F Minor",
            "lufsIntegrated": -8.5,
            "sidechainDetail": {"pumpingStrength": 0.47},
        }

        checks = intake.check_measurable_intent(intent, fingerprint)

        self.assertEqual([check.path for check in checks], list(intent))
        self.assertTrue(all(check.passed for check in checks), checks)

    def test_reports_missing_and_out_of_tolerance_measurements(self):
        checks = intake.check_measurable_intent(
            {
                "bpm": {"target": 145, "tolerance": 1},
                "kickDetail.fundamentalHz": {"target": 45, "tolerance": 15},
            },
            {"bpm": 130},
        )

        self.assertFalse(checks[0].passed)
        self.assertIn("outside", checks[0].message)
        self.assertFalse(checks[1].passed)
        self.assertIn("missing", checks[1].message)

    def test_accepts_the_existing_equals_form_for_categorical_targets(self):
        checks = intake.check_measurable_intent(
            {"acidDetail.isAcid": {"equals": True}},
            {"acidDetail": {"isAcid": True}},
        )

        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0].passed, checks[0])
        self.assertIs(checks[0].target, True)


class RenderContractTests(unittest.TestCase):
    def test_accepts_the_declared_48khz_24bit_render(self):
        issues = intake.check_render_contract(
            {"sampleRateHz": 48000, "bitDepth": 24, "lengthSeconds": 16},
            sample_rate=48000,
            subtype="PCM_24",
            duration_seconds=15.2,
        )

        self.assertEqual(issues, [])

    def test_rejects_wrong_sample_rate_bit_depth_and_length(self):
        issues = intake.check_render_contract(
            {"sampleRateHz": 48000, "bitDepth": 24, "lengthSeconds": 16},
            sample_rate=44100,
            subtype="PCM_16",
            duration_seconds=9.0,
        )

        self.assertEqual(len(issues), 3)
        self.assertIn("sample rate", issues[0])
        self.assertIn("bit depth", issues[1])
        self.assertIn("duration", issues[2])


class DeterministicProjectionTests(unittest.TestCase):
    def test_projects_raw_phase1_into_the_existing_audio_features_contract(self):
        fingerprint = {
            "bpm": 145.2,
            "key": "F Minor",
            "crestFactor": 5.4,
            "durationSeconds": 15.8,
            "bpmConfidence": 0.88,
            "spectralBalance": {
                "subBass": -6.0,
                "lowBass": -10.0,
                "lowMids": -20.0,
                "mids": -25.0,
                "upperMids": -31.0,
                "highs": -42.0,
                "brilliance": -55.0,
            },
            "spectralBalanceTimeSeries": [
                {"subBass": -4.0, "lowBass": -8.0},
                {"subBass": -7.0, "lowBass": -9.0},
            ],
            "spectralDetail": {"spectralCentroid": 2400.0},
            "rhythmDetail": {"onsetRate": 8.2},
        }

        features = intake.project_deterministic_audio_features(fingerprint)

        self.assertEqual(features["key"], {"root": "F", "scale": "minor"})
        self.assertEqual(features["duration"], 15.8)
        self.assertEqual(features["onsetDensity"], 8.2)
        self.assertEqual(features["spectralCentroidMean"], 2400.0)
        self.assertEqual(features["spectralBands"][0], {
            "name": "Sub Bass",
            "rangeHz": [20, 60],
            "averageDb": -6.0,
            "peakDb": -4.0,
            "dominance": "dominant",
        })
        self.assertEqual(features["spectralBands"][-1]["dominance"], "absent")


class VerificationArtifactTests(unittest.TestCase):
    def test_renders_the_frontend_typescript_artifact(self):
        artifact = {
            "fixtures": 1,
            "sources": ["claude"],
            "perDomain": {
                domain: {
                    "support": 1,
                    "meanRecall": 0.5,
                    "meanScore": 0.25,
                    "confidence": "LOW",
                }
                for domain in intake.DOMAINS
            },
        }

        rendered = intake.render_verification_typescript(artifact)

        self.assertIn("Generated from real Ableton renders", rendered)
        self.assertIn("fixtures: 1", rendered)
        self.assertIn('sources: ["claude"]', rendered)
        self.assertIn(
            'kick: { support: 1, meanRecall: 0.5, meanScore: 0.25, confidence: "LOW" }',
            rendered,
        )


class IntakeWorkflowTests(unittest.TestCase):
    def test_one_command_builds_all_pilot_evidence_after_intent_passes(self):
        source_fixture = (
            Path(__file__).parent
            / "fixtures"
            / "recommendation_tracks"
            / "hard_techno_rumble_145"
        )
        fingerprint = {
            "phase1Version": "phase1.v2",
            "bpm": 145.0,
            "key": "F Minor",
            "kickDetail": {"fundamentalHz": 45.0},
            "lufsIntegrated": -7.0,
            "truePeak": -0.3,
            "crestFactor": 5.0,
            "durationSeconds": 15.5,
            "bpmConfidence": 0.9,
            "spectralBalance": {
                "subBass": -8.0,
                "lowBass": -10.0,
                "lowMids": -22.0,
                "mids": -25.0,
                "upperMids": -30.0,
                "highs": -35.0,
                "brilliance": -45.0,
            },
            "spectralDetail": {"spectralCentroid": 2200.0},
            "rhythmDetail": {"onsetRate": 8.0},
        }

        with tempfile.TemporaryDirectory() as tmp:
            corpus_dir = Path(tmp) / "recommendation_tracks"
            fixture_dir = corpus_dir / source_fixture.name
            fixture_dir.mkdir(parents=True)
            shutil.copy2(source_fixture / "manifest.json", fixture_dir / "manifest.json")
            (fixture_dir / "audio.flac").touch()
            ui_artifact = Path(tmp) / "recommendationVerification.ts"

            def fake_run(command, **kwargs):
                if Path(command[1]).name == "analyze.py":
                    return subprocess.CompletedProcess(command, 0, json.dumps(fingerprint), "")
                if command[0] == "node":
                    recs = [{
                        "domain": "kick",
                        "device": "Operator",
                        "parameter": None,
                        "value": None,
                        "citations": [],
                        "family": None,
                    }]
                    return subprocess.CompletedProcess(command, 0, json.dumps(recs), "")
                if Path(command[1]).name == "gen_claude_phase2.py":
                    phase2 = {
                        "abletonRecommendations": [{
                            "trackContext": "Kick",
                            "category": "DYNAMICS",
                            "device": "Operator",
                            "parameter": "Amp Envelope Decay",
                            "value": "250 ms",
                            "phase1Fields": ["kickDetail.fundamentalHz"],
                        }],
                    }
                    (fixture_dir / "phase2.claude.json").write_text(json.dumps(phase2))
                    return subprocess.CompletedProcess(command, 0, "", "")
                raise AssertionError(command)

            result = intake.run_fixture_intake(
                fixture_dir,
                ui_artifact_path=ui_artifact,
                command_runner=fake_run,
                audio_info_reader=lambda _path: SimpleNamespace(
                    samplerate=48000,
                    subtype="PCM_24",
                    duration=15.5,
                ),
            )

            self.assertTrue(result.passed, result)
            self.assertTrue((fixture_dir / "phase1_fingerprint.json").is_file())
            stored_fingerprint = json.loads((fixture_dir / "phase1_fingerprint.json").read_text())
            self.assertEqual(stored_fingerprint["spectralDetail"]["spectralCentroidMean"], 2200.0)
            self.assertTrue((fixture_dir / "recommendations.deterministic.json").is_file())
            scores = json.loads((fixture_dir / "recommendation_scores.json").read_text())
            self.assertEqual([score["source"] for score in scores], [
                "claude",
                "deterministic",
                "baseline",
            ])
            self.assertIn("fixtures: 1", ui_artifact.read_text())


if __name__ == "__main__":
    unittest.main()
