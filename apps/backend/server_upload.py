"""Upload handling: size enforcement, file persistence, error responses."""

import os
import tempfile
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import UploadFile
from fastapi.responses import JSONResponse
from python_multipart.multipart import MultipartParseError, MultipartParser, parse_options_header

import upload_limits


LEGACY_ENDPOINT_SUNSET = "Wed, 31 Dec 2026 23:59:59 GMT"

ERROR_PHASE_LOCAL_DSP = "phase1_local_dsp"
ERROR_PHASE_GEMINI = "phase2_gemini"


class UploadTooLargeError(ValueError):
    def __init__(self, limit_bytes: int):
        self.limit_bytes = limit_bytes
        super().__init__(
            f"Uploaded audio exceeds the backend upload limit of {limit_bytes} bytes."
        )


def _mark_legacy_endpoint_response(response: JSONResponse, *, endpoint: str) -> JSONResponse:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = LEGACY_ENDPOINT_SUNSET
    response.headers["Link"] = '</api/analysis-runs>; rel="successor-version"'
    response.headers["Warning"] = (
        f'299 - "{endpoint} is deprecated; use /api/analysis-runs instead."'
    )
    return response


def _scope_header_value(scope: dict[str, Any], header_name: bytes) -> str | None:
    for name, value in scope.get("headers", []):
        if name.lower() != header_name:
            continue
        try:
            return value.decode("latin-1")
        except UnicodeDecodeError:
            return None
    return None


class _MultipartTrackSizeCounter:
    def __init__(self, *, content_type_header: str | None, track_field_name: str, limit_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        self.track_field_name = track_field_name
        self.track_bytes = 0
        self.overflowed = False
        self.disabled = False
        self._current_headers: dict[bytes, bytes] = {}
        self._current_header_field = bytearray()
        self._current_header_value = bytearray()
        self._current_part_is_track_file = False
        self._parser = self._build_parser(content_type_header)

    def _build_parser(self, content_type_header: str | None) -> MultipartParser | None:
        content_type, options = parse_options_header(content_type_header)
        if content_type != b"multipart/form-data":
            return None
        boundary = options.get(b"boundary")
        if not boundary:
            return None
        return MultipartParser(
            boundary,
            callbacks={
                "on_part_begin": self.on_part_begin,
                "on_header_begin": self.on_header_begin,
                "on_header_field": self.on_header_field,
                "on_header_value": self.on_header_value,
                "on_header_end": self.on_header_end,
                "on_headers_finished": self.on_headers_finished,
                "on_part_data": self.on_part_data,
                "on_part_end": self.on_part_end,
            },
        )

    def feed(self, chunk: bytes) -> None:
        if not chunk or self._parser is None or self.disabled or self.overflowed:
            return
        try:
            self._parser.write(chunk)
        except MultipartParseError:
            self.disabled = True

    def on_part_begin(self) -> None:
        self._current_headers = {}
        self._current_header_field = bytearray()
        self._current_header_value = bytearray()
        self._current_part_is_track_file = False

    def on_header_begin(self) -> None:
        self._current_header_field = bytearray()
        self._current_header_value = bytearray()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._current_header_field.extend(data[start:end])

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._current_header_value.extend(data[start:end])

    def on_header_end(self) -> None:
        if not self._current_header_field:
            return
        self._current_headers[
            bytes(self._current_header_field).lower()
        ] = bytes(self._current_header_value)

    def on_headers_finished(self) -> None:
        disposition = self._current_headers.get(b"content-disposition")
        if disposition is None:
            return
        _, options = parse_options_header(disposition)
        field_name = options.get(b"name")
        self._current_part_is_track_file = (
            field_name == self.track_field_name.encode("utf-8")
            and b"filename" in options
        )

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if not self._current_part_is_track_file:
            return
        self.track_bytes += end - start
        if self.track_bytes > self.limit_bytes:
            self.overflowed = True

    def on_part_end(self) -> None:
        self._current_part_is_track_file = False


class UploadSizeLimitMiddleware:
    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in upload_limits.UPLOAD_LIMITED_POST_PATHS
        ):
            await self.app(scope, receive, send)
            return

        raw_limit_bytes = upload_limits.MAX_UPLOAD_SIZE_BYTES
        request_limit_bytes = upload_limits.MAX_UPLOAD_REQUEST_BYTES
        content_length = _scope_header_value(scope, b"content-length")
        try:
            declared_length = int(content_length) if content_length is not None else None
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > request_limit_bytes:
            response = _upload_too_large_response_for_path(scope["path"], limit_bytes=raw_limit_bytes)
            await response(scope, receive, send)
            return

        size_counter = _MultipartTrackSizeCounter(
            content_type_header=_scope_header_value(scope, b"content-type"),
            track_field_name="track",
            limit_bytes=raw_limit_bytes,
        )
        overflowed = False
        response_started = False
        synthetic_response_sent = False

        def send_upload_limit_response() -> JSONResponse:
            return _upload_too_large_response_for_path(scope["path"], limit_bytes=raw_limit_bytes)

        async def limited_receive() -> dict[str, Any]:
            nonlocal overflowed
            if overflowed:
                return {"type": "http.disconnect"}
            message = await receive()
            if message.get("type") != "http.request":
                return message
            body = message.get("body", b"")
            if isinstance(body, bytes):
                size_counter.feed(body)
            if size_counter.overflowed:
                overflowed = True
                return {"type": "http.disconnect"}
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started, synthetic_response_sent
            if overflowed:
                if not synthetic_response_sent:
                    synthetic_response_sent = True
                    response_started = True
                    await send_upload_limit_response()(scope, receive, send)
                return
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except UploadTooLargeError:
            if response_started:
                raise
            await send_upload_limit_response()(scope, receive, send)
            return

        if overflowed and not synthetic_response_sent and not response_started:
            await send_upload_limit_response()(scope, receive, send)


