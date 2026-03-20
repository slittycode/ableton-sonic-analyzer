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


def _run_analyze(audio_path: Path) -> dict[str, Any]:
    command = [sys.executable, str(REPO_DIR / "analyze.py"), str(audio_path), "--yes"]
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
    if not isinstance(actual, (int, float)):
        return FixtureCheck(
            name=f"threshold:{field}",
            passed=False,
            message=f"expected numeric target={target}±{tolerance}, actual={actual}",
        )
    delta = abs(float(actual) - target)
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
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures = manifest.get("fixtures", [])
    stability_checks = manifest.get("stabilityChecks", [])
    if not isinstance(fixtures, list) or len(fixtures) == 0:
        raise ValueError("Manifest must define one or more fixtures.")

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

    summary = {
        "fixtures": len(fixture_reports),
        "checksPassed": passed_checks,
        "checksFailed": failed_checks,
        "allPassed": failed_checks == 0,
    }

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "manifestPath": str(manifest_path),
        "runsPerFixture": runs_per_fixture,
        "fixtures": fixture_reports,
        "summary": summary,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report
