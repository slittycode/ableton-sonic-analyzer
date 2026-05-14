"""Phase 1 response building: coercion, normalization, timing, diagnostics."""

import sys
from datetime import datetime
from math import ceil, isfinite
from typing import Any

from fastapi.responses import JSONResponse

from analysis_runtime import AnalysisRuntime
from server_upload import ERROR_PHASE_LOCAL_DSP
from stage_status import to_public_status


# ── Constants ────────────────────────────────────────────────────────────────

ENGINE_VERSION = "analyze.py"
MAX_SNIPPET_LENGTH = 2000

ANALYZE_TIMEOUT_BUFFER_SECONDS = 120
ANALYZE_TIMEOUT_FLOOR_SECONDS = 300
ANALYZE_TIMEOUT_FALLBACK_SECONDS = 900
ANALYZE_TIMEOUT_ESTIMATE_MULTIPLIER = 2.0


# ── Type-coercion helpers ────────────────────────────────────────────────────

def _coerce_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        numeric = float(value)
        if isfinite(numeric):
            return numeric
    return default


def _coerce_string(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _coerce_nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _coerce_positive_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        numeric = int(round(float(value)))
        return numeric if numeric >= 0 else default
    return default


def _coerce_nullable_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if isfinite(numeric):
            return numeric
    return None


# ── Timing helpers ───────────────────────────────────────────────────────────

def _elapsed_ms(started_at: datetime | None, ended_at: datetime | None) -> float:
    if started_at is None or ended_at is None:
        return 0.0
    return max((ended_at - started_at).total_seconds() * 1000, 0.0)


# ── Phase 1 normalization ───────────────────────────────────────────────────

def _normalize_spectral_detail(detail: Any) -> dict[str, Any] | None:
    """Map analyzer field names to the frontend-expected SpectralDetail contract.

    The analyzer emits ``spectralCentroid`` / ``spectralRolloff`` (singular) but
    the frontend ``SpectralDetail`` interface expects ``spectralCentroidMean`` /
    ``spectralRolloffMean``.
    """
    if not isinstance(detail, dict):
        return None
    out = dict(detail)
    if "spectralCentroid" in out and "spectralCentroidMean" not in out:
        out["spectralCentroidMean"] = out.pop("spectralCentroid")
    if "spectralRolloff" in out and "spectralRolloffMean" not in out:
        out["spectralRolloffMean"] = out.pop("spectralRolloff")
    if "spectralBandwidth" in out and "spectralBandwidthMean" not in out:
        out["spectralBandwidthMean"] = out.pop("spectralBandwidth")
    if "spectralFlatness" in out and "spectralFlatnessMean" not in out:
        out["spectralFlatnessMean"] = out.pop("spectralFlatness")
    return out


def _normalize_stem_analysis(stem_analysis: Any) -> dict[str, Any] | None:
    """Apply ``_normalize_spectral_detail`` to every per-stem spectralDetail.

    Keeps the field-name contract consistent between the top-level
    ``spectralDetail`` and the per-stem nested ``stemAnalysis.{stem}.spectralDetail``
    so the frontend, Gemini, and the citation validator all speak the same
    naming convention. Other per-stem keys (spectralBalance, lufsCurve,
    stereoDetail, etc.) keep their existing shapes — only the spectralDetail
    rename is needed today.
    """
    if not isinstance(stem_analysis, dict):
        return None
    out: dict[str, Any] = {}
    for stem_name, stem_entry in stem_analysis.items():
        if not isinstance(stem_entry, dict):
            out[stem_name] = stem_entry
            continue
        stem_copy = dict(stem_entry)
        if isinstance(stem_copy.get("spectralDetail"), dict):
            stem_copy["spectralDetail"] = _normalize_spectral_detail(stem_copy["spectralDetail"])
        out[stem_name] = stem_copy
    return out


def _build_phase1(payload: dict[str, Any]) -> dict[str, Any]:
    stereo_detail = payload.get("stereoDetail")
    if not isinstance(stereo_detail, dict):
        stereo_detail = {}

    spectral_balance = payload.get("spectralBalance")
    if not isinstance(spectral_balance, dict):
        spectral_balance = {}

    plr = _coerce_nullable_number(payload.get("plr"))
    if plr is None:
        lufs_integrated = _coerce_nullable_number(payload.get("lufsIntegrated"))
        true_peak = _coerce_nullable_number(payload.get("truePeak"))
        if lufs_integrated is not None and true_peak is not None:
            plr = round(true_peak - lufs_integrated, 2)

    mono_compatible = payload.get("monoCompatible")
    if not isinstance(mono_compatible, bool):
        sub_bass_mono = stereo_detail.get("subBassMono")
        mono_compatible = sub_bass_mono if isinstance(sub_bass_mono, bool) else None

    return {
        "bpm": _coerce_number(payload.get("bpm")),
        "bpmConfidence": _coerce_number(payload.get("bpmConfidence")),
        "bpmPercival": _coerce_nullable_number(payload.get("bpmPercival")),
        "bpmAgreement": payload.get("bpmAgreement"),
        "bpmDoubletime": payload.get("bpmDoubletime"),
        "bpmSource": payload.get("bpmSource"),
        "bpmRawOriginal": _coerce_nullable_number(payload.get("bpmRawOriginal")),
        "key": _coerce_nullable_string(payload.get("key")),
        "keyConfidence": _coerce_number(payload.get("keyConfidence")),
        "keyProfile": payload.get("keyProfile"),
        "tuningFrequency": _coerce_nullable_number(payload.get("tuningFrequency")),
        "tuningCents": _coerce_nullable_number(payload.get("tuningCents")),
        "timeSignature": _coerce_string(payload.get("timeSignature"), "4/4"),
        "timeSignatureSource": _coerce_nullable_string(payload.get("timeSignatureSource")),
        "timeSignatureConfidence": _coerce_nullable_number(payload.get("timeSignatureConfidence")),
        "durationSeconds": _coerce_number(payload.get("durationSeconds")),
        "sampleRate": payload.get("sampleRate"),
        "lufsIntegrated": _coerce_number(payload.get("lufsIntegrated")),
        "lufsRange": _coerce_nullable_number(payload.get("lufsRange")),
        "lufsMomentaryMax": _coerce_nullable_number(payload.get("lufsMomentaryMax")),
        "lufsShortTermMax": _coerce_nullable_number(payload.get("lufsShortTermMax")),
        "lufsCurve": payload.get("lufsCurve"),
        "truePeak": _coerce_number(payload.get("truePeak")),
        "plr": plr,
        "crestFactor": _coerce_nullable_number(payload.get("crestFactor")),
        "dynamicSpread": _coerce_nullable_number(payload.get("dynamicSpread")),
        "dynamicCharacter": payload.get("dynamicCharacter"),
        "textureCharacter": payload.get("textureCharacter"),
        "stereoWidth": _coerce_number(stereo_detail.get("stereoWidth")),
        "stereoCorrelation": _coerce_number(stereo_detail.get("stereoCorrelation")),
        "stereoDetail": payload.get("stereoDetail"),
        "monoCompatible": mono_compatible,
        "spectralBalance": {
            "subBass": _coerce_number(spectral_balance.get("subBass")),
            "lowBass": _coerce_number(spectral_balance.get("lowBass")),
            "lowMids": _coerce_number(spectral_balance.get("lowMids")),
            "mids": _coerce_number(spectral_balance.get("mids")),
            "upperMids": _coerce_number(spectral_balance.get("upperMids")),
            "highs": _coerce_number(spectral_balance.get("highs")),
            "brilliance": _coerce_number(spectral_balance.get("brilliance")),
        },
        "spectralBalanceTimeSeries": payload.get("spectralBalanceTimeSeries"),
        # Stem subtree is forwarded as-is, but per-stem spectralDetail keys are
        # renamed to match the top-level Mean-suffix contract — keeps the
        # frontend and the Gemini citation contract speaking one schema.
        "stemAnalysis": _normalize_stem_analysis(payload.get("stemAnalysis")),
        "transientDensityDetail": payload.get("transientDensityDetail"),
        "saturationDetail": payload.get("saturationDetail"),
        "snareDetail": payload.get("snareDetail"),
        "hihatDetail": payload.get("hihatDetail"),
        "spectralDetail": _normalize_spectral_detail(payload.get("spectralDetail")),
        "rhythmDetail": payload.get("rhythmDetail"),
        "melodyDetail": payload.get("melodyDetail"),
        "transcriptionDetail": payload.get("transcriptionDetail"),
        "pitchDetail": payload.get("pitchDetail"),
        "grooveDetail": payload.get("grooveDetail"),
        "beatsLoudness": payload.get("beatsLoudness"),
        "rhythmTimeline": payload.get("rhythmTimeline"),
        "sidechainDetail": payload.get("sidechainDetail"),
        "acidDetail": payload.get("acidDetail"),
        "reverbDetail": payload.get("reverbDetail"),
        "vocalDetail": payload.get("vocalDetail"),
        "supersawDetail": payload.get("supersawDetail"),
        "bassDetail": payload.get("bassDetail"),
        "kickDetail": payload.get("kickDetail"),
        "genreDetail": payload.get("genreDetail"),
        "effectsDetail": payload.get("effectsDetail"),
        "synthesisCharacter": payload.get("synthesisCharacter"),
        "danceability": payload.get("danceability"),
        "structure": payload.get("structure"),
        "arrangementDetail": payload.get("arrangementDetail"),
        "segmentLoudness": payload.get("segmentLoudness"),
        "segmentSpectral": payload.get("segmentSpectral"),
        "segmentStereo": payload.get("segmentStereo"),
        "segmentKey": payload.get("segmentKey"),
        "chordDetail": payload.get("chordDetail"),
        "perceptual": payload.get("perceptual"),
        "essentiaFeatures": payload.get("essentiaFeatures"),
    }


def _annotate_public_status(stages: dict[str, Any]) -> dict[str, Any]:
    """Attach ``publicStatus`` to every stage whose ``status`` is set.

    Returns a shallow-copy of ``stages`` with each stage dict updated.
    The original ``status`` field is preserved untouched; ``publicStatus``
    is the additive 5-state collapse documented in
    :mod:`stage_status`.

    Defensive against non-dict stage entries (e.g. nulls in legacy
    snapshots) — those pass through unchanged.
    """
    annotated: dict[str, Any] = {}
    for stage_name, stage_value in stages.items():
        if not isinstance(stage_value, dict):
            annotated[stage_name] = stage_value
            continue
        stage_copy = dict(stage_value)
        # `status` may legitimately be absent on legacy/partial snapshots;
        # to_public_status(None) yields None which we expose as null.
        stage_copy["publicStatus"] = to_public_status(stage_copy.get("status"))
        annotated[stage_name] = stage_copy
    return annotated


def _normalize_run_snapshot(
    snapshot: dict[str, Any], runtime: AnalysisRuntime | None = None
) -> dict[str, Any]:
    """Apply _build_phase1 normalization to a run snapshot's measurement result.

    The analysis-run pathway stores raw analyze.py output in the DB, but the
    frontend parser (parsePhase1Result) expects the same normalized shape that
    _build_phase1 produces for the legacy /api/analyze endpoint — notably,
    top-level stereoWidth/stereoCorrelation extracted from stereoDetail.

    Each stage in ``stages`` is also annotated with a ``publicStatus`` field
    that collapses the 8 internal stage statuses to 5 public ones (see
    :mod:`stage_status`). The original ``status`` field is preserved; this
    is purely additive.

    When *runtime* is provided, spectral visualization artifacts (spectrogram
    PNGs and time-series JSON) are attached under ``artifacts.spectral``.
    """
    stages = snapshot.get("stages")
    if not isinstance(stages, dict):
        return snapshot
    snapshot = dict(snapshot)
    snapshot["stages"] = _annotate_public_status(stages)

    measurement = snapshot["stages"].get("measurement")
    if isinstance(measurement, dict):
        raw_result = measurement.get("result")
        if isinstance(raw_result, dict):
            # Reuse the dict we already copied in _annotate_public_status;
            # no need to clone twice.
            measurement["result"] = _build_phase1(raw_result)

    if runtime is not None:
        run_id = snapshot.get("runId")
        if run_id:
            snapshot = dict(snapshot)
            snapshot["artifacts"] = dict(snapshot.get("artifacts") or {})
            spectral_artifacts = runtime.get_artifacts_by_kind(run_id, "spectrogram")
            ts_artifacts = runtime.get_artifacts_by_kind(run_id, "spectral_time_series")
            _strip_internal = lambda a: {
                "artifactId": a["artifactId"],
                "kind": a["kind"],
                "filename": a["filename"],
                "mimeType": a["mimeType"],
                "sizeBytes": a["sizeBytes"],
            }
            onset_artifacts = runtime.get_artifacts_by_kind(run_id, "onset_strength")
            chroma_artifacts = runtime.get_artifacts_by_kind(run_id, "chroma_interactive")
            snapshot["artifacts"]["spectral"] = {
                "spectrograms": [_strip_internal(a) for a in spectral_artifacts],
                "timeSeries": _strip_internal(ts_artifacts[0]) if ts_artifacts else None,
                "onsetStrength": _strip_internal(onset_artifacts[0]) if onset_artifacts else None,
                "chromaInteractive": _strip_internal(chroma_artifacts[0]) if chroma_artifacts else None,
            }

    return snapshot


# ── Provenance / snippets ────────────────────────────────────────────────────

def _build_measurement_provenance(
    *,
    run_separation: bool,
    run_transcribe: bool,
    run_standard: bool,
    run_fast: bool,
) -> dict[str, Any]:
    analysis_mode = "standard" if run_standard else "full"
    return {
        "schemaVersion": "measurement.v1",
        "engineVersion": ENGINE_VERSION,
        "requestOptions": {
            "analysisMode": analysis_mode,
            "separate": run_separation,
            "transcribe": run_transcribe,
            "standard": run_standard,
            "fast": run_fast,
        },
    }


def _safe_snippet(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    snippet = text.strip()
    if not snippet:
        return None
    return snippet[:MAX_SNIPPET_LENGTH]


# ── Estimate helpers ─────────────────────────────────────────────────────────

def _normalize_estimate_stage(raw_stage: dict[str, Any]) -> dict[str, Any]:
    raw_key = _coerce_string(raw_stage.get("key"), "local_dsp")
    raw_label = _coerce_string(raw_stage.get("label"), "Local DSP analysis")
    stage_key = {
        "dsp": "local_dsp",
        "separation": "demucs_separation",
    }.get(raw_key, raw_key)
    stage_label = {
        "local_dsp": "Local DSP analysis",
        "demucs_separation": "Demucs separation",
    }.get(stage_key, raw_label)
    seconds = raw_stage.get("seconds")
    if not isinstance(seconds, dict):
        seconds = {}
    low_ms = _coerce_positive_int(seconds.get("min")) * 1000
    high_ms = _coerce_positive_int(seconds.get("max")) * 1000
    if high_ms < low_ms:
        high_ms = low_ms
    return {
        "key": stage_key,
        "label": stage_label,
        "lowMs": low_ms,
        "highMs": high_ms,
    }


def _compute_timeout_seconds(estimate: dict[str, Any]) -> int:
    estimated_high_ms = _coerce_positive_int(estimate.get("totalHighMs"))
    if estimated_high_ms > 0:
        estimated_high_seconds = ceil(estimated_high_ms / 1000)
        estimated_budget_seconds = (
            ceil(estimated_high_seconds * ANALYZE_TIMEOUT_ESTIMATE_MULTIPLIER)
            + ANALYZE_TIMEOUT_BUFFER_SECONDS
        )
        return max(
            estimated_budget_seconds,
            ANALYZE_TIMEOUT_FLOOR_SECONDS,
        )
    return ANALYZE_TIMEOUT_FALLBACK_SECONDS


# ── Timing / diagnostics ────────────────────────────────────────────────────

def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _round_timing_value(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _format_timing_summary_value(
    value: float | None, suffix: str = "", digits: int = 1
) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}{suffix}"


def _build_timings(
    *,
    response_ready_at: datetime,
    request_started_at: datetime,
    analysis_started_at: datetime | None,
    analysis_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    file_duration_seconds: float | None,
) -> dict[str, Any]:
    total_ms = _elapsed_ms(request_started_at, response_ready_at)
    analysis_ms = _elapsed_ms(analysis_started_at, analysis_completed_at)
    server_overhead_ms = max(total_ms - analysis_ms, 0.0)
    normalized_duration_seconds = _coerce_nullable_number(file_duration_seconds)
    ms_per_second_of_audio = None
    if normalized_duration_seconds is not None and normalized_duration_seconds > 0:
        ms_per_second_of_audio = analysis_ms / normalized_duration_seconds

    return {
        "totalMs": _round_timing_value(total_ms),
        "analysisMs": _round_timing_value(analysis_ms),
        "serverOverheadMs": _round_timing_value(server_overhead_ms),
        "flagsUsed": list(flags_used),
        "fileSizeBytes": int(file_size_bytes),
        "fileDurationSeconds": _round_timing_value(normalized_duration_seconds),
        "msPerSecondOfAudio": _round_timing_value(ms_per_second_of_audio),
    }


def _log_timing_summary(timings: dict[str, Any]) -> None:
    flags_used = timings.get("flagsUsed")
    flags_label = (
        f"[{', '.join(flags_used)}]"
        if isinstance(flags_used, list) and flags_used
        else "[]"
    )
    file_size_bytes = _coerce_positive_int(timings.get("fileSizeBytes"))
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(
        f"[TIMING] total={_format_timing_summary_value(timings.get('totalMs'), 'ms')} "
        f"analysis={_format_timing_summary_value(timings.get('analysisMs'), 'ms')} "
        f"overhead={_format_timing_summary_value(timings.get('serverOverheadMs'), 'ms')} "
        f"flags={flags_label} "
        f"fileSize={_format_timing_summary_value(file_size_mb, 'MB')} "
        f"duration={_format_timing_summary_value(timings.get('fileDurationSeconds'), 's')} "
        f"ms/s={_format_timing_summary_value(timings.get('msPerSecondOfAudio'), digits=2)}",
        file=sys.stderr,
    )


def _build_diagnostics(
    *,
    response_ready_at: datetime,
    request_id: str,
    estimate: dict[str, Any],
    timeout_seconds: int,
    request_started_at: datetime,
    analysis_started_at: datetime | None,
    analysis_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    file_duration_seconds: float | None,
    engine_version: str | None = None,
    stdout: Any = None,
    stderr: Any = None,
    validation_warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    timings = _build_timings(
        response_ready_at=response_ready_at,
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=file_duration_seconds,
    )
    _log_timing_summary(timings)
    return _compact_dict(
        {
            "requestId": request_id,
            "backendDurationMs": timings["analysisMs"],
            "engineVersion": engine_version,
            "estimatedLowMs": _coerce_positive_int(estimate.get("totalLowMs")),
            "estimatedHighMs": _coerce_positive_int(estimate.get("totalHighMs")),
            "timeoutSeconds": timeout_seconds,
            "timings": timings,
            "stdoutSnippet": _safe_snippet(stdout),
            "stderrSnippet": _safe_snippet(stderr),
            "validationWarnings": validation_warnings if validation_warnings else None,
        }
    )


# ── Legacy response builders (unused but kept for backward compat) ───────────

def _build_error_response(
    *,
    response_ready_at: datetime,
    request_id: str,
    status_code: int,
    error_code: str,
    message: str,
    retryable: bool,
    timeout_seconds: int,
    estimate: dict[str, Any],
    request_started_at: datetime,
    analysis_started_at: datetime | None,
    analysis_completed_at: datetime | None,
    flags_used: list[str],
    file_size_bytes: int,
    file_duration_seconds: float | None,
    stdout: Any = None,
    stderr: Any = None,
) -> JSONResponse:
    diagnostics = _build_diagnostics(
        response_ready_at=response_ready_at,
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=timeout_seconds,
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=file_duration_seconds,
        stdout=stdout,
        stderr=stderr,
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "requestId": request_id,
            "error": {
                "code": error_code,
                "message": message,
                "phase": ERROR_PHASE_LOCAL_DSP,
                "retryable": retryable,
            },
            "diagnostics": diagnostics,
        },
    )


def _build_success_response(
    *,
    response_ready_at: datetime,
    request_id: str,
    analysis_run_id: str | None,
    payload: dict[str, Any],
    timeout_seconds: int,
    estimate: dict[str, Any],
    request_started_at: datetime,
    analysis_started_at: datetime,
    analysis_completed_at: datetime,
    flags_used: list[str],
    file_size_bytes: int,
) -> JSONResponse:
    diagnostics = _build_diagnostics(
        response_ready_at=response_ready_at,
        request_id=request_id,
        estimate=estimate,
        timeout_seconds=timeout_seconds,
        request_started_at=request_started_at,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        flags_used=flags_used,
        file_size_bytes=file_size_bytes,
        file_duration_seconds=payload.get("durationSeconds"),
        engine_version=ENGINE_VERSION,
    )
    return JSONResponse(
        content={
            "requestId": request_id,
            "analysisRunId": analysis_run_id,
            "phase1": _build_phase1(payload),
            "diagnostics": diagnostics,
        }
    )
