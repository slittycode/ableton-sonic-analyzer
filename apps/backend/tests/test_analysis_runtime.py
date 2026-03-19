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

    def test_resolve_measurement_flags_supports_known_symbolic_modes(self) -> None:
        runtime = self._runtime()

        self.assertEqual(runtime.resolve_measurement_flags("off"), (False, False))
        self.assertEqual(runtime.resolve_measurement_flags("stem_notes"), (True, True))

    def test_resolve_measurement_flags_rejects_unknown_symbolic_mode(self) -> None:
        runtime = self._runtime()

        with self.assertRaisesRegex(ValueError, "Unsupported symbolic mode 'melody_only'"):
            runtime.resolve_measurement_flags("melody_only")

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
            symbolic_mode="stem_notes",
            symbolic_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
            legacy_request_id="legacy_req_1",
        )

        snapshot = runtime.get_run(created["runId"])

        self.assertEqual(snapshot["artifacts"]["sourceAudio"]["filename"], "track.mp3")
        self.assertEqual(snapshot["stages"]["measurement"]["status"], "queued")
        self.assertTrue(snapshot["stages"]["measurement"]["authoritative"])
        self.assertEqual(snapshot["stages"]["symbolicExtraction"]["status"], "blocked")
        self.assertFalse(snapshot["stages"]["symbolicExtraction"]["authoritative"])
        self.assertEqual(snapshot["stages"]["interpretation"]["status"], "blocked")
        self.assertEqual(snapshot["requestedStages"]["symbolicMode"], "stem_notes")
        self.assertEqual(snapshot["requestedStages"]["interpretationMode"], "async")

    def test_measurement_completion_strips_transcription_and_enqueues_symbolic_stage(
        self,
    ) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            symbolic_mode="stem_notes",
            symbolic_backend="auto",
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
                    "transcriptionMethod": "basic-pitch-legacy",
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

        # symbolic extraction should be queued for the symbolic worker — NOT
        # pre-populated from measurement output (no laundering)
        self.assertEqual(snapshot["stages"]["symbolicExtraction"]["status"], "queued")
        self.assertIsNone(snapshot["stages"]["symbolicExtraction"]["result"])
        self.assertEqual(len(snapshot["stages"]["symbolicExtraction"]["attemptsSummary"]), 1)
        self.assertEqual(
            snapshot["stages"]["symbolicExtraction"]["attemptsSummary"][0]["status"],
            "queued",
        )

    def test_runtime_can_resolve_runs_by_legacy_request_id(self) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            symbolic_mode="off",
            symbolic_backend="auto",
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
            symbolic_mode="stem_notes",
            symbolic_backend="auto",
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

        symbolic_attempt = runtime.reserve_next_symbolic_attempt()
        self.assertIsNotNone(symbolic_attempt)
        symbolic_attempt_id = str(symbolic_attempt["attemptId"])
        progress = runtime.update_symbolic_attempt_progress(
            symbolic_attempt_id,
            step_key="run_backend",
            message="Running symbolic transcription backend.",
        )
        self.assertIsNotNone(progress)
        snapshot = runtime.get_run(created["runId"])
        self.assertEqual(
            snapshot["stages"]["symbolicExtraction"]["diagnostics"]["progress"]["stepKey"],
            "run_backend",
        )
        self.assertEqual(
            snapshot["stages"]["symbolicExtraction"]["diagnostics"]["progress"]["seq"],
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
            symbolic_mode="stem_notes",
            symbolic_backend="auto",
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
            message="Legacy Basic Pitch transcription is queued for bass and other stems.",
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
            symbolic_mode="stem_notes",
            symbolic_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
        )

        job = runtime.reserve_next_measurement_run()

        self.assertIsNotNone(job)
        self.assertEqual(job["runId"], created["runId"])
        self.assertEqual(job["requestedSymbolicMode"], "stem_notes")
        self.assertEqual(job["requestedSymbolicBackend"], "auto")

    def test_reserve_next_measurement_run_returns_off_when_symbolic_disabled(self) -> None:
        runtime = self._runtime()
        runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            symbolic_mode="off",
            symbolic_backend="auto",
            interpretation_mode="off",
            interpretation_profile="producer_summary",
            interpretation_model=None,
        )

        job = runtime.reserve_next_measurement_run()

        self.assertIsNotNone(job)
        self.assertEqual(job["requestedSymbolicMode"], "off")

    def test_recover_interrupted_attempts_requeues_measurement_and_symbolic_only(self) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            symbolic_mode="stem_notes",
            symbolic_backend="auto",
            interpretation_mode="async",
            interpretation_profile="producer_summary",
            interpretation_model="gemini-2.5-flash",
        )

        runtime.mark_measurement_running(created["runId"])
        runtime.create_symbolic_attempt(
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

        self.assertEqual(snapshot["stages"]["measurement"]["status"], "queued")
        self.assertEqual(snapshot["stages"]["symbolicExtraction"]["status"], "queued")
        self.assertEqual(snapshot["stages"]["interpretation"]["status"], "interrupted")

    def test_interpretation_attempts_store_grounding_columns(self) -> None:
        runtime = self._runtime()
        created = runtime.create_run(
            filename="track.mp3",
            content=b"fake-audio",
            mime_type="audio/mpeg",
            symbolic_mode="stem_notes",
            symbolic_backend="auto",
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
        symbolic_attempt_id = runtime.create_symbolic_attempt(
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
                "groundedSymbolicAttemptId": grounding["symbolicAttemptId"],
            },
            diagnostics={"backendDurationMs": 250},
            grounded_measurement_output_id=grounding["measurementOutputId"],
            grounded_symbolic_attempt_id=grounding["symbolicAttemptId"],
        )

        with runtime._connect() as conn:
            row = conn.execute(
                """
                SELECT grounded_measurement_output_id, grounded_symbolic_attempt_id
                FROM interpretation_attempts
                WHERE id = ?
                """,
                (interpretation_attempt_id,),
            ).fetchone()

        self.assertEqual(row["grounded_measurement_output_id"], grounding["measurementOutputId"])
        self.assertEqual(row["grounded_symbolic_attempt_id"], symbolic_attempt_id)
