#!/usr/bin/env python3
"""Replay the Live 12 catalog validation against the v3.1 stems-gate
snapshots without spending Gemini API budget.

For each snapshot in `/tmp/decision_gate_{stems,real}_gemini-*.json`:
  1. Pull the model's Phase 2 result dict from
     stages.interpretation.profiles["producer_summary"].result
     (the "preferred" attempt for this model).
  2. Re-run `_validate_phase2_semantics()` against the freshly-loaded
     catalog. The catalog now has Auto Filter parameterAliases and
     Glue Compressor's expanded allowedParameters.
  3. Tally `UNKNOWN_PARAMETER` + `UNKNOWN_DEVICE` counts per model:
       - `before`: the count emitted into the snapshot when the gate
                   originally ran (read from
                   stages.interpretation.profiles[].diagnostics.validationWarnings).
       - `after`:  the count produced by the live re-validation.

Expected outcome:
  - Auto Filter "Filter Resonance" + Glue Compressor "Sidechain" hits → 0
  - Compressor "Sustain" hits remain (v3.2 prompt target)
  - "Ableton Project Settings" / "Mixer" UNKNOWN_DEVICE hits remain
    (v3.2 prompt target)

Run:
    ./venv/bin/python scripts/replay_catalog_validation.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_phase2 import _validate_phase2_semantics  # noqa: E402


# Glob covers both stem and non-stem snapshots from v3.1 (and any earlier
# generators that share the naming convention).
SNAPSHOT_GLOBS = ("/tmp/decision_gate_stems_gemini-*.json",
                  "/tmp/decision_gate_real_gemini-*.json")


def _extract_model_name_from_path(path: Path) -> str:
    # /tmp/decision_gate_stems_gemini-2.5-flash.json → gemini-2.5-flash
    stem = path.stem  # decision_gate_stems_gemini-2.5-flash
    for prefix in ("decision_gate_stems_", "decision_gate_real_"):
        if stem.startswith(prefix):
            return stem[len(prefix):]
    return stem


def _phase2_result_from_snapshot(snap: dict) -> dict | None:
    stages = snap.get("stages") or {}
    interp = stages.get("interpretation") or {}
    # First try the "preferred" path used by the live UI; fall back to the
    # profiles map (canonical when v3-style 1-meas/N-interp pattern was used).
    if isinstance(interp.get("result"), dict):
        return interp["result"]
    profiles = interp.get("profiles") or {}
    pref = profiles.get("producer_summary") or {}
    if isinstance(pref.get("result"), dict):
        return pref["result"]
    return None


def _existing_warning_counts(snap: dict) -> Counter:
    # Mirrors the v3 comparator's diagnostics access path. The "before"
    # numbers are whatever the backend originally emitted at gate-run time.
    stages = snap.get("stages") or {}
    interp = stages.get("interpretation") or {}
    counts: Counter = Counter()

    diag = interp.get("diagnostics") or {}
    for w in (diag.get("validationWarnings") or []):
        if isinstance(w, dict):
            counts[w.get("code", "UNKNOWN")] += 1

    profiles = interp.get("profiles") or {}
    pref = profiles.get("producer_summary") or {}
    pref_diag = pref.get("diagnostics") or {}
    for w in (pref_diag.get("validationWarnings") or []):
        if isinstance(w, dict):
            counts[w.get("code", "UNKNOWN")] += 1

    return counts


def main() -> int:
    snapshot_paths: list[Path] = []
    for pattern in SNAPSHOT_GLOBS:
        snapshot_paths.extend(sorted(Path("/").glob(pattern.lstrip("/"))))

    if not snapshot_paths:
        print("No snapshots found at", " or ".join(SNAPSHOT_GLOBS), file=sys.stderr)
        return 1

    headline = (
        f"{'snapshot':<60} {'before-UP':>10} {'after-UP':>10} "
        f"{'before-UD':>10} {'after-UD':>10}"
    )
    print(headline)
    print("-" * len(headline))

    grand_before_up = 0
    grand_after_up = 0
    grand_before_ud = 0
    grand_after_ud = 0

    for path in snapshot_paths:
        try:
            snap = json.loads(path.read_text())
        except Exception as exc:
            print(f"{path.name}: PARSE ERROR ({exc})")
            continue
        phase2 = _phase2_result_from_snapshot(snap)
        if not phase2:
            print(f"{path.name}: NO PHASE 2 RESULT (skipped)")
            continue

        before = _existing_warning_counts(snap)
        # Live re-validation against the current catalog dict.
        after_warnings = _validate_phase2_semantics(phase2)
        after = Counter()
        for w in after_warnings:
            after[w.get("code", "UNKNOWN")] += 1

        before_up = before.get("UNKNOWN_PARAMETER", 0)
        after_up = after.get("UNKNOWN_PARAMETER", 0)
        before_ud = before.get("UNKNOWN_DEVICE", 0)
        after_ud = after.get("UNKNOWN_DEVICE", 0)

        grand_before_up += before_up
        grand_after_up += after_up
        grand_before_ud += before_ud
        grand_after_ud += after_ud

        print(
            f"{path.name:<60} "
            f"{before_up:>10} {after_up:>10} {before_ud:>10} {after_ud:>10}"
        )

    print("-" * len(headline))
    print(
        f"{'TOTAL':<60} "
        f"{grand_before_up:>10} {grand_after_up:>10} "
        f"{grand_before_ud:>10} {grand_after_ud:>10}"
    )

    # Show which specific (device, parameter) pairs remain after the
    # catalog change — the post-fix offenders are the v3.2 prompt targets.
    print("\n--- Remaining UNKNOWN_* after re-validation ---")
    remaining: Counter = Counter()
    remaining_examples: dict[str, list[str]] = {}
    for path in snapshot_paths:
        try:
            snap = json.loads(path.read_text())
        except Exception:
            continue
        phase2 = _phase2_result_from_snapshot(snap)
        if not phase2:
            continue
        after_warnings = _validate_phase2_semantics(phase2)
        for w in after_warnings:
            code = w.get("code")
            if code not in ("UNKNOWN_PARAMETER", "UNKNOWN_DEVICE"):
                continue
            msg = w.get("message", "")
            key = msg.split(" in the curated")[0] if "in the curated" in msg else msg[:80]
            remaining[(code, key)] += 1
            remaining_examples.setdefault((code, key), []).append(path.name)

    for (code, key), count in remaining.most_common():
        sample_files = ", ".join(sorted(set(remaining_examples[(code, key)]))[:4])
        print(f"  {count:>3} × {code} :: {key}")
        print(f"         seen in: {sample_files}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
