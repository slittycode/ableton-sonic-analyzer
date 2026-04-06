#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PYTHON="$ROOT_DIR/apps/backend/venv/bin/python"
BACKEND_URL="${VITE_API_BASE_URL:-http://127.0.0.1:8100}"
BACKEND_LOG="$(mktemp -t sonic-analyzer-e2e-integration-backend.XXXXXX.log)"
BACKEND_PID=""

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
    and "/api/analysis-runs/estimate" in paths
    and "/api/analysis-runs" in paths
    and "/api/analysis-runs/{run_id}" in paths
):
    sys.exit(0)

sys.exit(1)
PY
}

cleanup() {
  if [[ -n "${BACKEND_PID}" ]]; then
    kill "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT

if [[ ! -x "${BACKEND_PYTHON}" ]]; then
  echo "Missing backend interpreter at ${BACKEND_PYTHON}. Run ./apps/backend/scripts/bootstrap.sh first." >&2
  exit 1
fi

if [[ "${BACKEND_URL}" != "http://127.0.0.1:8100" ]]; then
  echo "scripts/test-e2e-integration.sh expects VITE_API_BASE_URL to be http://127.0.0.1:8100 for the local backend run." >&2
  exit 1
fi

(
  cd "${ROOT_DIR}/apps/backend"
  SONIC_ANALYZER_PORT=8100 "${BACKEND_PYTHON}" server.py >"${BACKEND_LOG}" 2>&1
) &
BACKEND_PID=$!

for _ in $(seq 1 30); do
  if verify_backend_contract; then
    break
  fi
  sleep 1
done

if ! verify_backend_contract; then
  echo "Backend did not become ready on http://127.0.0.1:8100 with the canonical analysis-runs contract within 30 seconds." >&2
  echo "Backend log:" >&2
  cat "${BACKEND_LOG}" >&2
  exit 1
fi

(
  cd "${ROOT_DIR}/apps/ui"
  export VITE_API_BASE_URL="http://127.0.0.1:8100"
  export VITE_ENABLE_PHASE2_GEMINI="false"
  npm run test:e2e:integration
)
