#!/usr/bin/env python3
"""Interactive scorecard CLI for polyphonic evaluation reports.

Reads a polyphonic evaluation report produced by `evaluate_polyphonic.py`,
walks the unscored clip/candidate pairs, prompts the reviewer for the five
manual scorecard fields, and writes the updates back into the report in place.

Replaces hand-editing the report JSON. Idempotent without `--rescore` — already
scored entries are skipped.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from polyphonic_evaluation import (  # noqa: E402  - sys.path mutated above
    DEFAULT_REPORT_PATH,
    build_manual_scorecard,
)

SCORECARD_FIELDS = (
    "bassRecognizable",
    "toplineRecognizable",
    "chordsNotObviouslyWrong",
    "cleanupMinutes30s",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Interactively score polyphonic evaluation clips. Updates the "
            "report JSON in place. Pass --no-play to skip audio playback "
            "(required for non-interactive / headless usage)."
        )
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Path to the polyphonic evaluation report (default: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--rescore",
        action="store_true",
        help="Re-prompt for clips that already have a complete scorecard.",
    )
    parser.add_argument(
        "--no-play",
        action="store_true",
        help="Skip audio playback. Required for headless / non-interactive runs.",
    )
    parser.add_argument(
        "--candidate",
        type=str,
        default=None,
        help="Limit scoring to a single candidate id (e.g. 'basic-pitch').",
    )
    return parser.parse_args()


def _scorecard_is_complete(scorecard: dict[str, Any] | None) -> bool:
    if not isinstance(scorecard, dict):
        return False
    return all(scorecard.get(field) is not None for field in SCORECARD_FIELDS)


def _resolve_player() -> list[str] | None:
    """Find a system audio player. Returns the command prefix or None."""
    for binary in ("afplay", "paplay", "aplay"):
        path = shutil.which(binary)
        if path:
            return [path]
    return None


def _play_audio(player: list[str] | None, audio_path: Path) -> None:
    if player is None:
        print("  [warn] no audio player found (afplay / paplay / aplay). Skipping playback.")
        return
    if not audio_path.exists():
        print(f"  [warn] audio not found at {audio_path}; skipping playback.")
        return
    try:
        subprocess.run([*player, str(audio_path)], check=False)
    except KeyboardInterrupt:
        # Allow the reviewer to interrupt playback without exiting the CLI.
        print("  [info] playback interrupted; continuing to prompts.")


def _prompt_yes_no(label: str, default: str = "n") -> bool:
    suffix = "Y/n" if default.lower() == "y" else "y/N"
    while True:
        raw = input(f"  {label} [{suffix}]: ").strip().lower()
        if raw == "":
            raw = default.lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("    please answer y or n.")


def _prompt_float(label: str, *, min_value: float = 0.0) -> float:
    while True:
        raw = input(f"  {label}: ").strip()
        try:
            value = float(raw)
        except ValueError:
            print("    please enter a number.")
            continue
        if value < min_value:
            print(f"    must be >= {min_value}.")
            continue
        return value


def _prompt_optional_text(label: str) -> str:
    return input(f"  {label}: ").rstrip("\n")


def _score_one(
    clip_id: str,
    candidate_id: str,
    candidate_report: dict[str, Any],
    audio_path: Path,
    player: list[str] | None,
    play: bool,
) -> dict[str, Any]:
    metrics = candidate_report.get("metrics") or {}
    flags = metrics.get("flags") or []
    print(f"\n=== {clip_id} :: {candidate_id} ===")
    print(f"  audio: {audio_path}")
    print(
        "  metrics: noteCount={n} maxPolyphony={mp} noteDensityPerSecond={d}".format(
            n=metrics.get("noteCount", "?"),
            mp=metrics.get("maxPolyphony", "?"),
            d=metrics.get("noteDensityPerSecond", "?"),
        )
    )
    if flags:
        print(f"  flags: {', '.join(flags)}")
    else:
        print("  flags: (none)")

    if play:
        _play_audio(player, audio_path)

    existing = candidate_report.get("scorecard") if isinstance(candidate_report.get("scorecard"), dict) else None
    bass = _prompt_yes_no("bassRecognizable?")
    topline = _prompt_yes_no("toplineRecognizable?")
    chords = _prompt_yes_no("chordsNotObviouslyWrong?")
    cleanup = _prompt_float("cleanupMinutes30s")
    notes_default = (existing or {}).get("notes", "")
    notes = _prompt_optional_text(f"notes (current: {notes_default!r})")
    if notes == "":
        notes = notes_default

    return build_manual_scorecard(
        {
            "bassRecognizable": bass,
            "toplineRecognizable": topline,
            "chordsNotObviouslyWrong": chords,
            "cleanupMinutes30s": cleanup,
            "notes": notes,
        }
    )


def main() -> None:
    args = parse_args()
    report_path: Path = args.report
    if not report_path.exists():
        print(f"error: report not found at {report_path}", file=sys.stderr)
        raise SystemExit(2)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    clips = report.get("clips")
    if not isinstance(clips, list) or len(clips) == 0:
        print("error: report has no clips to score.", file=sys.stderr)
        raise SystemExit(2)

    player = _resolve_player()
    scored_count = 0
    skipped_count = 0

    for clip in clips:
        if not isinstance(clip, dict):
            continue
        clip_id = str(clip.get("id") or "unknown")
        audio_path_str = clip.get("audioPath") or ""
        audio_path = Path(audio_path_str)
        candidates = clip.get("candidates") or {}
        if not isinstance(candidates, dict):
            continue

        for candidate_id, candidate_report in candidates.items():
            if args.candidate and candidate_id != args.candidate:
                continue
            if not isinstance(candidate_report, dict):
                continue
            existing = candidate_report.get("scorecard")
            if _scorecard_is_complete(existing) and not args.rescore:
                skipped_count += 1
                continue
            try:
                new_scorecard = _score_one(
                    clip_id=clip_id,
                    candidate_id=candidate_id,
                    candidate_report=candidate_report,
                    audio_path=audio_path,
                    player=player,
                    play=not args.no_play,
                )
            except EOFError:
                print("\n[info] input stream closed; stopping early.", file=sys.stderr)
                break
            candidate_report["scorecard"] = new_scorecard
            scored_count += 1

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "reportPath": str(report_path),
                "scored": scored_count,
                "skippedAlreadyComplete": skipped_count,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
