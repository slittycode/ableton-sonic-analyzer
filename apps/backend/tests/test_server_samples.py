"""Contract tests for the audition-sample HTTP helper layer.

We test the helper module directly (rather than spinning up a full FastAPI
TestClient) because the layered server is heavy to boot and the route
handlers themselves are thin wrappers. The helpers are where the precondition
logic, manifest decoration, and artifact persistence happen — and those are
the places a bug would slip through.
"""

import sys
import tempfile
import unittest
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from analysis_runtime import AnalysisRuntime  # noqa: E402
import server_samples  # noqa: E402


def _baseline_snapshot(*, phase2_completed: bool = True) -> dict:
    interpretation = {"status": "completed", "result": {"trackCharacter": "fixture"}}
    if not phase2_completed:
        interpretation = {"status": "ready", "result": None}
    return {
        "stages": {
            "measurement": {
                "status": "completed",
                "result": {
                    "bpm": 124.0,
                    "bpmConfidence": 0.9,
                    "key": "F# minor",
                    "keyConfidence": 0.78,
                    "kickDetail": {
                        "fundamentalHz": 55.0,
                        "decayTimeMs": 240.0,
                        "confidence": 0.8,
                    },
                },
            },
            "interpretation": interpretation,
        }
    }


class ServerSamplesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="asa_server_samples_test_")
        self.runtime = AnalysisRuntime(Path(self.tempdir.name) / "runtime")
        result = self.runtime.create_run(
            filename="test.wav",
            content=b"\x00" * 256,
            mime_type="audio/wav",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="default",
            interpretation_model=None,
        )
        self.run_id = result["runId"]

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_generation_succeeds_with_phase1_only(self) -> None:
        # Phase 2 absent is acceptable; we still emit tonal/drum samples.
        snapshot = _baseline_snapshot(phase2_completed=False)
        manifest = server_samples.generate_and_register_samples(
            runtime=self.runtime,
            run_id=self.run_id,
            snapshot=snapshot,
            force=False,
            allow_soundfont_backends=False,
        )
        self.assertEqual(manifest["schemaVersion"], "samples.v1")
        self.assertIn("manifestArtifactId", manifest)
        # Every sample carries an artifactId for the frontend to dereference.
        for sample in manifest["samples"]:
            self.assertIn(
                "artifactId",
                sample,
                f"sample {sample['id']} missing artifactId",
            )

    def test_rejects_when_measurement_not_completed(self) -> None:
        snapshot = _baseline_snapshot()
        snapshot["stages"]["measurement"]["status"] = "running"
        with self.assertRaises(server_samples.SamplesPreconditionError) as ctx:
            server_samples.generate_and_register_samples(
                runtime=self.runtime,
                run_id=self.run_id,
                snapshot=snapshot,
                allow_soundfont_backends=False,
            )
        self.assertEqual(ctx.exception.code, "MEASUREMENT_NOT_COMPLETED")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_rejects_regeneration_unless_force(self) -> None:
        snapshot = _baseline_snapshot()
        server_samples.generate_and_register_samples(
            runtime=self.runtime,
            run_id=self.run_id,
            snapshot=snapshot,
            allow_soundfont_backends=False,
        )
        with self.assertRaises(server_samples.SamplesPreconditionError) as ctx:
            server_samples.generate_and_register_samples(
                runtime=self.runtime,
                run_id=self.run_id,
                snapshot=snapshot,
                force=False,
                allow_soundfont_backends=False,
            )
        self.assertEqual(ctx.exception.code, "SAMPLES_ALREADY_GENERATED")

    def test_force_regenerates(self) -> None:
        snapshot = _baseline_snapshot()
        first = server_samples.generate_and_register_samples(
            runtime=self.runtime,
            run_id=self.run_id,
            snapshot=snapshot,
            allow_soundfont_backends=False,
        )
        second = server_samples.generate_and_register_samples(
            runtime=self.runtime,
            run_id=self.run_id,
            snapshot=snapshot,
            force=True,
            allow_soundfont_backends=False,
        )
        # New manifest artifact id; the SQLite ids are UUIDs so they will differ.
        self.assertNotEqual(first["manifestArtifactId"], second["manifestArtifactId"])

    def test_fetch_existing_returns_none_before_generation(self) -> None:
        self.assertIsNone(
            server_samples.fetch_existing_manifest(
                runtime=self.runtime, run_id=self.run_id
            )
        )

    def test_fetch_existing_returns_decorated_manifest_after_generation(self) -> None:
        snapshot = _baseline_snapshot()
        created = server_samples.generate_and_register_samples(
            runtime=self.runtime,
            run_id=self.run_id,
            snapshot=snapshot,
            allow_soundfont_backends=False,
        )
        fetched = server_samples.fetch_existing_manifest(
            runtime=self.runtime, run_id=self.run_id
        )
        self.assertIsNotNone(fetched)
        assert fetched is not None  # type narrow for the static checker
        # Same sample IDs, each with an artifactId.
        created_ids = {s["id"] for s in created["samples"]}
        fetched_ids = {s["id"] for s in fetched["samples"]}
        self.assertEqual(created_ids, fetched_ids)
        for sample in fetched["samples"]:
            self.assertIn("artifactId", sample)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
