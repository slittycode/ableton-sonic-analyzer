import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

        # Phase 1.B change: ``stem_notes`` mode now also runs separation at
        # measurement time so the stem-first overlay (stemAnalysis) populates
        # without waiting on the pitch-note worker stage. Transcription still
        # runs in its own stage, so ``run_transcribe`` stays False.
        self.assertEqual(runtime.resolve_measurement_flags("off"), (False, False))
        self.assertEqual(runtime.resolve_measurement_flags("stem_notes"), (True, False))

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

    def test_create_run_from_source_path_persists_streamed_source_artifact(self) -> None:
        runtime = self._runtime()
        source_path = Path(self.temp_dir.name) / "source-track.mp3"
        source_bytes = b"streamed-audio-data"
        source_path.write_bytes(source_bytes)

        created = runtime.create_run_from_source_path(
            filename="track.mp3",
            source_path=str(source_path),
            mime_type="audio/mpeg",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )

        snapshot = runtime.get_run(created["runId"])
        source_audio = snapshot["artifacts"]["sourceAudio"]
        self.assertEqual(source_audio["filename"], "track.mp3")
        self.assertEqual(source_audio["sizeBytes"], len(source_bytes))
        self.assertEqual(
            source_audio["contentSha256"],
            hashlib.sha256(source_bytes).hexdigest(),
        )
        self.assertEqual(snapshot["stages"]["measurement"]["status"], "queued")
        self.assertEqual(Path(source_audio["path"]).read_bytes(), source_bytes)

    def test_create_run_from_source_path_removes_partial_artifact_on_db_failure(self) -> None:
        runtime = self._runtime()
        source_path = Path(self.temp_dir.name) / "source-track.mp3"
        source_path.write_bytes(b"streamed-audio-data")

        class FailingConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, *_args, **_kwargs):
                raise sqlite3.OperationalError("db write failed")

        with patch.object(runtime, "_connect", return_value=FailingConnection()):
            with self.assertRaisesRegex(sqlite3.OperationalError, "db write failed"):
                runtime.create_run_from_source_path(
                    filename="track.mp3",
                    source_path=str(source_path),
                    mime_type="audio/mpeg",
                    pitch_note_mode="off",
                    pitch_note_backend="auto",
                    interpretation_mode="off",
                    interpretation_profile="producer_summary",
                    interpretation_model=None,
                )

        self.assertEqual(list(runtime.artifacts_dir.iterdir()), [])

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

        # reserve_next_interpretation_attempt now blocks while a pitch_note (or
        # mt3) attempt is in-flight, so settle the reserved pitch_note attempt
        # before reserving interpretation. This test asserts interpretation
        # PROGRESS visibility, not the cross-stage gate (covered by the
        # InterpretationGatingTests class below).
        runtime.complete_pitch_note_attempt(
            pitch_note_attempt_id,
            result={"transcriptionMethod": "stub", "noteCount": 0, "notes": []},
            provenance={"backendId": "auto"},
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

    def test_interpretation_grounding_exposes_mt3_result(self) -> None:
        """F3: get_interpretation_grounding surfaces a completed MT3 attempt so
        _execute_interpretation_attempt can forward it to Gemini. When no MT3
        attempt exists the fields stay null / 'not_requested' (additive only)."""
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
        )
        run_id = created["runId"]
        runtime.complete_measurement(
            run_id,
            payload={"bpm": 128, "durationSeconds": 60.0},
            provenance={"schemaVersion": "measurement.v1"},
            diagnostics={"backendDurationMs": 1000},
        )

        # No MT3 attempt yet: grounding stays additive-null.
        grounding_before = runtime.get_interpretation_grounding(run_id)
        self.assertIsNone(grounding_before["mt3Result"])
        self.assertIsNone(grounding_before["mt3AttemptId"])
        self.assertEqual(grounding_before["mt3Status"], "not_requested")

        mt3_result = {
            "version": "magenta-mt3-base",
            "stemsUsed": ["bass", "other"],
            "tracks": [
                {
                    "instrument": "bass",
                    "midiArtifactId": "artifact-1",
                    "midiSizeBytes": 256,
                    "noteCount": 42,
                    "pitchRange": [28, 52],
                }
            ],
        }
        mt3_attempt_id = runtime.create_mt3_attempt(
            run_id,
            status="completed",
            result=mt3_result,
            provenance={"resolvedCheckpointId": "magenta-mt3-base"},
        )

        grounding_after = runtime.get_interpretation_grounding(run_id)
        self.assertEqual(grounding_after["mt3Result"], mt3_result)
        self.assertEqual(grounding_after["mt3AttemptId"], mt3_attempt_id)
        self.assertEqual(grounding_after["mt3Status"], "completed")


