"""Pure helpers for recommendation-fixture render intake.

EVAL / RESEARCH ONLY. The command-line driver lives in
``scripts/intake_recommendation_fixture.py``; keeping validation and projection
here makes the evidence-building path directly testable.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DOMAINS: tuple[str, ...] = (
    "kick",
    "bass",
    "melody",
    "groove",
    "fx",
    "stereo",
    "master",
)

_SPECTRAL_BANDS: tuple[tuple[str, str, tuple[int, int]], ...] = (
    ("Sub Bass", "subBass", (20, 60)),
    ("Low Bass", "lowBass", (60, 120)),
    ("Low Mids", "lowMids", (120, 250)),
    ("Mids", "mids", (250, 2000)),
    ("Upper Mids", "upperMids", (2000, 6000)),
    ("Highs", "highs", (6000, 12000)),
    ("Brilliance", "brilliance", (12000, 20000)),
)


@dataclass(frozen=True)
class IntentCheck:
    path: str
    actual: Any
    target: Any
    passed: bool
    message: str


@dataclass(frozen=True)
class IntakeResult:
    passed: bool
    message: str
    scores: tuple[dict[str, Any], ...] = ()


def _resolve_path(payload: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def check_measurable_intent(
    measurable_intent: Mapping[str, Mapping[str, Any]],
    fingerprint: Mapping[str, Any],
) -> list[IntentCheck]:
    """Compare measured Phase 1 values with a fixture's declared intent."""
    checks: list[IntentCheck] = []
    for path, expectation in measurable_intent.items():
        found, actual = _resolve_path(fingerprint, path)
        target = expectation.get("target", expectation.get("equals"))
        if not found or actual is None:
            checks.append(IntentCheck(path, actual, target, False, "measurement is missing"))
            continue

        if _is_number(actual) and _is_number(target):
            tolerance = expectation.get("tolerance", 0)
            tolerance = float(tolerance) if _is_number(tolerance) else 0.0
            direction = str(expectation.get("direction", "exact")).lower()
            if direction == "min":
                passed = float(actual) >= float(target) - tolerance
            elif direction == "max":
                passed = float(actual) <= float(target) + tolerance
            else:
                passed = abs(float(actual) - float(target)) <= tolerance
            message = (
                "within declared intent"
                if passed
                else f"outside target {target!r} with tolerance {tolerance:g}"
            )
        else:
            passed = str(actual).strip().casefold() == str(target).strip().casefold()
            message = "matches declared intent" if passed else f"does not match target {target!r}"
        checks.append(IntentCheck(path, actual, target, passed, message))
    return checks


def check_render_contract(
    render: Mapping[str, Any],
    *,
    sample_rate: int,
    subtype: str,
    duration_seconds: float,
) -> list[str]:
    """Validate the exported audio against the manifest's render contract."""
    issues: list[str] = []
    expected_rate = render.get("sampleRateHz")
    if _is_number(expected_rate) and sample_rate != int(expected_rate):
        issues.append(f"sample rate is {sample_rate} Hz; expected {int(expected_rate)} Hz")

    expected_depth = render.get("bitDepth")
    actual_depth = int(subtype.removeprefix("PCM_")) if subtype.startswith("PCM_") else None
    if _is_number(expected_depth) and actual_depth != int(expected_depth):
        issues.append(f"bit depth is {subtype}; expected PCM_{int(expected_depth)}")

    expected_length = render.get("lengthSeconds")
    if _is_number(expected_length):
        tolerance = max(2.0, float(expected_length) * 0.15)
        if abs(duration_seconds - float(expected_length)) > tolerance:
            issues.append(
                f"duration is {duration_seconds:.2f} s; expected about "
                f"{float(expected_length):g} s (±{tolerance:.1f} s)"
            )
    return issues


def _number(payload: Mapping[str, Any], path: str, default: float = 0.0) -> float:
    found, value = _resolve_path(payload, path)
    return float(value) if found and _is_number(value) else default


def _parse_key(value: Any) -> dict[str, str]:
    parts = str(value or "").strip().split(maxsplit=1)
    root = parts[0] if parts else "Unknown"
    scale = parts[1].lower() if len(parts) > 1 else "unknown"
    return {"root": root, "scale": scale}


def _dominance(average_db: float) -> str:
    if average_db >= -12.0:
        return "dominant"
    if average_db >= -36.0:
        return "present"
    return "absent"


