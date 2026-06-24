#!/usr/bin/env bash

set -euo pipefail

err() {
  echo "$@" >&2
}

usage() {
  cat <<'EOF'
usage: ./scripts/reclaim-disk.sh [--dry-run]

Conservatively reclaim local disk space from regenerable ASA artifacts.

Automatic cleanup:
  - prune stale Git worktree registration metadata
  - delete repo caches: __pycache__/, .pytest_cache/, .ruff_cache/, apps/ui/test-results/
  - delete generated output: apps/ui/dist/, apps/backend/.runtime/

Manual follow-up only:
  - virtualenvs such as .venv/
  - Git worktree directories under .worktrees/ or .claude/worktrees/
  - .git/

Options:
  --dry-run   Show what would be removed, without deleting anything
  -h, --help  Show this help
EOF
}

DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown option: $1"
      err "Run ./scripts/reclaim-disk.sh --help for usage."
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -P "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"

human_bytes() {
  awk -v bytes="$1" 'BEGIN {
    split("B KiB MiB GiB TiB", units, " ")
    size = bytes + 0
    unit = 1
    while (size >= 1024 && unit < 5) {
      size = size / 1024
      unit++
    }
    if (unit == 1) {
      printf "%.0f %s", size, units[unit]
    } else {
      printf "%.1f %s", size, units[unit]
    }
  }'
}

path_size_bytes() {
  local path="$1"
  local kib

  if [[ ! -e "$path" ]]; then
    echo 0
    return 0
  fi

  kib="$(du -sk "$path" 2>/dev/null | awk '{print $1}')"
  if [[ -z "$kib" ]]; then
    echo 0
    return 0
  fi

  echo $((kib * 1024))
}

rel_path() {
  local path="$1"
  case "$path" in
    "$REPO_ROOT")
      echo "."
      ;;
    "$REPO_ROOT"/*)
      echo "${path#$REPO_ROOT/}"
      ;;
    *)
      echo "$path"
      ;;
  esac
}

assert_safe_path() {
  local path="$1"

  case "$path" in
    "$REPO_ROOT"|"${REPO_ROOT}/.git"|"$REPO_ROOT/.git/"*)
      err "Refusing to remove protected path: $(rel_path "$path")"
      exit 1
      ;;
    "$REPO_ROOT"/*)
      ;;
    *)
      err "Refusing to remove path outside repo: $path"
      exit 1
      ;;
  esac
}

sum_existing_size() {
  local total=0
  local path size

  for path in "$@"; do
    size="$(path_size_bytes "$path")"
    total=$((total + size))
  done

  echo "$total"
}

delete_path() {
  local path="$1"
  local label size

  assert_safe_path "$path"
  label="$(rel_path "$path")"

  if [[ ! -e "$path" ]]; then
    echo "skip missing: $label"
    return 0
  fi

  size="$(path_size_bytes "$path")"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "would delete: $label ($(human_bytes "$size"))"
    return 0
  fi

  echo "deleting: $label ($(human_bytes "$size"))"
  rm -rf -- "$path"
}

PYCACHE_DIRS=()
while IFS= read -r -d '' path; do
  PYCACHE_DIRS+=("$path")
done < <(
  find "$REPO_ROOT" \
    \( \
      -path "$REPO_ROOT/.git" -o \
      -path "$REPO_ROOT/apps/ui/node_modules" -o \
      -path "$REPO_ROOT/.venv" -o \
      -path "$REPO_ROOT/apps/backend/venv" -o \
      -path "$REPO_ROOT/apps/backend/.venv" -o \
      -path "$REPO_ROOT/.worktrees" -o \
      -path "$REPO_ROOT/.claude/worktrees" -o \
      -path "$REPO_ROOT/apps/ui/dist" -o \
      -path "$REPO_ROOT/apps/ui/test-results" -o \
      -path "$REPO_ROOT/apps/backend/.runtime" \
    \) -prune -o \
    -type d -name __pycache__ -print0
)

DELETE_TARGETS=(
  "$REPO_ROOT/.pytest_cache"
  "$REPO_ROOT/.ruff_cache"
  "$REPO_ROOT/apps/ui/test-results"
  "$REPO_ROOT/apps/ui/dist"
  "$REPO_ROOT/apps/backend/.runtime"
)

ALL_TARGETS=("${PYCACHE_DIRS[@]}" "${DELETE_TARGETS[@]}")
BEFORE_BYTES="$(sum_existing_size "${ALL_TARGETS[@]}")"

echo "ASA disk reclaim"
echo "Repo: $REPO_ROOT"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  echo "Dry run: no files will be deleted."
  echo "would run: git worktree prune -v"
else
  echo
  echo "Pruning stale Git worktree registration metadata..."
  git -C "$REPO_ROOT" worktree prune -v
fi

echo
echo "Regenerable cleanup candidates before cleanup: $(human_bytes "$BEFORE_BYTES")"

if [[ -e "$REPO_ROOT/apps/backend/.runtime" ]]; then
  echo
  echo "Warning: apps/backend/.runtime stores local analysis-run history and generated artifacts."
  echo "Deleting it may remove local run history, but it does not delete source code."
fi

echo
if [[ "${#PYCACHE_DIRS[@]}" -eq 0 ]]; then
  echo "No __pycache__/ directories found outside protected folders."
else
  for path in "${PYCACHE_DIRS[@]}"; do
    delete_path "$path"
  done
fi

for path in "${DELETE_TARGETS[@]}"; do
  delete_path "$path"
done

AFTER_BYTES="$(sum_existing_size "${ALL_TARGETS[@]}")"
RECLAIMED_BYTES=$((BEFORE_BYTES - AFTER_BYTES))
if [[ "$RECLAIMED_BYTES" -lt 0 ]]; then
  RECLAIMED_BYTES=0
fi

echo
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry-run summary: up to $(human_bytes "$BEFORE_BYTES") can be reclaimed automatically."
else
  echo "Reclaimed: $(human_bytes "$RECLAIMED_BYTES")"
  echo "Remaining candidate size: $(human_bytes "$AFTER_BYTES")"
fi

echo
echo "Manual follow-up, review before running:"
git -C "$REPO_ROOT" worktree list || true
cat <<'EOF'

Worktrees are separate checkouts. Review the list above, then remove only stale ones:
  git worktree remove <path>

Virtualenvs can be large but may be useful for local development. Remove only when you are ready to rebuild them:
  rm -rf .venv
  rm -rf apps/backend/venv
  rm -rf apps/backend/.venv

Do not delete .git unless you intentionally want to remove this repository checkout.
EOF
