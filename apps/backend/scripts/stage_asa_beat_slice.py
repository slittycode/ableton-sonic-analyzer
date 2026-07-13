#!/usr/bin/env python3
"""Stage the deterministic 18-clip ASA electronic slice for the beat gate.

Research-only. Picks GiantSteps Beatport previews (fetched locally by
scripts/fetch_giantsteps.py) spanning the plan's four families and copies them
to tests/fixtures/beat_tracks/asa/audio/, writing SELECTION.tsv alongside.
Selection is deterministic — per genre, the lexicographically first N clips
whose audio is present — so re-running reproduces the identical slice.

Beatport's 2015 taxonomy has no "garage" genre; breaks + dubstep stand in for
that family. Annotation workflow: tests/fixtures/beat_tracks/README.md.

    ./venv/bin/python scripts/stage_asa_beat_slice.py
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_GIANTSTEPS_ROOT = BACKEND_DIR / "tests" / "fixtures" / "giantsteps"
DEFAULT_DEST = BACKEND_DIR / "tests" / "fixtures" / "beat_tracks" / "asa"

# family -> [(beatport_genre, clip_count)]; 18 total (>= MIN_CLIPS_ASA=15 with headroom).
SLICE_PLAN = (
    ("house", (("house", 1), ("deep-house", 1), ("tech-house", 1), ("electro-house", 1), ("progressive-house", 1))),
    ("techno", (("techno", 3), ("minimal", 1), ("hardcore-hard-techno", 1))),
    ("dnb", (("drum-and-bass", 4),)),
    ("garage*", (("breaks", 2), ("dubstep", 2))),  # no 'garage' on 2015 Beatport
)


def pool_clips(giantsteps_root: Path) -> dict[str, tuple[str, Path]]:
    """Map clip stem -> (beatport genre, audio path) across both subsets."""
    pools: dict[str, tuple[str, Path]] = {}
    for subset, repo in (("key", "giantsteps-key-dataset"), ("tempo", "giantsteps-tempo-dataset")):
        genre_dir = giantsteps_root / "_repos" / repo / "annotations" / "genre"
        audio_dir = giantsteps_root / subset / "audio"
        if not genre_dir.is_dir():
            continue
        for genre_file in sorted(genre_dir.glob("*.genre")):
            raw = genre_file.read_text(encoding="utf-8", errors="replace").strip()
            genre = raw.splitlines()[-1].split("\t")[-1].strip() if raw else ""
            stem = genre_file.name[: -len(".genre")]
            audio = audio_dir / f"{stem}.mp3"
            if genre and audio.exists() and stem not in pools:
                pools[stem] = (genre, audio)
    return pools


def select_slice(pools: dict[str, tuple[str, Path]]) -> list[tuple[str, str, str]]:
    """Apply SLICE_PLAN -> [(stem, family, genre)], deterministic order."""
    rows: list[tuple[str, str, str]] = []
    for family, wants in SLICE_PLAN:
        for genre, count in wants:
            stems = sorted(s for s, (g, _) in pools.items() if g == genre)[:count]
            if len(stems) < count:
                print(f"[warn] only {len(stems)}/{count} clips available for {genre}", file=sys.stderr)
            rows.extend((s, family, genre) for s in stems)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage the ASA electronic beat slice (research-only).")
    parser.add_argument("--giantsteps-root", type=Path, default=DEFAULT_GIANTSTEPS_ROOT)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()

    pools = pool_clips(args.giantsteps_root)
    if not pools:
        print(
            f"No GiantSteps clips with genre + audio under {args.giantsteps_root} — "
            "run scripts/fetch_giantsteps.py first.",
            file=sys.stderr,
        )
        return 1
    rows = select_slice(pools)

    (args.dest / "audio").mkdir(parents=True, exist_ok=True)
    (args.dest / "annotations").mkdir(parents=True, exist_ok=True)
    for stem, _family, _genre in rows:
        _, audio = pools[stem]
        shutil.copy2(audio, args.dest / "audio" / audio.name)

    selection = args.dest / "SELECTION.tsv"
    with selection.open("w", encoding="utf-8") as handle:
        handle.write("clip_id\tfamily\tbeatport_genre\n")
        for stem, family, genre in rows:
            handle.write(f"{stem}\t{family}\t{genre}\n")

    print(f"staged {len(rows)} clips under {args.dest / 'audio'}; selection -> {selection}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
