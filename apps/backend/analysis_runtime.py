from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

SQLITE_BUSY_TIMEOUT_MS = 5_000
MEASUREMENT_PIPELINE_PROGRESS_STATUSES = {"pending", "running", "completed"}


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


class UnsupportedSymbolicModeError(ValueError):
    def __init__(self, symbolic_mode: str):
        self.symbolic_mode = symbolic_mode
        super().__init__(f"Unsupported symbolic mode '{symbolic_mode}'.")


class AnalysisRuntime:
    def __init__(self, runtime_dir: Path, max_pending_per_stage: int = 4):
        self.runtime_dir = Path(runtime_dir)
        self.max_pending_per_stage = max_pending_per_stage
        self.artifacts_dir = self.runtime_dir / "artifacts"
        self.db_path = self.runtime_dir / "analysis_runs.sqlite3"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
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
                    requested_symbolic_mode TEXT NOT NULL,
                    requested_symbolic_backend TEXT NOT NULL,
                    requested_interpretation_mode TEXT NOT NULL,
                    requested_interpretation_profile TEXT NOT NULL,
                    requested_interpretation_model TEXT,
                    legacy_request_id TEXT,
                    preferred_symbolic_attempt_id TEXT,
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

                CREATE TABLE IF NOT EXISTS symbolic_extraction_attempts (
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
                    grounded_symbolic_attempt_id TEXT,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    provenance_json TEXT,
                    diagnostics_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
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
                "grounded_symbolic_attempt_id",
                "TEXT",
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
        symbolic_mode: str,
        symbolic_backend: str,
        interpretation_mode: str,
        interpretation_profile: str,
        interpretation_model: str | None,
        legacy_request_id: str | None = None,
    ) -> dict[str, Any]:
        if self._count_active_measurement_runs() >= self.max_pending_per_stage:
            raise RuntimeError("Measurement queue is full.")
        run_id = str(uuid4())
        artifact_id = str(uuid4())
        created_at = _utc_now_iso()
        content_sha256 = hashlib.sha256(content).hexdigest()
        suffix = Path(filename).suffix or ".bin"
        artifact_path = self.artifacts_dir / f"{artifact_id}{suffix}"
        artifact_path.write_bytes(content)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_runs (
                    id,
                    source_artifact_id,
                    requested_symbolic_mode,
                    requested_symbolic_backend,
                    requested_interpretation_mode,
                    requested_interpretation_profile,
                    requested_interpretation_model,
                    legacy_request_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    artifact_id,
                    symbolic_mode,
                    symbolic_backend,
                    interpretation_mode,
                    interpretation_profile,
                    interpretation_model,
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
                    len(content),
                    content_sha256,
                    str(artifact_path),
                    None,
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

    def get_run_by_legacy_request_id(self, legacy_request_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM analysis_runs WHERE legacy_request_id = ?",
                (legacy_request_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown legacy request {legacy_request_id}")
        return self.get_run(row["id"])

    def get_run_id_by_legacy_request_id(self, legacy_request_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM analysis_runs WHERE legacy_request_id = ?",
                (legacy_request_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown legacy request {legacy_request_id}")
        return str(row["id"])

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
            "artifactId": artifact_row["id"],
            "filename": artifact_row["filename"],
            "mimeType": artifact_row["mime_type"],
            "sizeBytes": artifact_row["size_bytes"],
            "contentSha256": artifact_row["content_sha256"],
            "path": artifact_row["path"],
            "provenance": _json_loads(artifact_row["provenance_json"]),
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
            symbolic_rows = conn.execute(
                """
                SELECT * FROM symbolic_extraction_attempts
                WHERE run_id = ?
                ORDER BY created_at DESC
                """,
                (run_id,),
            ).fetchall()
        if run_row is None or measurement_row is None:
            raise KeyError(f"Unknown run {run_id}")
        preferred_symbolic = self._preferred_symbolic_row(run_row, symbolic_rows)
        return {
            "measurementOutputId": str(measurement_row["id"]),
            "measurementStatus": str(measurement_row["status"]),
            "measurementResult": _json_loads(measurement_row["result_json"]),
            "symbolicAttemptId": (
                str(preferred_symbolic["id"]) if preferred_symbolic is not None else None
            ),
            "symbolicStatus": (
                str(preferred_symbolic["status"]) if preferred_symbolic is not None else "not_requested"
            ),
            "symbolicResult": (
                _json_loads(preferred_symbolic["result_json"])
                if preferred_symbolic is not None
                else None
            ),
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            run_row = conn.execute(
                "SELECT * FROM analysis_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if run_row is None:
                raise KeyError(f"Unknown run {run_id}")

            artifact_row = conn.execute(
                "SELECT * FROM run_artifacts WHERE id = ?", (run_row["source_artifact_id"],)
            ).fetchone()
            measurement_row = conn.execute(
                "SELECT * FROM measurement_outputs WHERE run_id = ?", (run_id,)
            ).fetchone()
            symbolic_rows = conn.execute(
                """
                SELECT * FROM symbolic_extraction_attempts
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

        preferred_symbolic = self._preferred_symbolic_row(run_row, symbolic_rows)
        preferred_interpretation = self._preferred_interpretation_row(
            run_row, interpretation_rows
        )
        measurement_status = measurement_row["status"]

        return {
            "runId": run_id,
            "requestedStages": {
                "symbolicMode": run_row["requested_symbolic_mode"],
                "symbolicBackend": run_row["requested_symbolic_backend"],
                "interpretationMode": run_row["requested_interpretation_mode"],
                "interpretationProfile": run_row["requested_interpretation_profile"],
                "interpretationModel": run_row["requested_interpretation_model"],
            },
            "artifacts": {
                "sourceAudio": {
                    "artifactId": artifact_row["id"],
                    "filename": artifact_row["filename"],
                    "mimeType": artifact_row["mime_type"],
                    "sizeBytes": artifact_row["size_bytes"],
                    "contentSha256": artifact_row["content_sha256"],
                    "path": artifact_row["path"],
                }
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
                "symbolicExtraction": self._symbolic_stage_snapshot(
                    run_row["requested_symbolic_mode"],
                    measurement_status,
                    preferred_symbolic,
                    symbolic_rows,
                ),
                "interpretation": self._interpretation_stage_snapshot(
                    run_row["requested_interpretation_mode"],
                    measurement_status,
                    preferred_interpretation,
                    interpretation_rows,
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
                       ar.requested_symbolic_mode, ar.requested_symbolic_backend
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
            "requestedSymbolicMode": row["requested_symbolic_mode"],
            "requestedSymbolicBackend": row["requested_symbolic_backend"],
        }

    def complete_measurement(
        self,
        run_id: str,
        *,
        payload: dict[str, Any],
        provenance: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> None:
        measurement_result = dict(payload)
        # Strip transcriptionDetail — it's a Layer 2 (symbolic extraction) concern.
        # The symbolic worker produces this independently through its own stage.
        measurement_result.pop("transcriptionDetail", None)
        self._update_measurement_row(
            run_id,
            status="completed",
            result=measurement_result,
            provenance=provenance,
            diagnostics=diagnostics,
            error=None,
        )
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
        )

    def create_symbolic_attempt(
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
                INSERT INTO symbolic_extraction_attempts (
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
                    SET preferred_symbolic_attempt_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (attempt_id, now, run_id),
                )
        return attempt_id

    def reserve_symbolic_attempt(self, attempt_id: str) -> bool:
        now = _utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE symbolic_extraction_attempts
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, attempt_id),
            )
        return cursor.rowcount > 0

    def reserve_next_symbolic_attempt(self) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sea.id, sea.run_id, sea.backend_id, sea.mode
                FROM symbolic_extraction_attempts sea
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
                UPDATE symbolic_extraction_attempts
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

    def complete_symbolic_attempt(
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
                "SELECT run_id FROM symbolic_extraction_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()
            if attempt_row is None:
                raise KeyError(f"Unknown symbolic attempt {attempt_id}")
            conn.execute(
                """
                UPDATE symbolic_extraction_attempts
                SET status = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE id = ?
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
            conn.execute(
                """
                UPDATE analysis_runs
                SET preferred_symbolic_attempt_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (attempt_id, now, attempt_row["run_id"]),
            )

    def fail_symbolic_attempt(
        self,
        attempt_id: str,
        *,
        error: dict[str, Any],
        provenance: dict[str, Any] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        self._update_attempt_row(
            table="symbolic_extraction_attempts",
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
            row = conn.execute(
                """
                SELECT ia.id, ia.run_id, ia.profile_id, ia.model_name
                FROM interpretation_attempts ia
                JOIN measurement_outputs mo ON mo.run_id = ia.run_id
                WHERE ia.status = 'queued' AND mo.status = 'completed'
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
        grounded_symbolic_attempt_id: str | None = None,
    ) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            attempt_row = conn.execute(
                "SELECT run_id FROM interpretation_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()
            if attempt_row is None:
                raise KeyError(f"Unknown interpretation attempt {attempt_id}")
            conn.execute(
                """
                UPDATE interpretation_attempts
                SET status = ?, grounded_measurement_output_id = ?, grounded_symbolic_attempt_id = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    "completed",
                    grounded_measurement_output_id,
                    grounded_symbolic_attempt_id,
                    _json_dumps(result),
                    _json_dumps(provenance),
                    _json_dumps(diagnostics),
                    None,
                    now,
                    attempt_id,
                ),
            )
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
        grounded_symbolic_attempt_id: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE interpretation_attempts
                SET status = ?, grounded_measurement_output_id = ?, grounded_symbolic_attempt_id = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    "failed",
                    grounded_measurement_output_id,
                    grounded_symbolic_attempt_id,
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
        source = Path(source_path)
        suffix = source.suffix or Path(filename).suffix or ".bin"
        destination = self.artifacts_dir / f"{artifact_id}{suffix}"
        digest = hashlib.sha256()
        size_bytes = 0
        with source.open("rb") as src, destination.open("wb") as dest:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dest.write(chunk)
                digest.update(chunk)
                size_bytes += len(chunk)
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
                    size_bytes,
                    digest.hexdigest(),
                    str(destination),
                    _json_dumps(provenance),
                    created_at,
                ),
            )
        return {
            "artifactId": artifact_id,
            "path": str(destination),
            "kind": kind,
            "filename": filename,
            "mimeType": mime_type,
        }

    def get_artifacts_by_kind(self, run_id: str, kind_prefix: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM run_artifacts
                WHERE run_id = ? AND kind LIKE ?
                ORDER BY created_at ASC
                """,
                (run_id, f"{kind_prefix}%"),
            ).fetchall()
        return [
            {
                "artifactId": row["id"],
                "kind": row["kind"],
                "filename": row["filename"],
                "mimeType": row["mime_type"],
                "sizeBytes": row["size_bytes"],
                "contentSha256": row["content_sha256"],
                "path": row["path"],
                "provenance": _json_loads(row["provenance_json"]),
            }
            for row in rows
        ]

    def recover_incomplete_attempts(self) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE measurement_outputs
                SET status = 'queued', updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            conn.execute(
                """
                UPDATE symbolic_extraction_attempts
                SET status = 'queued', updated_at = ?
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

    def update_measurement_progress(
        self,
        run_id: str,
        *,
        step_key: str,
        message: str,
    ) -> dict[str, Any] | None:
        return self._update_stage_progress(
            table="measurement_outputs",
            identifier_column="run_id",
            identifier=run_id,
            step_key=step_key,
            message=message,
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

    def update_symbolic_attempt_progress(
        self,
        attempt_id: str,
        *,
        step_key: str,
        message: str,
    ) -> dict[str, Any] | None:
        return self._update_stage_progress(
            table="symbolic_extraction_attempts",
            identifier_column="id",
            identifier=attempt_id,
            step_key=step_key,
            message=message,
        )

    def update_interpretation_attempt_progress(
        self,
        attempt_id: str,
        *,
        step_key: str,
        message: str,
    ) -> dict[str, Any] | None:
        return self._update_stage_progress(
            table="interpretation_attempts",
            identifier_column="id",
            identifier=attempt_id,
            step_key=step_key,
            message=message,
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
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE measurement_outputs
                SET status = ?, result_json = ?, provenance_json = ?, diagnostics_json = ?, error_json = ?, updated_at = ?
                WHERE run_id = ?
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
                WHERE id = ?
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
            symbolic_exists = conn.execute(
                "SELECT 1 FROM symbolic_extraction_attempts WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
            interpretation_exists = conn.execute(
                "SELECT 1 FROM interpretation_attempts WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()

        if (
            run_row["requested_symbolic_mode"] != "off"
            and symbolic_exists is None
        ):
            self.create_symbolic_attempt(
                run_id,
                backend_id=self._resolve_symbolic_backend(
                    run_row["requested_symbolic_backend"]
                ),
                mode=run_row["requested_symbolic_mode"],
                status="queued",
                provenance={
                    "backendId": self._resolve_symbolic_backend(
                        run_row["requested_symbolic_backend"]
                    ),
                },
            )

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
    def _resolve_symbolic_backend(requested_backend: str) -> str:
        if requested_backend == "auto":
            return "auto"
        return requested_backend

    @staticmethod
    def resolve_measurement_flags(
        requested_symbolic_mode: str,
    ) -> tuple[bool, bool]:
        # Symbolic work (separation + transcription) is handled by the dedicated
        # symbolic_extraction stage enqueued via _enqueue_requested_followups().
        # Running it inline during measurement was redundant — the result was
        # stripped anyway (see complete_measurement: pop("transcriptionDetail")).
        if requested_symbolic_mode not in ("off", "stem_notes"):
            raise UnsupportedSymbolicModeError(requested_symbolic_mode)
        return False, False

    @staticmethod
    def _preferred_symbolic_row(
        run_row: sqlite3.Row, symbolic_rows: list[sqlite3.Row]
    ) -> sqlite3.Row | None:
        preferred_id = run_row["preferred_symbolic_attempt_id"]
        if preferred_id:
            for row in symbolic_rows:
                if row["id"] == preferred_id:
                    return row
        return symbolic_rows[0] if symbolic_rows else None

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
    def _symbolic_stage_snapshot(
        requested_mode: str,
        measurement_status: str,
        preferred_row: sqlite3.Row | None,
        rows: list[sqlite3.Row],
    ) -> dict[str, Any]:
        if preferred_row is not None:
            status = preferred_row["status"]
        elif requested_mode == "off":
            status = "not_requested"
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
        if preferred_row is not None:
            status = preferred_row["status"]
        elif requested_mode == "off":
            status = "not_requested"
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
        }
