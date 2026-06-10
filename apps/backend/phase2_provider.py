"""Phase 2 interpretation provider abstraction (gemini | moss).

The product default is Gemini, whose call lives inline in ``server.py``
(``_run_interpretation_request_with_profile_config``) and is **unchanged**. This
module adds a pluggable seam so the *same* Phase 2 request — same built prompt,
same audio, same authoritative Phase 1 JSON, same ``response_schema`` — can be
routed to a self-hosted OpenMOSS **MOSS-Audio** model running as a FastAPI
sidecar instead, while flowing through the *identical* downstream parse /
validate / citation / catalogue path in ``server.py``. That shared tail is what
guarantees the "identical recommendation schema" DoD: both providers emit a raw
``Phase2Result`` JSON string, and ``server.py`` validates both the same way.

Selection is env-gated and **default-off**::

    ASA_PHASE2_PROVIDER = "gemini" (default) | "moss" | "claude"

``resolve_external_phase2_provider()`` returns ``None`` for the Gemini default
(meaning: use ``server.py``'s native Gemini path, byte-for-byte unchanged) and a
``MossSidecarProvider`` / ``ClaudeCliProvider`` only when ``moss`` / ``claude``
is explicitly selected. The ``claude`` provider runs the operator's local
Claude Code CLI headless and is **text-only**: it grounds the interpretation in
the prompt's embedded Phase 1 JSON and never receives the audio, so it needs no
``GEMINI_API_KEY`` and no network credits beyond the operator's existing Claude
subscription. The MOSS path
applies to the ``producer_summary`` profile only (the recommendation-emitting
interpretation); the ``stem_summary`` path stays on Gemini.

LICENCE NOTE (STEP ONE gate — see ``docs/PHASE2_PROVIDER.md`` and the
``asa-moss-audio-licence-gate`` memory): MOSS-Audio *weights* are Apache-2.0, but
the *modeling code* you must run carries no effective licence (the GitHub repo's
``pyproject`` points at a ``LICENSE`` file that does not exist). This abstraction
and the sidecar therefore execute **no** OpenMOSS code on the product path: the
sidecar ships a deterministic mock interpreter for the experiment/eval, and the
real model wiring is a documented, gated stub. Gemini stays the product default.
This is a default-off research experiment, mirroring the MSST separation backend.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


DEFAULT_PHASE2_PROVIDER = "gemini"
SUPPORTED_PHASE2_PROVIDERS = ("gemini", "moss", "claude")

_DEFAULT_SIDECAR_URL = "http://127.0.0.1:8200"
_DEFAULT_SIDECAR_TIMEOUT_SECONDS = 180

_DEFAULT_CLAUDE_CLI = "claude"
# A full producer_summary prompt (~240k chars) on the CLI's default model was
# measured at ~6 minutes end-to-end; 300s would kill legitimate calls.
_DEFAULT_CLAUDE_TIMEOUT_SECONDS = 600
# Mirror server.py's INLINE_SIZE_LIMIT intent: above this we do not inline-base64
# the audio into the JSON body. The sidecar/model path is a default-off
# experiment, so the simple JSON+base64 transport is acceptable for the small
# eval corpus; large files degrade to a typed, retryable error rather than
# silently shipping a huge body.
_MAX_INLINE_AUDIO_BYTES = 24 * 1024 * 1024


@dataclass
class Phase2ProviderRequest:
    """Everything a provider needs to produce a raw ``Phase2Result`` JSON string.

    ``prompt`` already embeds the authoritative Phase 1 JSON, the Live 12 device
    catalogue, and grounding metadata (built by ``server_phase2._build_phase2_prompt``).
    ``phase1_result`` is forwarded *separately* as well so a sidecar can ground
    citations in real measurement paths without re-parsing the prompt — matching
    the goal's "fed the same audio + Phase-1 JSON".
    """

    prompt: str
    response_schema: dict[str, Any]
    phase1_result: dict[str, Any]
    model_name: str
    request_id: str
    source_path: str | None = None
    filename: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None


@dataclass
class Phase2ProviderResponse:
    """A provider's raw output, shaped to slot into ``server.py``'s shared tail.

    ``text`` is the raw JSON string of a ``Phase2Result`` (or ``None`` to signal
    a skip) — the SAME thing ``response.text`` is for the Gemini path. It is fed
    to the profile's ``parseResult`` / ``parseDebugResult`` and then through the
    citation + catalogue validators, exactly like Gemini output.
    """

    text: str | None
    flags: list[str] = field(default_factory=list)
    message_suffix: str | None = None


class Phase2ProviderError(Exception):
    """A provider-side failure that ``server.py`` converts to an execution error.

    Carries the fields the interpretation execution dict needs so a MOSS sidecar
    failure degrades the same way a Gemini failure does (retryable, surfaced in
    the UI as a failed attempt — never a silent success).
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "MOSS_SIDECAR_FAILED",
        status_code: int = 502,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.retryable = retryable