class InterpretationGatingTests(unittest.TestCase):
    """The interpretation stage must wait for the additive grounding peers
    (mt3 + pitch_note) to settle before it runs, so Gemini Phase 2 actually
    sees mt3Result / pitchNoteResult instead of None. reserve_next_interpretation_attempt
    blocks while either peer is in-flight ('queued'/'running'); terminal states
    (completed/failed/interrupted) unblock it.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="asa_interp_gate_test_")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _runtime(self):
        from analysis_runtime import AnalysisRuntime

        return AnalysisRuntime(Path(self.temp_dir.name) / "runtime", max_pending_per_stage=4)

    def _run_ready_for_interpretation(self, runtime, *, mt3_mode="off", pitch_note_mode="off"):
        """Create a run that requests interpretation (+ optionally mt3/pitch_note)
        and complete its measurement, which enqueues the requested followups as
        'queued' via _enqueue_requested_followups (the real production path)."""
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode=pitch_note_mode,
            pitch_note_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
            mt3_mode=mt3_mode,
        )
        run_id = created["runId"]
        runtime.complete_measurement(
            run_id,
            payload={"bpm": 128, "durationSeconds": 60.0},
            provenance={"schemaVersion": "measurement.v1"},
            diagnostics={"backendDurationMs": 1000},
        )
        return run_id

    @staticmethod
    def _mt3_result():
        return {"version": "magenta-mt3-base", "stemsUsed": [], "tracks": []}

    @staticmethod
    def _pitch_note_result():
        return {"transcriptionMethod": "stub", "noteCount": 0, "notes": []}

    @staticmethod
    def _stage_error(code):
        return {"code": code, "message": "simulated", "retryable": False, "phase": "test"}

    def test_interpretation_blocked_while_mt3_in_flight(self) -> None:
        # pitch_note off → isolate the mt3 guard.
        runtime = self._runtime()
        run_id = self._run_ready_for_interpretation(runtime, mt3_mode="enabled", pitch_note_mode="off")
        # mt3 attempt is 'queued' → interpretation must not reserve.
        self.assertIsNone(runtime.reserve_next_interpretation_attempt())
        mt3 = runtime.reserve_next_mt3_attempt()
        self.assertIsNotNone(mt3)  # mt3 now 'running'
        self.assertIsNone(runtime.reserve_next_interpretation_attempt())

    def test_interpretation_blocked_while_pitch_note_in_flight(self) -> None:
        # mt3 off → isolate the pitch_note guard.
        runtime = self._runtime()
        run_id = self._run_ready_for_interpretation(runtime, mt3_mode="off", pitch_note_mode="stem_notes")
        self.assertIsNone(runtime.reserve_next_interpretation_attempt())
        pn = runtime.reserve_next_pitch_note_attempt()
        self.assertIsNotNone(pn)  # pitch_note now 'running'
        self.assertIsNone(runtime.reserve_next_interpretation_attempt())

    def test_interpretation_waits_for_both_then_unblocks(self) -> None:
        runtime = self._runtime()
        run_id = self._run_ready_for_interpretation(runtime, mt3_mode="enabled", pitch_note_mode="stem_notes")
        self.assertIsNone(runtime.reserve_next_interpretation_attempt())  # both queued
        pn = runtime.reserve_next_pitch_note_attempt()
        runtime.complete_pitch_note_attempt(
            str(pn["attemptId"]), result=self._pitch_note_result(), provenance={"backendId": "auto"}
        )
        # pitch_note done but mt3 still queued → still blocked.
        self.assertIsNone(runtime.reserve_next_interpretation_attempt())
        mt3 = runtime.reserve_next_mt3_attempt()
        runtime.complete_mt3_attempt(
            str(mt3["attemptId"]), result=self._mt3_result(), provenance={}
        )
        # both terminal → unblocks.
        self.assertIsNotNone(runtime.reserve_next_interpretation_attempt())

    def test_interpretation_reserved_after_grounding_failed(self) -> None:
        runtime = self._runtime()
        run_id = self._run_ready_for_interpretation(runtime, mt3_mode="enabled", pitch_note_mode="stem_notes")
        pn = runtime.reserve_next_pitch_note_attempt()
        runtime.fail_pitch_note_attempt(str(pn["attemptId"]), error=self._stage_error("PITCH_NOTE_TRANSLATION_FAILED"))
        mt3 = runtime.reserve_next_mt3_attempt()
        runtime.fail_mt3_attempt(str(mt3["attemptId"]), error=self._stage_error("MT3_TRANSCRIPTION_FAILED"))
        # failed is terminal → interpretation unblocks (runs with grounding=None).
        self.assertIsNotNone(runtime.reserve_next_interpretation_attempt())

    def test_interpretation_reserved_immediately_without_grounding_stages(self) -> None:
        # Regression guard: a run requesting neither grounding stage must not block.
        runtime = self._runtime()
        run_id = self._run_ready_for_interpretation(runtime, mt3_mode="off", pitch_note_mode="off")
        self.assertIsNotNone(runtime.reserve_next_interpretation_attempt())

    def test_interpretation_unblocks_after_recovery_clears_stale_running_grounding(self) -> None:
        # A crash mid-grounding leaves rows 'running'; restart recovery interrupts
        # them so interpretation can never deadlock forever.
        runtime = self._runtime()
        run_id = self._run_ready_for_interpretation(runtime, mt3_mode="enabled", pitch_note_mode="stem_notes")
        runtime.reserve_next_pitch_note_attempt()  # → running
        runtime.reserve_next_mt3_attempt()  # → running
        self.assertIsNone(runtime.reserve_next_interpretation_attempt())
        runtime.recover_incomplete_attempts()  # running → interrupted
        self.assertIsNotNone(runtime.reserve_next_interpretation_attempt())

    def test_enqueue_creates_interpretation_attempt_last(self) -> None:
        # Regression guard for the enqueue-ordering fix: interpretation must be
        # created AFTER mt3 and pitch_note so it can never be reserved in the
        # window before a grounding row commits. Record the create order through
        # the real _enqueue_requested_followups path (driven by complete_measurement).
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
            mt3_mode="enabled",
        )
        run_id = created["runId"]

        call_order: list[str] = []
        originals = {
            "pitch_note": runtime.create_pitch_note_attempt,
            "mt3": runtime.create_mt3_attempt,
            "interpretation": runtime.create_interpretation_attempt,
        }

        def _recorder(name):
            def _wrapped(*args, **kwargs):
                call_order.append(name)
                return originals[name](*args, **kwargs)

            return _wrapped

        runtime.create_pitch_note_attempt = _recorder("pitch_note")
        runtime.create_mt3_attempt = _recorder("mt3")
        runtime.create_interpretation_attempt = _recorder("interpretation")

        runtime.complete_measurement(
            run_id,
            payload={"bpm": 128, "durationSeconds": 60.0},
            provenance={"schemaVersion": "measurement.v1"},
            diagnostics={"backendDurationMs": 1000},
        )

        self.assertEqual(call_order, ["pitch_note", "mt3", "interpretation"])


class SpectralArtifactSnapshotTests(unittest.TestCase):
    """Verifies the STFT-spectrogram sampleRate provenance is exposed on the
    public artifact ref via `_normalize_run_snapshot` while mel and other
    kinds remain unaffected."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="asa_spectral_snapshot_test_")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _runtime(self):
        from analysis_runtime import AnalysisRuntime

        return AnalysisRuntime(Path(self.temp_dir.name) / "runtime", max_pending_per_stage=4)

    def _stub_png(self, name: str) -> str:
        png_path = Path(self.temp_dir.name) / name
        # 8-byte PNG header + minimal padding; size_bytes just needs to be > 0.
        png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        return str(png_path)

    def test_stft_spectrogram_exposes_sample_rate_on_public_ref(self) -> None:
        from server_phase1 import _normalize_run_snapshot

        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.wav",
            content=b"fake-audio",
            mime_type="audio/wav",
            owner_user_id="user_xyz",
            pitch_note_mode="off",
            pitch_note_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )
        run_id = created["runId"]

        runtime.record_artifact(
            run_id,
            kind="spectrogram_mel",
            source_path=self._stub_png("mel.png"),
            filename="mel_spectrogram.png",
            mime_type="image/png",
            provenance={"generator": "spectral_viz", "schemaVersion": "spectral.v1"},
        )
        runtime.record_artifact(
            run_id,
            kind="spectrogram_stft",
            source_path=self._stub_png("stft.png"),
            filename="stft_spectrogram.png",
            mime_type="image/png",
            provenance={
                "generator": "spectral_viz",
                "schemaVersion": "spectral.v1",
                "sampleRate": 48000,
            },
        )

        snapshot = runtime.get_run(run_id, owner_user_id="user_xyz")
        normalized = _normalize_run_snapshot(snapshot, runtime=runtime)

        spectrograms = normalized["artifacts"]["spectral"]["spectrograms"]
        by_kind = {s["kind"]: s for s in spectrograms}

        self.assertIn("spectrogram_mel", by_kind)
        self.assertIn("spectrogram_stft", by_kind)
        self.assertNotIn("sampleRate", by_kind["spectrogram_mel"])
        self.assertEqual(by_kind["spectrogram_stft"]["sampleRate"], 48000)

        # path and contentSha256 must NOT leak into the public envelope.
        self.assertNotIn("path", by_kind["spectrogram_stft"])
        self.assertNotIn("contentSha256", by_kind["spectrogram_stft"])
        self.assertNotIn("provenance", by_kind["spectrogram_stft"])


