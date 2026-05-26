#!/usr/bin/env python3
"""ASA contract-protecting PostToolUse hook.

Reads the Claude Code hook payload on stdin, inspects the file just edited,
and emits reminders tied to the load-bearing tripwires documented in
apps/backend/CLAUDE.md and the root CLAUDE.md:

  * Tripwire #1 — stdout in analyze.py is the JSON contract. A blocking note
    fires when a print() targets stdout without file=sys.stderr (the lone
    legitimate stdout emit is print(json.dumps(...))).
  * Tripwire #4 — new/renamed analyzer output keys must be mirrored into
    JSON_SCHEMA.md, EXPECTED_TOP_LEVEL_KEYS, and src/types/measurement.ts.
  * Tripwire #3 — the Phase 1 camelCase boundary has two sides (analyze.py and
    src/types/measurement.ts) with no conversion layer between them.
  * Tripwire #6 — artifact paths must go through artifact_storage.py, not raw
    Path(...).

Design: soft reminders are returned as PostToolUse additionalContext (visible
to the model, not spammed to the user); a confirmed stdout-contract break is
returned as decision="block" with a reason fed back to the model. The hook is
non-fatal — any internal error exits 0 silently so editing is never wedged.
"""

from __future__ import annotations

import ast
import json
import os
import sys


def _added_text(tool_input: dict) -> str:
    """Best-effort concatenation of text this tool call introduced."""
    parts: list[str] = []
    content = tool_input.get("content")
    if isinstance(content, str):
        parts.append(content)
    new_string = tool_input.get("new_string")
    if isinstance(new_string, str):
        parts.append(new_string)
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            parts.append(edit["new_string"])
    return "\n".join(parts)


def _stray_stdout_prints(path: str) -> list[int]:
    """Line numbers of print() calls that write stdout and aren't the JSON emit.

    A print() with any file= keyword (the file=sys.stderr convention) is fine,
    and the single legitimate stdout emit print(json.dumps(...)) is allowed.
    Uses the AST so multi-line print(..., file=sys.stderr) calls aren't
    misjudged the way a line-oriented grep would be.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
    except (OSError, SyntaxError, ValueError):
        return []
    violations: list[int] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            continue
        if any(kw.arg == "file" for kw in node.keywords):
            continue
        first = node.args[0] if node.args else None
        if (
            isinstance(first, ast.Call)
            and isinstance(first.func, ast.Attribute)
            and first.func.attr == "dumps"
        ):
            continue
        violations.append(node.lineno)
    return violations


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path")
    if not isinstance(path, str) or not path:
        return

    norm = path.replace("\\", "/")
    base = os.path.basename(norm)

    is_analyze = norm.endswith("apps/backend/analyze.py") or (
        "apps/backend/" in norm
        and base.startswith("analyze_")
        and base.endswith(".py")
    )
    is_measurement_types = norm.endswith("apps/ui/src/types/measurement.ts")

    hard: list[str] = []
    reminders: list[str] = []

    # Tripwire #1 — stdout is the JSON contract.
    if is_analyze:
        strays = _stray_stdout_prints(path)
        if strays:
            lines = ", ".join(str(n) for n in strays)
            hard.append(
                f"[ASA contract guard] {base}: print() writes stdout at line(s) "
                f"{lines} without file=sys.stderr. stdout is the JSON contract "
                "(tripwire #1) — diagnostics must use file=sys.stderr; only the "
                "final print(json.dumps(...)) may write stdout. Fix this."
            )
        # Tripwire #4 — output-key changes ripple to three other places.
        reminders.append(
            f"[ASA contract guard] Edited {base}: if you added/renamed analyzer "
            "OUTPUT keys, mirror them in JSON_SCHEMA.md, EXPECTED_TOP_LEVEL_KEYS "
            "(tests/test_analyze.py), and src/types/measurement.ts (tripwire #4), "
            "then run `./venv/bin/python -m unittest tests.test_analyze` from "
            "apps/backend."
        )

    # Tripwire #3 — the camelCase boundary has two sides.
    if is_analyze or is_measurement_types:
        reminders.append(
            "[ASA contract guard] The Phase 1 contract is emitted as camelCase by "
            "analyze.py and consumed by src/types/measurement.ts with NO conversion "
            "layer. A field rename on one side silently disappears (tripwire #3) — "
            "change both sides together."
        )

    # Tripwire #6 — artifact access goes through artifact_storage.py.
    if norm.endswith(".py") and "apps/backend/" in norm and base != "artifact_storage.py":
        added = _added_text(tool_input)
        if "Path(" in added and ("artifact" in added or ".runtime" in added):
            reminders.append(
                "[ASA contract guard] This edit adds Path(...) near an artifact "
                "path. Artifact access must go through artifact_storage.py "
                "(tripwire #6) — raw paths work in the local profile and break "
                "silently in hosted. Ignore if this Path() is unrelated to artifacts."
            )

    out: dict = {}
    if hard:
        out["decision"] = "block"
        out["reason"] = "\n".join(hard + reminders)
    elif reminders:
        out["hookSpecificOutput"] = {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(reminders),
        }
    if out:
        print(json.dumps(out))


if __name__ == "__main__":
    main()
