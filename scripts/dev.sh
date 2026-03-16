#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_DIR="$ROOT_DIR/apps/ui"
BACKEND_DIR="$ROOT_DIR/apps/backend"

UI_PORT=3100
BACKEND_PORT=8100
UI_URL="http://127.0.0.1:${UI_PORT}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"

UI_ENV_KEYS=(
  VITE_API_BASE_URL
  VITE_ENABLE_PHASE2_GEMINI
  VITE_GEMINI_API_KEY
  DISABLE_HMR
)

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

read_env_file_value() {
  local env_file="$1"
  local key="$2"

  python3 - "$env_file" "$key" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
key = sys.argv[2]

if not env_path.exists():
    raise SystemExit(1)

for raw_line in env_path.read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue

    name, value = line.split("=", 1)
    if name.strip() != key:
        continue

    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]

    print(value, end="")
    raise SystemExit(0)

raise SystemExit(1)
PY
}

load_ui_env_file() {
  local env_file="$UI_DIR/.env"
  local key value

  if [[ ! -f "$env_file" ]]; then
    return 0
  fi

  for key in "${UI_ENV_KEYS[@]}"; do
    if [[ -n "${!key-}" ]]; then
      continue
    fi

    if value="$(read_env_file_value "$env_file" "$key" 2>/dev/null)"; then
      export "$key=$value"
    fi
  done
}

print_missing_backend_env() {
  echo "Missing backend virtualenv python: ${BACKEND_DIR}/venv/bin/python" >&2
  echo "Run ./apps/backend/scripts/bootstrap.sh to create the Python 3.11 backend environment." >&2
}

ensure_backend_env() {
  if [[ ! -e "$BACKEND_DIR/venv/bin/python" ]]; then
    print_missing_backend_env
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
    echo "This launcher now reads ${env_file}, so update that file or override it with exported env vars before rerunning ./scripts/dev.sh." >&2
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

main() {
  trap cleanup EXIT INT TERM

  require_command grep
  require_command lsof
  require_command npm
  require_command python3

  ensure_exists "$UI_DIR/package.json" "frontend package.json"
  ensure_exists "$BACKEND_DIR/server.py" "backend server entrypoint"
  ensure_backend_env

  warn_if_stale_ui_env
  load_ui_env_file

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

  local ui_api_base_url="${VITE_API_BASE_URL:-$BACKEND_URL}"

  echo "Starting Sonic Analyzer UI on ${UI_URL}..."
  (
    cd "$UI_DIR"
    VITE_API_BASE_URL="$ui_api_base_url" npm run dev:local
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
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
