#!/usr/bin/env bash

set -euo pipefail

# reclaim-disk.sh — reclaim local checkout disk space, conservatively.
#
# The asa checkout accumulates non-source bloat over time: stale git worktree
# registrations, Python bytecode caches, and regenerable build/runtime output.
# This script deletes ONLY regenerable, already-gitignored artifacts — never
# source, never history (.git/), never a virtualenv or worktree it can't prove
# is safe. The genuinely destructive moves (removing individual worktrees,
# deleting venv copies) are PRINTED as guidance for you to run by hand, not
# automated.
#
# Usage:
#   scripts/reclaim-disk.sh [--dry-run]
#
#   --dry-run   Report what WOULD be freed without deleting anything.
#
# Safe to run repeatedly; everything it clears is regenerated on next use
# (caches on next test/run, dist on next build, .runtime on next analysis).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      echo "usage: scripts/reclaim-disk.sh [--dry-run]"
      echo "  Clears regenerable caches + build/runtime output and prunes stale"
      echo "  worktree registrations. --dry-run reports without deleting."
      exit 0 ;;
    *) echo "reclaim-disk: unknown option: $1" >&2; exit 1 ;;
  esac
done

err() { echo "$@" >&2; }

# Print a path's size if it exists, else nothing. Never fails under `set -e`.
dir_size() {
  [[ -e "$1" ]] && du -sh "$1" 2>/dev/null | cut -f1 || true
}

# Delete a path (honoring --dry-run) and report. Skips silently when absent.
reclaim_path() {
  local target="$1"
  [[ -e "$target" ]] || return 0
  local size; size="$(dir_size "$target")"
  local rel="${target#"$ROOT_DIR"/}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  would free ${size:-?}	${rel}"
  else
    rm -rf "$target"
    echo "  freed     ${size:-?}	${rel}"
  fi
}

cd "$ROOT_DIR"

BEFORE="$(dir_size "$ROOT_DIR")"
echo "reclaim-disk: checkout is ${BEFORE:-?} (${ROOT_DIR})"
[[ "$DRY_RUN" -eq 1 ]] && echo "(dry run — nothing will be deleted)"
echo

# 1. Prune stale git worktree registrations. This only removes administrative
#    entries for worktrees whose directory is already gone — it never deletes a
#    live worktree or touches a branch.
echo "[1/3] git worktree prune"
if [[ "$DRY_RUN" -eq 1 ]]; then
  git worktree prune --dry-run -v 2>&1 | sed 's/^/  /' || true
else
  git worktree prune -v 2>&1 | sed 's/^/  /' || true
fi
echo

# 2. Regenerable caches (regenerated on next test/lint run). Scoped to exclude
#    node_modules so we never touch installed dependency trees.
echo "[2/3] regenerable caches"
while IFS= read -r -d '' cache; do
  reclaim_path "$cache"
done < <(find "$ROOT_DIR" \
  -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) \
  -not -path '*/node_modules/*' -prune -print0 2>/dev/null)
reclaim_path "$ROOT_DIR/apps/ui/test-results"
echo

# 3. Regenerable build + runtime output.
echo "[3/3] build + runtime output"
reclaim_path "$ROOT_DIR/apps/backend/.runtime"
reclaim_path "$ROOT_DIR/apps/ui/dist"
echo

AFTER="$(dir_size "$ROOT_DIR")"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "reclaim-disk: dry run complete (checkout still ${AFTER:-?})"
else
  echo "reclaim-disk: done — checkout now ${AFTER:-?} (was ${BEFORE:-?})"
fi

# --- Guidance for the destructive, NOT-automated reclaims -------------------
# These can recover the bulk of a bloated checkout (duplicate venvs inside
# stale worktrees, an orphan root venv), but each is irreversible enough that
# this script leaves the call to you.
echo
echo "Further reclaims (run by hand after reviewing — NOT done automatically):"
echo
echo "  • Stale worktrees (each may carry its own multi-hundred-MB venv copy):"
echo "      git worktree list"
echo "    For any you no longer need, after confirming its branch is merged or"
echo "    pushed:"
echo "      git worktree remove <path>        # add --force only if you are sure"
echo
echo "  • Orphan root virtualenv (the product path uses apps/backend/venv;"
echo "    a root-level .venv/ is not referenced by scripts/dev.sh):"
if [[ -e "$ROOT_DIR/.venv" ]]; then
  echo "      rm -rf .venv                      # present here: $(dir_size "$ROOT_DIR/.venv")"
else
  echo "      rm -rf .venv                      # (none present in this checkout)"
fi
echo
echo "  • .git/ history is intentionally left untouched — shrinking it needs a"
echo "    history rewrite (git count-objects -v showed no reclaimable garbage)."
