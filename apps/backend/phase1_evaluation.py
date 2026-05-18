"""Phase 1 evaluation harness for deterministic metrics and detector stability."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

REPO_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = REPO_DIR / "tests" / "fixtures" / "phase1_eval_manifest.json"
DEFAULT_REPORT_PATH = REPO_DIR / ".runtime" / "reports" / "phase1_eval_report.json"
DEFAULT_BENCH_TRACKS_DIR = REPO_DIR / "tests" / "fixtures" / "bench_tracks"
DEFAULT_TRANSCRIPTION_TRACKS_DIR = REPO_DIR / "tests" / "fixtures" / "transcription_tracks"
EXPECTED_SPECTRAL_KEYS = {
    "subBass",
    "lowBass",
    "lowMids",
    "mids",
    "upperMids",
    "highs",
    "brilliance",
}


@dataclass
class FixtureCheck:
    name: str
    passed: bool
    message: str


@dataclass
class RealTrackResult:
    track_id: str
    audio_path: str
    category: str
    description: str
    status: str  # "evaluated" | "skipped_audio_missing" | "skipped_analyze_failed"
    skip_reason: str | None
    checks: list[FixtureCheck]
    all_passed: bool


@dataclass
class TranscriptionTrackResult:
    track_id: str
    audio_path: str
    category: str
    description: str
    status: str  # "evaluated" | "skipped_audio_missing" | "skipped_analyze_failed" | "skipped_no_transcription"
    skip_reason: str | None
    checks: list[FixtureCheck]
    note_metrics: dict[str, Any] | None
    all_passed: bool


def _write_stereo_wav(path: Path, mono: np.ndarray, sample_rate: int) -> None:
    mono_arr = np.asarray(mono, dtype=np.float32)
    stereo = np.stack([mono_arr, mono_arr], axis=1)
    pcm = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def _generate_fixture_audio(generator: dict[str, Any]) -> tuple[np.ndarray, int]:
    fixture_type = str(generator.get("type", "")).strip().lower()
    sample_rate = int(generator.get("sampleRate", 44_100))
    duration_seconds = float(generator.get("durationSeconds", 8.0))
    total_samples = int(round(duration_seconds * sample_rate))
    if total_samples <= 0:
        raise ValueError("Fixture durationSeconds must be positive.")

    if fixture_type == "sine":
        frequency_hz = float(generator.get("frequencyHz", 220.0))
        amplitude = float(generator.get("amplitude", 0.5))
        time_axis = np.linspace(
            0.0, duration_seconds, total_samples, endpoint=False, dtype=np.float32
        )
        mono = amplitude * np.sin(2.0 * np.pi * frequency_hz * time_axis)
        return mono.astype(np.float32), sample_rate

    if fixture_type == "click_track":
        bpm = float(generator.get("bpm", 120.0))
        click_ms = float(generator.get("clickMs", 10.0))
        amplitude = float(generator.get("amplitude", 0.9))
        beat_interval = int(round(sample_rate * 60.0 / bpm))
        click_samples = max(8, int(round(sample_rate * click_ms / 1000.0)))
        click_shape = np.hanning(click_samples).astype(np.float32) * amplitude

        mono = np.zeros(total_samples, dtype=np.float32)
        for start in range(0, total_samples, beat_interval):
            stop = min(total_samples, start + click_samples)
            mono[start:stop] += click_shape[: stop - start]
        return np.clip(mono, -1.0, 1.0), sample_rate

    raise ValueError(f"Unsupported fixture generator type '{fixture_type}'.")


def _run_analyze(audio_path: Path, extra_flags: list[str] | None = None) -> dict[str, Any]:
    command = [sys.executable, str(REPO_DIR / "analyze.py"), str(audio_path), "--yes"]
    if extra_flags:
        command.extend(extra_flags)
    completed = subprocess.run(
        command,
        cwd=REPO_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("analyze.py did not return a JSON object.")
    return payload


def _get_nested_value(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for key in dotted_path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _evaluate_threshold(
    payload: dict[str, Any],
    field: str,
    config: dict[str, Any],
) -> FixtureCheck:
    actual = _get_nested_value(payload, field)
    if "equals" in config:
        expected = config.get("equals")
        passed = actual == expected
        return FixtureCheck(
            name=f"threshold:{field}",
            passed=passed,
            message=f"expected={expected} actual={actual}",
        )

    target = float(config.get("target"))
    tolerance = float(config.get("tolerance", 0.0))
    direction = str(config.get("direction", "")).strip().lower()
    if not isinstance(actual, (int, float)):
        return FixtureCheck(
            name=f"threshold:{field}",
            passed=False,
            message=f"expected numeric target={target}±{tolerance}, actual={actual}",
        )
    actual_value = float(actual)
    if direction == "min":
        bound = target - tolerance
        passed = actual_value >= bound
        return FixtureCheck(
            name=f"threshold:{field}",
            passed=passed,
            message=f"target>={target} tolerance={tolerance} bound={round(bound, 6)} actual={actual}",
        )
    if direction == "max":
        bound = target + tolerance
        passed = actual_value <= bound
        return FixtureCheck(
            name=f"threshold:{field}",
            passed=passed,
            message=f"target<={target} tolerance={tolerance} bound={round(bound, 6)} actual={actual}",
        )
    delta = abs(actual_value - target)
    passed = delta <= tolerance
    return FixtureCheck(
        name=f"threshold:{field}",
        passed=passed,
        message=f"target={target} tolerance={tolerance} actual={actual} delta={round(delta, 6)}",
    )


def _evaluate_spectral_presence(payload: dict[str, Any]) -> FixtureCheck:
    spectral = payload.get("spectralBalance")
    if not isinstance(spectral, dict):
        return FixtureCheck(
            name="spectral:presence",
            passed=False,
            message="spectralBalance missing or not an object",
        )
    keys = set(spectral.keys())
    if keys != EXPECTED_SPECTRAL_KEYS:
        return FixtureCheck(
            name="spectral:presence",
            passed=False,
            message=f"expected keys={sorted(EXPECTED_SPECTRAL_KEYS)} actual={sorted(keys)}",
        )
    for key, value in spectral.items():
        if not isinstance(value, (int, float)) or not np.isfinite(float(value)):
            return FixtureCheck(
                name=f"spectral:{key}",
                passed=False,
                message=f"value is not finite numeric ({value})",
            )
    return FixtureCheck(
        name="spectral:presence",
        passed=True,
        message="all spectral bands present and finite",
    )


def _evaluate_plr_consistency(payload: dict[str, Any]) -> FixtureCheck:
    plr = payload.get("plr")
    true_peak = payload.get("truePeak")
    lufs = payload.get("lufsIntegrated")
    if not all(isinstance(v, (int, float)) for v in (plr, true_peak, lufs)):
        return FixtureCheck(
            name="plr:consistency",
            passed=False,
            message=f"non-numeric values plr={plr} truePeak={true_peak} lufsIntegrated={lufs}",
        )
    expected = float(true_peak) - float(lufs)
    delta = abs(float(plr) - expected)
    passed = delta <= 0.11
    return FixtureCheck(
        name="plr:consistency",
        passed=passed,
        message=f"plr={plr} expected={round(expected, 4)} delta={round(delta, 6)}",
    )


def _evaluate_real_track(
    entry: dict[str, Any],
    real_tracks_dir: Path,
) -> RealTrackResult:
    """Evaluate a single real-track entry from the manifest.

    Gracefully skips with a clear reason when the audio file is absent, so that
    a missing bench track never fails the run — opt-in real-track gate only
    surfaces failures when audio is present AND analyzer output disagrees with
    ground truth.
    """
    track_id = str(entry.get("id") or "unknown")
    audio_rel = str(entry.get("audioPath") or "")
    category = str(entry.get("category") or "uncategorized")
    description = str(entry.get("description") or "")
    thresholds = entry.get("thresholds")
    analyze_flags = entry.get("analyzeFlags")

    if not isinstance(thresholds, dict):
        thresholds = {}
    if isinstance(analyze_flags, list):
        flags_list = [str(flag) for flag in analyze_flags]
    else:
        flags_list = None

    if not audio_rel:
        return RealTrackResult(
            track_id=track_id,
            audio_path="",
            category=category,
            description=description,
            status="skipped_audio_missing",
            skip_reason="manifest entry has no audioPath",
            checks=[],
            all_passed=True,
        )

    audio_path = (real_tracks_dir / audio_rel).resolve()
    if not audio_path.exists():
        return RealTrackResult(
            track_id=track_id,
            audio_path=str(audio_path),
            category=category,
            description=description,
            status="skipped_audio_missing",
            skip_reason=(
                f"audio not present at {audio_path} — add the file locally to "
                "include this track in real-track evaluation"
            ),
            checks=[],
            all_passed=True,
        )

    try:
        payload = _run_analyze(audio_path, flags_list)
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or "")[-400:]
        return RealTrackResult(
            track_id=track_id,
            audio_path=str(audio_path),
            category=category,
            description=description,
            status="skipped_analyze_failed",
            skip_reason=f"analyze.py failed (exit {exc.returncode}): {stderr_tail}",
            checks=[],
            all_passed=False,
        )

    checks: list[FixtureCheck] = []
    for field, config in thresholds.items():
        if not isinstance(config, dict):
            continue
        checks.append(_evaluate_threshold(payload, field, config))

    return RealTrackResult(
        track_id=track_id,
        audio_path=str(audio_path),
        category=category,
        description=description,
        status="evaluated",
        skip_reason=None,
        checks=checks,
        all_passed=all(check.passed for check in checks),
    )


def _match_notes(
    detected: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    onset_window_s: float = 0.05,
    pitch_tolerance_semitones: int = 1,
) -> list[tuple[int, int]]:
    """Greedy onset-sorted matching of detected notes to ground-truth notes.

    For each ground-truth note (in onset order), pair with the earliest unused
    detected note whose onset is within ±onset_window_s AND whose pitch differs
    by no more than pitch_tolerance_semitones. Returns (gt_index, det_index)
    pairs. Mirrors mir_eval.transcription onset/pitch semantics.
    """
    gt_indices = sorted(
        range(len(ground_truth)),
        key=lambda i: float(ground_truth[i].get("onsetSeconds", 0.0)),
    )
    det_indices_sorted = sorted(
        range(len(detected)),
        key=lambda i: float(detected[i].get("onsetSeconds", 0.0)),
    )
    used: set[int] = set()
    matches: list[tuple[int, int]] = []
    for gt_idx in gt_indices:
        gt_onset = float(ground_truth[gt_idx].get("onsetSeconds", 0.0))
        gt_pitch = int(ground_truth[gt_idx].get("pitchMidi", 0))
        for det_idx in det_indices_sorted:
            if det_idx in used:
                continue
            det_onset = float(detected[det_idx].get("onsetSeconds", 0.0))
            if abs(det_onset - gt_onset) > onset_window_s:
                continue
            det_pitch = int(detected[det_idx].get("pitchMidi", 0))
            if abs(det_pitch - gt_pitch) > pitch_tolerance_semitones:
                continue
            used.add(det_idx)
            matches.append((gt_idx, det_idx))
            break
    return matches


def _compute_note_metrics(
    detected: list[dict[str, Any]],
    ground_truth: list[dict[str, Any]],
    matches: list[tuple[int, int]],
) -> dict[str, Any]:
    """Compute precision/recall/F1 and mean signed pitch error in cents.

    Note: pitchMidi is an integer per the analyze.py contract, so
    meanPitchCentsError is always a multiple of 100. This is a deliberate
    coarseness limit — switch to a sub-semitone-aware detector if finer
    pitch-accuracy reporting is needed.
    """
    matched_count = len(matches)
    detected_count = len(detected)
    gt_count = len(ground_truth)
    missed_count = gt_count - matched_count
    false_positive_count = detected_count - matched_count

    if detected_count == 0:
        precision = 1.0
    else:
        precision = matched_count / detected_count
    if gt_count == 0:
        recall = 1.0
    else:
        recall = matched_count / gt_count
    if precision + recall == 0.0:
        f1 = 0.0
    else:
        f1 = (2.0 * precision * recall) / (precision + recall)

    if matched_count == 0:
        mean_cents_error = 0.0
    else:
        cents_errors = [
            (int(detected[d].get("pitchMidi", 0)) - int(ground_truth[g].get("pitchMidi", 0))) * 100
            for g, d in matches
        ]
        mean_cents_error = sum(cents_errors) / float(matched_count)

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "meanPitchCentsError": round(mean_cents_error, 4),
        "matchedCount": matched_count,
        "missedCount": missed_count,
        "falsePositiveCount": false_positive_count,
    }


def _evaluate_transcription_track(
    entry: dict[str, Any],
    transcription_tracks_dir: Path,
    transcribe_runner: Any = None,
) -> TranscriptionTrackResult:
    """Evaluate a single transcription-track entry from the manifest.

    Mirrors `_evaluate_real_track` semantics — gracefully skips when the audio
    is absent so a missing track never fails the run. `transcribe_runner` is a
    callable `(audio_path, extra_flags) -> dict`; defaults to `_run_analyze`.
    """
    if transcribe_runner is None:
        transcribe_runner = _run_analyze

    track_id = str(entry.get("id") or "unknown")
    audio_rel = str(entry.get("audioPath") or "")
    category = str(entry.get("category") or "uncategorized")
    description = str(entry.get("description") or "")
    thresholds = entry.get("thresholds")
    analyze_flags = entry.get("analyzeFlags")
    ground_truth_notes = entry.get("groundTruthNotes")

    if not isinstance(thresholds, dict):
        thresholds = {}
    if isinstance(analyze_flags, list):
        flags_list = [str(flag) for flag in analyze_flags]
    else:
        flags_list = ["--transcribe"]
    if not isinstance(ground_truth_notes, list):
        ground_truth_notes = []

    if not audio_rel:
        return TranscriptionTrackResult(
            track_id=track_id,
            audio_path="",
            category=category,
            description=description,
            status="skipped_audio_missing",
            skip_reason="manifest entry has no audioPath",
            checks=[],
            note_metrics=None,
            all_passed=True,
        )

    audio_path = (transcription_tracks_dir / audio_rel).resolve()
    if not audio_path.exists():
        return TranscriptionTrackResult(
            track_id=track_id,
            audio_path=str(audio_path),
            category=category,
            description=description,
            status="skipped_audio_missing",
            skip_reason=(
                f"audio not present at {audio_path} — add the file locally to "
                "include this track in transcription evaluation"
            ),
            checks=[],
            note_metrics=None,
            all_passed=True,
        )

    try:
        payload = transcribe_runner(audio_path, flags_list)
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or "")[-400:]
        return TranscriptionTrackResult(
            track_id=track_id,
            audio_path=str(audio_path),
            category=category,
            description=description,
            status="skipped_analyze_failed",
            skip_reason=f"analyze.py failed (exit {exc.returncode}): {stderr_tail}",
            checks=[],
            note_metrics=None,
            all_passed=False,
        )

    transcription_detail = payload.get("transcriptionDetail") if isinstance(payload, dict) else None
    if not isinstance(transcription_detail, dict):
        return TranscriptionTrackResult(
            track_id=track_id,
            audio_path=str(audio_path),
            category=category,
            description=description,
            status="skipped_no_transcription",
            skip_reason="analyze.py output had no transcriptionDetail block",
            checks=[],
            note_metrics=None,
            all_passed=False,
        )

    detected_notes = transcription_detail.get("notes") or []
    if not isinstance(detected_notes, list):
        detected_notes = []
    matches = _match_notes(detected_notes, ground_truth_notes)
    note_metrics = _compute_note_metrics(detected_notes, ground_truth_notes, matches)

    eval_payload = dict(payload)
    eval_payload["noteMetrics"] = note_metrics

    checks: list[FixtureCheck] = []
    for field, config in thresholds.items():
        if not isinstance(config, dict):
            continue
        checks.append(_evaluate_threshold(eval_payload, field, config))

    return TranscriptionTrackResult(
        track_id=track_id,
        audio_path=str(audio_path),
        category=category,
        description=description,
        status="evaluated",
        skip_reason=None,
        checks=checks,
        note_metrics=note_metrics,
        all_passed=all(check.passed for check in checks),
    )


def _evaluate_stepped_sine_synthetic(
    transcribe_runner: Any = None,
) -> TranscriptionTrackResult:
    """Generate a stepped-sine WAV and evaluate it as a harness self-test.

    Four notes at known MIDI pitches with 0.2s gaps. Provides at least one
    transcription result even when no real tracks are present.
    """
    if transcribe_runner is None:
        transcribe_runner = _run_analyze

    sample_rate = 16000
    note_duration_s = 0.6
    gap_s = 0.2
    pitch_midi_values = [60, 64, 67, 72]  # C4, E4, G4, C5
    ground_truth: list[dict[str, Any]] = []
    segments: list[np.ndarray] = []
    cursor = 0.0
    for pitch_midi in pitch_midi_values:
        freq_hz = 440.0 * (2.0 ** ((pitch_midi - 69) / 12.0))
        n_samples = int(round(note_duration_s * sample_rate))
        t = np.linspace(0.0, note_duration_s, n_samples, endpoint=False, dtype=np.float32)
        tone = 0.5 * np.sin(2.0 * np.pi * freq_hz * t)
        envelope = np.ones_like(tone)
        ramp = max(1, int(round(0.01 * sample_rate)))
        envelope[:ramp] = np.linspace(0.0, 1.0, ramp, dtype=np.float32)
        envelope[-ramp:] = np.linspace(1.0, 0.0, ramp, dtype=np.float32)
        segments.append(tone * envelope)
        ground_truth.append(
            {
                "pitchMidi": pitch_midi,
                "onsetSeconds": round(cursor, 4),
                "durationSeconds": round(note_duration_s, 4),
            }
        )
        cursor += note_duration_s
        gap = np.zeros(int(round(gap_s * sample_rate)), dtype=np.float32)
        segments.append(gap)
        cursor += gap_s

    mono = np.concatenate(segments).astype(np.float32)

    with tempfile.TemporaryDirectory(prefix="asa_stepped_sine_") as temp_dir:
        wav_path = Path(temp_dir) / "stepped_sine.wav"
        _write_stereo_wav(wav_path, mono, sample_rate)
        entry = {
            "id": "stepped_sine_synthetic",
            "audioPath": wav_path.name,
            "category": "synthetic_self_test",
            "description": "Stepped sine self-test: four monophonic notes (C4, E4, G4, C5).",
            "analyzeFlags": ["--transcribe"],
            "groundTruthNotes": ground_truth,
            "thresholds": {
                "noteMetrics.f1": {"target": 0.5, "tolerance": 0.0, "direction": "min"},
                "noteMetrics.meanPitchCentsError": {"target": 0.0, "tolerance": 100.0},
            },
        }
        return _evaluate_transcription_track(
            entry,
            wav_path.parent,
            transcribe_runner=transcribe_runner,
        )


def _evaluate_stability(
    outputs: list[dict[str, Any]],
    stability_checks: list[dict[str, Any]],
) -> list[FixtureCheck]:
    checks: list[FixtureCheck] = []
    if len(outputs) < 2:
        return checks

    for check in stability_checks:
        field = str(check.get("field"))
        mode = str(check.get("mode", "")).strip().lower()
        values = [_get_nested_value(payload, field) for payload in outputs]

        if mode == "exact":
            passed = len({json.dumps(value, sort_keys=True) for value in values}) == 1
            checks.append(
                FixtureCheck(
                    name=f"stability:{field}",
                    passed=passed,
                    message=f"values={values}",
                )
            )
            continue

        max_delta = float(check.get("maxDelta", 0.0))
        numeric_values = [float(value) for value in values if isinstance(value, (int, float))]
        if len(numeric_values) != len(values):
            checks.append(
                FixtureCheck(
                    name=f"stability:{field}",
                    passed=False,
                    message=f"expected numeric values, got={values}",
                )
            )
            continue
        drift = max(numeric_values) - min(numeric_values)
        checks.append(
            FixtureCheck(
                name=f"stability:{field}",
                passed=drift <= max_delta,
                message=f"values={numeric_values} drift={round(drift, 6)} maxDelta={max_delta}",
            )
        )
    return checks


def run_phase1_evaluation(
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    runs_per_fixture: int = 2,
    include_real: bool = False,
    real_tracks_dir: Path = DEFAULT_BENCH_TRACKS_DIR,
    include_transcription: bool = False,
    transcription_tracks_dir: Path = DEFAULT_TRANSCRIPTION_TRACKS_DIR,
    transcribe_runner: Any = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures = manifest.get("fixtures", [])
    stability_checks = manifest.get("stabilityChecks", [])
    real_tracks_manifest = manifest.get("realTracks", []) if include_real else []
    transcription_manifest = (
        manifest.get("transcriptionTracks", []) if include_transcription else []
    )
    if not isinstance(fixtures, list) or len(fixtures) == 0:
        raise ValueError("Manifest must define one or more fixtures.")
    if not isinstance(real_tracks_manifest, list):
        raise ValueError("Manifest 'realTracks' must be a list when present.")
    if not isinstance(transcription_manifest, list):
        raise ValueError("Manifest 'transcriptionTracks' must be a list when present.")

    fixture_reports: list[dict[str, Any]] = []
    passed_checks = 0
    failed_checks = 0

    with tempfile.TemporaryDirectory(prefix="asa_phase1_eval_") as temp_dir:
        temp_root = Path(temp_dir)
        for fixture in fixtures:
            fixture_id = str(fixture.get("id"))
            generator = fixture.get("generator")
            thresholds = fixture.get("thresholds", {})
            if not isinstance(generator, dict):
                raise ValueError(f"Fixture '{fixture_id}' missing generator configuration.")
            if not isinstance(thresholds, dict):
                raise ValueError(f"Fixture '{fixture_id}' thresholds must be an object.")

            mono, sample_rate = _generate_fixture_audio(generator)
            fixture_path = temp_root / f"{fixture_id}.wav"
            _write_stereo_wav(fixture_path, mono, sample_rate)

            outputs = [_run_analyze(fixture_path) for _ in range(runs_per_fixture)]

            checks: list[FixtureCheck] = []
            for field, config in thresholds.items():
                if not isinstance(config, dict):
                    continue
                checks.append(_evaluate_threshold(outputs[0], field, config))
            checks.append(_evaluate_spectral_presence(outputs[0]))
            checks.append(_evaluate_plr_consistency(outputs[0]))
            checks.extend(_evaluate_stability(outputs, stability_checks))

            fixture_passed = all(check.passed for check in checks)
            passed_checks += sum(1 for check in checks if check.passed)
            failed_checks += sum(1 for check in checks if not check.passed)

            fixture_reports.append(
                {
                    "id": fixture_id,
                    "audioPath": str(fixture_path),
                    "runs": outputs,
                    "checks": [
                        {
                            "name": check.name,
                            "passed": check.passed,
                            "message": check.message,
                        }
                        for check in checks
                    ],
                    "allPassed": fixture_passed,
                }
            )

    real_track_reports: list[dict[str, Any]] = []
    real_evaluated = 0
    real_skipped = 0
    real_failed_subprocess = 0

    if include_real:
        for raw_entry in real_tracks_manifest:
            if not isinstance(raw_entry, dict):
                continue
            result = _evaluate_real_track(raw_entry, real_tracks_dir)
            if result.status == "evaluated":
                real_evaluated += 1
                passed_checks += sum(1 for check in result.checks if check.passed)
                failed_checks += sum(1 for check in result.checks if not check.passed)
            elif result.status == "skipped_audio_missing":
                real_skipped += 1
            elif result.status == "skipped_analyze_failed":
                # An analyze.py crash on a present audio file is a real failure
                # — count it once so summary.allPassed reflects the breakage.
                real_failed_subprocess += 1
                failed_checks += 1

            real_track_reports.append(
                {
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
                        }
                        for check in result.checks
                    ],
                    "allPassed": result.all_passed,
                }
            )

    transcription_reports: list[dict[str, Any]] = []
    transcription_evaluated = 0
    transcription_skipped = 0
    transcription_failed_subprocess = 0

    if include_transcription:
        # Self-test first — guarantees the report has at least one transcription
        # row even when no real tracks have been added to the manifest.
        self_test = _evaluate_stepped_sine_synthetic(transcribe_runner=transcribe_runner)
        if self_test.status == "evaluated":
            transcription_evaluated += 1
            passed_checks += sum(1 for check in self_test.checks if check.passed)
            failed_checks += sum(1 for check in self_test.checks if not check.passed)
        elif self_test.status == "skipped_audio_missing":
            transcription_skipped += 1
        else:
            transcription_failed_subprocess += 1
            failed_checks += 1
        transcription_reports.append(_transcription_track_to_report(self_test))

        for raw_entry in transcription_manifest:
            if not isinstance(raw_entry, dict):
                continue
            result = _evaluate_transcription_track(
                raw_entry, transcription_tracks_dir, transcribe_runner=transcribe_runner
            )
            if result.status == "evaluated":
                transcription_evaluated += 1
                passed_checks += sum(1 for check in result.checks if check.passed)
                failed_checks += sum(1 for check in result.checks if not check.passed)
            elif result.status == "skipped_audio_missing":
                transcription_skipped += 1
            else:
                transcription_failed_subprocess += 1
                failed_checks += 1
            transcription_reports.append(_transcription_track_to_report(result))

    summary = {
        "fixtures": len(fixture_reports),
        "realTracksEvaluated": real_evaluated,
        "realTracksSkipped": real_skipped,
        "realTracksAnalyzeFailed": real_failed_subprocess,
        "transcriptionTracksEvaluated": transcription_evaluated,
        "transcriptionTracksSkipped": transcription_skipped,
        "transcriptionTracksAnalyzeFailed": transcription_failed_subprocess,
        "checksPassed": passed_checks,
        "checksFailed": failed_checks,
        "allPassed": failed_checks == 0,
    }

    report: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "manifestPath": str(manifest_path),
        "runsPerFixture": runs_per_fixture,
        "includeReal": include_real,
        "realTracksDir": str(real_tracks_dir) if include_real else None,
        "includeTranscription": include_transcription,
        "transcriptionTracksDir": str(transcription_tracks_dir) if include_transcription else None,
        "fixtures": fixture_reports,
        "summary": summary,
    }
    if include_real:
        report["realTracks"] = real_track_reports
    if include_transcription:
        report["transcriptionTracks"] = transcription_reports

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report


def _transcription_track_to_report(result: TranscriptionTrackResult) -> dict[str, Any]:
    return {
        "id": result.track_id,
        "audioPath": result.audio_path,
        "category": result.category,
        "description": result.description,
        "status": result.status,
        "skipReason": result.skip_reason,
        "noteMetrics": result.note_metrics,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "message": check.message,
            }
            for check in result.checks
        ],
        "allPassed": result.all_passed,
    }
