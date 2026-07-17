"""Phase 2 interpretation provider abstraction (gemini | claude).

The product default is Gemini, whose call lives inline in ``server.py``
(``_run_interpretation_request_with_profile_config``) and is **unchanged**. This
module adds a pluggable seam so the *same* Phase 2 request — same built prompt,
same audio, same authoritative Phase 1 JSON, same ``response_schema`` — can be
routed to the local Claude Code CLI instead, while flowing through the
*identical* downstream parse / validate / citation / catalogue path in
``server.py``. That shared tail is what guarantees the "identical recommendation
schema" DoD: both providers emit a raw ``Phase2Result`` JSON string, and
``server.py`` validates both the same way.

Selection is env-gated and **default-off**::

    ASA_PHASE2_PROVIDER = "gemini" (default) | "claude"

``resolve_external_phase2_provider()`` returns ``None`` for the Gemini default
(meaning: use ``server.py``'s native Gemini path, byte-for-byte unchanged) and a
``ClaudeCliProvider`` only when ``claude`` is explicitly selected. The ``claude``
provider runs the operator's local Claude Code CLI headless and is **text-only**:
it grounds the interpretation in the prompt's embedded Phase 1 JSON and never
receives the audio, so it needs no ``GEMINI_API_KEY`` and no network credits
beyond the operator's existing Claude subscription.

The former MOSS sidecar path was a permanent licence dead-end (modeling code had
no effective licence; real-model path was a designed-in 501 stub) and was removed
in the 2026-07 trust diet — see ``docs/PHASE2_PROVIDER.md`` and
``plans/trust-diet-2026-07.md``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


DEFAULT_PHASE2_PROVIDER = "gemini"
SUPPORTED_PHASE2_PROVIDERS = ("gemini", "claude")

_DEFAULT_CLAUDE_CLI = "claude"
# A full producer_summary prompt (~240k chars) on the CLI's default model was
# measured at ~6 minutes end-to-end; 300s would kill legitimate calls.
_DEFAULT_CLAUDE_TIMEOUT_SECONDS = 600


@dataclass
class Phase2ProviderRequest:
    """Everything a provider needs to produce a raw ``Phase2Result`` JSON string.

    ``prompt`` already embeds the authoritative Phase 1 JSON, the Live 12 device
    catalogue, and grounding metadata (built by ``server_phase2._build_phase2_prompt``).
    ``phase1_result`` is forwarded *separately* as well so a provider can ground
    citations in real measurement paths without re-parsing the prompt.
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

    Carries the fields the interpretation execution dict needs so an external
    provider failure degrades the same way a Gemini failure does (retryable,
    surfaced in the UI as a failed attempt — never a silent success).
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "PHASE2_PROVIDER_FAILED",
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
    and no separate API credits are required. Default-off.
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
    unless ``ASA_PHASE2_PROVIDER=claude`` is explicitly set.
    """
    provider_name = resolve_phase2_provider_name()
    if provider_name == "claude":
        return ClaudeCliProvider.from_env()
    return None