def _persist_upload(
    track: UploadFile,
    *,
    max_bytes: int | None = None,
) -> tuple[str, int]:
    effective_max_bytes = (
        upload_limits.MAX_UPLOAD_SIZE_BYTES if max_bytes is None else max_bytes
    )
    suffix = Path(track.filename or "upload.bin").suffix or ".bin"
    temp_path: str | None = None
    try:
        track.file.seek(0)
    except Exception:
        pass
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            total_bytes = 0
            while True:
                chunk = track.file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > effective_max_bytes:
                    raise UploadTooLargeError(effective_max_bytes)
                temp_file.write(chunk)
        return temp_path, total_bytes
    except Exception:
        _cleanup_temp_path(temp_path)
        raise


def _cleanup_temp_path(temp_path: str | None) -> None:
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _value_error_code(value_error: ValueError) -> str:
    message = str(value_error).lower()
    if "analysis mode" in message:
        return "ANALYSIS_MODE_UNSUPPORTED"
    return "INTERPRETATION_PROFILE_UNSUPPORTED"


def _canonical_upload_too_large_response(exc: UploadTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "error": {
                "code": "UPLOAD_TOO_LARGE",
                "message": str(exc),
            }
        },
    )


def _legacy_upload_too_large_response(
    *,
    request_id: str,
    phase: str,
    endpoint: str,
    analysis_run_id: str | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "requestId": request_id,
        "error": {
            "code": "UPLOAD_TOO_LARGE",
            "message": upload_limits.upload_too_large_message(),
            "phase": phase,
            "retryable": False,
        },
    }
    if analysis_run_id is not None:
        content["analysisRunId"] = analysis_run_id
    return _mark_legacy_endpoint_response(
        JSONResponse(status_code=413, content=content),
        endpoint=endpoint,
    )


def _upload_too_large_response_for_path(
    path: str,
    *,
    limit_bytes: int,
) -> JSONResponse:
    if path in {"/api/analyze", "/api/analyze/estimate"}:
        return _legacy_upload_too_large_response(
            request_id=str(uuid4()),
            phase=ERROR_PHASE_LOCAL_DSP,
            endpoint=path,
        )
    if path == "/api/phase2":
        return _legacy_upload_too_large_response(
            request_id=str(uuid4()),
            phase=ERROR_PHASE_GEMINI,
            endpoint=path,
        )
    return _canonical_upload_too_large_response(UploadTooLargeError(limit_bytes))
