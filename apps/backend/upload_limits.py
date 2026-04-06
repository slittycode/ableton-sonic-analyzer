from __future__ import annotations

import json
from typing import Any


MAX_UPLOAD_SIZE_BYTES = 104_857_600
UPLOAD_REQUEST_SIZE_SLACK_BYTES = 1_048_576
MAX_UPLOAD_REQUEST_BYTES = MAX_UPLOAD_SIZE_BYTES + UPLOAD_REQUEST_SIZE_SLACK_BYTES
UPLOAD_LIMITED_POST_PATHS = (
    "/api/analysis-runs",
    "/api/analysis-runs/estimate",
    "/api/analyze",
    "/api/analyze/estimate",
    "/api/phase2",
)

_BYTES_PER_MIB = 1024 * 1024


def bytes_to_mib(value: int) -> int:
    return value // _BYTES_PER_MIB


def bytes_to_mib_label(value: int) -> str:
    return f"{bytes_to_mib(value)} MiB"


def upload_too_large_message(limit_bytes: int = MAX_UPLOAD_SIZE_BYTES) -> str:
    return f"Uploaded audio exceeds the backend upload limit of {limit_bytes} bytes."


def build_proxy_snippets() -> dict[str, str]:
    request_limit_mib = bytes_to_mib(MAX_UPLOAD_REQUEST_BYTES)
    return {
        "nginx": f"client_max_body_size {request_limit_mib}m;",
        "Caddy": (
            "request_body {\n"
            f"  max_size {MAX_UPLOAD_REQUEST_BYTES}\n"
            "}"
        ),
        "Traefik": (
            "http:\n"
            "  middlewares:\n"
            "    asa-upload-limit:\n"
            "      buffering:\n"
            f"        maxRequestBodyBytes: {MAX_UPLOAD_REQUEST_BYTES}"
        ),
    }


def build_upload_limit_contract() -> dict[str, Any]:
    return {
        "rawAudioLimitBytes": MAX_UPLOAD_SIZE_BYTES,
        "rawAudioLimitMiB": bytes_to_mib(MAX_UPLOAD_SIZE_BYTES),
        "requestEnvelopeLimitBytes": MAX_UPLOAD_REQUEST_BYTES,
        "requestEnvelopeLimitMiB": bytes_to_mib(MAX_UPLOAD_REQUEST_BYTES),
        "requestSlackBytes": UPLOAD_REQUEST_SIZE_SLACK_BYTES,
        "requestSlackMiB": bytes_to_mib(UPLOAD_REQUEST_SIZE_SLACK_BYTES),
        "protectedPostRoutes": list(UPLOAD_LIMITED_POST_PATHS),
        "proxySnippets": build_proxy_snippets(),
    }


def render_upload_limit_contract_text() -> str:
    contract = build_upload_limit_contract()
    route_lines = "\n".join(
        f"- POST {route}"
        for route in contract["protectedPostRoutes"]
    )
    proxy_snippets = contract["proxySnippets"]
    json_summary = json.dumps(contract, indent=2)
    return (
        "Upload Limit Contract\n"
        "=====================\n\n"
        "Plain English\n"
        "-------------\n"
        f"- Raw audio uploads are capped at {MAX_UPLOAD_SIZE_BYTES} bytes "
        f"({bytes_to_mib_label(MAX_UPLOAD_SIZE_BYTES)}).\n"
        f"- Full HTTP upload requests are allowed up to {MAX_UPLOAD_REQUEST_BYTES} bytes "
        f"({bytes_to_mib_label(MAX_UPLOAD_REQUEST_BYTES)}) so multipart framing does not "
        "cause false rejects.\n"
        "- Only the protected upload POST routes below should be capped at the edge.\n\n"
        "Protected POST Routes\n"
        "---------------------\n"
        f"{route_lines}\n\n"
        "Machine-readable JSON\n"
        "---------------------\n"
        f"{json_summary}\n\n"
        "Proxy Snippets\n"
        "--------------\n"
        "nginx\n"
        f"{proxy_snippets['nginx']}\n\n"
        "Caddy\n"
        f"{proxy_snippets['Caddy']}\n\n"
        "Traefik\n"
        f"{proxy_snippets['Traefik']}\n\n"
        "Deployment Checklist\n"
        "--------------------\n"
        f"- Edge request-body limit matches {MAX_UPLOAD_REQUEST_BYTES} bytes "
        f"({bytes_to_mib_label(MAX_UPLOAD_REQUEST_BYTES)}).\n"
        "- Only the five protected upload POST routes are capped.\n"
        "- Backend startup log shows the same raw and edge limits after deploy.\n"
        "- A near-limit valid upload succeeds and an oversized upload returns HTTP 413.\n"
    )
