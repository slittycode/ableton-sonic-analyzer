import tempfile
import unittest
from pathlib import Path


class AnalysisRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="asa_runtime_test_")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _runtime(self):
        from analysis_runtime import AnalysisRuntime

        return AnalysisRuntime(Path(self.temp_dir.name) / "runtime", max_pending_per_stage=4)

    def test_resolve_measurement_flags_supports_known_pitch_note_modes(self) -> None:
        runtime = self._runtime()

        # Pitch/note translation work is now handled by the dedicated pitch_note_translation stage,
        # not inline during measurement. Both modes return (False, False).
        self.assertEqual(runtime.resolve_measurement_flags("off"), (False, False))
        self.assertEqual(runtime.resolve_measurement_flags("stem_notes"), (False, False))

    def test_resolve_measurement_flags_rejects_unknown_pitch_note_mode(self) -> None:
        runtime = self._runtime()

        with self.assertRaisesRegex(ValueError, "Unsupported pitch/note mode 'melody_only'"):
            runtime.resolve_measurement_flags("melody_only")

    def test_resolve_pitch_note_backend_resolves_auto_and_aliases(self) -> None:
        runtime = self._runtime()

        self.assertEqual(
            runtime._resolve_pitch_note_backend("auto"),
            "torchcrepe-viterbi",
        )
        self.assertEqual(
            runtime._resolve_pitch_note_backend("torchcrepe"),
            "torchcrepe-viterbi",
        )

    def test_resolve_pitch_note_backend_rejects_unknown_backend(self) -> None:
        runtime = self._runtime()

        with self.assertRaisesRegex(
            ValueError,
            "Unsupported pitch/note backend 'mystery-backend'",
        ):
            runtime._resolve_pitch_note_backend("mystery-backend")

    def test_resolve_pitch_note_backend_rejects_penn(self) -> None:
        runtime = self._runtime()

        with self.assertRaisesRegex(
            ValueError,
            "Unsupported pitch/note backend 'penn'",
        ):
            runtime._resolve_pitch_note_backend("penn")

    def test_runtime_initializes_sqlite_for_poll_heavy_local_access(self) -> None:
        runtime = self._runtime()

        with runtime._connect() as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]

        self.assertEqual(str(journal_mode).lower(), "wal")
        self.assertEqual(int(synchronous), 1)

    def test_create_run_persists_source_artifact_and_stage_requests(self) -> None:
        runtime = self._runtime()

        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            owner_user_id="user_123",
            pitch_note_mode="stem_notes",
            pitch_note_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
            legacy_request_id="legacy_req_1",
        )

        snapshot = runtime.get_run(created["runId"])

        self.assertEqual(snapshot["artifacts"]["sourceAudio"]["filename"], "track.mp3")
        self.assertNotIn("path", snapshot["artifacts"]["sourceAudio"])
        self.assertEqual(snapshot["stages"]["measurement"]["status"], "queued")
        self.assertTrue(snapshot["stages"]["measurement"]["authoritative"])
        self.assertEqual(snapshot["stages"]["pitchNoteTranslation"]["status"], "blocked")
        self.assertFalse(snapshot["stages"]["pitchNoteTranslation"]["authoritative"])
        self.assertEqual(snapshot["stages"]["interpretation"]["status"], "blocked")
        self.assertEqual(snapshot["requestedStages"]["pitchNoteMode"], "stem_notes")
        self.assertEqual(snapshot["requestedStages"]["interpretationMode"], "async")
        self.assertEqual(runtime.get_run_owner_user_id(created["runId"]), "user_123")

    def test_get_run_rejects_wrong_owner(self) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            owner_user_id="user_123",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )

        with self.assertRaisesRegex(PermissionError, "does not belong to user"):
            runtime.get_run(created["runId"], owner_user_id="user_456")

    def test_runtime_uses_injected_artifact_storage_for_create_and_delete(self) -> None:
        from analysis_runtime import AnalysisRuntime
        from artifact_storage import StoredArtifact

        class RecordingArtifactStorage:
            def __init__(self) -> None:
                self.deleted_refs: list[str] = []

            def store_bytes(
                self,
                *,
                artifact_id: str,
                filename: str,
                content: bytes,
            ) -> StoredArtifact:
                return StoredArtifact(
                    storage_ref=f"memory://{artifact_id}/{filename}",
                    size_bytes=len(content),
                    content_sha256="sha-from-storage",
                )

            def store_file(
                self,
                *,
                artifact_id: str,
                filename: str,
                source_path: str,
            ) -> StoredArtifact:
                return StoredArtifact(
                    storage_ref=f"memory://{artifact_id}/{filename}",
                    size_bytes=0,
                    content_sha256="sha-from-storage",
                )

            def delete(self, storage_ref: str) -> None:
                self.deleted_refs.append(storage_ref)

            def resolve_local_path(self, storage_ref: str) -> Path | None:
                return None

        storage = RecordingArtifactStorage()
        runtime = AnalysisRuntime(
            Path(self.temp_dir.name) / "runtime",
            artifact_storage=storage,
        )
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )

        source = runtime.get_source_artifact(created["runId"])
        self.assertEqual(source["path"], f"memory://{source['artifactId']}/track.mp3")
        self.assertEqual(source["contentSha256"], "sha-from-storage")

        runtime.delete_run(created["runId"])
        self.assertEqual(storage.deleted_refs, [f"memory://{source['artifactId']}/track.mp3"])

    def test_measurement_completion_strips_transcription_and_enqueues_pitch_note_stage(
        self,
    ) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="stem_notes",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )

        runtime.complete_measurement(
            created["runId"],
            payload={
                "bpm": 128,
                "key": "A minor",
                "durationSeconds": 184.2,
                "transcriptionDetail": {
                    "transcriptionMethod": "torchcrepe-viterbi",
                    "noteCount": 2,
                    "averageConfidence": 0.83,
                    "stemSeparationUsed": True,
                    "fullMixFallback": False,
                    "stemsTranscribed": ["bass", "other"],
                    "dominantPitches": [],
                    "pitchRange": {
                        "minMidi": 48,
                        "maxMidi": 67,
                        "minName": "C3",
                        "maxName": "G4",
                    },
                    "notes": [],
                },
            },
            provenance={"schemaVersion": "measure.v1", "engineVersion": "analyze.py"},
            diagnostics={"backendDurationMs": 1200},
        )

        snapshot = runtime.get_run(created["runId"])

        # transcriptionDetail must NOT appear in authoritative measurement
        self.assertNotIn("transcriptionDetail", snapshot["stages"]["measurement"]["result"])
        self.assertEqual(snapshot["stages"]["measurement"]["provenance"]["schemaVersion"], "measure.v1")

        # pitch/note translation should be queued for the pitch/note translation worker — NOT
        # pre-populated from measurement output (no laundering)
        self.assertEqual(snapshot["stages"]["pitchNoteTranslation"]["status"], "queued")
        self.assertIsNone(snapshot["stages"]["pitchNoteTranslation"]["result"])
        self.assertEqual(len(snapshot["stages"]["pitchNoteTranslation"]["attemptsSummary"]), 1)
        self.assertEqual(
            snapshot["stages"]["pitchNoteTranslation"]["attemptsSummary"][0]["status"],
            "queued",
        )

    def test_runtime_can_resolve_runs_by_legacy_request_id(self) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
            legacy_request_id="legacy_req_42",
        )

        resolved = runtime.get_run_by_legacy_request_id("legacy_req_42")

        self.assertEqual(resolved["runId"], created["runId"])
        self.assertEqual(
            runtime.get_run_id_by_legacy_request_id("legacy_req_42"),
            created["runId"],
        )

    def test_stage_progress_updates_are_visible_in_stage_diagnostics(self) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="stem_notes",
            pitch_note_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
        )

        measurement_job = runtime.reserve_next_measurement_run()
        self.assertIsNotNone(measurement_job)
        progress = runtime.update_measurement_progress(
            created["runId"],
            step_key="loading_audio",
            message="Loading and validating uploaded audio for local analysis.",
        )
        self.assertIsNotNone(progress)
        snapshot = runtime.get_run(created["runId"])
        self.assertEqual(
            snapshot["stages"]["measurement"]["diagnostics"]["progress"]["stepKey"],
            "loading_audio",
        )
        self.assertEqual(
            snapshot["stages"]["measurement"]["diagnostics"]["progress"]["seq"],
            1,
        )

        runtime.complete_measurement(
            created["runId"],
            payload={"bpm": 128, "durationSeconds": 60.0},
            provenance={"schemaVersion": "measurement.v1"},
            diagnostics={"backendDurationMs": 1000},
        )

        pitch_note_attempt = runtime.reserve_next_pitch_note_attempt()
        self.assertIsNotNone(pitch_note_attempt)
        pitch_note_attempt_id = str(pitch_note_attempt["attemptId"])
        progress = runtime.update_pitch_note_attempt_progress(
            pitch_note_attempt_id,
            step_key="run_backend",
            message="Running pitch/note translation backend.",
        )
        self.assertIsNotNone(progress)
        snapshot = runtime.get_run(created["runId"])
        self.assertEqual(
            snapshot["stages"]["pitchNoteTranslation"]["diagnostics"]["progress"]["stepKey"],
            "run_backend",
        )
        self.assertEqual(
            snapshot["stages"]["pitchNoteTranslation"]["diagnostics"]["progress"]["seq"],
            1,
        )

        interpretation_attempt = runtime.reserve_next_interpretation_attempt()
        self.assertIsNotNone(interpretation_attempt)
        interpretation_attempt_id = str(interpretation_attempt["attemptId"])
        progress = runtime.update_interpretation_attempt_progress(
            interpretation_attempt_id,
            step_key="build_prompt",
            message="Building grounded interpretation prompt.",
        )
        self.assertIsNotNone(progress)
        snapshot = runtime.get_run(created["runId"])
        self.assertEqual(
            snapshot["stages"]["interpretation"]["diagnostics"]["progress"]["stepKey"],
            "build_prompt",
        )
        self.assertEqual(
            snapshot["stages"]["interpretation"]["diagnostics"]["progress"]["seq"],
            1,
        )

    def test_measurement_pipeline_progress_updates_are_visible_in_stage_diagnostics(
        self,
    ) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="stem_notes",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )

        measurement_job = runtime.reserve_next_measurement_run()
        self.assertIsNotNone(measurement_job)

        progress = runtime.update_measurement_pipeline_progress(
            created["runId"],
            pipeline_key="separation",
            status="pending",
            step_key="separation_pending",
            message="Demucs separation is queued and waiting to start.",
        )
        self.assertIsNotNone(progress)
        self.assertEqual(progress["seq"], 1)

        progress = runtime.update_measurement_pipeline_progress(
            created["runId"],
            pipeline_key="separation",
            status="running",
            step_key="separation_running",
            message="Demucs is separating stems from the source audio.",
        )
        self.assertIsNotNone(progress)
        self.assertEqual(progress["seq"], 2)

        progress = runtime.update_measurement_pipeline_progress(
            created["runId"],
            pipeline_key="transcription_stems",
            status="pending",
            step_key="transcription_pending",
            message="Torchcrepe transcription is queued for bass and other stems.",
        )
        self.assertIsNotNone(progress)
        self.assertEqual(progress["seq"], 1)

        snapshot = runtime.get_run(created["runId"])
        self.assertEqual(
            snapshot["stages"]["measurement"]["diagnostics"]["pipelineProgress"][
                "separation"
            ]["status"],
            "running",
        )
        self.assertEqual(
            snapshot["stages"]["measurement"]["diagnostics"]["pipelineProgress"][
                "separation"
            ]["seq"],
            2,
        )
        self.assertEqual(
            snapshot["stages"]["measurement"]["diagnostics"]["pipelineProgress"][
                "transcription_stems"
            ]["status"],
            "pending",
        )

        runtime.complete_measurement(
            created["runId"],
            payload={"bpm": 128, "durationSeconds": 60.0},
            provenance={"schemaVersion": "measurement.v1"},
            diagnostics={"backendDurationMs": 1000},
        )

        progress = runtime.update_measurement_pipeline_progress(
            created["runId"],
            pipeline_key="separation",
            status="completed",
            step_key="separation_complete",
            message="Demucs stem separation complete.",
        )
        self.assertIsNone(progress)

    def test_reserve_next_measurement_run_returns_requested_options(self) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="stem_notes",
            pitch_note_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
        )

        job = runtime.reserve_next_measurement_run()

        self.assertIsNotNone(job)
        self.assertEqual(job["runId"], created["runId"])
        self.assertEqual(job["requestedPitchNoteMode"], "stem_notes")
        self.assertEqual(job["requestedPitchNoteBackend"], "auto")

    def test_reserve_next_measurement_run_returns_off_when_pitch_note_disabled(self) -> None:
        runtime = self._runtime()
        runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )

        job = runtime.reserve_next_measurement_run()

        self.assertIsNotNone(job)
        self.assertEqual(job["requestedPitchNoteMode"], "off")

    def test_recover_interrupted_attempts_requeues_measurement_and_pitch_note_only(self) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="stem_notes",
            pitch_note_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
        )

        runtime.mark_measurement_running(created["runId"])
        runtime.create_pitch_note_attempt(
            created["runId"],
            backend_id="auto",
            mode="stem_notes",
            status="running",
        )
        runtime.create_interpretation_attempt(
            created["runId"],
            profile_id="producer_summary",
            model_name="gemini-2.5-flash",
            status="running",
        )

        runtime.recover_incomplete_attempts()
        snapshot = runtime.get_run(created["runId"])

        self.assertEqual(snapshot["stages"]["measurement"]["status"], "interrupted")
        self.assertEqual(snapshot["stages"]["pitchNoteTranslation"]["status"], "interrupted")
        self.assertEqual(snapshot["stages"]["interpretation"]["status"], "interrupted")

    def test_interpretation_attempts_store_grounding_columns(self) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="stem_notes",
            pitch_note_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
        )
        runtime.complete_measurement(
            created["runId"],
            payload={"bpm": 128, "durationSeconds": 60.0},
            provenance={"schemaVersion": "measurement.v1"},
            diagnostics={"backendDurationMs": 1000},
        )
        pitch_note_attempt_id = runtime.create_pitch_note_attempt(
            created["runId"],
            backend_id="auto",
            mode="stem_notes",
            status="completed",
            result={
                "transcriptionMethod": "stub-backend",
                "noteCount": 1,
                "averageConfidence": 0.8,
                "stemSeparationUsed": True,
                "fullMixFallback": False,
                "stemsTranscribed": ["bass"],
                "dominantPitches": [],
                "pitchRange": {
                    "minMidi": 48,
                    "maxMidi": 48,
                    "minName": "C3",
                    "maxName": "C3",
                },
                "notes": [],
            },
            provenance={"backendId": "auto"},
        )
        interpretation_attempt_id = runtime.create_interpretation_attempt(
            created["runId"],
            profile_id="producer_summary",
            model_name="gemini-2.5-flash",
            status="queued",
        )
        grounding = runtime.get_interpretation_grounding(created["runId"])

        runtime.complete_interpretation_attempt(
            interpretation_attempt_id,
            result={"trackCharacter": "Grounded summary"},
            provenance={
                "groundedMeasurementOutputId": grounding["measurementOutputId"],
                "groundedPitchNoteAttemptId": grounding["pitchNoteAttemptId"],
            },
            diagnostics={"backendDurationMs": 250},
            grounded_measurement_output_id=grounding["measurementOutputId"],
            grounded_pitch_note_attempt_id=grounding["pitchNoteAttemptId"],
        )

        with runtime._connect() as conn:
            row = conn.execute(
                """
                SELECT grounded_measurement_output_id, grounded_pitch_note_attempt_id
                FROM interpretation_attempts
                WHERE id = ?
                """,
                (interpretation_attempt_id,),
            ).fetchone()

        self.assertEqual(row["grounded_measurement_output_id"], grounding["measurementOutputId"])
        self.assertEqual(row["grounded_pitch_note_attempt_id"], pitch_note_attempt_id)