@runtime_checkable
class Phase2Provider(Protocol):
    name: str

    def generate(self, request: Phase2ProviderRequest) -> Phase2ProviderResponse: ...


class MossSidecarProvider:
    """HTTP client for the MOSS-Audio FastAPI sidecar (``moss_sidecar/app.py``).

    Posts ``{prompt, response_schema, phase1, model, audio?}`` to ``/v1/phase2``
    and returns the sidecar's ``Phase2Result`` re-serialized to a JSON string so
    ``server.py`` validates it through the identical path as Gemini. Any
    transport / non-2xx / unparseable-response condition raises a typed,
    retryable ``Phase2ProviderError`` so the run degrades cleanly (the licence
    gate already means MOSS is never the product default).
    """

    name = "moss"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = _DEFAULT_SIDECAR_TIMEOUT_SECONDS,
        model_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.model_id = model_id

    @classmethod
    def from_env(cls) -> "MossSidecarProvider":
        return cls(
            base_url=os.getenv("ASA_MOSS_SIDECAR_URL", _DEFAULT_SIDECAR_URL),
            timeout_seconds=float(
                os.getenv("ASA_MOSS_SIDECAR_TIMEOUT_SECONDS", str(_DEFAULT_SIDECAR_TIMEOUT_SECONDS))
            ),
            model_id=os.getenv("ASA_MOSS_MODEL_ID") or None,
        )

    def _encode_audio(self, request: Phase2ProviderRequest) -> dict[str, Any] | None:
        path = request.source_path
        if not path or not os.path.isfile(path):
            # No rendered audio is a valid state for the experiment (the
            # recommendation corpus ships Phase 1 fingerprints without renders).
            # The sidecar grounds on Phase 1 JSON; audio is additive.
            return None
        size = os.path.getsize(path)
        if size > _MAX_INLINE_AUDIO_BYTES:
            raise Phase2ProviderError(
                f"Audio {size} bytes exceeds the {_MAX_INLINE_AUDIO_BYTES}-byte inline "
                "limit for the MOSS sidecar transport.",
                error_code="MOSS_AUDIO_TOO_LARGE",
                status_code=413,
                retryable=False,
            )
        import base64

        with open(path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
        return {
            "filename": request.filename or os.path.basename(path),
            "mime_type": request.mime_type or "application/octet-stream",
            "base64": encoded,
        }

    def generate(self, request: Phase2ProviderRequest) -> Phase2ProviderResponse:
        import requests  # product dependency (requests==2.32.5); imported lazily

        body = {
            "prompt": request.prompt,
            "response_schema": request.response_schema,
            "phase1": request.phase1_result,
            "model": self.model_id or request.model_name,
            "request_id": request.request_id,
            "audio": self._encode_audio(request),
        }
        url = f"{self.base_url}/v1/phase2"
        try:
            response = requests.post(url, json=body, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise Phase2ProviderError(
                f"MOSS sidecar request to {url} failed: {exc}",
                error_code="MOSS_SIDECAR_UNREACHABLE",
            ) from exc

        if response.status_code != 200:
            snippet = response.text[:200] if isinstance(response.text, str) else ""
            raise Phase2ProviderError(
                f"MOSS sidecar returned HTTP {response.status_code}: {snippet}",
                error_code="MOSS_SIDECAR_HTTP_ERROR",
                # Only transient server errors are worth retrying. 4xx and 501
                # (the licence-gated "model not wired" stub) are permanent — a
                # retry loop against them would never converge.
                retryable=response.status_code in (500, 502, 503, 504),
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise Phase2ProviderError(
                f"MOSS sidecar returned non-JSON: {exc}",
                error_code="MOSS_SIDECAR_BAD_RESPONSE",
            ) from exc

        result = payload.get("result")
        provider_label = str(payload.get("provider") or self.name)
        warnings = payload.get("warnings")
        suffix = f"MOSS interpretation complete ({provider_label})."
        if isinstance(warnings, list) and warnings:
            suffix = f"{suffix} {len(warnings)} sidecar warning(s)."
        # ``None`` result → text=None → server's parse path emits a skip, just
        # like an empty Gemini response. A dict result is re-serialized so the
        # shared tail parses + validates it identically to Gemini output.
        text = None if result is None else json.dumps(result)
        return Phase2ProviderResponse(
            text=text,
            flags=[f"provider:{provider_label}"],
            message_suffix=suffix,
        )


_GEMINI_TO_JSON_SCHEMA_TYPES = {
    "OBJECT": "object",
    "ARRAY": "array",
    "STRING": "string",
    "NUMBER": "number",
    "INTEGER": "integer",
    "BOOLEAN": "boolean",
}


def _gemini_schema_to_json_schema(node: Any) -> Any:
    """Convert the Gemini response-schema dialect to standard JSON Schema.

    The profile ``responseSchema`` constants use Gemini's uppercase type names
    (``"OBJECT"``, ``"STRING"``, …) and OpenAPI-style ``nullable``; the Claude
    CLI's ``--json-schema`` flag expects standard JSON Schema (lowercase types,
    ``["string", "null"]`` unions). Everything else passes through unchanged.
    """
    if isinstance(node, list):
        return [_gemini_schema_to_json_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    converted: dict[str, Any] = {}
    nullable = bool(node.get("nullable"))
    for key, value in node.items():
        if key == "nullable":
            continue
        if key == "type" and isinstance(value, str):
            converted[key] = _GEMINI_TO_JSON_SCHEMA_TYPES.get(value, value.lower())
        else:
            converted[key] = _gemini_schema_to_json_schema(value)
    if nullable and isinstance(converted.get("type"), str):
        converted["type"] = [converted["type"], "null"]
    return converted


def _strip_code_fences(text: str) -> str:
    """Remove a single wrapping ``` / ```json fence pair, if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    first_newline = stripped.find("\n")
    if first_newline == -1:
        return stripped
    body = stripped[first_newline + 1 :]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[: -len("```")]
    return body.strip()


class ClaudeCliProvider:
    """Text-only Phase 2 provider running the local Claude Code CLI headless.

    Unlike the Gemini path (audio + prompt), this provider sends ONLY the
    prompt — which already embeds the authoritative Phase 1 JSON and the
    Live 12 device catalogue — so the interpretation is grounded purely in
    measurements; the request's audio fields are deliberately ignored. This is
    by design, not a limitation: PURPOSE.md invariant #1 makes Phase 1 ground
    truth, and the provider seam already documents audio as additive.

    The subprocess is sandboxed and deterministic in capability: ``--safe-mode``
    disables the operator's plugins/hooks/MCP servers/CLAUDE.md (a probe showed
    a default invocation loads all of them), ``--tools ""`` disables tool use,
    and ``--no-session-persistence`` leaves no session behind. The profile's
    Gemini-dialect ``response_schema`` is converted to JSON Schema and enforced
    via ``--json-schema``; the CLI's validated ``structured_output`` (or the raw
    ``result`` text as fallback) is returned to ``server.py``'s shared
    parse/citation/catalogue tail — identical handling to Gemini output.

    Auth rides on the operator's existing Claude Code login; no ``GEMINI_API_KEY``
    and no separate API credits are required. Default-off, mirroring MOSS.
    """

    name = "claude"

    def __init__(
        self,
        *,
        cli_path: str = _DEFAULT_CLAUDE_CLI,
        timeout_seconds: float = _DEFAULT_CLAUDE_TIMEOUT_SECONDS,
        model: str | None = None,
    ) -> None:
        self.cli_path = cli_path
        self.timeout_seconds = timeout_seconds
        self.model = model

    @classmethod
    def from_env(cls) -> "ClaudeCliProvider":
        return cls(
            cli_path=os.getenv("ASA_CLAUDE_CLI", "").strip() or _DEFAULT_CLAUDE_CLI,
            timeout_seconds=float(
                os.getenv("ASA_CLAUDE_TIMEOUT_SECONDS", str(_DEFAULT_CLAUDE_TIMEOUT_SECONDS))
            ),
            model=os.getenv("ASA_CLAUDE_MODEL", "").strip() or None,
        )

    def _build_command(self, request: Phase2ProviderRequest) -> list[str]:
        command = [
            self.cli_path,
            "-p",
            "--output-format",
            "json",
            "--safe-mode",
            "--tools",
            "",
            "--no-session-persistence",
            "--json-schema",
            json.dumps(_gemini_schema_to_json_schema(request.response_schema)),
        ]
        if self.model:
            command.extend(["--model", self.model])
        return command

    def _extract_result_text(self, stdout: str) -> str | None:
        try:
            payload = json.loads(stdout)
        except ValueError as exc:
            snippet = stdout[:200]
            raise Phase2ProviderError(
                f"Claude CLI returned non-JSON output: {exc}; head: {snippet!r}",
                error_code="CLAUDE_CLI_BAD_OUTPUT",
            ) from exc

        # --output-format json emits either a single result object or an array
        # of events whose last "type":"result" entry carries the outcome.
        events = payload if isinstance(payload, list) else [payload]
        result_event = None
        for event in events:
            if isinstance(event, dict) and event.get("type") == "result":
                result_event = event
        if result_event is None:
            raise Phase2ProviderError(
                "Claude CLI output contained no result event.",
                error_code="CLAUDE_CLI_BAD_OUTPUT",
            )
        if result_event.get("is_error"):
            raise Phase2ProviderError(
                f"Claude CLI reported an error result: {str(result_event.get('result'))[:200]}",
                error_code="CLAUDE_CLI_FAILED",
            )

        structured = result_event.get("structured_output")
        if isinstance(structured, dict):
            return json.dumps(structured)
        raw = result_event.get("result")
        if isinstance(raw, str) and raw.strip():
            # Fallback when schema enforcement did not produce a structured
            # object: hand the fence-stripped text to the shared parse/salvage
            # tail, same as a Gemini text response.
            return _strip_code_fences(raw)
        return None

    def generate(self, request: Phase2ProviderRequest) -> Phase2ProviderResponse:
        import subprocess  # stdlib; imported lazily to keep module import light

        command = self._build_command(request)
        try:
            completed = subprocess.run(
                command,
                input=request.prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise Phase2ProviderError(
                f"Claude CLI binary not found at {self.cli_path!r}. Install Claude Code "
                "or set ASA_CLAUDE_CLI to its path.",
                error_code="CLAUDE_CLI_UNAVAILABLE",
                retryable=False,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise Phase2ProviderError(
                f"Claude CLI timed out after {self.timeout_seconds:.0f}s.",
                error_code="CLAUDE_CLI_TIMEOUT",
            ) from exc

        if completed.returncode != 0:
            # In --output-format json mode the CLI reports failures as a
            # result event on STDOUT (is_error: true) and often leaves stderr
            # empty — surface that diagnostic instead of discarding it.
            detail = (completed.stderr or "").strip()
            try:
                payload = json.loads(completed.stdout or "")
                events = payload if isinstance(payload, list) else [payload]
                for event in events:
                    if isinstance(event, dict) and event.get("type") == "result":
                        detail = str(event.get("result") or event.get("subtype") or detail)
            except ValueError:
                if not detail:
                    detail = (completed.stdout or "").strip()
            raise Phase2ProviderError(
                f"Claude CLI exited with code {completed.returncode}: {detail[:300]}",
                error_code="CLAUDE_CLI_FAILED",
            )

        text = self._extract_result_text(completed.stdout)
        flags = ["text-only"]
        if self.model:
            flags.append(f"claude-model:{self.model}")
        return Phase2ProviderResponse(
            text=text,
            flags=flags,
            message_suffix="Claude CLI interpretation complete (measurement-grounded, no audio).",
        )


def resolve_phase2_provider_name() -> str:
    """The configured provider id, defaulting to ``gemini``.

    Unknown values degrade to ``gemini`` (the product default) rather than
    raising — a typo in the env must never take Phase 2 down.
    """
    raw = os.getenv("ASA_PHASE2_PROVIDER", DEFAULT_PHASE2_PROVIDER).strip().lower()
    return raw if raw in SUPPORTED_PHASE2_PROVIDERS else DEFAULT_PHASE2_PROVIDER


def resolve_external_phase2_provider() -> Phase2Provider | None:
    """Return a non-Gemini provider, or ``None`` to use server.py's native Gemini.

    ``None`` is the default — the product Gemini path is left entirely untouched
    unless ``ASA_PHASE2_PROVIDER=moss`` or ``=claude`` is explicitly set.
    """
    provider_name = resolve_phase2_provider_name()
    if provider_name == "moss":
        return MossSidecarProvider.from_env()
    if provider_name == "claude":
        return ClaudeCliProvider.from_env()
    return None