class StagedRunInterruptResurrectionTests(unittest.TestCase):
    """Regression guard: a late/orphaned stage writer must not resurrect a run
    that was interrupted while the stage's subprocess was still finishing.

    Before the staged-run lifecycle fix the stage executors could call
    complete/fail on an attempt the interrupt had already flipped to
    'interrupted', flipping it back to a terminal-success/failed state and
    (for measurement) enqueuing a fresh downstream pipeline for a cancelled run.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="asa_resurrect_test_")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _runtime(self):
        from analysis_runtime import AnalysisRuntime

        return AnalysisRuntime(Path(self.temp_dir.name) / "runtime", max_pending_per_stage=4)

    def _run_with_completed_measurement(self, runtime, *, interpretation_mode="off"):
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            pitch_note_mode="stem_notes",
            pitch_note_backend="auto",
            interpretation_mode=interpretation_mode,
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash" if interpretation_mode != "off" else None,
        )
        run_id = created["runId"]
        runtime.reserve_next_measurement_run()
        runtime.complete_measurement(
            run_id,
            payload={"bpm": 128, "durationSeconds": 60.0},
            provenance={"schemaVersion": "measurement.v1"},
            diagnostics={"backendDurationMs": 1000},
        )
        return run_id

    def test_complete_pitch_note_attempt_does_not_resurrect_interrupted_attempt(self) -> None:
        runtime = self._runtime()
        run_id = self._run_with_completed_measurement(runtime)
        attempt = runtime.reserve_next_pitch_note_attempt()
        self.assertIsNotNone(attempt)
        attempt_id = str(attempt["attemptId"])

        runtime.interrupt_run(run_id)

        # The now-orphaned subprocess finishes and reports success.
        runtime.complete_pitch_note_attempt(
            attempt_id,
            result={"transcriptionMethod": "stub", "noteCount": 0, "notes": []},
            provenance={"backendId": "auto"},
        )

        with runtime._connect() as conn:
            status = conn.execute(
                "SELECT status FROM pitch_note_translation_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()[0]
            preferred = conn.execute(
                "SELECT preferred_pitch_note_attempt_id FROM analysis_runs WHERE id = ?",
                (run_id,),
            ).fetchone()[0]
        self.assertEqual(status, "interrupted")
        self.assertIsNone(preferred)

    def test_fail_pitch_note_attempt_does_not_overwrite_interrupted_attempt(self) -> None:
        runtime = self._runtime()
        run_id = self._run_with_completed_measurement(runtime)
        attempt = runtime.reserve_next_pitch_note_attempt()
        attempt_id = str(attempt["attemptId"])

        runtime.interrupt_run(run_id)

        # Interrupt kills the child → non-zero exit → fail_pitch_note_attempt.
        runtime.fail_pitch_note_attempt(
            attempt_id,
            error={
                "code": "PITCH_NOTE_TRANSLATION_FAILED",
                "message": "subprocess terminated",
                "retryable": True,
                "phase": "pitch_note_translation",
            },
        )

        with runtime._connect() as conn:
            status = conn.execute(
                "SELECT status FROM pitch_note_translation_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()[0]
        self.assertEqual(status, "interrupted")

    def test_complete_mt3_attempt_does_not_resurrect_interrupted_attempt(self) -> None:
        runtime = self._runtime()
        run_id = self._run_with_completed_measurement(runtime)
        mt3_attempt_id = runtime.create_mt3_attempt(run_id)
        self.assertTrue(runtime.reserve_mt3_attempt(mt3_attempt_id))

        runtime.interrupt_run(run_id)

        runtime.complete_mt3_attempt(
            mt3_attempt_id,
            result={"tracks": []},
            provenance={"checkpointId": "test"},
        )

        with runtime._connect() as conn:
            status = conn.execute(
                "SELECT status FROM mt3_attempts WHERE id = ?",
                (mt3_attempt_id,),
            ).fetchone()[0]
            preferred = conn.execute(
                "SELECT preferred_mt3_attempt_id FROM analysis_runs WHERE id = ?",
                (run_id,),
            ).fetchone()[0]
        self.assertEqual(status, "interrupted")
        self.assertIsNone(preferred)

    def test_complete_measurement_after_interrupt_does_not_enqueue_followups(self) -> None:
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
        run_id = created["runId"]
        runtime.reserve_next_measurement_run()  # → measurement 'running'

        runtime.interrupt_run(run_id)

        # A racing/orphaned measurement subprocess reports success after the
        # interrupt. The guard must no-op the status flip AND skip enqueuing the
        # downstream pitch-note/interpretation pipeline for a cancelled run.
        runtime.complete_measurement(
            run_id,
            payload={"bpm": 128, "durationSeconds": 60.0},
            provenance={"schemaVersion": "measurement.v1"},
            diagnostics={"backendDurationMs": 1000},
        )

        with runtime._connect() as conn:
            measurement_status = conn.execute(
                "SELECT status FROM measurement_outputs WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            pn_count = conn.execute(
                "SELECT COUNT(*) FROM pitch_note_translation_attempts WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            interp_count = conn.execute(
                "SELECT COUNT(*) FROM interpretation_attempts WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
        self.assertEqual(measurement_status, "interrupted")
        self.assertEqual(pn_count, 0)
        self.assertEqual(interp_count, 0)
