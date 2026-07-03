#!/usr/bin/env python3
"""Fetch the GiantSteps Key + Tempo corpora (operator-run, local only).

Clones the two annotation repositories (MIT-licensed annotations) and
downloads the matching Beatport preview clips, verifying each file against
the repos' committed MD5 checksums. Audio is Beatport's — it lives only in
the gitignored corpus directory and is NEVER committed.

Run this on your own machine (cloud sessions typically sit behind a proxy
that blocks the download hosts):

    ./venv/bin/python scripts/fetch_giantsteps.py            # both subsets
    ./venv/bin/python scripts/fetch_giantsteps.py --subset key
    ./venv/bin/python scripts/fetch_giantsteps.py --verify-only

Preview URLs rot (the datasets are from 2015); each file is tried against
the Beatport sample host first and the JKU mirror second, and an existing
file that passes its checksum is never re-downloaded. Re-run with
--verify-only after any interruption to see corpus health.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = BACKEND_DIR / "tests" / "fixtures" / "giantsteps"

REPOS = {
    "key": "https://github.com/GiantSteps/giantsteps-key-dataset",
    "tempo": "https://github.com/GiantSteps/giantsteps-tempo-dataset",
}

# Preview mirrors, tried in order. {name} is e.g. "1234567.LOFI.mp3".
AUDIO_MIRRORS = (
    "http://geo-samples.beatport.com/lofi/{name}",
    "http://www.cp.jku.at/datasets/giantsteps/backup/{name}",
)


def _clone_or_update(repo_url: str, dest: Path) -> None:
    if (dest / ".git").is_dir():
        subprocess.run(["git", "-C", str(dest), "pull", "--ff-only"], check=True)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", repo_url, str(dest)], check=True)


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_checksums(repo_dir: Path) -> dict[str, str]:
    """Map audio filename -> expected md5 from the repo's md5/ directory."""
    checksums: dict[str, str] = {}
    md5_dir = repo_dir / "md5"
    if not md5_dir.is_dir():
        return checksums
    for md5_file in md5_dir.rglob("*.md5"):
        text = md5_file.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        # Formats seen upstream: "<hex>  <name>" or just "<hex>".
        parts = text.split()
        digest = parts[0].lower()
        name = parts[1] if len(parts) > 1 else md5_file.name[: -len(".md5")]
        checksums[Path(name).name] = digest
    return checksums


def _annotation_stems(repo_dir: Path, subset: str) -> list[str]:
    suffix = ".key" if subset == "key" else ".bpm"
    annotations = repo_dir / "annotations"
    return sorted(
        path.name[: -len(suffix)]
        for path in annotations.rglob(f"*{suffix}")
    )


def _stage_annotations(repo_dir: Path, subset_root: Path, subset: str) -> int:
    suffix = ".key" if subset == "key" else ".bpm"
    dest = subset_root / "annotations"
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in (repo_dir / "annotations").rglob(f"*{suffix}"):
        shutil.copy2(path, dest / path.name)
        count += 1
    return count


def _download(name: str, dest: Path) -> bool:
    for mirror in AUDIO_MIRRORS:
        url = mirror.format(name=name)
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            if len(data) < 10_000:  # error pages are small; previews are ~2 MB
                continue
            dest.write_bytes(data)
            return True
        except Exception as exc:  # noqa: BLE001 — report and try next mirror
            print(f"  [warn] {url}: {exc}", file=sys.stderr)
    return False


def process_subset(root: Path, subset: str, *, verify_only: bool) -> dict[str, int]:
    repo_dir = root / "_repos" / f"giantsteps-{subset}-dataset"
    subset_root = root / subset
    audio_dir = subset_root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    if not verify_only:
        _clone_or_update(REPOS[subset], repo_dir)
        staged = _stage_annotations(repo_dir, subset_root, subset)
        print(f"[{subset}] staged {staged} annotations")

    checksums = _load_checksums(repo_dir)
    stems = _annotation_stems(repo_dir, subset) if repo_dir.is_dir() else []
    stats = {"total": len(stems), "present": 0, "downloaded": 0, "checksum_failed": 0, "unavailable": 0}

    for stem in stems:
        name = f"{stem}.mp3"
        dest = audio_dir / name
        expected = checksums.get(name)
        if dest.exists():
            if expected and _md5(dest) != expected:
                print(f"  [warn] checksum mismatch: {name} (delete to re-fetch)", file=sys.stderr)
                stats["checksum_failed"] += 1
            else:
                stats["present"] += 1
            continue
        if verify_only:
            stats["unavailable"] += 1
            continue
        if _download(name, dest):
            if expected and _md5(dest) != expected:
                print(f"  [warn] checksum mismatch after download: {name}", file=sys.stderr)
                dest.unlink(missing_ok=True)
                stats["checksum_failed"] += 1
            else:
                stats["downloaded"] += 1
        else:
            stats["unavailable"] += 1

    print(f"[{subset}] {stats}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch/verify the GiantSteps corpora locally.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--subset", choices=("key", "tempo", "both"), default="both")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    subsets = ("key", "tempo") if args.subset == "both" else (args.subset,)
    any_audio = False
    for subset in subsets:
        stats = process_subset(args.root, subset, verify_only=args.verify_only)
        any_audio = any_audio or stats["present"] + stats["downloaded"] > 0
    if not any_audio:
        print(
            "No audio present. Preview mirrors may have rotted — see the README "
            "for alternate acquisition (mirdata) and keep annotations from the repos.",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
