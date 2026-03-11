#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR"
WORKSPACE_DIR="$(cd "$ROOT_DIR/.." && pwd)"
UI_DIR="$WORKSPACE_DIR/sonic-analyzer-UI"

UI_PORT=3100
BACKEND_PORT=8100
UI_URL="http://127.0.0.1:${UI_PORT}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"

BACKEND_PID=""
UI_PID=""

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

ensure_exists() {
  local path="$1"
  local description="$2"
  if [[ ! -e "$path" ]]; then
    echo "Missing ${description}: ${path}" >&2
    exit 1
  fi
}

print_port_conflict() {
  local port="$1"
  local service_name="$2"

  echo "Port ${port} is already in use, so the ${service_name} cannot start." >&2
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >&2 || true
  echo "Stop the process above or choose a different local stack before rerunning ./scripts/dev.sh." >&2
}

ensure_port_free() {
  local port="$1"
  local service_name="$2"

  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    print_port_conflict "$port" "$service_name"
    exit 1
  fi
}

warn_if_stale_ui_env() {
  local env_file="$UI_DIR/.env"
  if [[ -f "$env_file" ]] && grep -q "localhost:8000" "$env_file"; then
    echo "Warning: ${env_file} still points at localhost:8000." >&2
    echo "This launcher will override it with ${BACKEND_URL}, but manual UI runs can stay misconfigured until that ignored file is updated or removed." >&2
  fi
}

verify_backend_contract() {
  python3 - "$BACKEND_URL" <<'PY'
import json
import sys
import urllib.request

base_url = sys.argv[1].rstrip("/")
request = urllib.request.Request(f"{base_url}/openapi.json", method="GET")

try:
    with urllib.request.urlopen(request, timeout=2.5) as response:
        payload = json.load(response)
except Exception:
    sys.exit(1)

info = payload.get("info") or {}
paths = payload.get("paths") or {}

if (
    info.get("title") == "Sonic Analyzer Local API"
    and "/api/analyze" in paths
    and "/api/analyze/estimate" in paths
):
    sys.exit(0)

sys.exit(1)
PY
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  for pid in "$UI_PID" "$BACKEND_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done

  exit "$exit_code"
}

trap cleanup EXIT INT TERM

require_command grep
require_command lsof
require_command npm
require_command python3

ensure_exists "$UI_DIR/package.json" "frontend package.json"
ensure_exists "$BACKEND_DIR/server.py" "backend server entrypoint"
ensure_exists "$BACKEND_DIR/venv/bin/python" "backend virtualenv python"

warn_if_stale_ui_env

ensure_port_free "$BACKEND_PORT" "backend"
ensure_port_free "$UI_PORT" "UI dev server"

echo "Starting Sonic Analyzer backend on ${BACKEND_URL}..."
(
  cd "$BACKEND_DIR"
  SONIC_ANALYZER_PORT="$BACKEND_PORT" ./venv/bin/python server.py
) &
BACKEND_PID=$!

echo "Waiting for backend contract on ${BACKEND_URL}/openapi.json..."
for _attempt in $(seq 1 60); do
  if verify_backend_contract; then
    break
  fi
  sleep 1
done

if ! verify_backend_contract; then
  echo "Backend did not become ready on ${BACKEND_URL} with the expected Sonic Analyzer contract." >&2
  exit 1
fi

echo "Starting Sonic Analyzer UI on ${UI_URL}..."
(
  cd "$UI_DIR"
  VITE_API_BASE_URL="$BACKEND_URL" npm run dev:local
) &
UI_PID=$!

echo "Local stack running:"
echo "  UI: ${UI_URL}"
echo "  Backend: ${BACKEND_URL}"
echo "Press Ctrl-C to stop both processes."

while true; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    wait "$BACKEND_PID" || true
    echo "Backend process exited." >&2
    exit 1
  fi

  if ! kill -0 "$UI_PID" 2>/dev/null; then
    wait "$UI_PID" || true
    echo "UI process exited." >&2
    exit 1
  fi

  sleep 1
done
