"""Local-only quality summary for Phase 1 musical fundamentals.

This module does not measure audio. It summarizes how much authority the
existing local DSP output has for core musical facts so downstream code can
avoid presenting weak estimates as settled truth.
"""

from __future__ import annotations

from typing import Any


QUALITY_SCHEMA_VERSION = "fundamentals-quality.v1"
TARGET_PROFILE = "electronic_ableton_v1"

STATUS_AUTHORITATIVE = "authoritative"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_FAILED = "failed"
STATUS_NOT_RUN = "not_run"


def build_fundamentals_quality(
    payload: dict[str, Any],
    *,
    analysis_mode: str = "full",
) -> dict[str, Any]:
    """Build a compact local-authority summary for core musical fields."""
    domains = {
        "tempo": _tempo_quality(payload),
        "beatGrid": _beat_grid_quality(payload),
        "downbeats": _downbeat_quality(payload),
        "meter": _meter_quality(payload),
        "key": _key_quality(payload),
        "chords": _chord_quality(payload),
        "percussion": _percussion_quality(payload),
        "transcription": _transcription_quality(payload),
    }
    return {
        "schemaVersion": QUALITY_SCHEMA_VERSION,
        "targetProfile": TARGET_PROFILE,
        "analysisMode": analysis_mode,
        "localOnly": True,
        "llmExcluded": True,
        "overallStatus": _overall_status(domains),
        "domains": domains,
    }


def _domain(
    *,
    status: str,
    plain: str,
    source: str | None,
    confidence: float | None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "plainEnglish": plain,
        "source": source,
        "confidence": _confidence(confidence),
        "evidence": evidence or {},
    }


