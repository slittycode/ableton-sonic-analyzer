#!/usr/bin/env bash

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$BACKEND_DIR/venv"
PYTHON_BIN="python3.11"
REQUIREMENTS_FILE="$BACKEND_DIR/requirements.txt"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Missing required interpreter: python3.11" >&2
  echo "Install Python 3.11 and rerun ./apps/backend/scripts/bootstrap.sh." >&2
  exit 1
fi

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  echo "Missing requirements file: $REQUIREMENTS_FILE" >&2
  exit 1
fi

echo "Creating Sonic Analyzer backend virtualenv with $PYTHON_BIN..."
"$PYTHON_BIN" -m venv --clear "$VENV_DIR"

echo "Upgrading pip..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip

echo "Installing pinned backend requirements..."
"$VENV_DIR/bin/python" -m pip install -r "$REQUIREMENTS_FILE"

echo "Backend bootstrap complete."
echo "  Python: $("$VENV_DIR/bin/python" -V)"
echo "  Venv: $VENV_DIR"
