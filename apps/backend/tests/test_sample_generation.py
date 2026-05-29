"""End-to-end orchestrator tests.

These tests feed synthetic Phase 1 / Phase 2 dicts into `generate_samples`
and assert on the manifest contract documented in
`docs/SAMPLE_GENERATION.md`. The citation array is the chain of custody for
this stage — if a generated sample isn't tied back to a Phase 1 field, the
audition has nothing to justify it.
"""

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sample_generation  # noqa: E402


def _baseline_phase1() -> dict:
    return {
        "bpm": 124.0,
        "bpmConfidence": 0.91,
        "key": "F# minor",
        "keyConfidence": 0.83,
        "kickDetail": {
            "fundamentalHz": 55.0,
            "decayTimeMs": 220.0,
            "confidence": 0.82,
        },
        "melodyDetail": {"placeholder": True},
    }


def _baseline_phase2() -> dict:
    return {
        "trackCharacter": "deep house",
        "styleProfile": {
            "genre": "Deep House",
            "authoritativeMeasurements": {"bpm": 124.0, "key": "F# minor"},
        },
        "sonicElements": {
            "kick": "Punchy sub-heavy kick around 55 Hz.",
            "harmonicContent": "Minor 7th pads, layered piano.",
        },
    }


class OrchestratorTests(unittest.TestCase):
    def test_full_input_produces_all_sample_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = sample_generation.generate_samples(
                run_id="run-1",
                phase1=_baseline_phase1(),
                phase2=_baseline_phase2(),
                output_dir=Path(tmp),
                pitch_note_hints=[1, 2, 3, 5],
                allow_soundfont_backends=False,
            )

            sample_ids = {s["id"] for s in result.manifest["samples"]}
            self.assertIn("tonal_chord_progression", sample_ids)
            self.assertIn("tonal_bass_root", sample_ids)
            self.assertIn("drum_kick", sample_ids)
            self.assertIn("drum_snare", sample_ids)
            self.assertIn("drum_hat", sample_ids)
            self.assertIn("melody_lead", sample_ids)

            # Every WAV file on disk.
            for sample in result.manifest["samples"]:
                wav_path = Path(tmp) / sample["filename"]
                self.assertTrue(wav_path.is_file(), f"missing {wav_path}")
                with wave.open(str(wav_path), "rb") as wav:
                    self.assertGreater(wav.getnframes(), 0)

            # Manifest file written.
            manifest_on_disk = json.loads(result.manifest_path.read_text())
            self.assertEqual(manifest_on_disk["runId"], "run-1")
            self.assertEqual(manifest_on_disk["schemaVersion"], "samples.v1")
            self.assertEqual(manifest_on_disk["synthesisBackend"], "sine_fallback")

    def test_tonal_samples_skipped_when_key_missing(self) -> None:
        phase1 = _baseline_phase1()
        phase1.pop("key")
        with tempfile.TemporaryDirectory() as tmp:
            result = sample_generation.generate_samples(
                run_id="run-no-key",
                phase1=phase1,
                phase2=None,
                output_dir=Path(tmp),
                allow_soundfont_backends=False,
            )
        sample_ids = {s["id"] for s in result.manifest["samples"]}
        self.assertNotIn("tonal_chord_progression", sample_ids)
        self.assertNotIn("tonal_bass_root", sample_ids)
        self.assertNotIn("melody_lead", sample_ids)
        # Drums still emitted.
        self.assertIn("drum_kick", sample_ids)

    def test_low_confidence_key_flags_tonal_samples(self) -> None:
        phase1 = _baseline_phase1()
        phase1["keyConfidence"] = 0.2
        with tempfile.TemporaryDirectory() as tmp:
            result = sample_generation.generate_samples(
                run_id="run-low-confidence",
                phase1=phase1,
                phase2=None,
                output_dir=Path(tmp),
                allow_soundfont_backends=False,
            )
        tonal = [s for s in result.manifest["samples"] if s["category"] == "tonal"]
        self.assertTrue(tonal, "expected tonal samples even at low confidence")
        for sample in tonal:
            self.assertTrue(sample["lowConfidence"])
            self.assertEqual(sample["confidence"], "LOW")
        # Drums shouldn't be flagged off the back of key confidence.
        kick = next(s for s in result.manifest["samples"] if s["id"] == "drum_kick")
        self.assertEqual(kick["confidence"], "HIGH")

    def test_every_sample_cites_or_explains_absence(self) -> None:
        # Chain-of-custody invariant: a sample must either cite a Phase 1
        # field or carry a rationale that explicitly names it as heuristic.
        with tempfile.TemporaryDirectory() as tmp:
            result = sample_generation.generate_samples(
                run_id="run-cite",
                phase1=_baseline_phase1(),
                phase2=_baseline_phase2(),
                output_dir=Path(tmp),
                allow_soundfont_backends=False,
            )
        for sample in result.manifest["samples"]:
            cites = sample["cites"]
            has_phase1 = len(cites["phase1Fields"]) > 0
            rationale = cites["rationale"].lower()
            mentions_heuristic = (
                "heuristic" in rationale or "default" in rationale
            )
            self.assertTrue(
                has_phase1 or mentions_heuristic,
                f"{sample['id']} cites nothing and isn't labeled heuristic: {sample}",
            )

    def test_kick_uses_measured_fundamental_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = sample_generation.generate_samples(
                run_id="run-kick",
                phase1=_baseline_phase1(),
                phase2=None,
                output_dir=Path(tmp),
                allow_soundfont_backends=False,
            )
        kick = next(s for s in result.manifest["samples"] if s["id"] == "drum_kick")
        self.assertEqual(kick["cites"]["phase1Fields"], [
            "kickDetail.fundamentalHz",
            "kickDetail.decayTimeMs",
        ])
        self.assertIn("55", kick["label"])  # "Kick at 55 Hz"

    def test_manifest_records_theory_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = sample_generation.generate_samples(
                run_id="run-backend",
                phase1=_baseline_phase1(),
                phase2=None,
                output_dir=Path(tmp),
                allow_soundfont_backends=False,
            )
        self.assertIn(result.manifest["theoryBackend"], {"pytheory", "fallback"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
