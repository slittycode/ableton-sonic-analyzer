"""Offline evaluation harness for beat/downbeat tracking — the beat_this gate.

This module is intentionally separate from analyze.py and server.py. It exists to
measure, on a contamination-free labeled corpus, whether the neural tracker
CPJKU/beat_this is materially better at DOWNBEATS than ASA's shipping kick-accent
heuristic — enough to justify a neural dependency. It is research-only and does
NOT touch the analyze.py stdout contract, the HTTP envelope, or
EXPECTED_TOP_LEVEL_KEYS. Deleting this file (and its sibling script) restores the
product exactly. Mirrors the pattern of polyphonic_evaluation.py.

Three downbeat methods are compared per clip:
  - stride      : ticks[::4]                       (legacy 4/4 baseline)
  - kick_accent : the SHIPPING heuristic — reuses analyze_rhythm._compute_downbeat_phase
  - beat_this   : the neural model (measured, NOT integrated)

beat_this and mir_eval are OPTIONAL: imported lazily/guarded so stride-vs-kick_accent
runs in the product venv with zero new dependencies (metrics fall back to a
hand-rolled F-measure when mir_eval is absent).
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO_DIR = Path(__file__).resolve().parent  # apps/backend
DEFAULT_OUTPUT_DIR = REPO_DIR / ".runtime" / "beat_eval"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "beat_eval_report.json"

# Metric conventions (mir_eval standards).
F_MEASURE_WINDOW_S = 0.07          # ±70 ms onset tolerance
TRIM_SECONDS = 5.0                 # ignore the first 5 s (start-up transient bias)

# Pre-registered pass bar (frozen BEFORE running — see the decision record).
ADOPT_MARGIN = 0.10                # min downbeat-F1 gain over best non-neural method
BEAT_REGRESSION_TOLERANCE = 0.02   # beat_this may not drop beat-F1 by more than this
MIN_CLIPS_PRIMARY = 200            # below this the GTZAN result is "underpowered"
MIN_CLIPS_ASA = 15                 # below this the ASA-slice clause is "underpowered"

DEFAULT_METHODS = ("stride", "kick_accent", "beat_this")
NON_NEURAL_METHODS = ("stride", "kick_accent")
_METRIC_KEYS = (
    "beatF1",
    "beatCMLt",
    "beatAMLt",
    "beatInfoGain",
    "downbeatF1Strict",
    "downbeatF1Tolerant",
    "tempoAcc1",
    "tempoAcc2",
)


# --------------------------------------------------------------------------- #
# Backend imports (lazy — keep this module loadable without essentia/torch).
# --------------------------------------------------------------------------- #
def _ensure_backend_on_path() -> None:
    if str(REPO_DIR) not in sys.path:
        sys.path.insert(0, str(REPO_DIR))


def _load_mir_eval():
    """Return the mir_eval module, or None if unavailable / numpy-incompatible."""
    try:
        import mir_eval  # type: ignore

        return mir_eval
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Path + annotation parsing.
# --------------------------------------------------------------------------- #
def _resolve_path(manifest_path: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    manifest_relative = (manifest_path.parent / candidate).resolve()
    if manifest_relative.exists():
        return manifest_relative
    return (REPO_DIR / candidate).resolve()


def _parse_gtzan_rhythm(annotation_path: Path) -> dict[str, Any]:
    """Parse a GTZAN-Rhythm annotation into beats / downbeats / meter / tempo.

    Format: whitespace-delimited lines of ``<time_seconds> [beat_position]`` where
    beat_position == 1 marks a downbeat. Tolerates a one-column (beats-only) file
    and an optional sibling ``<stem>.downbeats`` file. The single highest-risk
    correctness surface in this harness — unit-tested directly.
    """
    times: list[float] = []
    positions: list[int] = []
    for line in Path(annotation_path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            t = float(parts[0])
        except ValueError:
            continue
        times.append(t)
        if len(parts) >= 2:
            try:
                positions.append(int(float(parts[1])))
            except ValueError:
                positions.append(0)
        else:
            positions.append(0)

    order = np.argsort(times)
    times = [times[i] for i in order]
    positions = [positions[i] for i in order]

    downbeats: list[float] = [t for t, p in zip(times, positions) if p == 1]
    sibling = Path(annotation_path).with_suffix(".downbeats")
    if not downbeats and sibling.exists():
        downbeats = sorted(
            float(line.split()[0])
            for line in sibling.read_text(encoding="utf-8").splitlines()
            if line.split()
        )

    meter = _infer_meter(times, downbeats, positions)
    tempo = None
    if len(times) >= 2:
        diffs = np.diff(np.asarray(times, dtype=np.float64))
        diffs = diffs[diffs > 0]
        if diffs.size:
            tempo = round(60.0 / float(np.median(diffs)), 3)

    return {"beats": times, "downbeats": downbeats, "meter": meter, "tempo": tempo}


def _infer_meter(times: list[float], downbeats: list[float], positions: list[int]) -> int | None:
    """Beats-per-bar from beats between consecutive downbeats; fall back to max position."""
    if downbeats and len(downbeats) >= 2 and times:
        time_to_index = {round(t, 6): i for i, t in enumerate(times)}
        db_indices = [time_to_index[round(d, 6)] for d in downbeats if round(d, 6) in time_to_index]
        if len(db_indices) >= 2:
            gaps = np.diff(np.asarray(sorted(db_indices), dtype=np.int64))
            gaps = gaps[gaps > 0]
            if gaps.size:
                return int(np.bincount(gaps).argmax())
    valid_positions = [p for p in positions if p > 0]
    if valid_positions:
        return int(max(valid_positions))
    return None


# --------------------------------------------------------------------------- #
# Metrics — mir_eval primary, hand-rolled fallback.
# --------------------------------------------------------------------------- #
def _trim(times: Any) -> list[float]:
    return [float(t) for t in sorted(float(x) for x in times) if float(t) >= TRIM_SECONDS]


def _handroll_f1(ref: list[float], est: list[float], window: float = F_MEASURE_WINDOW_S) -> float:
    """Greedy one-to-one onset matching (adapted from phase1_evaluation._match_notes)."""
    ref_sorted = sorted(ref)
    est_sorted = sorted(est)
    used = [False] * len(est_sorted)
    matched = 0
    for r in ref_sorted:
        for j, e in enumerate(est_sorted):
            if used[j]:
                continue
            if e < r - window:
                continue
            if e > r + window:
                break
            used[j] = True
            matched += 1
            break
    precision = matched / len(est_sorted) if est_sorted else (1.0 if not ref_sorted else 0.0)
    recall = matched / len(ref_sorted) if ref_sorted else 1.0
    if precision + recall == 0.0:
        return 0.0
    return (2.0 * precision * recall) / (precision + recall)


def _fmeasure(ref: Any, est: Any, mir, window: float = F_MEASURE_WINDOW_S) -> float:
    ref_t = _trim(ref)
    est_t = _trim(est)
    if mir is not None and ref_t and est_t:
        try:
            return float(
                mir.beat.f_measure(
                    np.asarray(ref_t, dtype=np.float64),
                    np.asarray(est_t, dtype=np.float64),
                    f_measure_threshold=window,
                )
            )
        except Exception:
            pass
    return _handroll_f1(ref_t, est_t, window)


def _continuity(ref: Any, est: Any, mir) -> dict[str, float] | None:
    if mir is None:
        return None
    ref_t = _trim(ref)
    est_t = _trim(est)
    if not ref_t or not est_t:
        return None
    try:
        cmlc, cmlt, amlc, amlt = mir.beat.continuity(
            np.asarray(ref_t, dtype=np.float64), np.asarray(est_t, dtype=np.float64)
        )
        return {"CMLt": float(cmlt), "AMLt": float(amlt)}
    except Exception:
        return None


def _info_gain(ref: Any, est: Any, mir) -> float | None:
    if mir is None:
        return None
    ref_t = _trim(ref)
    est_t = _trim(est)
    if not ref_t or not est_t:
        return None
    try:
        return float(mir.beat.information_gain(
            np.asarray(ref_t, dtype=np.float64), np.asarray(est_t, dtype=np.float64)
        ))
    except Exception:
        return None


def _tempo_from_beats(beats: Any) -> float | None:
    arr = np.asarray(sorted(float(b) for b in beats), dtype=np.float64)
    if arr.size < 2:
        return None
    diffs = np.diff(arr)
    diffs = diffs[diffs > 0]
    if diffs.size == 0:
        return None
    return 60.0 / float(np.median(diffs))


def _tempo_accuracy(ref_tempo: float | None, est_tempo: float | None) -> tuple[float | None, float | None]:
    if not ref_tempo or not est_tempo:
        return None, None

    def _within(value: float, target: float, tol: float = 0.04) -> bool:
        return abs(value - target) <= tol * target

    acc1 = 1.0 if _within(est_tempo, ref_tempo) else 0.0
    acc2 = 1.0 if any(_within(est_tempo, ref_tempo * m) for m in (1 / 3, 1 / 2, 1, 2, 3)) else 0.0
    return acc1, acc2


def _infer_meter_from_beats(beats: list[float], downbeats: list[float]) -> int:
    if not beats or len(downbeats) < 2:
        return 4
    times = sorted(float(b) for b in beats)
    time_to_index = {round(t, 6): i for i, t in enumerate(times)}
    db_idx = sorted(time_to_index[round(d, 6)] for d in downbeats if round(d, 6) in time_to_index)
    if len(db_idx) >= 2:
        gaps = np.diff(np.asarray(db_idx, dtype=np.int64))
        gaps = gaps[gaps > 0]
        if gaps.size:
            return int(np.bincount(gaps).argmax())
    return 4


def _downbeat_tolerant(ref_db: Any, est_beats: list[float], meter: int, mir) -> float:
    """Best downbeat F1 over all `meter` phase shifts of the method's own beat grid."""
    if not ref_db or not est_beats or meter < 1:
        return 0.0
    grid = sorted(float(b) for b in est_beats)
    return max(_fmeasure(ref_db, grid[k::meter], mir) for k in range(meter))


