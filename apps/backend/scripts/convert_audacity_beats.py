#!/usr/bin/env python3
"""Convert an Audacity label track to a GTZAN-Rhythm `.beats` file.

Research-only helper for the ASA electronic slice — the beat gate's one manual
labeling task (see tests/fixtures/beat_tracks/README.md). The annotator taps a
point label on every beat in Audacity (or Sonic Visualiser, exported the same
way) and labels *at least each downbeat* with its beat position ("1"); labels
left blank continue counting from the previous position, cycling at --meter.

Input  (Audacity "Export Labels"): `<start>\t<end>\t<label>` per line.
Output (GTZAN-Rhythm):             `<time>\t<beat_position>` per line, pos 1 =
downbeat — exactly what beat_evaluation.py's annotation reader consumes.

    ./venv/bin/python scripts/convert_audacity_beats.py labels.txt \
        --out tests/fixtures/beat_tracks/asa/annotations/1034795.LOFI.beats

Explicit numeric labels always win and reset the cycle (so a mid-track meter
change is expressible, same as upstream GTZAN-Rhythm); the first label must be
numeric so bar 1 is anchored by a human, never inferred.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def convert_labels(lines: list[str], meter: int = 4) -> list[tuple[float, int]]:
    """Audacity label lines -> [(time_seconds, beat_position)]. Raises ValueError."""
    if meter < 2:
        raise ValueError(f"--meter must be >= 2, got {meter}")
    beats: list[tuple[float, int]] = []
    prev_time = -1.0
    prev_pos: int | None = None
    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        try:
            time = float(parts[0])
        except ValueError as exc:
            raise ValueError(f"line {lineno}: unparseable start time {parts[0]!r}") from exc
        if time < prev_time:
            raise ValueError(f"line {lineno}: time {time} goes backwards (previous {prev_time})")
        label = parts[2].strip() if len(parts) > 2 else ""
        if label:
            try:
                pos = int(label)
            except ValueError as exc:
                raise ValueError(f"line {lineno}: label {label!r} is not a beat position") from exc
            if not 1 <= pos <= meter:
                raise ValueError(f"line {lineno}: position {pos} outside 1..{meter}")
        elif prev_pos is None:
            raise ValueError("first label must carry an explicit beat position (anchor bar 1 by hand)")
        else:
            pos = prev_pos % meter + 1
        beats.append((time, pos))
        prev_time = time
        prev_pos = pos
    if not beats:
        raise ValueError("no labels found")
    return beats


def main() -> int:
    parser = argparse.ArgumentParser(description="Audacity labels -> GTZAN-Rhythm .beats (research-only).")
    parser.add_argument("labels", type=Path, help="Audacity 'Export Labels' text file.")
    parser.add_argument("--out", type=Path, required=True, help="Destination .beats path.")
    parser.add_argument("--meter", type=int, default=4, help="Beats per bar for blank-label cycling (default 4).")
    args = parser.parse_args()

    lines = args.labels.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        beats = convert_labels(lines, meter=args.meter)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(f"{time:.3f}\t{pos}\n" for time, pos in beats), encoding="utf-8")
    downbeats = sum(1 for _, pos in beats if pos == 1)
    print(f"wrote {len(beats)} beats ({downbeats} downbeats) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