def _confidence(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric != numeric:
            return None
        return round(min(max(numeric, 0.0), 1.0), 3)
    return None


def _status_from_confidence(
    confidence: Any,
    *,
    high: float = 0.7,
    present: bool = True,
) -> str:
    if not present:
        return STATUS_FAILED
    score = _confidence(confidence)
    if score is None:
        return STATUS_AMBIGUOUS
    return STATUS_AUTHORITATIVE if score >= high else STATUS_AMBIGUOUS


def _tempo_quality(payload: dict[str, Any]) -> dict[str, Any]:
    bpm = payload.get("bpm")
    confidence = payload.get("bpmConfidence")
    agreement = payload.get("bpmAgreement")
    source = payload.get("bpmSource")
    if not isinstance(bpm, (int, float)):
        return _domain(
            status=STATUS_FAILED,
            plain="Tempo was not measured locally.",
            source=None,
            confidence=None,
            evidence={"bpm": bpm},
        )
    status = _status_from_confidence(confidence)
    if agreement is False and payload.get("bpmDoubletime") is not True:
        status = STATUS_AMBIGUOUS
    elif (
        status == STATUS_AMBIGUOUS
        and agreement is True
        and isinstance(confidence, (int, float))
        and confidence >= 0.5
    ):
        # Two independent estimators (RhythmExtractor2013 + Percival) agree
        # within tolerance — the cross-check itself is the settling evidence
        # even when the extractor's own confidence sits mid-range. Marking
        # this "cross-check not strong enough" was factually wrong.
        status = STATUS_AUTHORITATIVE
    return _domain(
        status=status,
        plain=(
            "Tempo was measured locally."
            if status == STATUS_AUTHORITATIVE
            else "Tempo was measured locally, but the cross-check is not strong enough to treat it as settled."
        ),
        source=str(source) if source else "rhythm_extractor",
        confidence=confidence,
        evidence={
            "bpm": bpm,
            "bpmPercival": payload.get("bpmPercival"),
            "bpmAgreement": agreement,
            "bpmDoubletime": payload.get("bpmDoubletime"),
            "bpmRawOriginal": payload.get("bpmRawOriginal"),
        },
    )


def _beat_grid_quality(payload: dict[str, Any]) -> dict[str, Any]:
    rhythm = payload.get("rhythmDetail") if isinstance(payload.get("rhythmDetail"), dict) else None
    beat_grid = rhythm.get("beatGrid") if rhythm else None
    if not isinstance(beat_grid, list) or len(beat_grid) < 2:
        return _domain(
            status=STATUS_NOT_RUN,
            plain="Beat grid was not produced in this analysis mode.",
            source=None,
            confidence=None,
            evidence={"beatCount": 0},
        )
    confidence = payload.get("bpmConfidence")
    # Beat-grid authority reflects whether beats were reliably located, which the
    # tempo detector itself treats as settled at raw confidence >= 2.0
    # (normalized 0.4 — see analyze_core.analyze_bpm). Reusing the tempo domain's
    # stricter 0.7 here wrongly marked ordinary, well-tracked grids "ambiguous",
    # forcing every beat-grid-citing Phase 2 recommendation to be hedged.
    return _domain(
        status=_status_from_confidence(confidence, high=0.4),
        plain="Beat grid was derived locally from the measured tempo and beat tracker.",
        source=str(rhythm.get("source") or "rhythm_extractor"),
        confidence=confidence,
        evidence={
            "beatCount": len(beat_grid),
            "firstBeatSec": beat_grid[0],
            "lastBeatSec": beat_grid[-1],
        },
    )


def _downbeat_quality(payload: dict[str, Any]) -> dict[str, Any]:
    rhythm = payload.get("rhythmDetail") if isinstance(payload.get("rhythmDetail"), dict) else None
    downbeats = rhythm.get("downbeats") if rhythm else None
    confidence = rhythm.get("downbeatConfidence") if rhythm else None
    source = rhythm.get("downbeatSource") if rhythm else None
    if not isinstance(downbeats, list) or len(downbeats) == 0:
        return _domain(
            status=STATUS_NOT_RUN,
            plain="Downbeats were not produced in this analysis mode.",
            source=None,
            confidence=None,
            evidence={"downbeatCount": 0},
        )
    status = _status_from_confidence(confidence, high=0.6)
    return _domain(
        status=status,
        plain=(
            "Bar starts were located locally."
            if status == STATUS_AUTHORITATIVE
            else "The beat grid is usable, but exact bar starts are uncertain."
        ),
        source=str(source) if source else "rhythm_detail",
        confidence=confidence,
        evidence={"downbeatCount": len(downbeats)},
    )


def _meter_quality(payload: dict[str, Any]) -> dict[str, Any]:
    meter = payload.get("timeSignature")
    source = payload.get("timeSignatureSource")
    confidence = payload.get("timeSignatureConfidence")
    if not isinstance(meter, str) or not meter:
        return _domain(
            status=STATUS_FAILED,
            plain="Meter was not measured locally.",
            source=None,
            confidence=None,
            evidence={"timeSignature": meter},
        )
    assumed = source == "assumed_four_four" or _confidence(confidence) == 0.0
    status = STATUS_AMBIGUOUS if assumed else _status_from_confidence(confidence, high=0.5)
    return _domain(
        status=status,
        plain=(
            "Meter was detected locally."
            if status == STATUS_AUTHORITATIVE
            else "Meter is a local working assumption, not a confirmed reading."
        ),
        source=str(source) if source else "time_signature",
        confidence=confidence,
        evidence={"timeSignature": meter},
    )


def _key_quality(payload: dict[str, Any]) -> dict[str, Any]:
    key = payload.get("key")
    confidence = payload.get("keyConfidence")
    if not isinstance(key, str) or not key:
        return _domain(
            status=STATUS_FAILED,
            plain="Key was not measured locally.",
            source=str(payload.get("keyProfile") or "edma"),
            confidence=None,
            evidence={"key": key},
        )
    status = _status_from_confidence(confidence, high=0.7)
    return _domain(
        status=status,
        plain=(
            "Key was measured locally."
            if status == STATUS_AUTHORITATIVE
            else "Key was estimated locally and should be checked by ear."
        ),
        source=str(payload.get("keyProfile") or "edma"),
        confidence=confidence,
        evidence={
            "key": key,
            "tuningFrequency": payload.get("tuningFrequency"),
            "tuningCents": payload.get("tuningCents"),
        },
    )


def _chord_quality(payload: dict[str, Any]) -> dict[str, Any]:
    chord = payload.get("chordDetail") if isinstance(payload.get("chordDetail"), dict) else None
    if chord is None:
        return _domain(
            status=STATUS_NOT_RUN,
            plain="Chord analysis was not run in this analysis mode.",
            source=None,
            confidence=None,
            evidence={},
        )
    confidence = chord.get("chordStrength")
    agreement = chord.get("chordTimelineAgreement")
    status = _status_from_confidence(confidence, high=0.7)
    if agreement is False:
        status = STATUS_AMBIGUOUS
    return _domain(
        status=status,
        plain=(
            "Chord labels were measured locally and agree across detectors."
            if status == STATUS_AUTHORITATIVE
            else "Chord labels are local estimates; detector disagreement or low strength means they should be treated carefully."
        ),
        source=str(chord.get("chordTimelineSource") or "essentia_chords"),
        confidence=confidence,
        evidence={
            "chordStrength": confidence,
            "chordTimelineAgreement": agreement,
            "chordChangeCount": chord.get("chordChangeCount"),
            "dominantChords": chord.get("dominantChords"),
        },
    )


def _percussion_quality(payload: dict[str, Any]) -> dict[str, Any]:
    kick = payload.get("kickDetail") if isinstance(payload.get("kickDetail"), dict) else None
    snare = payload.get("snareDetail") if isinstance(payload.get("snareDetail"), dict) else None
    hihat = payload.get("hihatDetail") if isinstance(payload.get("hihatDetail"), dict) else None
    has_any = any(isinstance(item, dict) for item in (kick, snare, hihat))
    if not has_any:
        return _domain(
            status=STATUS_NOT_RUN,
            plain="Percussion detail was not run in this analysis mode.",
            source=None,
            confidence=None,
            evidence={},
        )
    kick_count = kick.get("kickCount") if kick else None
    snare_count = snare.get("hitCount") if snare else None
    hihat_count = hihat.get("hitCount") if hihat else None
    confidence = 0.6
    if isinstance(kick_count, int) and kick_count > 0:
        confidence = 0.7
    status = STATUS_AUTHORITATIVE if confidence >= 0.7 else STATUS_AMBIGUOUS
    return _domain(
        status=status,
        plain=(
            "Percussion events were measured locally."
            if status == STATUS_AUTHORITATIVE
            else "Percussion detail is local, but not all drum families have strong evidence."
        ),
        source="local_band_and_stem_detectors",
        confidence=confidence,
        evidence={
            "kickCount": kick_count,
            "kickFundamentalHz": kick.get("fundamentalHz") if kick else None,
            "snareHitCount": snare_count,
            "hihatHitCount": hihat_count,
        },
    )


def _transcription_quality(payload: dict[str, Any]) -> dict[str, Any]:
    detail = (
        payload.get("transcriptionDetail")
        if isinstance(payload.get("transcriptionDetail"), dict)
        else None
    )
    if detail is None:
        return _domain(
            status=STATUS_NOT_RUN,
            plain="Monophonic note transcription was not run.",
            source=None,
            confidence=None,
            evidence={},
        )
    confidence = detail.get("averageConfidence")
    full_mix = detail.get("fullMixFallback") is True
    status = _status_from_confidence(confidence, high=0.75)
    if full_mix and status == STATUS_AUTHORITATIVE:
        status = STATUS_AMBIGUOUS
    return _domain(
        status=status,
        plain=(
            "Monophonic notes were translated locally from stem-aware pitch tracking."
            if status == STATUS_AUTHORITATIVE
            else "Note transcription is local, but it is approximate and should not be treated as a complete polyphonic score."
        ),
        source=str(detail.get("transcriptionMethod") or "torchcrepe"),
        confidence=confidence,
        evidence={
            "noteCount": detail.get("noteCount"),
            "fullMixFallback": full_mix,
            "perStemAverageConfidence": detail.get("perStemAverageConfidence"),
        },
    )


def _overall_status(domains: dict[str, dict[str, Any]]) -> str:
    # Domains that were not run in this analysis mode carry no quality signal —
    # a clean standard run never runs transcription, and fast mode skips several
    # domains. Excluding them keeps a fully-measured run from being dragged to
    # "ambiguous" by a domain that simply wasn't executed.
    ran = [
        str(domain.get("status"))
        for domain in domains.values()
        if str(domain.get("status")) != STATUS_NOT_RUN
    ]
    if not ran:
        return STATUS_NOT_RUN
    if STATUS_FAILED in ran:
        return STATUS_FAILED
    if STATUS_AMBIGUOUS in ran:
        return STATUS_AMBIGUOUS
    return STATUS_AUTHORITATIVE
