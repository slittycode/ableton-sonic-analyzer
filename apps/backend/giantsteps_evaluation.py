"""GiantSteps key/tempo evaluation harness (research-only).

Scores ASA's Phase 1 key and tempo measurements against the GiantSteps Key
and GiantSteps Tempo datasets — Beatport preview clips with expert
annotations, i.e. *real electronic music*, not synthetic renders. This is
the real-audio check the accuracy program requires before promoting any
key/tempo-affecting change (see audits/accuracy-baseline-2026-07-03.md).

Not on the product path: driven by scripts/evaluate_giantsteps.py, corpus
fetched locally by the operator via scripts/fetch_giantsteps.py (audio is
Beatport's and is never committed — see tests/fixtures/giantsteps/README.md).

The analyzer subprocess inherits the environment, so the same harness scores
alternative backends: e.g. `ASA_KEY_BACKEND=... scripts/evaluate_giantsteps.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from fundamentals_evaluation import _parse_key_pc

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_CORPUS_ROOT = BACKEND_DIR / "tests" / "fixtures" / "giantsteps"
DEFAULT_REPORT_DIR = BACKEND_DIR / ".runtime" / "reports"

_AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aif", ".aiff")

Subset = Literal["key", "tempo"]
Runner = Callable[[Path, list[str] | None], dict[str, Any]]


@dataclass(frozen=True)
class GiantstepsClip:
    clip_id: str
    audio_path: Path
    expected_key: str | None
    expected_bpm: float | None


def load_giantsteps_corpus(root: Path, subset: Subset) -> list[GiantstepsClip]:
    """Load clips from ``root/<subset>/{annotations,audio}/``.

    One clip per annotation file (``*.key`` = key string like "D minor",
    ``*.bpm`` = a single BPM float). Audio is matched by stem under
    ``audio/`` with any common extension; clips whose audio is absent are
    still returned (with the conventional path) so the caller can count and
    report them as missing rather than silently shrinking the corpus.
    """
    annotations_dir = root / subset / "annotations"
    audio_dir = root / subset / "audio"
    suffix = ".key" if subset == "key" else ".bpm"
    clips: list[GiantstepsClip] = []
    if not annotations_dir.is_dir():
        return clips
    for annotation_path in sorted(annotations_dir.rglob(f"*{suffix}")):
        raw = annotation_path.read_text(encoding="utf-8", errors="replace").strip()
        expected_key: str | None = None
        expected_bpm: float | None = None
        if subset == "key":
            expected_key = raw if raw else None
        else:
            try:
                expected_bpm = float(raw.split()[0]) if raw else None
            except ValueError:
                expected_bpm = None
        stem = annotation_path.name[: -len(suffix)]
        audio_path = audio_dir / f"{stem}.mp3"
        for extension in _AUDIO_EXTENSIONS:
            candidate = audio_dir / f"{stem}{extension}"
            if candidate.exists():
                audio_path = candidate
                break
        clips.append(
            GiantstepsClip(
                clip_id=stem,
                audio_path=audio_path,
                expected_key=expected_key,
                expected_bpm=expected_bpm,
            )
        )
    return clips


def mirex_key_score(expected: str, actual: str | None) -> float:
    """MIREX weighted key score, following the mir_eval.key convention.

    1.0 exact (enharmonic-folded) · 0.5 estimate a perfect fifth above the
    truth, same mode · 0.3 relative major/minor · 0.2 parallel (same tonic,
    other mode) · 0.0 otherwise or unparseable.
    """
    truth = _parse_key_pc(expected)
    estimate = _parse_key_pc(actual)
    if truth is None or estimate is None:
        return 0.0
    truth_pc, truth_mode = truth
    est_pc, est_mode = estimate
    if truth_mode not in ("major", "minor") or est_mode not in ("major", "minor"):
        return 1.0 if (truth_pc, truth_mode) == (est_pc, est_mode) else 0.0
    if (est_pc, est_mode) == (truth_pc, truth_mode):
        return 1.0
    if est_mode == truth_mode and est_pc == (truth_pc + 7) % 12:
        return 0.5
    if truth_mode == "major" and est_mode == "minor" and est_pc == (truth_pc + 9) % 12:
        return 0.3
    if truth_mode == "minor" and est_mode == "major" and est_pc == (truth_pc + 3) % 12:
        return 0.3
    if est_pc == truth_pc and est_mode != truth_mode:
        return 0.2
    return 0.0


def tempo_accuracies(
    expected: float, actual: float | None, tolerance: float = 0.04
) -> tuple[bool, bool]:
    """Standard tempo Accuracy1 / Accuracy2.

    Acc1: estimate within ±tolerance (relative) of the truth.
    Acc2: Acc1, or within tolerance of truth × {2, 3, 1/2, 1/3} — the
    octave/triple family RhythmExtractor's range preference collapses into.
    """
    if actual is None or not expected or expected <= 0:
        return False, False

    def within(target: float) -> bool:
        return abs(actual - target) <= tolerance * target

    acc1 = within(expected)
    acc2 = acc1 or any(within(expected * factor) for factor in (2.0, 3.0, 0.5, 1.0 / 3.0))
    return acc1, acc2


def _run_analyze(audio_path: Path, extra_flags: list[str] | None = None) -> dict[str, Any]:
    command = [sys.executable, str(BACKEND_DIR / "analyze.py"), str(audio_path), "--yes"]
    if extra_flags:
        command.extend(extra_flags)
    completed = subprocess.run(
        command,
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("analyze.py did not emit a JSON object")
    return payload


def evaluate_corpus(
    clips: list[GiantstepsClip],
    *,
    subset: Subset,
    runner: Runner | None = None,
    fast: bool = True,
    max_clips: int | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Score the corpus; returns the aggregate report dict.

    ``fast=True`` runs ``analyze.py --fast`` (BPM/key are populated in fast
    mode), which keeps a ~600-clip subset run tractable. The report's
    ``status`` is ``"underpowered"`` when zero clips were evaluable — callers
    must treat that as failure, never as a vacuous green.
    """
    if runner is None:
        runner = _run_analyze
    flags = ["--fast"] if fast else None

    selected = clips[:max_clips] if max_clips else clips
    per_clip: list[dict[str, Any]] = []
    missing_audio = 0
    analyze_failed = 0
    key_scores: list[float] = []
    key_exact = 0
    key_exact_or_relative = 0
    acc1_hits = 0
    acc2_hits = 0

    for clip in selected:
        if not clip.audio_path.exists():
            missing_audio += 1
            per_clip.append({"id": clip.clip_id, "status": "missing_audio"})
            continue
        try:
            payload = runner(clip.audio_path, flags)
        except subprocess.CalledProcessError as exc:
            analyze_failed += 1
            per_clip.append(
                {
                    "id": clip.clip_id,
                    "status": "analyze_failed",
                    "error": (exc.stderr or "")[-300:],
                }
            )
            continue

        entry: dict[str, Any] = {"id": clip.clip_id, "status": "evaluated"}
        if subset == "key" and clip.expected_key:
            actual_key = payload.get("key") if isinstance(payload.get("key"), str) else None
            score = mirex_key_score(clip.expected_key, actual_key)
            entry.update({"expectedKey": clip.expected_key, "actualKey": actual_key, "mirex": score})
            key_scores.append(score)
            if score == 1.0:
                key_exact += 1
            if score in (1.0, 0.3):
                key_exact_or_relative += 1
        if subset == "tempo" and clip.expected_bpm:
            actual_bpm = payload.get("bpm")
            actual_bpm = float(actual_bpm) if isinstance(actual_bpm, (int, float)) else None
            acc1, acc2 = tempo_accuracies(clip.expected_bpm, actual_bpm)
            entry.update(
                {"expectedBpm": clip.expected_bpm, "actualBpm": actual_bpm, "acc1": acc1, "acc2": acc2}
            )
            acc1_hits += int(acc1)
            acc2_hits += int(acc2)
        per_clip.append(entry)

    evaluated = sum(1 for entry in per_clip if entry["status"] == "evaluated")
    summary: dict[str, Any] = {
        "subset": subset,
        "clipsListed": len(selected),
        "clipsEvaluated": evaluated,
        "clipsMissingAudio": missing_audio,
        "clipsAnalyzeFailed": analyze_failed,
        "fastMode": fast,
        "status": "evaluated" if evaluated > 0 else "underpowered",
    }
    if subset == "key" and key_scores:
        summary["keyExactRate"] = round(key_exact / len(key_scores), 4)
        summary["keyExactOrRelativeRate"] = round(key_exact_or_relative / len(key_scores), 4)
        summary["mirexWeighted"] = round(sum(key_scores) / len(key_scores), 4)
    if subset == "tempo" and evaluated:
        summary["tempoAcc1"] = round(acc1_hits / evaluated, 4)
        summary["tempoAcc2"] = round(acc2_hits / evaluated, 4)

    report: dict[str, Any] = {
        "schemaVersion": "giantsteps-eval-report.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "clips": per_clip,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["reportPath"] = str(report_path)
    return report
