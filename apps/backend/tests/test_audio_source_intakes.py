import math
import struct
import tempfile
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from starlette.testclient import TestClient

import server

from analysis_runtime import (
    AnalysisRuntime,
    AudioSourceIntakeCapacityError,
    AudioSourceIntakeStateError,
)


class AudioSourceIntakeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="asa_intakes_")
        self.runtime = AnalysisRuntime(Path(self.temp_dir.name) / "runtime")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create(self, owner="user-1"):
        return self.runtime.create_audio_source_intake(
            owner_user_id=owner,
            provider="direct",
            raw_url="https://example.com/private-token?signature=secret",
            rights_confirmed=True,
        )

    def _ready(self, owner="user-1"):
        intake = self._create(owner)
        reserved = self.runtime.reserve_next_audio_source_intake()
        self.assertEqual(reserved["intakeId"], intake["intakeId"])
        source = Path(self.temp_dir.name) / f"{owner}.wav"
        source.write_bytes(b"same-source-bytes")
        return self.runtime.complete_audio_source_intake(
            intake["intakeId"],
            source_path=str(source),
            filename="track.wav",
            mime_type="audio/wav",
            metadata={
                "title": "Track",
                "creator": "Artist",
                "durationSeconds": 42.0,
                "attributionUrl": "https://example.com/track",
                "experimental": False,
            },
        )

    def test_rights_confirmation_and_safe_public_snapshot(self):
        with self.assertRaises(ValueError):
            self.runtime.create_audio_source_intake(
                owner_user_id="user-1",
                provider="direct",
                raw_url="https://example.com/a.mp3",
                rights_confirmed=False,
            )
        intake = self._create()
        self.assertNotIn("rawUrl", intake)
        self.assertNotIn("secret", str(intake))

    def test_one_active_per_owner_and_four_globally(self):
        self._create("user-1")
        with self.assertRaises(AudioSourceIntakeCapacityError):
            self._create("user-1")
        self._create("user-2")
        self._create("user-3")
        self._create("user-4")
        with self.assertRaises(AudioSourceIntakeCapacityError):
            self._create("user-5")

    def test_global_capacity_is_atomic_under_concurrent_creates(self):
        def create(index):
            try:
                self._create(f"parallel-{index}")
                return True
            except AudioSourceIntakeCapacityError:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(create, range(8)))
        self.assertEqual(sum(outcomes), 4)
        with self.runtime._connect() as conn:
            active = conn.execute(
                "SELECT COUNT(*) FROM audio_source_intakes WHERE status = 'queued'"
            ).fetchone()[0]
        self.assertEqual(active, 4)

    def test_ready_intake_has_expiry_and_adopts_artifact_without_copy(self):
        ready = self._ready()
        self.assertEqual(ready["status"], "ready")
        self.assertIsNotNone(ready["expiresAt"])
        self.assertEqual(ready["metadata"]["sizeBytes"], len(b"same-source-bytes"))
        with self.runtime._connect() as conn:
            staged_path = conn.execute(
                "SELECT artifact_path FROM audio_source_intakes WHERE id = ?", (ready["intakeId"],)
            ).fetchone()[0]

        created = self.runtime.create_run_from_intake(
            ready["intakeId"],
            owner_user_id="user-1",
            analysis_mode="full",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )
        retry = self.runtime.create_run_from_intake(
            ready["intakeId"],
            owner_user_id="user-1",
            analysis_mode="full",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )
        self.assertEqual(created, retry)
        snapshot = self.runtime.get_run(created["runId"], owner_user_id="user-1")
        self.assertEqual(snapshot["source"]["provider"], "direct")
        self.assertEqual(snapshot["source"]["title"], "Track")
        self.assertNotIn("signature", str(snapshot))
        with self.runtime._connect() as conn:
            run_path = conn.execute(
                "SELECT path FROM run_artifacts WHERE run_id = ? AND kind = 'source_audio'",
                (created["runId"],),
            ).fetchone()[0]
            intake_row = conn.execute(
                "SELECT status, raw_url, artifact_path FROM audio_source_intakes WHERE id = ?",
                (ready["intakeId"],),
            ).fetchone()
        self.assertEqual(staged_path, run_path)
        self.assertEqual(tuple(intake_row), ("completed", None, None))

    def test_interrupt_is_cooperative_and_clears_url(self):
        intake = self._create()
        self.runtime.reserve_next_audio_source_intake()
        interrupted = self.runtime.interrupt_audio_source_intake(
            intake["intakeId"], owner_user_id="user-1"
        )
        self.assertEqual(interrupted["status"], "interrupted")
        self.assertTrue(self.runtime.is_audio_source_intake_cancelled(intake["intakeId"]))
        with self.runtime._connect() as conn:
            raw_url = conn.execute(
                "SELECT raw_url FROM audio_source_intakes WHERE id = ?", (intake["intakeId"],)
            ).fetchone()[0]
        self.assertIsNone(raw_url)

    def test_restart_recovery_interrupts_work_and_removes_temp_directories(self):
        intake = self._create()
        self.runtime.reserve_next_audio_source_intake()
        orphan = self.runtime.runtime_dir / "asa_intake_orphan"
        orphan.mkdir()
        (orphan / "source.tmp").write_bytes(b"partial")
        self.runtime.recover_incomplete_attempts()
        recovered = self.runtime.get_audio_source_intake(intake["intakeId"], owner_user_id="user-1")
        self.assertEqual(recovered["status"], "interrupted")
        self.assertFalse(orphan.exists())

    def test_ready_intake_expires_and_deletes_staged_artifact(self):
        ready = self._ready()
        with self.runtime._connect() as conn:
            row = conn.execute(
                "SELECT artifact_path FROM audio_source_intakes WHERE id = ?", (ready["intakeId"],)
            ).fetchone()
            artifact_path = self.runtime.resolve_artifact_local_path(row["artifact_path"])
            conn.execute(
                "UPDATE audio_source_intakes SET expires_at = ? WHERE id = ?",
                ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), ready["intakeId"]),
            )
        self.assertTrue(artifact_path and artifact_path.exists())
        expired = self.runtime.get_audio_source_intake(ready["intakeId"], owner_user_id="user-1")
        self.assertEqual(expired["status"], "expired")
        self.assertFalse(artifact_path and artifact_path.exists())

    def test_api_and_worker_runtime_instances_share_intake_state(self):
        worker_runtime = AnalysisRuntime(self.runtime.runtime_dir)
        intake = self._create()
        reserved = worker_runtime.reserve_next_audio_source_intake()
        self.assertEqual(reserved["intakeId"], intake["intakeId"])
        source = Path(self.temp_dir.name) / "shared.wav"
        source.write_bytes(b"shared-audio")
        worker_runtime.complete_audio_source_intake(
            intake["intakeId"],
            source_path=str(source),
            filename="shared.wav",
            mime_type="audio/wav",
            metadata={"title": "Shared", "durationSeconds": 10.0, "experimental": False},
        )
        self.assertEqual(
            self.runtime.get_audio_source_intake(intake["intakeId"], owner_user_id="user-1")["status"],
            "ready",
        )
        created = self.runtime.create_run_from_intake(
            intake["intakeId"],
            owner_user_id="user-1",
            analysis_mode="standard",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )
        measurement_job = worker_runtime.reserve_next_measurement_run()
        self.assertEqual(measurement_job["runId"], created["runId"])

    def test_consumption_requires_ready_and_correct_owner(self):
        intake = self._create()
        with self.assertRaises(PermissionError):
            self.runtime.get_audio_source_intake(intake["intakeId"], owner_user_id="other")
        with self.assertRaises(AudioSourceIntakeStateError):
            self.runtime.create_run_from_intake(
                intake["intakeId"],
                owner_user_id="user-1",
                analysis_mode="full",
                pitch_note_mode="off",
                pitch_note_backend="auto",
                interpretation_mode="off",
                interpretation_profile="producer_summary",
                interpretation_model=None,
            )


class AudioSourceIntakeRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="asa_intake_routes_")
        self.previous_runtime = server._ANALYSIS_RUNTIME
        self.runtime = AnalysisRuntime(Path(self.temp_dir.name) / "runtime")
        server._ANALYSIS_RUNTIME = self.runtime
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        server._ANALYSIS_RUNTIME = self.previous_runtime
        self.temp_dir.cleanup()

    def test_capabilities_and_full_route_handoff(self):
        capabilities = self.client.get("/api/audio-source-capabilities")
        self.assertEqual(capabilities.status_code, 200)
        self.assertEqual(capabilities.json()["limits"]["maxDurationSeconds"], 900)

        denied = self.client.post(
            "/api/audio-source-intakes",
            json={"url": "https://example.com/track.wav", "rightsConfirmed": False},
        )
        self.assertEqual(denied.status_code, 400)

        created = self.client.post(
            "/api/audio-source-intakes",
            json={"url": "https://example.com/track.wav?token=private", "rightsConfirmed": True},
        )
        self.assertEqual(created.status_code, 202)
        intake_id = created.json()["intakeId"]
        self.assertNotIn("private", created.text)

        self.runtime.reserve_next_audio_source_intake()
        source = Path(self.temp_dir.name) / "track.wav"
        source.write_bytes(b"route-audio")
        self.runtime.complete_audio_source_intake(
            intake_id,
            source_path=str(source),
            filename="track.wav",
            mime_type="audio/wav",
            metadata={
                "title": "Route Track",
                "creator": "Route Artist",
                "durationSeconds": 30.0,
                "attributionUrl": "https://example.com/track",
                "experimental": False,
            },
        )

        options = {
            "analysisMode": "standard",
            "pitchNoteMode": "off",
            "pitchNoteBackend": "auto",
            "interpretationMode": "off",
            "interpretationProfile": "producer_summary",
            "mt3Mode": "off",
        }
        estimate = self.client.post(f"/api/audio-source-intakes/{intake_id}/estimate", json=options)
        self.assertEqual(estimate.status_code, 200)
        self.assertEqual(estimate.json()["estimate"]["durationSeconds"], 30.0)

        run_response = self.client.post(
            f"/api/audio-source-intakes/{intake_id}/analysis-runs", json=options
        )
        retry_response = self.client.post(
            f"/api/audio-source-intakes/{intake_id}/analysis-runs", json=options
        )
        self.assertEqual(run_response.status_code, 202)
        self.assertEqual(run_response.json()["runId"], retry_response.json()["runId"])
        run_id = run_response.json()["runId"]

        snapshot = self.client.get(f"/api/analysis-runs/{run_id}")
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["source"]["title"], "Route Track")
        self.assertNotIn("private", snapshot.text)
        playback = self.client.get(f"/api/analysis-runs/{run_id}/source-audio")
        self.assertEqual(playback.status_code, 200)
        self.assertEqual(playback.content, b"route-audio")

    def test_upload_and_link_artifacts_produce_identical_hash_and_phase1(self):
        fixture = Path(self.temp_dir.name) / "parity.wav"
        sample_rate = 22050
        with wave.open(str(fixture), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            samples = [
                int(0.25 * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
                for index in range(sample_rate * 3)
            ]
            wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
        audio_bytes = fixture.read_bytes()

        uploaded = self.runtime.create_run(
            filename="parity.wav",
            content=audio_bytes,
            mime_type="audio/wav",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
            analysis_mode="standard",
        )
        intake = self.runtime.create_audio_source_intake(
            owner_user_id="local-dev",
            provider="direct",
            raw_url="https://example.com/parity.wav",
            rights_confirmed=True,
        )
        self.runtime.reserve_next_audio_source_intake()
        self.runtime.complete_audio_source_intake(
            intake["intakeId"],
            source_path=str(fixture),
            filename="parity.wav",
            mime_type="audio/wav",
            metadata={"title": "Parity", "durationSeconds": 3.0, "experimental": False},
        )
        linked = self.runtime.create_run_from_intake(
            intake["intakeId"],
            owner_user_id="local-dev",
            analysis_mode="standard",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )

        for _ in range(2):
            job = self.runtime.reserve_next_measurement_run()
            self.assertIsNotNone(job)
            server._execute_reserved_measurement_job(self.runtime, job)

        upload_snapshot = self.runtime.get_run(uploaded["runId"])
        link_snapshot = self.runtime.get_run(linked["runId"])
        self.assertEqual(
            upload_snapshot["artifacts"]["sourceAudio"]["contentSha256"],
            link_snapshot["artifacts"]["sourceAudio"]["contentSha256"],
        )
        self.assertEqual(
            upload_snapshot["stages"]["measurement"]["result"],
            link_snapshot["stages"]["measurement"]["result"],
        )


if __name__ == "__main__":
    unittest.main()
