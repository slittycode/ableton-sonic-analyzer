#!/usr/bin/env python3
"""Generate a beat-eval manifest by scanning a local GTZAN beat_tracks/ directory.

Research-only helper — avoids hand-writing ~1000 manifest entries. Expects:
  <root>/gtzan/audio/<genre>/<genre>.000NN.wav
  <root>/gtzan/annotations/<genre>.000NN.beats

Genres in ASA_RELEVANT_GENRES are flagged asaRelevant=true (the pass bar is
judged on that electronic-adjacent subset).

  ./venv/bin/python scripts/build_beat_manifest.py \
      --root tests/fixtures/beat_tracks --out tests/fixtures/beat_eval_manifest.gtzan.json
"""

import argparse
import json
from pathlib import Path

ASA_RELEVANT_GENRES = {"disco", "hiphop", "pop"}
AUDIO_SUFFIXES = (".wav", ".au", ".mp3", ".flac")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a GTZAN beat-eval manifest from a local directory.")
    parser.add_argument("--root", type=Path, required=True, help="beat_tracks root (contains gtzan/audio + gtzan/annotations).")
    parser.add_argument("--out", type=Path, required=True, help="Output manifest JSON path.")
    parser.add_argument("--annotation-suffix", type=str, default=".beats", help="Annotation file suffix.")
    args = parser.parse_args()

    audio_root = args.root / "gtzan" / "audio"
    annotation_root = args.root / "gtzan" / "annotations"
    if not audio_root.is_dir():
        raise SystemExit(f"No audio directory at {audio_root}")

    clips = []
    missing_annotations = 0
    for genre_dir in sorted(p for p in audio_root.iterdir() if p.is_dir()):
        genre = genre_dir.name
        for audio in sorted(genre_dir.iterdir()):
            if audio.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            annotation = annotation_root / f"{audio.stem}{args.annotation_suffix}"
            if not annotation.exists():
                missing_annotations += 1
                continue
            clips.append(
                {
                    "id": audio.stem,
                    "genre": genre,
                    "audioPath": str(audio.relative_to(args.root.parent)),
                    "annotationPath": str(annotation.relative_to(args.root.parent)),
                    "asaRelevant": genre in ASA_RELEVANT_GENRES,
                }
            )

    manifest = {
        "datasetName": "GTZAN + GTZAN-Rhythm (Marchand/Fresnel/Peeters 2015)",
        "annotationFormat": "gtzan_rhythm",
        "currentShippingMethod": "kick_accent",
        "clips": clips,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(clips)} clips ({sum(c['asaRelevant'] for c in clips)} asaRelevant) to {args.out}; "
        f"{missing_annotations} audio files had no matching annotation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
