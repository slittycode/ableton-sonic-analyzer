from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from artifact_storage import ArtifactStorage, FilesystemArtifactStorage
import uuid

# Single source of truth for the MT3 checkpoint identifier — used as the
# default `checkpoint_id` column value when queuing an mt3 attempt. The
# executor overrides this with whatever transcribe() actually ran with so
# the recorded value reflects the run, but having a default here lets the
# runtime emit queued snapshots before the worker has picked the row up.
# Import is module-level-safe: mt3_transcription.py top-level is stdlib
# + dataclass only; JAX/t5x are lazy inside transcribe().
from mt3_transcription import MT3_CHECKPOINT_ID as DEFAULT_MT3_CHECKPOINT_ID

SQLITE_BUSY_TIMEOUT_MS = 5_000
MEASUREMENT_PIPELINE_PROGRESS_STATUSES = {"pending", "running", "completed"}
LOCAL_RUNTIME_OWNER_USER_ID = "local-dev"
AUDIO_SOURCE_READY_TTL_MINUTES = 15

# Stage-status values for the MT3 stage. Mirrors pitch_note_translation:
# {queued, running, completed, failed, interrupted}. Added to the public
# snapshot via _mt3_stage_snapshot below.


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def _json_loads(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


class UnsupportedPitchNoteModeError(ValueError):
    def __init__(self, pitch_note_mode: str):
        self.pitch_note_mode = pitch_note_mode
        super().__init__(f"Unsupported pitch/note mode '{pitch_note_mode}'.")


class UnsupportedPitchNoteBackendError(ValueError):
    def __init__(self, pitch_note_backend: str):
        self.pitch_note_backend = pitch_note_backend
        super().__init__(f"Unsupported pitch/note backend '{pitch_note_backend}'.")


class UnsupportedMt3ModeError(ValueError):
    """Raised when the create-run request specifies an unknown mt3_mode.

    The route layer (server.py) catches this and surfaces it as a typed
    400 ``MT3_MODE_UNSUPPORTED`` response. Mirror of UnsupportedPitchNoteModeError.
    """

    def __init__(self, mt3_mode: str):
        self.mt3_mode = mt3_mode
        super().__init__(f"Unsupported mt3 mode '{mt3_mode}'.")


class AudioSourceIntakeCapacityError(RuntimeError):
    pass


class AudioSourceIntakeStateError(RuntimeError):
    pass


class AnalysisRuntime:
    def __init__(
        self,
        runtime_dir: Path,
        max_pending_per_stage: int = 4,
        artifact_storage: ArtifactStorage | None = None,
    ):
        self.runtime_dir = Path(runtime_dir)
        self.max_pending_per_stage = max_pending_per_stage
        self.artifacts_dir = self.runtime_dir / "artifacts"
        self.db_path = self.runtime_dir / "analysis_runs.sqlite3"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_storage = artifact_storage or FilesystemArtifactStorage(self.artifacts_dir)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id TEXT PRIMARY KEY,
                    source_artifact_id TEXT NOT NULL,
                    requested_pitch_note_mode TEXT NOT NULL,
                    requested_pitch_note_backend TEXT NOT NULL,
                    requested_interpretation_mode TEXT NOT NULL,
                    requested_interpretation_profile TEXT NOT NULL,
                    requested_interpretation_model TEXT,
                    legacy_request_id TEXT,
                    preferred_pitch_note_attempt_id TEXT,
                    preferred_interpretation_attempt_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_artifacts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    path TEXT NOT NULL,
                    provenance_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS measurement_outputs (
                    id TEXT PRIMARY KEY,
                    run_id TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    provenance_json TEXT,
                    diagnostics_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pitch_note_translation_attempts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    backend_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    provenance_json TEXT,
                    diagnostics_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS interpretation_attempts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    model_name TEXT,
                    grounded_measurement_output_id TEXT,
                    grounded_pitch_note_attempt_id TEXT,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    provenance_json TEXT,
                    diagnostics_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mt3_attempts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    provenance_json TEXT,
                    diagnostics_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audio_source_intakes (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    raw_url TEXT,
                    rights_confirmed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT,
                    artifact_id TEXT,
                    artifact_filename TEXT,
                    artifact_mime_type TEXT,
                    artifact_size_bytes INTEGER,
                    artifact_sha256 TEXT,
                    artifact_path TEXT,
                    diagnostics_json TEXT,
                    error_json TEXT,
                    analysis_options_json TEXT,
                    run_id TEXT,
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_active_audio_source_intake_per_owner
                ON audio_source_intakes(owner_user_id)
                WHERE status IN ('queued', 'fetching', 'normalizing', 'ready');

                CREATE INDEX IF NOT EXISTS audio_source_intakes_status_created
                ON audio_source_intakes(status, created_at);
                """
            )
            self._ensure_column(
                conn,
                "analysis_runs",
                "requested_analysis_mode",
                "TEXT",
            )
            self._ensure_column(
                conn,
                "analysis_runs",
                "owner_user_id",
                "TEXT",
            )
            conn.execute(
                """
                UPDATE analysis_runs
                SET requested_analysis_mode = 'full'
                WHERE requested_analysis_mode IS NULL
                """
            )
            conn.execute(
                """
                UPDATE analysis_runs
                SET owner_user_id = ?
                WHERE owner_user_id IS NULL OR TRIM(owner_user_id) = ''
                """,
                (LOCAL_RUNTIME_OWNER_USER_ID,),
            )
            self._ensure_column(
                conn,
                "interpretation_attempts",
                "grounded_measurement_output_id",
                "TEXT",
            )
            self._ensure_column(
                conn,
                "interpretation_attempts",
                "grounded_pitch_note_attempt_id",
                "TEXT",
            )
            # MT3 stage columns. Default to 'off' so existing local DBs that
            # predate the staged MT3 stage continue to opt out cleanly —
            # matches the `requested_analysis_mode = 'full'` backfill above.
            self._ensure_column(
                conn,
                "analysis_runs",
                "requested_mt3_mode",
                "TEXT",
            )
            self._ensure_column(
                conn,
                "analysis_runs",
                "preferred_mt3_attempt_id",
                "TEXT",
            )
            conn.execute(
                """
                UPDATE analysis_runs
                SET requested_mt3_mode = 'off'
                WHERE requested_mt3_mode IS NULL
                """
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        column_type: str,
    ) -> None:
        existing_columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column in existing_columns:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def create_run(
        self,
        *,
        filename: str,
        content: bytes,
        mime_type: str,
        owner_user_id: str = LOCAL_RUNTIME_OWNER_USER_ID,
        pitch_note_mode: str,
        pitch_note_backend: str,
        interpretation_mode: str,
        interpretation_profile: str,
        interpretation_model: str | None,
        legacy_request_id: str | None = None,
        analysis_mode: str = "full",
        mt3_mode: str = "off",
        expose_source_path_in_snapshot: bool = False,
    ) -> dict[str, Any]:
        # Validate mt3_mode here so a typed error reaches the route layer
        # rather than silently inserting an unknown enum value.
        if mt3_mode not in {"off", "enabled"}:
            raise UnsupportedMt3ModeError(mt3_mode)
        artifact_id = str(uuid4())
        created_at = _utc_now_iso()
        stored_artifact = self.artifact_storage.store_bytes(
            artifact_id=artifact_id,
            filename=filename,
            content=content,
        )

        run_id = str(uuid.uuid4())
        resolved_analysis_mode = analysis_mode or "standard"
        source_artifact_provenance = (
            _json_dumps({"exposePathInSnapshot": True})
            if expose_source_path_in_snapshot
            else None
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_runs (
                    id,
                    source_artifact_id,
                    requested_analysis_mode,
                    owner_user_id,
                    requested_pitch_note_mode,
                    requested_pitch_note_backend,
                    requested_interpretation_mode,
                    requested_interpretation_profile,
                    requested_interpretation_model,
                    requested_mt3_mode,
                    legacy_request_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    artifact_id,
                    resolved_analysis_mode,
                    owner_user_id or LOCAL_RUNTIME_OWNER_USER_ID,
                    pitch_note_mode,
                    pitch_note_backend,
                    interpretation_mode,
                    interpretation_profile,
                    interpretation_model,
                    mt3_mode,
                    legacy_request_id,
                    created_at,
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO run_artifacts (
                    id,
                    run_id,
                    kind,
                    filename,
                    mime_type,
                    size_bytes,
                    content_sha256,
                    path,
                    provenance_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    run_id,
                    "source_audio",
                    filename,
                    mime_type,
                    stored_artifact.size_bytes,
                    stored_artifact.content_sha256,
                    stored_artifact.storage_ref,
                    source_artifact_provenance,
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO measurement_outputs (
                    id,
                    run_id,
                    status,
                    result_json,
                    provenance_json,
                    diagnostics_json,
                    error_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    run_id,
                    "queued",
                    None,
                    None,
                    None,
                    None,
                    created_at,
                    created_at,
                ),
            )

        return {"runId": run_id}

    @staticmethod
    def _public_audio_source_intake(row: sqlite3.Row) -> dict[str, Any]:
        metadata = _json_loads(row["metadata_json"])
        error = _json_loads(row["error_json"])
        return {
            "intakeId": str(row["id"]),
            "provider": str(row["provider"]),
            "status": str(row["status"]),
            "rightsConfirmedAt": str(row["rights_confirmed_at"]),
            "metadata": metadata if isinstance(metadata, dict) else None,
            "error": error if isinstance(error, dict) else None,
            "expiresAt": row["expires_at"],
            "runId": row["run_id"],
            "createdAt": str(row["created_at"]),
            "updatedAt": str(row["updated_at"]),
        }

    def create_audio_source_intake(
        self,
        *,
        owner_user_id: str,
        provider: str,
        raw_url: str,
        rights_confirmed: bool,
        max_active_intakes: int = 4,
    ) -> dict[str, Any]:
        if not rights_confirmed:
            raise ValueError("Permission confirmation is required before checking a link.")
        self.cleanup_expired_audio_source_intakes()
        now = _utc_now_iso()
        intake_id = str(uuid4())
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                active_count = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM audio_source_intakes
                    WHERE status IN ('queued', 'fetching', 'normalizing', 'ready')
                    """
                ).fetchone()
                if int(active_count["count"]) >= max_active_intakes:
                    raise AudioSourceIntakeCapacityError(
                        "The link preparation queue is full. Try again after another intake finishes."
                    )
                conn.execute(
                    """
                    INSERT INTO audio_source_intakes (
                        id, owner_user_id, provider, raw_url,
                        rights_confirmed_at, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
                    """,
                    (
                        intake_id,
                        owner_user_id or LOCAL_RUNTIME_OWNER_USER_ID,
                        provider,
                        raw_url,
                        now,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AudioSourceIntakeCapacityError(
                "You already have a link being prepared. Stop it or use it before checking another link."
            ) from exc
        return self.get_audio_source_intake(intake_id, owner_user_id=owner_user_id)

    def _get_audio_source_intake_row(
        self,
        intake_id: str,
        *,
        owner_user_id: str | None = None,
    ) -> sqlite3.Row:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM audio_source_intakes WHERE id = ?",
                (intake_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown audio source intake {intake_id}")
        if owner_user_id is not None:
            stored_owner = str(row["owner_user_id"] or LOCAL_RUNTIME_OWNER_USER_ID)
            if stored_owner != owner_user_id:
                raise PermissionError(f"Audio source intake '{intake_id}' does not belong to this user.")
        return row

    def get_audio_source_intake(
        self,
        intake_id: str,
        *,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._get_audio_source_intake_row(intake_id, owner_user_id=owner_user_id)
        if row["status"] == "ready" and row["expires_at"]:
            expires_at = datetime.fromisoformat(str(row["expires_at"]))
            if expires_at <= datetime.now(UTC):
                self._expire_audio_source_intake(intake_id)
                row = self._get_audio_source_intake_row(intake_id, owner_user_id=owner_user_id)
        return self._public_audio_source_intake(row)

    def reserve_next_audio_source_intake(self) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM audio_source_intakes
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            cursor = conn.execute(
                """
                UPDATE audio_source_intakes
                SET status = 'fetching', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, row["id"]),
            )
            if cursor.rowcount == 0:
                return None
        return {
            "intakeId": str(row["id"]),
            "ownerUserId": str(row["owner_user_id"]),
            "provider": str(row["provider"]),
            "rawUrl": str(row["raw_url"]),
            "rightsConfirmedAt": str(row["rights_confirmed_at"]),
        }

    def set_audio_source_intake_status(self, intake_id: str, status: str) -> bool:
        if status not in {"fetching", "normalizing"}:
            raise ValueError(f"Unsupported active intake status '{status}'.")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE audio_source_intakes
                SET status = ?, updated_at = ?
                WHERE id = ? AND status IN ('fetching', 'normalizing')
                """,
                (status, _utc_now_iso(), intake_id),
            )
        return cursor.rowcount > 0

    def is_audio_source_intake_cancelled(self, intake_id: str) -> bool:
        try:
            row = self._get_audio_source_intake_row(intake_id)
        except KeyError:
            return True
        return str(row["status"]) in {"interrupted", "expired"}

    def complete_audio_source_intake(
        self,
        intake_id: str,
        *,
        source_path: str,
        filename: str,
        mime_type: str,
        metadata: dict[str, Any],
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_id = str(uuid4())
        stored = self.artifact_storage.store_file(
            artifact_id=artifact_id,
            filename=filename,
            source_path=source_path,
        )
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=AUDIO_SOURCE_READY_TTL_MINUTES)
        public_metadata = {
            **metadata,
            "filename": filename,
            "mimeType": mime_type,
            "sizeBytes": stored.size_bytes,
        }
        adopted = False
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    UPDATE audio_source_intakes
                    SET status = 'ready', raw_url = NULL,
                        metadata_json = ?, artifact_id = ?, artifact_filename = ?,
                        artifact_mime_type = ?, artifact_size_bytes = ?, artifact_sha256 = ?,
                        artifact_path = ?, diagnostics_json = ?, error_json = NULL,
                        expires_at = ?, updated_at = ?
                    WHERE id = ? AND status IN ('fetching', 'normalizing')
                    """,
                    (
                        _json_dumps(public_metadata),
                        artifact_id,
                        filename,
                        mime_type,
                        stored.size_bytes,
                        stored.content_sha256,
                        stored.storage_ref,
                        _json_dumps(diagnostics),
                        expires_at.isoformat(),
                        now.isoformat(),
                        intake_id,
                    ),
                )
                adopted = cursor.rowcount > 0
        finally:
            if not adopted:
                self.artifact_storage.delete(stored.storage_ref)
        if not adopted:
            raise AudioSourceIntakeStateError("Link preparation finished after it was stopped.")
        return self.get_audio_source_intake(intake_id)

    def fail_audio_source_intake(
        self,
        intake_id: str,
        *,
        error: dict[str, Any],
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        failed = False
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT artifact_path FROM audio_source_intakes WHERE id = ?",
                (intake_id,),
            ).fetchone()
            cursor = conn.execute(
                """
                UPDATE audio_source_intakes
                SET status = 'failed', raw_url = NULL, error_json = ?, diagnostics_json = ?,
                    artifact_path = NULL, expires_at = NULL, updated_at = ?
                WHERE id = ? AND status IN ('queued', 'fetching', 'normalizing')
                """,
                (_json_dumps(error), _json_dumps(diagnostics), now, intake_id),
            )
            failed = cursor.rowcount > 0
        if failed and row and row["artifact_path"]:
            self.artifact_storage.delete(str(row["artifact_path"]))
        return self.get_audio_source_intake(intake_id)

    def interrupt_audio_source_intake(
        self,
        intake_id: str,
        *,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        self._get_audio_source_intake_row(intake_id, owner_user_id=owner_user_id)
        now = _utc_now_iso()
        interrupted = False
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status, artifact_path FROM audio_source_intakes WHERE id = ?",
                (intake_id,),
            ).fetchone()
            if row["status"] == "completed":
                raise AudioSourceIntakeStateError(
                    "This intake already created an analysis run; interrupt the run instead."
                )
            cursor = conn.execute(
                """
                UPDATE audio_source_intakes
                SET status = 'interrupted', raw_url = NULL, artifact_path = NULL,
                    expires_at = NULL, updated_at = ?
                WHERE id = ? AND status IN ('queued', 'fetching', 'normalizing', 'ready')
                """,
                (now, intake_id),
            )
            interrupted = cursor.rowcount > 0
        if interrupted and row["artifact_path"]:
            self.artifact_storage.delete(str(row["artifact_path"]))
        return self.get_audio_source_intake(intake_id, owner_user_id=owner_user_id)

    def _expire_audio_source_intake(self, intake_id: str) -> None:
        now = _utc_now_iso()
        expired = False
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status, artifact_path FROM audio_source_intakes WHERE id = ?",
                (intake_id,),
            ).fetchone()
            if row is None or row["status"] != "ready":
                return
            cursor = conn.execute(
                """
                UPDATE audio_source_intakes
                SET status = 'expired', raw_url = NULL, artifact_path = NULL, updated_at = ?
                WHERE id = ? AND status = 'ready'
                """,
                (now, intake_id),
            )
            expired = cursor.rowcount > 0
        if expired and row["artifact_path"]:
            self.artifact_storage.delete(str(row["artifact_path"]))

    def cleanup_expired_audio_source_intakes(self) -> int:
        now = datetime.now(UTC)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM audio_source_intakes
                WHERE status = 'ready' AND expires_at IS NOT NULL AND expires_at <= ?
                """,
                (now.isoformat(),),
            ).fetchall()
        for row in rows:
            self._expire_audio_source_intake(str(row["id"]))
        return len(rows)

    def create_run_from_intake(
        self,
        intake_id: str,
        *,
        owner_user_id: str,
        analysis_mode: str,
        pitch_note_mode: str,
        pitch_note_backend: str,
        interpretation_mode: str,
        interpretation_profile: str,
        interpretation_model: str | None,
        mt3_mode: str = "off",
    ) -> dict[str, Any]:
        self.get_audio_source_intake(intake_id, owner_user_id=owner_user_id)
        if mt3_mode not in {"off", "enabled"}:
            raise UnsupportedMt3ModeError(mt3_mode)
        resolved_analysis_mode = self._resolve_analysis_mode(analysis_mode)
        run_id = str(uuid4())
        created_at = _utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM audio_source_intakes WHERE id = ?",
                (intake_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown audio source intake {intake_id}")
            stored_owner = str(row["owner_user_id"] or LOCAL_RUNTIME_OWNER_USER_ID)
            if stored_owner != owner_user_id:
                raise PermissionError("Audio source intake does not belong to this user.")
            if row["run_id"]:
                return {"runId": str(row["run_id"])}
            if row["status"] != "ready":
                raise AudioSourceIntakeStateError(
                    f"Audio source intake is '{row['status']}', not ready."
                )
            required_artifact_fields = (
                "artifact_id",
                "artifact_filename",
                "artifact_mime_type",
                "artifact_size_bytes",
                "artifact_sha256",
                "artifact_path",
            )
            if any(row[field] is None for field in required_artifact_fields):
                raise AudioSourceIntakeStateError("Prepared audio artifact is missing.")
            metadata = _json_loads(row["metadata_json"])
            source = {
                "kind": "link",
                "provider": str(row["provider"]),
                "title": metadata.get("title") if isinstance(metadata, dict) else None,
                "creator": metadata.get("creator") if isinstance(metadata, dict) else None,
                "attributionUrl": metadata.get("attributionUrl") if isinstance(metadata, dict) else None,
                "rightsConfirmedAt": str(row["rights_confirmed_at"]),
                "experimental": bool(metadata.get("experimental")) if isinstance(metadata, dict) else False,
            }
            conn.execute(
                """
                INSERT INTO analysis_runs (
                    id, source_artifact_id, requested_analysis_mode, owner_user_id,
                    requested_pitch_note_mode, requested_pitch_note_backend,
                    requested_interpretation_mode, requested_interpretation_profile,
                    requested_interpretation_model, requested_mt3_mode,
                    legacy_request_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    run_id,
                    row["artifact_id"],
                    resolved_analysis_mode,
                    owner_user_id,
                    pitch_note_mode,
                    pitch_note_backend,
                    interpretation_mode,
                    interpretation_profile,
                    interpretation_model,
                    mt3_mode,
                    created_at,
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO run_artifacts (
                    id, run_id, kind, filename, mime_type, size_bytes,
                    content_sha256, path, provenance_json, created_at
                ) VALUES (?, ?, 'source_audio', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["artifact_id"],
                    run_id,
                    row["artifact_filename"],
                    row["artifact_mime_type"],
                    row["artifact_size_bytes"],
                    row["artifact_sha256"],
                    row["artifact_path"],
                    _json_dumps({"source": source}),
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO measurement_outputs (
                    id, run_id, status, result_json, provenance_json, diagnostics_json,
                    error_json, created_at, updated_at
                ) VALUES (?, ?, 'queued', NULL, NULL, NULL, NULL, ?, ?)
                """,
                (str(uuid4()), run_id, created_at, created_at),
            )
            conn.execute(
                """
                UPDATE audio_source_intakes
                SET status = 'completed', raw_url = NULL, artifact_path = NULL,
                    analysis_options_json = ?, run_id = ?, expires_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'ready'
                """,
                (
                    _json_dumps(
                        {
                            "analysisMode": resolved_analysis_mode,
                            "pitchNoteMode": pitch_note_mode,
                            "pitchNoteBackend": pitch_note_backend,
                            "interpretationMode": interpretation_mode,
                            "interpretationProfile": interpretation_profile,
                            "interpretationModel": interpretation_model,
                            "mt3Mode": mt3_mode,
                        }
                    ),
                    run_id,
                    created_at,
                    intake_id,
                ),
            )
        return {"runId": run_id}

    def get_run_by_legacy_request_id(
        self,
        legacy_request_id: str,
        *,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, owner_user_id FROM analysis_runs WHERE legacy_request_id = ?",
                (legacy_request_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown legacy request {legacy_request_id}")
        self._assert_run_owner(row, owner_user_id)
        return self.get_run(row["id"], owner_user_id=owner_user_id)

    def get_run_id_by_legacy_request_id(
        self,
        legacy_request_id: str,
        *,
        owner_user_id: str | None = None,
    ) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, owner_user_id FROM analysis_runs WHERE legacy_request_id = ?",
                (legacy_request_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown legacy request {legacy_request_id}")
        self._assert_run_owner(row, owner_user_id)
        return str(row["id"])

    @staticmethod
    def _public_artifact_record(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "artifactId": row["id"] if isinstance(row, sqlite3.Row) else row["artifactId"],
            "filename": row["filename"] if isinstance(row, sqlite3.Row) else row["filename"],
            "mimeType": row["mime_type"] if isinstance(row, sqlite3.Row) else row["mimeType"],
            "sizeBytes": row["size_bytes"] if isinstance(row, sqlite3.Row) else row["sizeBytes"],
            "contentSha256": (
                row["content_sha256"] if isinstance(row, sqlite3.Row) else row["contentSha256"]
            ),
            **(
                {"kind": row["kind"] if isinstance(row, sqlite3.Row) else row["kind"]}
                if (row["kind"] if isinstance(row, sqlite3.Row) else row.get("kind")) is not None
                else {}
            ),
        }

    @staticmethod
    def _internal_artifact_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "artifactId": row["id"],
            "kind": row["kind"],
            "filename": row["filename"],
            "mimeType": row["mime_type"],
            "sizeBytes": row["size_bytes"],
            "contentSha256": row["content_sha256"],
            "path": row["path"],
            "provenance": _json_loads(row["provenance_json"]),
        }

    @staticmethod
    def _assert_run_owner(row: sqlite3.Row, owner_user_id: str | None) -> None:
        if owner_user_id is None:
            return
        stored_owner = str(row["owner_user_id"] or LOCAL_RUNTIME_OWNER_USER_ID)
        if stored_owner != owner_user_id:
            raise PermissionError(
                f"Run '{row['id']}' does not belong to user '{owner_user_id}'."
            )


    def create_run_from_source_path(self, *, source_path, **kwargs):
        source = Path(source_path)
        content = source.read_bytes()

        existing_artifacts = set()
        if self.artifacts_dir.exists():
            existing_artifacts = set(self.artifacts_dir.iterdir())

        try:
            return self.create_run(
                content=content,
                expose_source_path_in_snapshot=True,
                **kwargs,
            )
        except Exception:
            if self.artifacts_dir.exists():
                for artifact_path in self.artifacts_dir.iterdir():
                    if artifact_path not in existing_artifacts and artifact_path.is_file():
                        artifact_path.unlink(missing_ok=True)
            raise


    def get_source_artifact(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            run_row = conn.execute(
                "SELECT source_artifact_id FROM analysis_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                raise KeyError(f"Unknown run {run_id}")
            artifact_row = conn.execute(
                "SELECT * FROM run_artifacts WHERE id = ?",
                (run_row["source_artifact_id"],),
            ).fetchone()
        if artifact_row is None:
            raise KeyError(f"Run {run_id} is missing its source artifact")
        return {
            "id": artifact_row["id"],
            "artifactId": artifact_row["id"],
            "runId": run_id,
            "kind": artifact_row["kind"],
            "filename": artifact_row["filename"],
            "mimeType": artifact_row["mime_type"],
            "sizeBytes": artifact_row["size_bytes"],
            "contentSha256": artifact_row["content_sha256"],
            "path": artifact_row["path"],
            "createdAt": artifact_row["created_at"],
        }


    def get_measurement_result(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM measurement_outputs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown run {run_id}")
        return _json_loads(row["result_json"])

    def get_measurement_status(self, run_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM measurement_outputs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown run {run_id}")
        return str(row["status"])

    def resolve_artifact_local_path(self, storage_ref: str | None) -> Path | None:
        if not isinstance(storage_ref, str) or not storage_ref:
            return None
        return self.artifact_storage.resolve_local_path(storage_ref)

    def require_local_artifact_path(self, storage_ref: str | None, *, purpose: str) -> str:
        local_path = self.resolve_artifact_local_path(storage_ref)
        if local_path is None or not local_path.is_file():
            raise FileNotFoundError(f"{purpose} is not available as a local file.")
        return str(local_path)

    def is_run_interrupted(self, run_id: str) -> bool:
        return self.get_measurement_status(run_id) == "interrupted"

    def get_interpretation_grounding(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            run_row = conn.execute(
                "SELECT * FROM analysis_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            measurement_row = conn.execute(
                "SELECT * FROM measurement_outputs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            pitch_note_rows = conn.execute(
                """
                SELECT * FROM pitch_note_translation_attempts
                WHERE run_id = ?
                ORDER BY created_at DESC
                """,
                (run_id,),
            ).fetchall()
            mt3_rows = conn.execute(
                """
                SELECT * FROM mt3_attempts
                WHERE run_id = ?
                ORDER BY created_at DESC
                """,
                (run_id,),
            ).fetchall()
        if run_row is None or measurement_row is None:
            raise KeyError(f"Unknown run {run_id}")
        preferred_pitch_note = self._preferred_pitch_note_row(run_row, pitch_note_rows)
        preferred_mt3 = self._preferred_mt3_row(run_row, mt3_rows)
        return {
            "measurementOutputId": str(measurement_row["id"]),
            "measurementStatus": str(measurement_row["status"]),
            "measurementResult": _json_loads(measurement_row["result_json"]),
            "pitchNoteAttemptId": (
                str(preferred_pitch_note["id"]) if preferred_pitch_note is not None else None
            ),
            "pitchNoteStatus": (
                str(preferred_pitch_note["status"]) if preferred_pitch_note is not None else "not_requested"
            ),
            "pitchNoteResult": (
                _json_loads(preferred_pitch_note["result_json"])
                if preferred_pitch_note is not None
                else None
            ),
            # MT3 grounding. Optional like pitchNote — present only when
            # an MT3 attempt has completed for the run. Phase 2 receives
            # this verbatim in OPTIONAL_MT3_TRANSCRIPTION_RESULT_JSON
            # (see _build_phase2_prompt). Additive only: PURPOSE.md
            # invariant #1 — Phase 1 is ground truth.
            "mt3AttemptId": (
                str(preferred_mt3["id"]) if preferred_mt3 is not None else None
            ),
            "mt3Status": (
                str(preferred_mt3["status"]) if preferred_mt3 is not None else "not_requested"
            ),
            "mt3Result": (
                _json_loads(preferred_mt3["result_json"])
                if preferred_mt3 is not None
                else None
            ),
        }

    def get_run(self, run_id: str, *, owner_user_id: str | None = None) -> dict[str, Any]:
        with self._connect() as conn:
            run_row = conn.execute(
                "SELECT * FROM analysis_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if run_row is None:
                raise KeyError(f"Unknown run {run_id}")
            self._assert_run_owner(run_row, owner_user_id)

            artifact_row = conn.execute(
                "SELECT * FROM run_artifacts WHERE id = ?", (run_row["source_artifact_id"],)
            ).fetchone()
            stem_rows = conn.execute(
                """
                SELECT * FROM run_artifacts
                WHERE run_id = ? AND kind LIKE 'stem_%'
                ORDER BY created_at ASC
                """,
                (run_id,),
            ).fetchall()
            measurement_row = conn.execute(
                "SELECT * FROM measurement_outputs WHERE run_id = ?", (run_id,)
            ).fetchone()
            pitch_note_rows = conn.execute(
                """
                SELECT * FROM pitch_note_translation_attempts
                WHERE run_id = ?
                ORDER BY created_at DESC
                """,
                (run_id,),
            ).fetchall()
            interpretation_rows = conn.execute(
                """
                SELECT * FROM interpretation_attempts
                WHERE run_id = ?
                ORDER BY created_at DESC
                """,
                (run_id,),
            ).fetchall()
            mt3_rows = conn.execute(
                """
                SELECT * FROM mt3_attempts
                WHERE run_id = ?
                ORDER BY created_at DESC
                """,
                (run_id,),
            ).fetchall()

        preferred_pitch_note = self._preferred_pitch_note_row(run_row, pitch_note_rows)
        preferred_interpretation = self._preferred_interpretation_row(
            run_row, interpretation_rows
        )
        preferred_mt3 = self._preferred_mt3_row(run_row, mt3_rows)
        measurement_status = measurement_row["status"]
        # requested_mt3_mode may be NULL on rows that predate the column
        # backfill (the _ensure_column UPDATE handles most cases but a race
        # at app start can leave one through). Default to "off" so the
        # snapshot is always coherent.
        requested_mt3_mode = (
            run_row["requested_mt3_mode"]
            if run_row["requested_mt3_mode"] is not None
            else "off"
        )

        source_artifact_provenance = _json_loads(artifact_row["provenance_json"]) or {}
        public_source = source_artifact_provenance.get("source")
        if not isinstance(public_source, dict):
            public_source = {
                "kind": "upload",
                "provider": "upload",
                "title": artifact_row["filename"],
                "creator": None,
                "attributionUrl": None,
                "rightsConfirmedAt": None,
                "experimental": False,
            }

        return {
            "runId": run_id,
            "source": public_source,
            "requestedStages": {
                "analysisMode": run_row["requested_analysis_mode"],
                "pitchNoteMode": run_row["requested_pitch_note_mode"],
                "pitchNoteBackend": run_row["requested_pitch_note_backend"],
                "interpretationMode": run_row["requested_interpretation_mode"],
                "interpretationProfile": run_row["requested_interpretation_profile"],
                "interpretationModel": run_row["requested_interpretation_model"],
                "mt3Mode": requested_mt3_mode,
            },
            "artifacts": {
                "sourceAudio": {
                    "artifactId": artifact_row["id"],
                    "filename": artifact_row["filename"],
                    "mimeType": artifact_row["mime_type"],
                    "sizeBytes": artifact_row["size_bytes"],
                    "contentSha256": artifact_row["content_sha256"],
                    **(
                        {"path": artifact_row["path"]}
                        if (_json_loads(artifact_row["provenance_json"]) or {}).get(
                            "exposePathInSnapshot"
                        )
                        else {}
                    ),
                },
                "stems": [self._public_artifact_record(row) for row in stem_rows],
            },
            "stages": {
                "measurement": {
                    "status": measurement_status,
                    "authoritative": True,
                    "result": _json_loads(measurement_row["result_json"]),
                    "provenance": _json_loads(measurement_row["provenance_json"]),
                    "diagnostics": _json_loads(measurement_row["diagnostics_json"]),
                    "error": _json_loads(measurement_row["error_json"]),
                },
                "pitchNoteTranslation": self._pitch_note_stage_snapshot(
                    run_row["requested_pitch_note_mode"],
                    measurement_status,
                    preferred_pitch_note,
                    pitch_note_rows,
                ),
                "interpretation": self._interpretation_stage_snapshot(
                    run_row["requested_interpretation_mode"],
                    measurement_status,
                    preferred_interpretation,
                    interpretation_rows,
                ),
                "mt3": self._mt3_stage_snapshot(
                    requested_mt3_mode,
                    measurement_status,
                    preferred_mt3,
                    mt3_rows,
                ),
            },
        }

    def mark_measurement_running(self, run_id: str) -> None:
        self._update_measurement_row(run_id, status="running")

    def reserve_measurement_run(self, run_id: str) -> bool:
        now = _utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE measurement_outputs
                SET status = 'running', updated_at = ?
                WHERE run_id = ? AND status = 'queued'
                """,
                (now, run_id),
            )
        return cursor.rowcount > 0

    def reserve_next_measurement_run(self) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT mo.id AS measurement_id, mo.run_id,
                       ar.requested_analysis_mode,
                       ar.requested_pitch_note_mode, ar.requested_pitch_note_backend
                FROM measurement_outputs mo
                JOIN analysis_runs ar ON ar.id = mo.run_id
                WHERE mo.status = 'queued'
                ORDER BY mo.created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            cursor = conn.execute(
                """
                UPDATE measurement_outputs
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, row["measurement_id"]),
            )
            if cursor.rowcount == 0:
                return None
        return {
            "runId": row["run_id"],
            "requestedAnalysisMode": row["requested_analysis_mode"],
            "requestedPitchNoteMode": row["requested_pitch_note_mode"],
            "requestedPitchNoteBackend": row["requested_pitch_note_backend"],
        }

    def get_run_owner_user_id(self, run_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT owner_user_id FROM analysis_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown run {run_id}")
        return str(row["owner_user_id"] or LOCAL_RUNTIME_OWNER_USER_ID)

    def complete_measurement(
        self,
        run_id: str,
        *,
        payload: dict[str, Any],
        provenance: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> None:
        measurement_result = dict(payload)
        # Strip transcriptionDetail — it's a Layer 2 (pitch/note translation) concern.
        # The pitch/note translation worker produces this independently through its own stage.
        measurement_result.pop("transcriptionDetail", None)
        # Strip transcription — same story for the MT3 polyphonic-transcription
        # namespace. analyze.py's legacy env-var hook (ASA_ENABLE_MT3=1) may
        # still emit it for direct CLI users, but the staged runtime owns
        # this stage now and stores it under stages.mt3 instead. The pop is
        # defense-in-depth so an operator who exports the env var globally
        # doesn't leak a stale `transcription` key into the measurement row.
        measurement_result.pop("transcription", None)
        updated = self._update_measurement_row(
            run_id,
            status="completed",
            result=measurement_result,
            provenance=provenance,
            diagnostics=diagnostics,
            error=None,
            guard_terminal=True,
        )
        # Only enqueue the downstream pipeline if this completion actually landed.
        # If the run was interrupted in the TOCTOU window the update no-ops, and
        # enqueuing here would resurrect a fresh pipeline for an interrupted run.
        if updated:
            self._enqueue_requested_followups(run_id)

    def fail_measurement(
        self,
        run_id: str,
        *,
        error: dict[str, Any],
        diagnostics: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        self._update_measurement_row(
            run_id,
            status="failed",
            result=None,
            provenance=provenance,
            diagnostics=diagnostics,
            error=error,
            guard_terminal=True,
        )

    def create_pitch_note_attempt(
        self,
        run_id: str,
        *,
        backend_id: str,
        mode: str,
        status: str = "queued",
        result: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> str:
        attempt_id = str(uuid4())
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pitch_note_translation_attempts (
                    id,
                    run_id,
                    backend_id,
                    mode,
                    status,
                    result_json,
                    provenance_json,
                    diagnostics_json,
                    error_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    run_id,
                    backend_id,
                    mode,
                    status,
                    _json_dumps(result),
                    _json_dumps(provenance),
                    None,
                    None,
                    now,
                    now,
                ),
            )
            if status == "completed":
                conn.execute(
                    """
                    UPDATE analysis_runs
                    SET preferred_pitch_note_attempt_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (attempt_id, now, run_id),
                )
        return attempt_id

    def reserve_pitch_note_attempt(self, attempt_id: str) -> bool:
        now = _utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE pitch_note_translation_attempts
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, attempt_id),
            )
        return cursor.rowcount > 0

    def reserve_next_pitch_note_attempt(self) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sea.id, sea.run_id, sea.backend_id, sea.mode
                FROM pitch_note_translation_attempts sea
                JOIN measurement_outputs mo ON mo.run_id = sea.run_id
                WHERE sea.status = 'queued' AND mo.status = 'completed'
                ORDER BY sea.created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            cursor = conn.execute(
                """
                UPDATE pitch_note_translation_attempts
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, row["id"]),
            )
            if cursor.rowcount == 0:
                return None
        return {
            "attemptId": row["id"],
            "runId": row["run_id"],
            "backendId": row["backend_id"],
            "mode": row["mode"],
        }

    def complete_pitch_note_attempt(
        self,
        attempt_id: str,
        *,
        result: dict[str, Any] | None,
        provenance: dict[str, Any] | None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            attempt_row = conn.execute(
                "SELECT run_id FROM pitch_note_translation_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()
            if attempt_row is None:
                raise KeyError(f"Unknown pitch/note translation attempt {attempt_id}")
            cursor = conn.execute(
                """
                UPDATE pitch_note_translation_attempts
                SET status = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE id = ? AND status NOT IN ('completed', 'failed', 'interrupted')
                """,
                (
                    "completed",
                    _json_dumps(result),
                    _json_dumps(provenance),
                    _json_dumps(diagnostics),
                    None,
                    now,
                    attempt_id,
                ),
            )
            if cursor.rowcount == 0:
                # Already terminal — e.g. interrupt_run flipped this attempt to
                # 'interrupted' while its (now-orphaned) subprocess was still
                # finishing. Do NOT resurrect it to 'completed' or hijack the
                # run's preferred pointer (the documented resurrection bug).
                return
            conn.execute(
                """
                UPDATE analysis_runs
                SET preferred_pitch_note_attempt_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (attempt_id, now, attempt_row["run_id"]),
            )

    def fail_pitch_note_attempt(
        self,
        attempt_id: str,
        *,
        error: dict[str, Any],
        provenance: dict[str, Any] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        self._update_attempt_row(
            table="pitch_note_translation_attempts",
            attempt_id=attempt_id,
            status="failed",
            result=None,
            provenance=provenance,
            diagnostics=diagnostics,
            error=error,
        )

    # ─── MT3 polyphonic-transcription stage ────────────────────────────
    # Peer of pitch_note_translation. Gated only on measurement completion
    # (NOT on pitch_note completion) so the two can run concurrently. See
    # docs/ARCHITECTURE_STRATEGY.md and mt3_transcription.py for the
    # additive-only invariant: MT3 output never feeds back into the
    # measurement result.

    def create_mt3_attempt(
        self,
        run_id: str,
        *,
        checkpoint_id: str = DEFAULT_MT3_CHECKPOINT_ID,
        status: str = "queued",
        result: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> str:
        attempt_id = str(uuid4())
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mt3_attempts (
                    id,
                    run_id,
                    checkpoint_id,
                    status,
                    result_json,
                    provenance_json,
                    diagnostics_json,
                    error_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    run_id,
                    checkpoint_id,
                    status,
                    _json_dumps(result),
                    _json_dumps(provenance),
                    None,
                    None,
                    now,
                    now,
                ),
            )
            if status == "completed":
                conn.execute(
                    """
                    UPDATE analysis_runs
                    SET preferred_mt3_attempt_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (attempt_id, now, run_id),
                )
        return attempt_id

    def reserve_mt3_attempt(self, attempt_id: str) -> bool:
        now = _utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE mt3_attempts
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, attempt_id),
            )
        return cursor.rowcount > 0

    def reserve_next_mt3_attempt(self) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ma.id, ma.run_id, ma.checkpoint_id
                FROM mt3_attempts ma
                JOIN measurement_outputs mo ON mo.run_id = ma.run_id
                WHERE ma.status = 'queued' AND mo.status = 'completed'
                ORDER BY ma.created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            cursor = conn.execute(
                """
                UPDATE mt3_attempts
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, row["id"]),
            )
            if cursor.rowcount == 0:
                return None
        return {
            "attemptId": row["id"],
            "runId": row["run_id"],
            "checkpointId": row["checkpoint_id"],
        }

    def complete_mt3_attempt(
        self,
        attempt_id: str,
        *,
        result: dict[str, Any] | None,
        provenance: dict[str, Any] | None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            attempt_row = conn.execute(
                "SELECT run_id FROM mt3_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()
            if attempt_row is None:
                raise KeyError(f"Unknown mt3 attempt {attempt_id}")
            cursor = conn.execute(
                """
                UPDATE mt3_attempts
                SET status = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE id = ? AND status NOT IN ('completed', 'failed', 'interrupted')
                """,
                (
                    "completed",
                    _json_dumps(result),
                    _json_dumps(provenance),
                    _json_dumps(diagnostics),
                    None,
                    now,
                    attempt_id,
                ),
            )
            if cursor.rowcount == 0:
                # Already terminal (interrupted while the orphaned MT3 subprocess
                # was still finishing) — do not resurrect or hijack the pointer.
                return
            conn.execute(
                """
                UPDATE analysis_runs
                SET preferred_mt3_attempt_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (attempt_id, now, attempt_row["run_id"]),
            )

    def fail_mt3_attempt(
        self,
        attempt_id: str,
        *,
        error: dict[str, Any],
        provenance: dict[str, Any] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        self._update_attempt_row(
            table="mt3_attempts",
            attempt_id=attempt_id,
            status="failed",
            result=None,
            provenance=provenance,
            diagnostics=diagnostics,
            error=error,
        )

    def create_interpretation_attempt(
        self,
        run_id: str,
        *,
        profile_id: str,
        model_name: str | None,
        status: str = "queued",
        result: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> str:
        attempt_id = str(uuid4())
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO interpretation_attempts (
                    id,
                    run_id,
                    profile_id,
                    model_name,
                    status,
                    result_json,
                    provenance_json,
                    diagnostics_json,
                    error_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    run_id,
                    profile_id,
                    model_name,
                    status,
                    _json_dumps(result),
                    _json_dumps(provenance),
                    None,
                    None,
                    now,
                    now,
                ),
            )
            if status == "completed":
                conn.execute(
                    """
                    UPDATE analysis_runs
                    SET preferred_interpretation_attempt_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (attempt_id, now, run_id),
                )
        return attempt_id

    def reserve_interpretation_attempt(self, attempt_id: str) -> bool:
        now = _utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE interpretation_attempts
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, attempt_id),
            )
        return cursor.rowcount > 0

    def reserve_next_interpretation_attempt(self) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self._connect() as conn:
            # Interpretation is the LAST stage: it consumes the additive
            # grounding produced by the mt3 and pitch_note peers (Gemini reads
            # mt3Result / pitchNoteResult from get_interpretation_grounding in
            # _execute_interpretation_attempt). Those peers race interpretation
            # and the slower one (MT3 loads multi-GB JAX weights) usually loses,
            # so without this guard the grounding is almost always None by the
            # time interpretation runs. Block a queued interpretation while
            # either grounding stage is still in-flight ('queued'/'running');
            # the guard reads no requested_*_mode because no in-flight rows means
            # the stage either wasn't requested or already settled. Terminal
            # states (completed/failed/interrupted) are not in-flight, so a
            # failure/interrupt/restart-recovery unblocks interpretation, which
            # then runs with whatever grounding is available (possibly None).
            row = conn.execute(
                """
                SELECT ia.id, ia.run_id, ia.profile_id, ia.model_name
                FROM interpretation_attempts ia
                JOIN measurement_outputs mo ON mo.run_id = ia.run_id
                WHERE ia.status = 'queued'
                  AND mo.status = 'completed'
                  AND NOT EXISTS (
                    SELECT 1 FROM mt3_attempts ma
                    WHERE ma.run_id = ia.run_id AND ma.status IN ('queued', 'running')
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM pitch_note_translation_attempts pna
                    WHERE pna.run_id = ia.run_id AND pna.status IN ('queued', 'running')
                  )
                ORDER BY ia.created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            cursor = conn.execute(
                """
                UPDATE interpretation_attempts
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, row["id"]),
            )
            if cursor.rowcount == 0:
                return None
        return {
            "attemptId": row["id"],
            "runId": row["run_id"],
            "profileId": row["profile_id"],
            "modelName": row["model_name"],
        }

    def complete_interpretation_attempt(
        self,
        attempt_id: str,
        *,
        result: dict[str, Any] | None,
        provenance: dict[str, Any] | None,
        diagnostics: dict[str, Any] | None = None,
        grounded_measurement_output_id: str | None = None,
        grounded_pitch_note_attempt_id: str | None = None,
    ) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            attempt_row = conn.execute(
                "SELECT run_id FROM interpretation_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()
            if attempt_row is None:
                raise KeyError(f"Unknown interpretation attempt {attempt_id}")
            cursor = conn.execute(
                """
                UPDATE interpretation_attempts
                SET status = ?, grounded_measurement_output_id = ?, grounded_pitch_note_attempt_id = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE id = ? AND status NOT IN ('completed', 'failed', 'interrupted')
                """,
                (
                    "completed",
                    grounded_measurement_output_id,
                    grounded_pitch_note_attempt_id,
                    _json_dumps(result),
                    _json_dumps(provenance),
                    _json_dumps(diagnostics),
                    None,
                    now,
                    attempt_id,
                ),
            )
            if cursor.rowcount == 0:
                # Already terminal (interrupted between the is_run_interrupted
                # gate and here) — do not resurrect or hijack the pointer.
                return
            conn.execute(
                """
                UPDATE analysis_runs
                SET preferred_interpretation_attempt_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (attempt_id, now, attempt_row["run_id"]),
            )

    def fail_interpretation_attempt(
        self,
        attempt_id: str,
        *,
        error: dict[str, Any],
        provenance: dict[str, Any] | None = None,
        diagnostics: dict[str, Any] | None = None,
        grounded_measurement_output_id: str | None = None,
        grounded_pitch_note_attempt_id: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE interpretation_attempts
                SET status = ?, grounded_measurement_output_id = ?, grounded_pitch_note_attempt_id = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE id = ? AND status NOT IN ('completed', 'failed', 'interrupted')
                """,
                (
                    "failed",
                    grounded_measurement_output_id,
                    grounded_pitch_note_attempt_id,
                    None,
                    _json_dumps(provenance),
                    _json_dumps(diagnostics),
                    _json_dumps(error),
                    _utc_now_iso(),
                    attempt_id,
                ),
            )

    def record_artifact(
        self,
        run_id: str,
        *,
        kind: str,
        source_path: str,
        filename: str,
        mime_type: str,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_id = str(uuid4())
        created_at = _utc_now_iso()
        stored_artifact = self.artifact_storage.store_file(
            artifact_id=artifact_id,
            filename=filename,
            source_path=source_path,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_artifacts (
                    id,
                    run_id,
                    kind,
                    filename,
                    mime_type,
                    size_bytes,
                    content_sha256,
                    path,
                    provenance_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    run_id,
                    kind,
                    filename,
                    mime_type,
                    stored_artifact.size_bytes,
                    stored_artifact.content_sha256,
                    stored_artifact.storage_ref,
                    _json_dumps(provenance),
                    created_at,
                ),
            )
        return {
            "artifactId": artifact_id,
            "path": stored_artifact.storage_ref,
            "kind": kind,
            "filename": filename,
            "mimeType": mime_type,
            "sizeBytes": stored_artifact.size_bytes,
        }

    def get_artifacts_by_kind(self, run_id: str, kind_prefix: str) -> list[dict[str, Any]]:
        return [
            self._public_artifact_record(record)
            for record in self.get_internal_artifacts_by_kind(run_id, kind_prefix)
        ]

    def get_internal_artifacts_by_kind(self, run_id: str, kind_prefix: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM run_artifacts
                WHERE run_id = ? AND kind LIKE ?
                ORDER BY created_at ASC
                """,
                (run_id, f"{kind_prefix}%"),
            ).fetchall()
        return [self._internal_artifact_record(row) for row in rows]

    def get_internal_artifact(self, run_id: str, artifact_id: str) -> dict[str, Any] | None:
        matches = [
            artifact
            for artifact in self.get_internal_artifacts_by_kind(run_id, "")
            if artifact["artifactId"] == artifact_id
        ]
        return matches[0] if matches else None

    def recover_incomplete_attempts(self) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE measurement_outputs
                SET status = 'interrupted', updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            conn.execute(
                """
                UPDATE pitch_note_translation_attempts
                SET status = 'interrupted', updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            conn.execute(
                """
                UPDATE interpretation_attempts
                SET status = 'interrupted', updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            conn.execute(
                """
                UPDATE mt3_attempts
                SET status = 'interrupted', updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            conn.execute(
                """
                UPDATE audio_source_intakes
                SET status = 'interrupted', raw_url = NULL, updated_at = ?
                WHERE status IN ('fetching', 'normalizing')
                """,
                (now,),
            )
        for temp_dir in self.runtime_dir.glob("asa_intake_*"):
            if temp_dir.is_dir():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def interrupt_run(self, run_id: str) -> dict[str, Any]:
        now = _utc_now_iso()
        with self._connect() as conn:
            run_row = conn.execute(
                "SELECT id FROM analysis_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                raise KeyError(f"Unknown run {run_id}")

            artifact_rows = conn.execute(
                """
                SELECT path FROM run_artifacts
                WHERE run_id = ? AND kind IN ('source_audio', 'stem_bass', 'stem_other')
                """,
                (run_id,),
            ).fetchall()

            interruption_diagnostics = _json_dumps({"interruptedAt": now})
            conn.execute(
                """
                UPDATE measurement_outputs
                SET status = 'interrupted',
                    result_json = NULL,
                    provenance_json = NULL,
                    diagnostics_json = ?,
                    error_json = NULL,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (interruption_diagnostics, now, run_id),
            )
            conn.execute(
                """
                UPDATE pitch_note_translation_attempts
                SET status = 'interrupted',
                    result_json = NULL,
                    provenance_json = NULL,
                    diagnostics_json = ?,
                    error_json = NULL,
                    updated_at = ?
                WHERE run_id = ? AND status IN ('queued', 'running', 'completed', 'failed')
                """,
                (interruption_diagnostics, now, run_id),
            )
            conn.execute(
                """
                UPDATE interpretation_attempts
                SET status = 'interrupted',
                    result_json = NULL,
                    diagnostics_json = ?,
                    error_json = NULL,
                    updated_at = ?
                WHERE run_id = ? AND status IN ('queued', 'running', 'completed', 'failed')
                """,
                (interruption_diagnostics, now, run_id),
            )
            conn.execute(
                """
                UPDATE mt3_attempts
                SET status = 'interrupted',
                    result_json = NULL,
                    provenance_json = NULL,
                    diagnostics_json = ?,
                    error_json = NULL,
                    updated_at = ?
                WHERE run_id = ? AND status IN ('queued', 'running', 'completed', 'failed')
                """,
                (interruption_diagnostics, now, run_id),
            )
            conn.execute(
                """
                UPDATE analysis_runs
                SET preferred_pitch_note_attempt_id = NULL,
                    preferred_interpretation_attempt_id = NULL,
                    preferred_mt3_attempt_id = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, run_id),
            )

        for row in artifact_rows:
            artifact_path = row["path"]
            if isinstance(artifact_path, str) and artifact_path:
                self.artifact_storage.delete(artifact_path)

        return self.get_run(run_id)

    def delete_run(self, run_id: str) -> None:
        with self._connect() as conn:
            run_row = conn.execute(
                "SELECT id FROM analysis_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                raise KeyError(f"Unknown run {run_id}")

            artifact_rows = conn.execute(
                "SELECT path FROM run_artifacts WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            conn.execute("DELETE FROM interpretation_attempts WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM pitch_note_translation_attempts WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM mt3_attempts WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM measurement_outputs WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM run_artifacts WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM analysis_runs WHERE id = ?", (run_id,))

        for row in artifact_rows:
            artifact_path = row["path"]
            if isinstance(artifact_path, str) and artifact_path:
                self.artifact_storage.delete(artifact_path)

    def update_measurement_progress(
        self,
        run_id: str,
        *,
        step_key: str,
        message: str,
        fraction: float | None = None,
    ) -> dict[str, Any] | None:
        return self._update_stage_progress(
            table="measurement_outputs",
            identifier_column="run_id",
            identifier=run_id,
            step_key=step_key,
            message=message,
            fraction=fraction,
        )

    def update_measurement_pipeline_progress(
        self,
        run_id: str,
        *,
        pipeline_key: str,
        status: str,
        step_key: str,
        message: str,
    ) -> dict[str, Any] | None:
        if status not in MEASUREMENT_PIPELINE_PROGRESS_STATUSES:
            raise ValueError(f"Unsupported measurement pipeline status '{status}'.")

        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status, diagnostics_json FROM measurement_outputs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown measurement run '{run_id}'")
            if str(row["status"]) != "running":
                return None

            diagnostics = _json_loads(row["diagnostics_json"])
            if not isinstance(diagnostics, dict):
                diagnostics = {}

            pipeline_progress_raw = diagnostics.get("pipelineProgress")
            pipeline_progress = (
                dict(pipeline_progress_raw)
                if isinstance(pipeline_progress_raw, dict)
                else {}
            )
            existing_progress = pipeline_progress.get(pipeline_key)
            if isinstance(existing_progress, dict):
                seq_raw = existing_progress.get("seq")
                seq = int(seq_raw) + 1 if isinstance(seq_raw, int) else 1
            else:
                seq = 1

            progress_payload = {
                "status": status,
                "stepKey": step_key,
                "message": message,
                "updatedAt": now,
                "seq": seq,
            }
            pipeline_progress[pipeline_key] = progress_payload
            diagnostics["pipelineProgress"] = pipeline_progress
            conn.execute(
                """
                UPDATE measurement_outputs
                SET diagnostics_json = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    _json_dumps(diagnostics),
                    now,
                    run_id,
                ),
            )
        return progress_payload

    def update_pitch_note_attempt_progress(
        self,
        attempt_id: str,
        *,
        step_key: str,
        message: str,
        fraction: float | None = None,
    ) -> dict[str, Any] | None:
        return self._update_stage_progress(
            table="pitch_note_translation_attempts",
            identifier_column="id",
            identifier=attempt_id,
            step_key=step_key,
            message=message,
            fraction=fraction,
        )

    def update_interpretation_attempt_progress(
        self,
        attempt_id: str,
        *,
        step_key: str,
        message: str,
        fraction: float | None = None,
    ) -> dict[str, Any] | None:
        return self._update_stage_progress(
            table="interpretation_attempts",
            identifier_column="id",
            identifier=attempt_id,
            step_key=step_key,
            message=message,
            fraction=fraction,
        )

    def _update_measurement_row(
        self,
        run_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        diagnostics: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        guard_terminal: bool = False,
    ) -> bool:
        # When guard_terminal is set, refuse to transition a measurement row that
        # is already terminal. This closes the interrupt TOCTOU: interrupt_run can
        # flip the row to 'interrupted' after _execute_measurement_run's
        # is_run_interrupted check but before complete/fail. Without the guard the
        # late writer resurrects it — and, via complete_measurement, would enqueue
        # a fresh follow-up pipeline for an interrupted run. Returns True iff a row
        # was actually updated.
        terminal_guard = (
            " AND status NOT IN ('completed', 'failed', 'interrupted')"
            if guard_terminal
            else ""
        )
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE measurement_outputs
                SET status = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE run_id = ?{terminal_guard}
                """,
                (
                    status,
                    _json_dumps(result),
                    _json_dumps(provenance),
                    _json_dumps(diagnostics),
                    _json_dumps(error),
                    _utc_now_iso(),
                    run_id,
                ),
            )
            updated = cursor.rowcount > 0
        return updated

    def _update_attempt_row(
        self,
        *,
        table: str,
        attempt_id: str,
        status: str,
        result: dict[str, Any] | None,
        provenance: dict[str, Any] | None,
        diagnostics: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE {table}
                SET status = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE id = ? AND status NOT IN ('completed', 'failed', 'interrupted')
                """,
                (
                    status,
                    _json_dumps(result),
                    _json_dumps(provenance),
                    _json_dumps(diagnostics),
                    _json_dumps(error),
                    _utc_now_iso(),
                    attempt_id,
                ),
            )

    def _update_stage_progress(
        self,
        *,
        table: str,
        identifier_column: str,
        identifier: str,
        step_key: str,
        message: str,
        fraction: float | None = None,
    ) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT status, diagnostics_json FROM {table} WHERE {identifier_column} = ?",
                (identifier,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown stage row for {identifier}")
            if str(row["status"]) != "running":
                return None

            diagnostics = _json_loads(row["diagnostics_json"])
            if not isinstance(diagnostics, dict):
                diagnostics = {}

            progress = diagnostics.get("progress")
            if isinstance(progress, dict):
                seq_raw = progress.get("seq")
                seq = int(seq_raw) + 1 if isinstance(seq_raw, int) else 1
            else:
                seq = 1

            progress_payload = {
                "stepKey": step_key,
                "message": message,
                "updatedAt": now,
                "seq": seq,
            }
            if isinstance(fraction, (int, float)):
                progress_payload["fraction"] = min(max(float(fraction), 0.0), 1.0)
            diagnostics["progress"] = progress_payload
            conn.execute(
                f"""
                UPDATE {table}
                SET diagnostics_json = ?, updated_at = ?
                WHERE {identifier_column} = ?
                """,
                (
                    _json_dumps(diagnostics),
                    now,
                    identifier,
                ),
            )
        return progress_payload

    def _enqueue_requested_followups(self, run_id: str) -> None:
        with self._connect() as conn:
            run_row = conn.execute(
                "SELECT * FROM analysis_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                return
            # Re-assert measurement is still completed before enqueuing. complete_measurement
            # commits the measurement-complete update in one transaction and calls this in a
            # separate one; an interrupt_run committing in between (measurement worker thread
            # vs. event-loop thread) would otherwise leave inert 'queued' follow-up rows on an
            # already-interrupted run. The caller's `if updated:` gate can't see this window.
            measurement_row = conn.execute(
                "SELECT status FROM measurement_outputs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if measurement_row is None or measurement_row["status"] != "completed":
                return
            pitch_note_exists = conn.execute(
                "SELECT 1 FROM pitch_note_translation_attempts WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
            interpretation_exists = conn.execute(
                "SELECT 1 FROM interpretation_attempts WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
            mt3_exists = conn.execute(
                "SELECT 1 FROM mt3_attempts WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()

        if (
            run_row["requested_pitch_note_mode"] != "off"
            and pitch_note_exists is None
        ):
            self.create_pitch_note_attempt(
                run_id,
                backend_id=self._resolve_pitch_note_backend(
                    run_row["requested_pitch_note_backend"]
                ),
                mode=run_row["requested_pitch_note_mode"],
                status="queued",
                provenance={
                    "backendId": self._resolve_pitch_note_backend(
                        run_row["requested_pitch_note_backend"]
                    ),
                },
            )

        # MT3 enqueue. requested_mt3_mode is read via .get-like fallback
        # because old SQLite rows may have NULL there (the _ensure_column
        # backfill above writes 'off', but defense-in-depth lets us survive
        # a race where a brand-new run is created right at the seam).
        requested_mt3_mode = (
            run_row["requested_mt3_mode"]
            if run_row["requested_mt3_mode"] is not None
            else "off"
        )
        if requested_mt3_mode != "off" and mt3_exists is None:
            self.create_mt3_attempt(
                run_id,
                checkpoint_id=DEFAULT_MT3_CHECKPOINT_ID,
                status="queued",
                provenance={"checkpointId": DEFAULT_MT3_CHECKPOINT_ID},
            )

        # Interpretation MUST be enqueued LAST — after the pitch_note and mt3
        # blocks above. reserve_next_interpretation_attempt blocks a queued
        # interpretation while an mt3/pitch_note attempt is in-flight
        # ('queued'/'running'), but each create_*_attempt commits in its own
        # transaction. Were the interpretation row created before the grounding
        # rows, the 0.25s-poll interpretation worker could reserve an ungrounded
        # attempt in the window before the grounding row commits — silently
        # defeating the gate for the mt3-on/pitch_note-off case. Creating it last
        # guarantees the grounding rows already exist whenever interpretation does.
        if (
            run_row["requested_interpretation_mode"] != "off"
            and interpretation_exists is None
        ):
            self.create_interpretation_attempt(
                run_id,
                profile_id=run_row["requested_interpretation_profile"],
                model_name=run_row["requested_interpretation_model"],
                status="queued",
                provenance={
                    "profileId": run_row["requested_interpretation_profile"],
                    "modelName": run_row["requested_interpretation_model"],
                },
            )

    def _count_active_measurement_runs(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM measurement_outputs
                WHERE status IN ('queued', 'running')
                """
            ).fetchone()
        return int(row["count"])

    @staticmethod
    def _resolve_pitch_note_backend(requested_backend: str) -> str:
        normalized = str(requested_backend or "").strip().lower()
        if normalized in ("auto", "", "default", "torchcrepe", "torchcrepe-viterbi"):
            return "torchcrepe-viterbi"
        raise UnsupportedPitchNoteBackendError(normalized)

    @staticmethod
    def _resolve_analysis_mode(requested_mode: str) -> str:
        if requested_mode in {"full", "standard"}:
            return requested_mode
        raise ValueError(f"Unsupported analysis mode '{requested_mode}'.")

    @staticmethod
    def resolve_measurement_flags(
        requested_pitch_note_mode: str,
    ) -> tuple[bool, bool]:
        # Transcription is handled by the dedicated pitch_note_translation
        # stage enqueued via _enqueue_requested_followups() — running it inline
        # during measurement was redundant since transcriptionDetail is popped
        # in complete_measurement.
        #
        # Separation is needed at MEASUREMENT time for the Phase 1.B stem-first
        # overlay (stemAnalysis namespace) — analyze.py only emits per-stem
        # analyzers when stems exist when the orchestrator runs. So when the
        # user opts into pitch-note translation (mode != "off"), run separation
        # inline so stemAnalysis is in the payload that Phase 2 sees, without
        # waiting on a second separation pass.
        if requested_pitch_note_mode not in ("off", "stem_notes"):
            raise UnsupportedPitchNoteModeError(requested_pitch_note_mode)
        run_separation = requested_pitch_note_mode == "stem_notes"
        return run_separation, False

    @staticmethod
    def _preferred_pitch_note_row(
        run_row: sqlite3.Row, pitch_note_rows: list[sqlite3.Row]
    ) -> sqlite3.Row | None:
        preferred_id = run_row["preferred_pitch_note_attempt_id"]
        if preferred_id:
            for row in pitch_note_rows:
                if row["id"] == preferred_id:
                    return row
        return pitch_note_rows[0] if pitch_note_rows else None

    @staticmethod
    def _preferred_mt3_row(
        run_row: sqlite3.Row, mt3_rows: list[sqlite3.Row]
    ) -> sqlite3.Row | None:
        # Mirror _preferred_pitch_note_row: explicit preference wins, else
        # newest attempt. _ensure_column may not have populated
        # preferred_mt3_attempt_id on legacy rows; the column access is
        # defensive (sqlite3.Row raises IndexError on missing columns,
        # so we read via try/except rather than [].).
        try:
            preferred_id = run_row["preferred_mt3_attempt_id"]
        except (IndexError, KeyError):
            preferred_id = None
        if preferred_id:
            for row in mt3_rows:
                if row["id"] == preferred_id:
                    return row
        return mt3_rows[0] if mt3_rows else None

    @staticmethod
    def _preferred_interpretation_row(
        run_row: sqlite3.Row, interpretation_rows: list[sqlite3.Row]
    ) -> sqlite3.Row | None:
        preferred_id = run_row["preferred_interpretation_attempt_id"]
        if preferred_id:
            for row in interpretation_rows:
                if row["id"] == preferred_id:
                    return row
        return interpretation_rows[0] if interpretation_rows else None

    @staticmethod
    def _mt3_stage_snapshot(
        requested_mode: str,
        measurement_status: str,
        preferred_row: sqlite3.Row | None,
        rows: list[sqlite3.Row],
    ) -> dict[str, Any]:
        """Mirror of _pitch_note_stage_snapshot. Always non-authoritative —
        MT3 output is purely additive and never overrides Phase 1 (PURPOSE.md
        invariant #1, "Phase 1 measurements are ground truth")."""
        if preferred_row is not None:
            status = preferred_row["status"]
        elif requested_mode == "off":
            status = "not_requested"
        elif measurement_status == "interrupted":
            status = "interrupted"
        elif measurement_status == "completed":
            status = "ready"
        else:
            status = "blocked"

        return {
            "status": status,
            "authoritative": False,
            "preferredAttemptId": preferred_row["id"] if preferred_row is not None else None,
            "attemptsSummary": [
                {
                    "attemptId": row["id"],
                    "checkpointId": row["checkpoint_id"],
                    "status": row["status"],
                }
                for row in rows
            ],
            "result": _json_loads(preferred_row["result_json"]) if preferred_row is not None else None,
            "provenance": _json_loads(preferred_row["provenance_json"]) if preferred_row is not None else None,
            "diagnostics": _json_loads(preferred_row["diagnostics_json"]) if preferred_row is not None else None,
            "error": _json_loads(preferred_row["error_json"]) if preferred_row is not None else None,
        }

    @staticmethod
    def _pitch_note_stage_snapshot(
        requested_mode: str,
        measurement_status: str,
        preferred_row: sqlite3.Row | None,
        rows: list[sqlite3.Row],
    ) -> dict[str, Any]:
        if preferred_row is not None:
            status = preferred_row["status"]
        elif requested_mode == "off":
            status = "not_requested"
        elif measurement_status == "interrupted":
            status = "interrupted"
        elif measurement_status == "completed":
            status = "ready"
        else:
            status = "blocked"

        return {
            "status": status,
            "authoritative": False,
            "preferredAttemptId": preferred_row["id"] if preferred_row is not None else None,
            "attemptsSummary": [
                {
                    "attemptId": row["id"],
                    "backendId": row["backend_id"],
                    "mode": row["mode"],
                    "status": row["status"],
                }
                for row in rows
            ],
            "result": _json_loads(preferred_row["result_json"]) if preferred_row is not None else None,
            "provenance": _json_loads(preferred_row["provenance_json"]) if preferred_row is not None else None,
            "diagnostics": _json_loads(preferred_row["diagnostics_json"]) if preferred_row is not None else None,
            "error": _json_loads(preferred_row["error_json"]) if preferred_row is not None else None,
        }

    @staticmethod
    def _interpretation_stage_snapshot(
        requested_mode: str,
        measurement_status: str,
        preferred_row: sqlite3.Row | None,
        rows: list[sqlite3.Row],
    ) -> dict[str, Any]:
        # If any attempt across any profile is still in-flight, the stage
        # is not terminal — even if the preferred (first-completed) profile
        # is done.  Without this, the frontend polling loop exits before
        # later profiles (e.g. stem_summary) finish.
        any_running = any(row["status"] == "running" for row in rows)
        any_queued = any(row["status"] == "queued" for row in rows)

        if any_running:
            status = "running"
        elif any_queued:
            status = "queued"
        elif preferred_row is not None:
            status = preferred_row["status"]
        elif requested_mode == "off":
            status = "not_requested"
        elif measurement_status == "interrupted":
            status = "interrupted"
        elif measurement_status == "completed":
            status = "ready"
        else:
            status = "blocked"

        profiles: dict[str, Any] = {}
        for row in rows:
            profile_id = str(row["profile_id"])
            if profile_id in profiles:
                continue
            profiles[profile_id] = {
                "attemptId": row["id"],
                "status": row["status"],
                "modelName": row["model_name"],
                "result": _json_loads(row["result_json"]),
                "provenance": _json_loads(row["provenance_json"]),
                "diagnostics": _json_loads(row["diagnostics_json"]),
                "error": _json_loads(row["error_json"]),
            }

        return {
            "status": status,
            "authoritative": False,
            "preferredAttemptId": preferred_row["id"] if preferred_row is not None else None,
            "attemptsSummary": [
                {
                    "attemptId": row["id"],
                    "profileId": row["profile_id"],
                    "modelName": row["model_name"],
                    "status": row["status"],
                }
                for row in rows
            ],
            "result": _json_loads(preferred_row["result_json"]) if preferred_row is not None else None,
            "provenance": _json_loads(preferred_row["provenance_json"]) if preferred_row is not None else None,
            "diagnostics": _json_loads(preferred_row["diagnostics_json"]) if preferred_row is not None else None,
            "error": _json_loads(preferred_row["error_json"]) if preferred_row is not None else None,
            "profiles": profiles,
        }
