"""Offline evaluation harness for polyphonic full-track transcription experiments.

This module is intentionally separate from analyze.py and server.py.
It exists to compare research candidates such as Basic Pitch and MT3 on a fixed
corpus without turning them into product backends.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pretty_midi
import soundfile as sf

REPO_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = REPO_DIR / ".runtime" / "polyphonic_eval"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "polyphonic_eval_report.json"
MAX_LOG_CHARS = 2000
MANUAL_SCORECARD_TEMPLATE = {
    "bassRecognizable": None,
    "toplineRecognizable": None,
    "chordsNotObviouslyWrong": None,
    "cleanupMinutes30s": None,
    "notes": "",
}

CandidateRunner = Callable[[str, Path, Path], dict[str, Any]]


def midi_to_note_name(midi_num: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    clamped = max(0, min(127, int(round(midi_num))))
    octave = (clamped // 12) - 1
    return f"{names[clamped % 12]}{octave}"


def build_manual_scorecard(existing: dict[str, Any] | None = None) -> dict[str, Any]:
    scorecard = dict(MANUAL_SCORECARD_TEMPLATE)
    if not isinstance(existing, dict):
        return scorecard
    for key in scorecard:
        if key in existing:
            scorecard[key] = existing[key]
    return scorecard


def summarize_midi_file(midi_path: Path, audio_duration_seconds: float) -> dict[str, Any]:
    midi_data = pretty_midi.PrettyMIDI(str(midi_path))
    notes = [note for instrument in midi_data.instruments for note in instrument.notes]
    if len(notes) == 0:
        return {
            "noteCount": 0,
            "distinctPitchCount": 0,
            "pitchRange": None,
            "maxPolyphony": 0,
            "meanTimelinePolyphony": 0.0,
            "meanActivePolyphony": 0.0,
            "averageNoteDurationSeconds": 0.0,
            "noteDensityPerSecond": 0.0,
            "flags": ["empty_output"],
        }

    total_note_duration = 0.0
    pitch_values: list[int] = []
    events: list[tuple[float, int]] = []
    for note in notes:
        duration = max(0.0, float(note.end) - float(note.start))
        total_note_duration += duration
        pitch_values.append(int(note.pitch))
        events.append((float(note.start), 1))
        events.append((float(note.end), -1))

    events.sort(key=lambda item: (item[0], item[1]))
    max_polyphony = 0
    active_notes = 0
    previous_time = 0.0
    active_time = 0.0
    weighted_active_polyphony = 0.0
    weighted_timeline_polyphony = 0.0

    for event_time, delta in events:
        if event_time > previous_time:
            interval = event_time - previous_time
            weighted_timeline_polyphony += active_notes * interval
            if active_notes > 0:
                active_time += interval
                weighted_active_polyphony += active_notes * interval
            previous_time = event_time
        active_notes = max(0, active_notes + delta)
        max_polyphony = max(max_polyphony, active_notes)

    duration_denominator = max(float(audio_duration_seconds), 1e-9)
    note_count = len(notes)
    note_density = note_count / duration_denominator
    flags: list[str] = []
    if max_polyphony <= 1:
        flags.append("monophonic_output")
    if note_density >= 12.0:
        flags.append("high_note_density")

    min_pitch = min(pitch_values)
    max_pitch = max(pitch_values)
    return {
        "noteCount": note_count,
        "distinctPitchCount": len(set(pitch_values)),
        "pitchRange": {
            "minMidi": min_pitch,
            "maxMidi": max_pitch,
            "minName": midi_to_note_name(min_pitch),
            "maxName": midi_to_note_name(max_pitch),
        },
        "maxPolyphony": max_polyphony,
        "meanTimelinePolyphony": round(weighted_timeline_polyphony / duration_denominator, 4),
        "meanActivePolyphony": round(
            weighted_active_polyphony / max(active_time, 1e-9),
            4,
        ),
        "averageNoteDurationSeconds": round(total_note_duration / note_count, 4),
        "noteDensityPerSecond": round(note_density, 4),
        "flags": flags,
    }


def summarize_candidate_gate(
    candidate_reports: list[dict[str, Any]],
    baseline_runtime_ms: float | None = None,
) -> dict[str, Any]:
    completed = [report for report in candidate_reports if report.get("status") == "completed"]
    runtime_values = [
        float(report["runtimeMs"])
        for report in completed
        if isinstance(report.get("runtimeMs"), (int, float))
    ]

    def _bool_rate(field: str) -> float | None:
        values = [
            report["scorecard"][field]
            for report in completed
            if isinstance(report.get("scorecard"), dict)
            and isinstance(report["scorecard"].get(field), bool)
        ]
        if len(values) == 0:
            return None
        return round(sum(1 for value in values if value) / len(values), 4)

    cleanup_values = [
        float(report["scorecard"]["cleanupMinutes30s"])
        for report in completed
        if isinstance(report.get("scorecard"), dict)
        and isinstance(report["scorecard"].get("cleanupMinutes30s"), (int, float))
    ]

    average_runtime_ms = (
        round(sum(runtime_values) / len(runtime_values), 2) if len(runtime_values) > 0 else None
    )
    runtime_ratio = None
    if average_runtime_ms is not None and isinstance(baseline_runtime_ms, (int, float)) and baseline_runtime_ms > 0:
        runtime_ratio = round(average_runtime_ms / float(baseline_runtime_ms), 4)

    bass_rate = _bool_rate("bassRecognizable")
    topline_rate = _bool_rate("toplineRecognizable")
    chord_rate = _bool_rate("chordsNotObviouslyWrong")
    average_cleanup_minutes = (
        round(sum(cleanup_values) / len(cleanup_values), 2) if len(cleanup_values) > 0 else None
    )

    gates = {
        "bassRecognizableAtLeast80Percent": None if bass_rate is None else bass_rate >= 0.8,
        "toplineRecognizableAtLeast80Percent": None if topline_rate is None else topline_rate >= 0.8,
        "chordsNotObviouslyWrongAtLeast80Percent": None if chord_rate is None else chord_rate >= 0.8,
        "averageCleanupWithinFiveMinutes": None
        if average_cleanup_minutes is None
        else average_cleanup_minutes <= 5.0,
        "runtimeWithinTwoTimesStemAwareBaseline": None
        if runtime_ratio is None
        else runtime_ratio <= 2.0,
    }

    reviewed_clip_count = sum(
        1
        for report in completed
        if isinstance(report.get("scorecard"), dict)
        and any(
            report["scorecard"].get(field) is not None
            for field in (
                "bassRecognizable",
                "toplineRecognizable",
                "chordsNotObviouslyWrong",
                "cleanupMinutes30s",
            )
        )
    )
    ready_to_reopen = len(gates) > 0 and all(value is True for value in gates.values())
    return {
        "clipsCompleted": len(completed),
        "clipsReviewed": reviewed_clip_count,
        "averageRuntimeMs": average_runtime_ms,
        "runtimeVsStemAwareBaseline": runtime_ratio,
        "bassRecognizableRate": bass_rate,
        "toplineRecognizableRate": topline_rate,
        "chordsNotObviouslyWrongRate": chord_rate,
        "averageCleanupMinutes30s": average_cleanup_minutes,
        "successCriteria": gates,
        "readyToReopenProductization": ready_to_reopen,
        "status": "ready_to_reopen" if ready_to_reopen else "research_only",
    }


def _truncate_log(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if len(trimmed) <= MAX_LOG_CHARS:
        return trimmed or None
    return trimmed[-MAX_LOG_CHARS:]


def _resolve_audio_path(manifest_path: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    manifest_relative = (manifest_path.parent / candidate).resolve()
    if manifest_relative.exists():
        return manifest_relative
    return (REPO_DIR / candidate).resolve()


def _find_output_file(directory: Path, suffix: str) -> Path | None:
    matches = sorted(directory.rglob(f"*{suffix}"))
    if len(matches) == 0:
        return None
    return matches[0]


def _resolve_basic_pitch_executable() -> Path | None:
    local_binary = Path(sys.executable).resolve().parent / "basic-pitch"
    if local_binary.exists():
        return local_binary
    discovered = shutil.which("basic-pitch")
    return Path(discovered) if discovered else None


def _build_basic_pitch_runner(timeout_seconds: int) -> CandidateRunner:
    def _runner(clip_id: str, audio_path: Path, output_dir: Path) -> dict[str, Any]:
        executable = _resolve_basic_pitch_executable()
        if executable is None:
            return {
                "status": "skipped",
                "reason": "basic-pitch is not installed in the active environment.",
            }

        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            str(executable),
            str(output_dir),
            str(audio_path),
            "--save-note-events",
        ]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "reason": f"basic-pitch timed out after {timeout_seconds} seconds.",
            }

        runtime_ms = round((time.perf_counter() - started) * 1000.0, 2)
        if completed.returncode != 0:
            return {
                "status": "failed",
                "reason": f"basic-pitch exited with code {completed.returncode}.",
                "runtimeMs": runtime_ms,
                "stdoutTail": _truncate_log(completed.stdout),
                "stderrTail": _truncate_log(completed.stderr),
                "command": command,
            }

        midi_path = _find_output_file(output_dir, ".mid")
        note_events_path = _find_output_file(output_dir, ".csv")
        if midi_path is None:
            return {
                "status": "failed",
                "reason": "basic-pitch completed but did not produce a MIDI file.",
                "runtimeMs": runtime_ms,
                "stdoutTail": _truncate_log(completed.stdout),
                "stderrTail": _truncate_log(completed.stderr),
                "command": command,
            }

        return {
            "status": "completed",
            "runtimeMs": runtime_ms,
            "midiPath": str(midi_path),
            "noteEventsPath": str(note_events_path) if note_events_path else None,
            "stdoutTail": _truncate_log(completed.stdout),
            "stderrTail": _truncate_log(completed.stderr),
            "command": command,
            "clipId": clip_id,
        }

    return _runner


def _build_mt3_runner(command_template: str, timeout_seconds: int) -> CandidateRunner:
    def _runner(clip_id: str, audio_path: Path, output_dir: Path) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        expected_midi_path = output_dir / f"{clip_id}.mid"
        rendered_command = command_template.format(
            audio_path=shlex.quote(str(audio_path)),
            output_dir=shlex.quote(str(output_dir)),
            midi_path=shlex.quote(str(expected_midi_path)),
            clip_id=shlex.quote(clip_id),
        )

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                rendered_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "reason": f"MT3 command timed out after {timeout_seconds} seconds.",
                "command": rendered_command,
            }

        runtime_ms = round((time.perf_counter() - started) * 1000.0, 2)
        if completed.returncode != 0:
            return {
                "status": "failed",
                "reason": f"MT3 command exited with code {completed.returncode}.",
                "runtimeMs": runtime_ms,
                "stdoutTail": _truncate_log(completed.stdout),
                "stderrTail": _truncate_log(completed.stderr),
                "command": rendered_command,
            }

        midi_path = expected_midi_path if expected_midi_path.exists() else _find_output_file(output_dir, ".mid")
        note_events_path = _find_output_file(output_dir, ".csv")
        if midi_path is None:
            return {
                "status": "failed",
                "reason": "MT3 command completed but no MIDI file was found in the output directory.",
                "runtimeMs": runtime_ms,
                "stdoutTail": _truncate_log(completed.stdout),
                "stderrTail": _truncate_log(completed.stderr),
                "command": rendered_command,
            }

        return {
            "status": "completed",
            "runtimeMs": runtime_ms,
            "midiPath": str(midi_path),
            "noteEventsPath": str(note_events_path) if note_events_path else None,
            "stdoutTail": _truncate_log(completed.stdout),
            "stderrTail": _truncate_log(completed.stderr),
            "command": rendered_command,
            "clipId": clip_id,
        }

    return _runner


def _build_candidate_runners(
    *,
    mt3_command: str | None,
    timeout_seconds: int,
) -> dict[str, CandidateRunner]:
    runners: dict[str, CandidateRunner] = {
        "basic-pitch": _build_basic_pitch_runner(timeout_seconds),
    }
    if mt3_command:
        runners["mt3"] = _build_mt3_runner(mt3_command, timeout_seconds)
    return runners


def _maybe_generate_demucs_diagnostics(audio_path: Path, output_dir: Path) -> dict[str, Any]:
    try:
        if str(REPO_DIR) not in sys.path:
            sys.path.insert(0, str(REPO_DIR))
        from analyze import separate_stems  # pylint: disable=import-outside-toplevel
    except Exception as exc:  # pragma: no cover - import path depends on local env
        return {
            "status": "failed",
            "reason": f"Could not import analyze.separate_stems: {exc}",
        }

    stem_output_dir = output_dir / "demucs_stems"
    try:
        stem_paths = separate_stems(str(audio_path), output_dir=str(stem_output_dir))
    except Exception as exc:  # pragma: no cover - depends on torchaudio model setup
        return {
            "status": "failed",
            "reason": f"Demucs diagnostics failed: {exc}",
        }

    if not isinstance(stem_paths, dict) or len(stem_paths) == 0:
        return {
            "status": "failed",
            "reason": "Demucs diagnostics completed without producing any stems.",
        }

    return {
        "status": "completed",
        "stems": {name: str(path) for name, path in stem_paths.items()},
    }


def run_polyphonic_evaluation(
    *,
    manifest_path: Path,
    report_path: Path = DEFAULT_REPORT_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    mt3_command: str | None = None,
    save_demucs_diagnostics: bool = False,
    runner_timeout_seconds: int = 600,
    candidate_runners: dict[str, CandidateRunner] | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clips = manifest.get("clips")
    if not isinstance(clips, list) or len(clips) == 0:
        raise ValueError("Polyphonic evaluation manifest must define one or more clips.")

    baseline_runtime_ms = manifest.get("currentStemAwareAverageRuntimeMs")
    if baseline_runtime_ms is not None and not isinstance(baseline_runtime_ms, (int, float)):
        raise ValueError("currentStemAwareAverageRuntimeMs must be numeric when provided.")

    runners = candidate_runners or _build_candidate_runners(
        mt3_command=mt3_command,
        timeout_seconds=runner_timeout_seconds,
    )
    if len(runners) == 0:
        raise ValueError("Polyphonic evaluation requires at least one enabled candidate runner.")

    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_reports: dict[str, list[dict[str, Any]]] = {name: [] for name in runners}
    clip_reports: list[dict[str, Any]] = []

    for clip in clips:
        if not isinstance(clip, dict):
            raise ValueError("Each manifest clip entry must be an object.")
        audio_path_value = clip.get("audioPath")
        if not isinstance(audio_path_value, str) or not audio_path_value.strip():
            raise ValueError("Each clip must provide a non-empty audioPath.")

        clip_id = str(clip.get("id") or Path(audio_path_value).stem)
        audio_path = _resolve_audio_path(manifest_path, audio_path_value)
        if not audio_path.exists():
            raise FileNotFoundError(f"Clip '{clip_id}' audio file does not exist: {audio_path}")

        clip_output_dir = output_dir / clip_id
        clip_output_dir.mkdir(parents=True, exist_ok=True)
        audio_info = sf.info(str(audio_path))
        audio_duration_seconds = round(
            float(audio_info.frames) / float(audio_info.samplerate),
            4,
        )
        clip_report = {
            "id": clip_id,
            "audioPath": str(audio_path),
            "audioDurationSeconds": audio_duration_seconds,
            "tags": clip.get("tags", []),
            "notes": clip.get("notes"),
            "candidates": {},
            "diagnostics": {},
        }

        if save_demucs_diagnostics:
            clip_report["diagnostics"]["demucs"] = _maybe_generate_demucs_diagnostics(
                audio_path,
                clip_output_dir,
            )

        manual_review_by_candidate = clip.get("manualReviewByCandidate", {})
        if manual_review_by_candidate is not None and not isinstance(manual_review_by_candidate, dict):
            raise ValueError("manualReviewByCandidate must be an object when provided.")

        for candidate_id, runner in runners.items():
            candidate_output_dir = clip_output_dir / candidate_id.replace("-", "_")
            result = runner(clip_id, audio_path, candidate_output_dir)
            scorecard = build_manual_scorecard(
                manual_review_by_candidate.get(candidate_id)
                if isinstance(manual_review_by_candidate, dict)
                else None
            )
            candidate_report = {
                "candidateId": candidate_id,
                **result,
                "scorecard": scorecard,
            }

            midi_path_value = result.get("midiPath")
            if result.get("status") == "completed" and isinstance(midi_path_value, str):
                candidate_report["metrics"] = summarize_midi_file(
                    Path(midi_path_value),
                    audio_duration_seconds,
                )
            else:
                candidate_report["metrics"] = None

            clip_report["candidates"][candidate_id] = candidate_report
            candidate_reports[candidate_id].append(candidate_report)

        clip_reports.append(clip_report)

    candidate_summaries = {
        candidate_id: summarize_candidate_gate(reports, baseline_runtime_ms)
        for candidate_id, reports in candidate_reports.items()
    }
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "manifestPath": str(manifest_path),
        "outputDir": str(output_dir),
        "baseline": {
            "currentStemAwareAverageRuntimeMs": baseline_runtime_ms,
        },
        "clips": clip_reports,
        "candidateSummaries": candidate_summaries,
        "summary": {
            "clipCount": len(clip_reports),
            "candidateCount": len(candidate_summaries),
            "researchOnly": True,
            "productRecommendation": (
                "Do not productize polyphonic full-track detection unless a candidate clears the manual usefulness gates on the target corpus."
            ),
        },
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report
