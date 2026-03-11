#!/usr/bin/env bash

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONOREPO_ROOT="$(cd "$BACKEND_DIR/../.." && pwd)"
ROOT_LAUNCHER="$MONOREPO_ROOT/scripts/dev.sh"

if [[ ! -x "$ROOT_LAUNCHER" ]]; then
  echo "Missing monorepo root launcher: $ROOT_LAUNCHER" >&2
  exit 1
fi

exec "$ROOT_LAUNCHER"