def _score_against_reference(ref: dict[str, Any], out: dict[str, Any], mir) -> dict[str, Any] | None:
    if out.get("status") != "completed" or not out.get("beats"):
        return None
    est_beats = out["beats"]
    est_db = out.get("downbeats") or []
    meter = out.get("meterUsed") or _infer_meter_from_beats(est_beats, est_db)
    continuity = _continuity(ref["beats"], est_beats, mir)
    info_gain = _info_gain(ref["beats"], est_beats, mir)
    acc1, acc2 = _tempo_accuracy(ref.get("tempo"), _tempo_from_beats(est_beats))
    return {
        "beatF1": round(_fmeasure(ref["beats"], est_beats, mir), 4),
        "beatCMLt": None if continuity is None else round(continuity["CMLt"], 4),
        "beatAMLt": None if continuity is None else round(continuity["AMLt"], 4),
        "beatInfoGain": None if info_gain is None else round(info_gain, 4),
        "downbeatF1Strict": round(_fmeasure(ref["downbeats"], est_db, mir), 4),
        "downbeatF1Tolerant": round(_downbeat_tolerant(ref["downbeats"], est_beats, meter, mir), 4),
        "tempoAcc1": acc1,
        "tempoAcc2": acc2,
    }


# --------------------------------------------------------------------------- #
# Methods (candidate runners).
# --------------------------------------------------------------------------- #
def _compute_asa_dsp(audio_path: Path) -> dict[str, Any] | None:
    """One Essentia pass shared by stride + kick_accent (ticks, detected meter, low band)."""
    _ensure_backend_on_path()
    try:
        from analyze_audio_io import load_mono
        from analyze_core import analyze_time_signature, extract_rhythm
        from analyze_rhythm import _extract_beat_loudness_data, _parse_meter
    except Exception as exc:
        return {"error": f"backend import failed: {exc}"}

    started = time.perf_counter()
    try:
        mono = load_mono(str(audio_path), 44100)
        rhythm = extract_rhythm(mono)
        if rhythm is None:
            return None
        ticks = np.asarray(rhythm.get("ticks", []), dtype=np.float64)
        time_signature = analyze_time_signature(rhythm, mono=mono, sample_rate=44100).get("timeSignature")
        detected_meter = _parse_meter(time_signature)
        beat_data = _extract_beat_loudness_data(mono, 44100, rhythm)
        low_band = (
            np.asarray(beat_data.get("lowBand", []), dtype=np.float64)
            if beat_data
            else np.asarray([], dtype=np.float64)
        )
        return {
            "ticks": ticks,
            "detectedMeter": int(detected_meter),
            "lowBand": low_band,
            "runtimeMs": round((time.perf_counter() - started) * 1000.0, 1),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _method_stride(asa: dict[str, Any]) -> dict[str, Any]:
    ticks = asa["ticks"]
    if ticks.size < 2:
        return _failed("stride", "insufficient_beats", asa.get("runtimeMs", 0.0))
    return {
        "status": "completed",
        "beats": ticks.tolist(),
        "downbeats": ticks[::4].tolist(),
        "meterUsed": 4,
        "meterSource": "fixed_4",
        "runtimeMs": asa.get("runtimeMs", 0.0),
        "reason": None,
    }


def _method_kick_accent(asa: dict[str, Any], meter: int, meter_source: str) -> dict[str, Any]:
    ticks = asa["ticks"]
    if ticks.size < 2:
        return _failed("kick_accent", "insufficient_beats", asa.get("runtimeMs", 0.0))
    _ensure_backend_on_path()
    from analyze_rhythm import _compute_downbeat_phase

    low_band = asa["lowBand"]
    if low_band.size >= meter:
        phase, confidence = _compute_downbeat_phase(low_band, meter)
    else:
        phase, confidence = 0, 0.0  # mirrors analyze_rhythm stride fallback
    return {
        "status": "completed",
        "beats": ticks.tolist(),
        "downbeats": ticks[phase::meter].tolist(),
        "meterUsed": int(meter),
        "meterSource": meter_source,
        "downbeatConfidence": round(float(confidence), 4),
        "downbeatPhase": int(phase),
        "runtimeMs": asa.get("runtimeMs", 0.0),
        "reason": None,
    }


def _method_beat_this(audio_path: Path, checkpoint: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from beat_this.inference import File2Beats  # type: ignore
    except Exception as exc:
        return _skipped("beat_this", f"beat_this not installed: {exc}")
    try:
        import torch  # type: ignore

        file2beats = File2Beats(checkpoint_path=checkpoint, dbn=False)
        beats, downbeats = file2beats(str(audio_path))
        return {
            "status": "completed",
            "beats": [float(x) for x in beats],
            "downbeats": [float(x) for x in downbeats],
            "meterUsed": None,
            "meterSource": "model",
            "runtimeMs": round((time.perf_counter() - started) * 1000.0, 1),
            "reason": None,
            "torchVersion": torch.__version__,
            "device": "cuda" if torch.cuda.is_available() else "cpu",
            "checkpoint": checkpoint,
        }
    except Exception as exc:
        return _failed("beat_this", str(exc), round((time.perf_counter() - started) * 1000.0, 1))


def _failed(method: str, reason: str, runtime_ms: float) -> dict[str, Any]:
    return {
        "status": "failed",
        "beats": None,
        "downbeats": None,
        "meterUsed": None,
        "meterSource": None,
        "runtimeMs": runtime_ms,
        "reason": reason,
    }


def _skipped(method: str, reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "beats": None,
        "downbeats": None,
        "meterUsed": None,
        "meterSource": "model" if method == "beat_this" else None,
        "runtimeMs": 0.0,
        "reason": reason,
    }


# --------------------------------------------------------------------------- #
# Aggregation + pass bar.
# --------------------------------------------------------------------------- #
def _mean(values: list[float]) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _summarize_method(clip_reports: list[dict[str, Any]], method: str, *, asa_only: bool) -> dict[str, Any]:
    metrics_rows: list[dict[str, Any]] = []
    completed = 0
    for clip in clip_reports:
        if asa_only and not clip.get("asaRelevant"):
            continue
        method_block = clip.get("methods", {}).get(method)
        if not method_block:
            continue
        if method_block.get("status") == "completed":
            completed += 1
        metrics = method_block.get("metrics")
        if metrics:
            metrics_rows.append(metrics)
    summary = {"clipsCompleted": completed, "clipsScored": len(metrics_rows)}
    for key in _METRIC_KEYS:
        summary[key] = _mean([row.get(key) for row in metrics_rows])
    return summary


def _meter_detection(clip_reports: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    exact = 0
    non_four_total = 0
    non_four_exact = 0
    confusion: dict[str, int] = {}
    for clip in clip_reports:
        truth = clip.get("annotation", {}).get("meter")
        detected = clip.get("asaDetectedMeter")
        if truth is None or detected is None:
            continue
        total += 1
        if int(truth) == int(detected):
            exact += 1
        if int(truth) != 4:
            non_four_total += 1
            if int(truth) == int(detected):
                non_four_exact += 1
        key = f"truth{int(truth)}->det{int(detected)}"
        confusion[key] = confusion.get(key, 0) + 1
    return {
        "clips": total,
        "exactMatchRate": round(exact / total, 4) if total else None,
        "nonFourFourClips": non_four_total,
        "nonFourFourExactMatchRate": round(non_four_exact / non_four_total, 4) if non_four_total else None,
        "confusion": confusion,
    }


def summarize_beat_gate(
    method_summaries_asa: dict[str, dict[str, Any]],
    asa_relevant_clip_count: int,
) -> dict[str, Any]:
    """Apply the pre-registered pass bar to the asaRelevant-subset summaries."""
    def _db(method: str) -> float | None:
        summary = method_summaries_asa.get(method) or {}
        return summary.get("downbeatF1Strict")

    def _beat(method: str) -> float | None:
        summary = method_summaries_asa.get(method) or {}
        return summary.get("beatF1")

    non_neural = [v for v in (_db("stride"), _db("kick_accent")) if v is not None]
    best_non_neural = max(non_neural) if non_neural else None
    bt_db = _db("beat_this")
    bt_beat = _beat("beat_this")
    ka_beat = _beat("kick_accent")

    underpowered = asa_relevant_clip_count < MIN_CLIPS_PRIMARY
    beat_this_present = bt_db is not None

    cond_downbeat_gain = (
        None if (bt_db is None or best_non_neural is None) else (bt_db - best_non_neural) >= ADOPT_MARGIN
    )
    cond_no_beat_regression = (
        None if (bt_beat is None or ka_beat is None) else bt_beat >= (ka_beat - BEAT_REGRESSION_TOLERANCE)
    )

    criteria = {
        "downbeatGainAtLeastMargin": cond_downbeat_gain,
        "noBeatRegression": cond_no_beat_regression,
        "asaSliceConfirms": None,  # set by the ASA-slice run (Phase D); pending on GTZAN
        "sufficientlyPowered": not underpowered,
    }

    if underpowered:
        recommendation = "underpowered"
    elif not beat_this_present:
        recommendation = "pending_beat_this"
    elif cond_downbeat_gain and cond_no_beat_regression:
        recommendation = "adopt_pending_asa_slice"
    else:
        recommendation = "keep_heuristic"

    return {
        "evaluatedOn": "asaRelevant_subset",
        "asaRelevantClipCount": asa_relevant_clip_count,
        "bestNonNeuralDownbeatF1": best_non_neural,
        "beatThisDownbeatF1": bt_db,
        "downbeatGain": None if (bt_db is None or best_non_neural is None) else round(bt_db - best_non_neural, 4),
        "adoptMargin": ADOPT_MARGIN,
        "successCriteria": criteria,
        "productRecommendation": recommendation,
    }


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def _score_clip(
    clip: dict[str, Any],
    manifest_path: Path,
    methods: tuple[str, ...],
    use_annotated_meter: bool,
    beat_this_checkpoint: str,
    mir,
) -> dict[str, Any]:
    audio_path = _resolve_path(manifest_path, clip["audioPath"])
    if not audio_path.exists():
        return {"id": clip.get("id"), "status": "skipped_audio_missing", "audioPath": str(audio_path)}
    annotation_path = _resolve_path(manifest_path, clip["annotationPath"])
    if not annotation_path.exists():
        return {"id": clip.get("id"), "status": "skipped_annotation_missing", "annotationPath": str(annotation_path)}

    ref = _parse_gtzan_rhythm(annotation_path)
    outputs: dict[str, Any] = {}
    asa: dict[str, Any] | None = None
    detected_meter: int | None = None

    if any(m in methods for m in NON_NEURAL_METHODS):
        asa = _compute_asa_dsp(audio_path)
        if asa is None or asa.get("error"):
            reason = (asa or {}).get("error", "asa_dsp_failed")
            for method in (m for m in methods if m in NON_NEURAL_METHODS):
                outputs[method] = _failed(method, reason, 0.0)
        else:
            detected_meter = asa.get("detectedMeter")
            if "stride" in methods:
                outputs["stride"] = _method_stride(asa)
            if "kick_accent" in methods:
                if use_annotated_meter and ref.get("meter"):
                    meter, meter_source = int(ref["meter"]), "annotated"
                else:
                    meter, meter_source = int(asa["detectedMeter"]), "asa_detected"
                outputs["kick_accent"] = _method_kick_accent(asa, meter, meter_source)

    if "beat_this" in methods:
        outputs["beat_this"] = _method_beat_this(audio_path, beat_this_checkpoint)

    scored = {
        method: {**out, "metrics": _score_against_reference(ref, out, mir)}
        for method, out in outputs.items()
    }
    return {
        "id": clip.get("id"),
        "genre": clip.get("genre"),
        "asaRelevant": bool(clip.get("asaRelevant")),
        "status": "evaluated",
        "annotation": {
            "beatCount": len(ref["beats"]),
            "downbeatCount": len(ref["downbeats"]),
            "meter": ref.get("meter"),
            "tempo": ref.get("tempo"),
        },
        "asaDetectedMeter": detected_meter,
        "methods": scored,
    }


def run_beat_evaluation(
    *,
    manifest_path: str | Path,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    methods: tuple[str, ...] = DEFAULT_METHODS,
    use_annotated_meter: bool = False,
    beat_this_checkpoint: str = "final0",
) -> dict[str, Any]:
    from datetime import datetime, timezone

    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clips = manifest.get("clips", [])
    if not isinstance(clips, list) or not clips:
        raise ValueError("Beat-eval manifest must define a non-empty 'clips' list.")

    mir = _load_mir_eval()
    clip_reports = [
        _score_clip(clip, manifest_path, methods, use_annotated_meter, beat_this_checkpoint, mir)
        for clip in clips
    ]
    evaluated = [c for c in clip_reports if c.get("status") == "evaluated"]

    method_summaries_full = {m: _summarize_method(evaluated, m, asa_only=False) for m in methods}
    method_summaries_asa = {m: _summarize_method(evaluated, m, asa_only=True) for m in methods}
    asa_relevant_count = sum(1 for c in evaluated if c.get("asaRelevant"))

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "manifestPath": str(manifest_path),
        "datasetName": manifest.get("datasetName"),
        "researchOnly": True,
        "metricsBackend": "mir_eval" if mir is not None else "handrolled_fallback",
        "config": {
            "methods": list(methods),
            "useAnnotatedMeter": use_annotated_meter,
            "beatThisCheckpoint": beat_this_checkpoint,
            "fMeasureWindowS": F_MEASURE_WINDOW_S,
            "trimSeconds": TRIM_SECONDS,
            "adoptMargin": ADOPT_MARGIN,
            "beatRegressionTolerance": BEAT_REGRESSION_TOLERANCE,
        },
        "clipCount": len(clips),
        "evaluatedClipCount": len(evaluated),
        "asaRelevantClipCount": asa_relevant_count,
        "meterDetection": _meter_detection(evaluated),
        "methodSummariesFull": method_summaries_full,
        "methodSummariesAsaRelevant": method_summaries_asa,
        "gate": summarize_beat_gate(method_summaries_asa, asa_relevant_count),
        "clips": clip_reports,
    }

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report
