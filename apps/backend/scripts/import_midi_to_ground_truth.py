#!/usr/bin/env python3
"""Convert a reference MIDI file into a `groundTruthNotes` JSON fragment.

Used to bootstrap entries in `tests/fixtures/phase1_eval_manifest.json` under
`transcriptionTracks[].groundTruthNotes`. Emits a JSON array to stdout so the
output can be pasted directly into the manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pretty_midi


def _flatten_notes(midi: pretty_midi.PrettyMIDI, offset_seconds: float) -> list[dict]:
    notes: list[dict] = []
    for instrument in midi.instruments:
        for note in instrument.notes:
            start = float(note.start) + offset_seconds
            end = float(note.end) + offset_seconds
            duration = max(0.0, end - start)
            notes.append(
                {
                    "pitchMidi": int(note.pitch),
                    "onsetSeconds": round(start, 4),
                    "durationSeconds": round(duration, 4),
                }
            )
    notes.sort(key=lambda entry: (entry["onsetSeconds"], entry["pitchMidi"]))
    return notes


def _detect_overlaps(notes: list[dict]) -> list[tuple[int, int]]:
    overlaps: list[tuple[int, int]] = []
    sorted_indices = sorted(range(len(notes)), key=lambda i: notes[i]["onsetSeconds"])
    for i_pos in range(len(sorted_indices)):
        i = sorted_indices[i_pos]
        i_end = notes[i]["onsetSeconds"] + notes[i]["durationSeconds"]
        for j_pos in range(i_pos + 1, len(sorted_indices)):
            j = sorted_indices[j_pos]
            if notes[j]["onsetSeconds"] >= i_end:
                break
            overlaps.append((i, j))
    return overlaps


def _collapse_monophonic_highest(notes: list[dict]) -> list[dict]:
    if len(notes) == 0:
        return notes
    indices_by_onset = sorted(range(len(notes)), key=lambda i: notes[i]["onsetSeconds"])
    keep: set[int] = set(indices_by_onset)
    for pos_i in range(len(indices_by_onset)):
        i = indices_by_onset[pos_i]
        if i not in keep:
            continue
        i_end = notes[i]["onsetSeconds"] + notes[i]["durationSeconds"]
        for pos_j in range(pos_i + 1, len(indices_by_onset)):
            j = indices_by_onset[pos_j]
            if j not in keep:
                continue
            if notes[j]["onsetSeconds"] >= i_end:
                break
            if notes[j]["pitchMidi"] > notes[i]["pitchMidi"]:
                keep.discard(i)
                break
            keep.discard(j)
    return [notes[i] for i in sorted(keep, key=lambda i: notes[i]["onsetSeconds"])]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a MIDI file into the groundTruthNotes JSON fragment for a "
            "transcriptionTracks manifest entry."
        )
    )
    parser.add_argument("midi_path", type=Path, help="Path to the .mid file to convert.")
    parser.add_argument(
        "--monophonic-collapse",
        choices=("highest", "reject"),
        default="reject",
        help=(
            "Behavior when notes overlap. 'reject' (default) exits non-zero on "
            "any overlap. 'highest' keeps the highest pitch in any overlapping "
            "group and drops the rest."
        ),
    )
    parser.add_argument(
        "--offset-seconds",
        type=float,
        default=0.0,
        help=(
            "Add N seconds to every onset. Use when DAW MIDI export starts at a "
            "different point than the audio (e.g. negative track delay)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.midi_path.exists():
        print(f"error: MIDI file not found at {args.midi_path}", file=sys.stderr)
        raise SystemExit(2)

    try:
        midi = pretty_midi.PrettyMIDI(str(args.midi_path))
    except Exception as exc:
        print(f"error: failed to parse MIDI: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    notes = _flatten_notes(midi, args.offset_seconds)
    overlaps = _detect_overlaps(notes)

    if len(overlaps) > 0:
        if args.monophonic_collapse == "reject":
            print(
                f"error: {len(overlaps)} overlapping note pair(s) detected. "
                "Pass --monophonic-collapse highest to keep the higher pitch in "
                "each overlapping group.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        notes = _collapse_monophonic_highest(notes)

    print(json.dumps(notes, indent=2))


if __name__ == "__main__":
    main()