def project_deterministic_audio_features(fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    """Project raw Phase 1 onto ``abletonDevices.ts``' AudioFeatures input."""
    balance = fingerprint.get("spectralBalance")
    if not isinstance(balance, Mapping):
        balance = {}
    series = fingerprint.get("spectralBalanceTimeSeries")
    rows = series if isinstance(series, list) else []

    bands: list[dict[str, Any]] = []
    for name, field, frequency_range in _SPECTRAL_BANDS:
        average_db = float(balance[field]) if _is_number(balance.get(field)) else -80.0
        peak_values = [row.get(field) for row in rows if isinstance(row, Mapping)]
        finite_peaks = [float(value) for value in peak_values if _is_number(value)]
        peak_db = max(finite_peaks, default=average_db)
        bands.append(
            {
                "name": name,
                "rangeHz": list(frequency_range),
                "averageDb": average_db,
                "peakDb": peak_db,
                "dominance": _dominance(average_db),
            }
        )

    return {
        "bpm": _number(fingerprint, "bpm"),
        "key": _parse_key(fingerprint.get("key")),
        "crestFactor": _number(fingerprint, "crestFactor"),
        "onsetDensity": _number(fingerprint, "rhythmDetail.onsetRate"),
        "duration": _number(fingerprint, "durationSeconds"),
        "bpmConfidence": _number(fingerprint, "bpmConfidence"),
        "spectralBands": bands,
        "spectralCentroidMean": _number(
            fingerprint,
            "spectralDetail.spectralCentroidMean",
            _number(fingerprint, "spectralDetail.spectralCentroid"),
        ),
    }


def render_verification_typescript(artifact: Mapping[str, Any]) -> str:
    """Render the generated corpus-verification data as the UI data module."""
    fixtures = int(artifact.get("fixtures", 0))
    sources = json.dumps(artifact.get("sources", []), separators=(", ", ": "))
    per_domain = artifact.get("perDomain")
    if not isinstance(per_domain, Mapping):
        raise ValueError("verification artifact is missing perDomain")

    domain_lines: list[str] = []
    for domain in DOMAINS:
        value = per_domain.get(domain)
        if not isinstance(value, Mapping):
            raise ValueError(f"verification artifact is missing domain {domain!r}")
        domain_lines.append(
            f"    {domain}: {{ support: {int(value.get('support', 0))}, "
            f"meanRecall: {value.get('meanRecall', 0.0)}, "
            f"meanScore: {value.get('meanScore', 0.0)}, "
            f"confidence: {json.dumps(value.get('confidence', 'NONE'))} }},"
        )

    return "\n".join(
        [
            "/**",
            " * Corpus-verification artifact for recommendation badges.",
            " *",
            " * Generated from real Ableton renders by:",
            " *   ./venv/bin/python scripts/intake_recommendation_fixture.py --fixture <slug>",
            " * Do not edit the values by hand.",
            " */",
            "",
            "export type VerificationConfidence = 'NONE' | 'LOW' | 'MED' | 'HIGH';",
            "",
            "/** The seven production domains (PURPOSE.md invariant #5). */",
            "export type RecommendationDomain =",
            "  | 'kick'",
            "  | 'bass'",
            "  | 'melody'",
            "  | 'groove'",
            "  | 'fx'",
            "  | 'stereo'",
            "  | 'master';",
            "",
            "export interface DomainVerification {",
            "  support: number;",
            "  meanRecall: number;",
            "  meanScore: number;",
            "  confidence: VerificationConfidence;",
            "}",
            "",
            "export interface RecommendationVerificationArtifact {",
            "  fixtures: number;",
            "  sources: string[];",
            "  perDomain: Record<RecommendationDomain, DomainVerification>;",
            "}",
            "",
            "export const RECOMMENDATION_VERIFICATION: RecommendationVerificationArtifact = {",
            f"  fixtures: {fixtures},",
            f"  sources: {sources},",
            "  perDomain: {",
            *domain_lines,
            "  },",
            "};",
            "",
        ]
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run(
    command_runner: Any,
    command: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    completed = command_runner(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    return completed


def _load_normalized_recommendations(path: Path) -> list[Any]:
    import recommendation_evaluation as rev

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path.name} must contain a JSON array")
    return [
        rev.NormalizedRec(
            domain=item.get("domain", rev.UNKNOWN_DOMAIN),
            device=item.get("device", ""),
            parameter=item.get("parameter"),
            value=item.get("value"),
            citations=tuple(item.get("citations", [])),
            family=item.get("family"),
        )
        for item in raw
        if isinstance(item, Mapping)
    ]


def run_fixture_intake(
    fixture_dir: Path,
    *,
    ui_artifact_path: Path | None = None,
    command_runner: Any = subprocess.run,
    audio_info_reader: Any = None,
) -> IntakeResult:
    """Run the complete real-render intake and evidence refresh for one fixture."""
    import recommendation_evaluation as rev

    fixture_dir = fixture_dir.resolve()
    backend_dir = Path(__file__).resolve().parent
    repo_root = backend_dir.parents[1]
    manifest_path = fixture_dir / "manifest.json"
    if not manifest_path.is_file():
        return IntakeResult(False, f"missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixture = rev.load_fixture(manifest_path)
    spec_issues = rev.validate_fixture_spec(fixture)
    if spec_issues:
        details = "; ".join(issue.message for issue in spec_issues)
        return IntakeResult(False, f"fixture spec is not catalog-valid: {details}")

    audio_path = fixture_dir / str(manifest.get("audioPath", "audio.flac"))
    if not audio_path.is_file():
        return IntakeResult(False, f"missing real render: {audio_path}")

    if audio_info_reader is None:
        import soundfile

        audio_info_reader = soundfile.info
    try:
        info = audio_info_reader(str(audio_path))
    except Exception as exc:
        return IntakeResult(False, f"cannot read render metadata: {exc}")
    render_issues = check_render_contract(
        manifest.get("render") or {},
        sample_rate=int(info.samplerate),
        subtype=str(info.subtype),
        duration_seconds=float(info.duration),
    )
    if render_issues:
        return IntakeResult(False, "render contract failed: " + "; ".join(render_issues))

    analyzed = _run(
        command_runner,
        [sys.executable, str(backend_dir / "analyze.py"), str(audio_path), "--yes"],
        cwd=backend_dir,
    )
    if analyzed.returncode != 0:
        return IntakeResult(False, f"Phase 1 analyzer failed with exit code {analyzed.returncode}")
    try:
        analyzer_payload = json.loads(analyzed.stdout)
    except json.JSONDecodeError as exc:
        return IntakeResult(False, f"Phase 1 analyzer returned invalid JSON: {exc}")
    if not isinstance(analyzer_payload, Mapping):
        return IntakeResult(False, "Phase 1 analyzer did not return a JSON object")

    # Store the canonical HTTP/Phase-2 contract, not raw analyzer-only names
    # such as spectralDetail.spectralCentroid. Manifest intent paths and provider
    # citations use the normalized Mean-suffix names from this exact projection.
    from server_phase1 import _build_phase1

    fingerprint = _build_phase1(dict(analyzer_payload))

    fingerprint_path = fixture_dir / str(
        manifest.get("phase1FingerprintPath", "phase1_fingerprint.json")
    )
    _write_json(fingerprint_path, fingerprint)

    intent_checks = check_measurable_intent(
        manifest.get("measurableIntent") or {},
        fingerprint,
    )
    failed_intent = [check for check in intent_checks if not check.passed]
    for check in intent_checks:
        label = "PASS" if check.passed else "FAIL"
        print(f"[{label}] {check.path}: measured {check.actual!r}; {check.message}")
    if failed_intent:
        return IntakeResult(
            False,
            f"{len(failed_intent)} measurable-intent check(s) failed; fingerprint retained for review",
        )

    features = project_deterministic_audio_features(fingerprint)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        dir=fixture_dir,
        encoding="utf-8",
    ) as feature_file:
        json.dump(features, feature_file)
        feature_file.flush()
        deterministic = _run(
            command_runner,
            [
                "node",
                str(backend_dir / "scripts" / "emit_deterministic_recs.ts"),
                feature_file.name,
            ],
            cwd=repo_root,
        )
    if deterministic.returncode != 0:
        return IntakeResult(
            False,
            f"deterministic recommendation bridge failed with exit code {deterministic.returncode}",
        )
    try:
        deterministic_payload = json.loads(deterministic.stdout)
    except json.JSONDecodeError as exc:
        return IntakeResult(False, f"deterministic bridge returned invalid JSON: {exc}")
    deterministic_path = fixture_dir / "recommendations.deterministic.json"
    _write_json(deterministic_path, deterministic_payload)

    claude = _run(
        command_runner,
        [
            sys.executable,
            str(backend_dir / "scripts" / "gen_claude_phase2.py"),
            "--fixture",
            fixture.slug,
            "--corpus-dir",
            str(fixture_dir.parent),
        ],
        cwd=backend_dir,
    )
    if claude.stdout:
        print(claude.stdout, end="")
    if claude.returncode != 0:
        return IntakeResult(False, f"Claude recommendation generation failed with exit code {claude.returncode}")

    claude_path = fixture_dir / "phase2.claude.json"
    if not claude_path.is_file():
        return IntakeResult(False, f"Claude run did not create {claude_path.name}")

    fixture = rev.load_fixture(manifest_path)
    claude_payload = rev.coerce_phase2_payload(
        json.loads(claude_path.read_text(encoding="utf-8"))
    )
    claude_recs = rev.normalize_phase2(claude_payload)
    if not claude_recs:
        return IntakeResult(False, "Claude output contains no scoreable recommendation cards")
    source_recs = (
        ("claude", claude_recs),
        ("deterministic", _load_normalized_recommendations(deterministic_path)),
        ("baseline", rev.normalize_baseline(fixture)),
    )
    scores = [rev.score_recommendations(fixture, recs, source) for source, recs in source_recs]
    score_payload = [score.as_dict() for score in scores]
    _write_json(fixture_dir / "recommendation_scores.json", score_payload)
    (fixture_dir / "recommendation_scores.md").write_text(
        rev.render_markdown_report(scores),
        encoding="utf-8",
    )

    verification = rev.aggregate_corpus_verification([scores[0]])
    _write_json(fixture_dir / "recommendation_verification.json", verification)
    if ui_artifact_path is None:
        ui_artifact_path = repo_root / "apps" / "ui" / "src" / "data" / "recommendationVerification.ts"
    ui_artifact_path.write_text(
        render_verification_typescript(verification),
        encoding="utf-8",
    )

    return IntakeResult(
        True,
        "render, measurable intent, recommendations, scores, and verification artifact passed",
        tuple(score_payload),
    )
