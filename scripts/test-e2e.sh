#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PYTHON="$ROOT_DIR/apps/backend/venv/bin/python"
BACKEND_URL="${VITE_API_BASE_URL:-http://127.0.0.1:8100}"
BACKEND_LOG="$(mktemp -t sonic-analyzer-e2e-backend.XXXXXX.log)"
BACKEND_PID=""

cleanup() {
  if [[ -n "${BACKEND_PID}" ]]; then
    kill "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
}

is_placeholder_api_key() {
  local key
  key="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]' | xargs)"
  if [[ -z "${key}" ]]; then
    return 0
  fi

  case "${key}" in
    your_real_key_here|your_key_here|test-gemini-key|playwright-smoke-key|replace_me|changeme)
      return 0
      ;;
  esac

  [[ "${key}" == *placeholder* || "${key}" == *dummy* || "${key}" == *example* ]]
}

trap cleanup EXIT

if [[ ! -x "${BACKEND_PYTHON}" ]]; then
  echo "Missing backend interpreter at ${BACKEND_PYTHON}. Run ./apps/backend/scripts/bootstrap.sh first." >&2
  exit 1
fi

if [[ "${BACKEND_URL}" != "http://127.0.0.1:8100" ]]; then
  echo "scripts/test-e2e.sh expects VITE_API_BASE_URL to be http://127.0.0.1:8100 for the local backend run." >&2
  exit 1
fi

if [[ "${VITE_ENABLE_PHASE2_GEMINI:-}" != "true" ]]; then
  echo "VITE_ENABLE_PHASE2_GEMINI must be set to true before running the full live E2E suite." >&2
  exit 1
fi

if is_placeholder_api_key "${VITE_GEMINI_API_KEY:-}"; then
  echo "VITE_GEMINI_API_KEY must be set to a real Gemini API key before running the full live E2E suite." >&2
  exit 1
fi

(
  cd "${ROOT_DIR}/apps/backend"
  SONIC_ANALYZER_PORT=8100 "${BACKEND_PYTHON}" server.py >"${BACKEND_LOG}" 2>&1
) &
BACKEND_PID=$!

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8100/openapi.json" >/dev/null; then
    break
  fi
  sleep 1
done

if ! curl -sf "http://127.0.0.1:8100/openapi.json" >/dev/null; then
  echo "Backend did not become ready on http://127.0.0.1:8100/openapi.json within 30 seconds." >&2
  echo "Backend log:" >&2
  cat "${BACKEND_LOG}" >&2
  exit 1
fi

(
  cd "${ROOT_DIR}/apps/ui"
  export VITE_API_BASE_URL="http://127.0.0.1:8100"
  npm run test:e2e
)
