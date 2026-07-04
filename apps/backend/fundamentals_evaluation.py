"""Evaluation harness for local musical-fundamentals accuracy gates."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = BACKEND_DIR / "tests" / "fixtures" / "fundamentals_eval_manifest.json"
DEFAULT_TRACKS_DIR = BACKEND_DIR / "tests" / "fixtures" / "fundamentals_tracks"
DEFAULT_REPORT_PATH = BACKEND_DIR / ".runtime" / "reports" / "fundamentals_eval_report.json"

STATUS_RANK = {
    "failed": 0,
    "not_run": 1,
    "ambiguous": 2,
    "authoritative": 3,
}


@dataclass
class FundamentalsCheck:
    name: str
    passed: bool
    message: str
    # Known-gap checks still run and report their score but do not gate the
    # summary — they keep a real baseline weakness visible in every report
    # without holding the regression gate red.
    informational: bool = False


@dataclass
class FundamentalsTrackResult:
    track_id: str
    audio_path: str
    category: str
    description: str
    status: str
    skip_reason: str | None
    checks: list[FundamentalsCheck]
    all_passed: bool


Runner = Callable[[Path, list[str] | None], dict[str, Any]]


def run_fundamentals_evaluation(
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    tracks_dir: Path = DEFAULT_TRACKS_DIR,
    report_path: Path = DEFAULT_REPORT_PATH,
    runner: Runner | None = None,
    fail_on_skip: bool = False,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracks = manifest.get("tracks", [])
    if not isinstance(tracks, list):
        raise ValueError("fundamentals manifest must define tracks as a list")
    if runner is None:
        runner = _run_analyze

    evaluated = 0
    skipped = 0
    failed_subprocess = 0
    passed_checks = 0
    failed_checks = 0
    informational_checks = 0
    track_reports: list[dict[str, Any]] = []

    for raw_track in tracks:
        if not isinstance(raw_track, dict):
            continue
        result = _evaluate_track(raw_track, tracks_dir, runner)
        if result.status == "evaluated":
            evaluated += 1
            passed_checks += sum(1 for check in result.checks if check.passed and not check.informational)
            failed_checks += sum(1 for check in result.checks if not check.passed and not check.informational)
            informational_checks += sum(1 for check in result.checks if check.informational)
        elif result.status == "skipped_audio_missing":
            skipped += 1
        else:
            failed_subprocess += 1
            failed_checks += 1
        track_reports.append(_track_result_to_report(result))

    summary = {
        "tracks": len(track_reports),
        "tracksEvaluated": evaluated,
        "tracksSkipped": skipped,
        "tracksAnalyzeFailed": failed_subprocess,
        "checksPassed": passed_checks,
        "checksFailed": failed_checks,
        "checksInformational": informational_checks,
        "failOnSkip": fail_on_skip,
        "allPassed": failed_checks == 0 and (not fail_on_skip or skipped == 0),
    }
    report: dict[str, Any] = {
        "schemaVersion": "fundamentals-eval-report.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "manifestPath": str(manifest_path),
        "tracksDir": str(tracks_dir),
        "targetProfile": manifest.get("targetProfile", "electronic_ableton_v1"),
        "gates": manifest.get("gates", {}),
        "tracks": track_reports,
        "summary": summary,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report


def _evaluate_track(raw: dict[str, Any], tracks_dir: Path, runner: Runner) -> FundamentalsTrackResult:
    track_id = str(raw.get("id") or "unknown")
    audio_rel = str(raw.get("audioPath") or "")
    category = str(raw.get("category") or "uncategorized")
    description = str(raw.get("description") or "")
    expected = raw.get("expected") if isinstance(raw.get("expected"), dict) else {}
    thresholds = raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else {}
    flags = raw.get("analyzeFlags")
    analyze_flags = [str(flag) for flag in flags] if isinstance(flags, list) else None
    raw_gaps = raw.get("knownGaps")
    known_gaps = {str(name) for name in raw_gaps} if isinstance(raw_gaps, list) else set()

    if not audio_rel:
        return FundamentalsTrackResult(
            track_id,
            "",
            category,
            description,
            "skipped_audio_missing",
            "manifest entry has no audioPath",
            [],
            True,
        )

    audio_path = (tracks_dir / audio_rel).resolve()
    if not audio_path.exists():
        return FundamentalsTrackResult(
            track_id,
            str(audio_path),
            category,
            description,
            "skipped_audio_missing",
            f"audio not present at {audio_path}; add the local file to activate this gate",
            [],
            True,
        )

    try:
        payload = runner(audio_path, analyze_flags)
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or "")[-400:]
        return FundamentalsTrackResult(
            track_id,
            str(audio_path),
            category,
            description,
            "skipped_analyze_failed",
            f"analyze.py failed (exit {exc.returncode}): {stderr_tail}",
            [],
            False,
        )

    checks = _evaluate_expected(payload, expected, thresholds)
    for check in checks:
        if check.name in known_gaps:
            check.informational = True
    return FundamentalsTrackResult(
        track_id,
        str(audio_path),
        category,
        description,
        "evaluated",
        None,
        checks,
        all(check.passed for check in checks if not check.informational),
    )


def _evaluate_expected(
    payload: dict[str, Any],
    expected: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[FundamentalsCheck]:
    checks: list[FundamentalsCheck] = []
    bpm = expected.get("bpm")
    if isinstance(bpm, (int, float)):
        tolerance = float(thresholds.get("bpmTolerance", 1.0))
        actual = _number(payload.get("bpm"))
        passed = actual is not None and abs(actual - float(bpm)) <= tolerance
        checks.append(FundamentalsCheck(
            "tempo:bpm",
            passed,
            f"target={bpm} tolerance={tolerance} actual={actual}",
        ))

    key = expected.get("key")
    if isinstance(key, str) and key.strip():
        actual_key = payload.get("key") if isinstance(payload.get("key"), str) else None
        allow_relative = thresholds.get("allowRelativeMajorMinor") is True
        passed = _keys_match(actual_key, key, allow_relative=allow_relative)
        checks.append(FundamentalsCheck(
            "key:label",
            passed,
            f"expected={key} actual={actual_key} allowRelativeMajorMinor={allow_relative}",
        ))

    meter = expected.get("timeSignature")
    if isinstance(meter, str) and meter.strip():
        actual_meter = payload.get("timeSignature") if isinstance(payload.get("timeSignature"), str) else None
        passed = _normalize_meter(actual_meter) == _normalize_meter(meter)
        checks.append(FundamentalsCheck(
            "meter:timeSignature",
            passed,
            f"expected={meter} actual={actual_meter}",
        ))

    if isinstance(expected.get("beatGrid"), list):
        threshold = float(thresholds.get("beatF1", 0.9))
        actual = _nested_list(payload, "rhythmDetail.beatGrid")
        f1 = _event_f1(actual, expected["beatGrid"], tolerance_seconds=float(thresholds.get("beatToleranceSeconds", 0.07)))
        checks.append(FundamentalsCheck(
            "beatGrid:f1",
            f1 >= threshold,
            f"target>={threshold} actual={round(f1, 4)}",
        ))

    if isinstance(expected.get("downbeats"), list):
        threshold = float(thresholds.get("downbeatF1", 0.75))
        actual = _nested_list(payload, "rhythmDetail.downbeats")
        f1 = _event_f1(actual, expected["downbeats"], tolerance_seconds=float(thresholds.get("downbeatToleranceSeconds", 0.1)))
        checks.append(FundamentalsCheck(
            "downbeats:f1",
            f1 >= threshold,
            f"target>={threshold} actual={round(f1, 4)}",
        ))

    if isinstance(expected.get("chordTimeline"), list):
        threshold = float(thresholds.get("chordSegmentAccuracy", 0.65))
        actual = _nested_list(payload, "chordDetail.chordTimeline")
        score = _chord_segment_accuracy(actual, expected["chordTimeline"])
        checks.append(FundamentalsCheck(
            "chords:segmentAccuracy",
            score >= threshold,
            f"target>={threshold} actual={round(score, 4)}",
        ))

    swing = expected.get("swingPercent")
    if isinstance(swing, (int, float)):
        tolerance = float(thresholds.get("swingTolerance", 3.0))
        actual = _number(_nested_value(payload, "rhythmDetail.swingDetail.swingPercent"))
        passed = actual is not None and abs(actual - float(swing)) <= tolerance
        checks.append(FundamentalsCheck(
            "swing:swingPercent",
            passed,
            f"target={swing} tolerance={tolerance} actual={actual}",
        ))

    percussion = expected.get("percussion")
    if isinstance(percussion, dict):
        checks.extend(_evaluate_percussion_counts(payload, percussion, thresholds))

    transcription_notes = expected.get("transcriptionNotes")
    if isinstance(transcription_notes, list):
        threshold = float(thresholds.get("transcriptionNoteF1", 0.75))
        actual = _nested_list(payload, "transcriptionDetail.notes")
        f1 = _note_f1(actual, transcription_notes)
        checks.append(FundamentalsCheck(
            "transcription:noteF1",
            f1 >= threshold,
            f"target>={threshold} actual={round(f1, 4)}",
        ))

    required_quality = thresholds.get("requiredQuality")
    if isinstance(required_quality, dict):
        checks.extend(_evaluate_required_quality(payload, required_quality))

    return checks


def _evaluate_percussion_counts(
    payload: dict[str, Any],
    percussion: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[FundamentalsCheck]:
    checks: list[FundamentalsCheck] = []
    count_specs = [
        ("kick", "kickDetail.kickCount"),
        ("snare", "snareDetail.hitCount"),
        ("hihat", "hihatDetail.hitCount"),
    ]
    tolerance = int(thresholds.get("percussionCountTolerance", 1))
    for label, path in count_specs:
        expected_count = percussion.get(f"{label}Count")
        if not isinstance(expected_count, int):
            continue
        actual_count = _number(_nested_value(payload, path))
        passed = actual_count is not None and abs(int(actual_count) - expected_count) <= tolerance
        checks.append(FundamentalsCheck(
            f"percussion:{label}Count",
            passed,
            f"expected={expected_count} tolerance={tolerance} actual={actual_count}",
        ))
    return checks


def _evaluate_required_quality(
    payload: dict[str, Any],
    required_quality: dict[str, Any],
) -> list[FundamentalsCheck]:
    checks: list[FundamentalsCheck] = []
    for domain, requirement in required_quality.items():
        actual = _nested_value(payload, f"fundamentalsQuality.domains.{domain}.status")
        if isinstance(requirement, list):
            allowed = [str(value) for value in requirement]
            passed = str(actual) in allowed
            message = f"allowed={allowed} actual={actual}"
        else:
            expected = str(requirement)
            passed = _status_rank(str(actual)) >= _status_rank(expected)
            message = f"minimum={expected} actual={actual}"
        checks.append(FundamentalsCheck(f"quality:{domain}", passed, message))
    return checks


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


def _track_result_to_report(result: FundamentalsTrackResult) -> dict[str, Any]:
    return {
        "id": result.track_id,
        "audioPath": result.audio_path,
        "category": result.category,
        "description": result.description,
        "status": result.status,
        "skipReason": result.skip_reason,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "message": check.message,
                "informational": check.informational,
            }
            for check in result.checks
        ],
        "allPassed": result.all_passed,
    }


def _nested_value(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _nested_list(payload: dict[str, Any], dotted_path: str) -> list[Any]:
    value = _nested_value(payload, dotted_path)
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _normalize_meter(value: str | None) -> str:
    return (value or "").strip().replace(" ", "").lower()


def _normalize_key(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    normalized = re.sub(r"\bmaj\b", "major", normalized)
    normalized = re.sub(r"\bmin\b", "minor", normalized)
    return re.sub(r"\s+", " ", normalized)


# Enharmonic-aware note-name → pitch-class map. KeyExtractor prefers sharp
# spellings ("C# Minor") while the Viterbi chord vocab and generated fixtures
# use flats ("Db"), so all key/chord comparisons fold to pitch classes.
_NOTE_TO_PC = {
    "cb": 11, "c": 0, "c#": 1, "db": 1, "d": 2, "d#": 3, "eb": 3,
    "e": 4, "e#": 5, "fb": 4, "f": 5, "f#": 6, "gb": 6, "g": 7,
    "g#": 8, "ab": 8, "a": 9, "a#": 10, "bb": 10, "b": 11, "b#": 0,
}


def _parse_key_pc(value: str | None) -> tuple[int, str] | None:
    parts = _normalize_key(value).split()
    if not parts:
        return None
    pc = _NOTE_TO_PC.get(parts[0])
    if pc is None:
        return None
    mode = parts[1] if len(parts) > 1 else "major"
    return pc, mode


def _keys_match(actual: str | None, expected: str, *, allow_relative: bool) -> bool:
    actual_pc = _parse_key_pc(actual)
    expected_pc = _parse_key_pc(expected)
    if actual_pc is None or expected_pc is None:
        return _normalize_key(actual) == _normalize_key(expected)
    if actual_pc == expected_pc:
        return True
    if not allow_relative:
        return False
    return _relative_of(actual_pc) == expected_pc or _relative_of(expected_pc) == actual_pc


def _relative_of(key: tuple[int, str]) -> tuple[int, str] | None:
    pc, mode = key
    if mode == "minor":
        return (pc + 3) % 12, "major"
    if mode == "major":
        return (pc + 9) % 12, "minor"
    return None


def _event_f1(actual: list[Any], expected: list[Any], *, tolerance_seconds: float) -> float:
    actual_times = [float(value) for value in actual if isinstance(value, (int, float))]
    expected_times = [float(value) for value in expected if isinstance(value, (int, float))]
    if not actual_times and not expected_times:
        return 1.0
    if not actual_times or not expected_times:
        return 0.0
    used: set[int] = set()
    matches = 0
    for expected_time in expected_times:
        for index, actual_time in enumerate(actual_times):
            if index in used:
                continue
            if abs(actual_time - expected_time) <= tolerance_seconds:
                used.add(index)
                matches += 1
                break
    precision = matches / len(actual_times) if actual_times else 0.0
    recall = matches / len(expected_times) if expected_times else 0.0
    return _f1(precision, recall)


def _chord_segment_accuracy(actual: list[Any], expected: list[Any]) -> float:
    expected_segments = [entry for entry in expected if isinstance(entry, dict)]
    actual_segments = [entry for entry in actual if isinstance(entry, dict)]
    if not expected_segments and not actual_segments:
        return 1.0
    if not expected_segments or not actual_segments:
        return 0.0
    total_duration = 0.0
    matching_duration = 0.0
    for expected_segment in expected_segments:
        start = _number(expected_segment.get("startSec"))
        end = _number(expected_segment.get("endSec"))
        label = str(expected_segment.get("label") or "")
        if start is None or end is None or end <= start:
            continue
        total_duration += end - start
        for actual_segment in actual_segments:
            actual_start = _number(actual_segment.get("startSec"))
            actual_end = _number(actual_segment.get("endSec"))
            actual_label = str(actual_segment.get("label") or "")
            if actual_start is None or actual_end is None:
                continue
            overlap = max(0.0, min(end, actual_end) - max(start, actual_start))
            if (
                overlap > 0.0
                and _normalize_chord_label(actual_label) == _normalize_chord_label(label)
            ):
                matching_duration += overlap
    return matching_duration / total_duration if total_duration > 0 else 0.0


def _normalize_chord_label(label: str | None) -> str:
    """Fold a triad label to a canonical pitch-class form ("9m", "1", "N").

    Enharmonic-aware (Db == C#) because the Viterbi vocab spells flats while
    generated fixtures or hand labels may spell sharps. Named differently from
    analyze_segments._normalize_chord_label_for_compare, which serves the
    chordTimelineAgreement comparison and has its own rules.
    """
    value = (label or "").strip()
    value = re.sub(r"\s+", "", value)
    value = value.replace(":maj", "").replace(":min", "m")
    value = re.sub(r"(?i)major$", "", value)
    value = re.sub(r"(?i)minor$", "m", value)
    if not value:
        return ""
    if value.upper() == "N":
        return "N"
    is_minor = value.endswith("m")
    root = value[:-1] if is_minor else value
    pc = _NOTE_TO_PC.get(root.lower())
    if pc is None:
        return value.lower()
    return f"{pc}{'m' if is_minor else ''}"


def _note_f1(actual: list[Any], expected: list[Any]) -> float:
    actual_notes = [entry for entry in actual if isinstance(entry, dict)]
    expected_notes = [entry for entry in expected if isinstance(entry, dict)]
    if not actual_notes and not expected_notes:
        return 1.0
    if not actual_notes or not expected_notes:
        return 0.0
    used: set[int] = set()
    matches = 0
    for expected_note in expected_notes:
        expected_onset = _number(expected_note.get("onsetSeconds"))
        expected_pitch = _number(expected_note.get("pitchMidi"))
        if expected_onset is None or expected_pitch is None:
            continue
        for index, actual_note in enumerate(actual_notes):
            if index in used:
                continue
            actual_onset = _number(actual_note.get("onsetSeconds"))
            actual_pitch = _number(actual_note.get("pitchMidi"))
            if actual_onset is None or actual_pitch is None:
                continue
            if abs(actual_onset - expected_onset) <= 0.05 and abs(actual_pitch - expected_pitch) <= 1:
                used.add(index)
                matches += 1
                break
    precision = matches / len(actual_notes) if actual_notes else 0.0
    recall = matches / len(expected_notes) if expected_notes else 0.0
    return _f1(precision, recall)


def _f1(precision: float, recall: float) -> float:
    return 0.0 if precision + recall == 0 else (2.0 * precision * recall) / (precision + recall)


def _status_rank(status: str) -> int:
    return STATUS_RANK.get(status, -1)
