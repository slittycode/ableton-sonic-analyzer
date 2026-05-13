#!/usr/bin/env python3
"""Track 2 audit pass 1.

Loads a Phase 1 measurement JSON for a real bench track and produces a
structured audit report comparing ASA's measurements against listener
ground-truth values declared inline below.

Audit-priority ordering matches the plan
(.claude/plans/okay-im-quite-worried-partitioned-reddy.md, Track 2 section).

Outputs a markdown report to .runtime/reports/audit_pass1_<date>.md.

Status verdicts:
  PASS              — measurement falls inside tolerance / matches ground truth
  WARN              — measurement is sane but outside tight tolerance OR confidence is honestly low
  FAIL              — confident wrong answer (the actual product risk)
  NEEDS_LISTENER    — requires human ground-truth comparison; documented for later pass
  N/A               — field structurally absent

NOTE: this script reads the raw analyze.py output (pre-HTTP-normalization).
Spectral-detail fields use their raw names (spectralCentroid, etc.) here.
The normalizer in server_phase1.py renames these to *Mean for the frontend
contract — but for raw-JSON auditing we use the analyzer-side names.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GroundTruth:
    """Per-track ground-truth values + audit tolerances."""

    label: str
    audio_relpath: str

    bpm_listener: float | None = None
    bpm_tolerance: float = 1.0

    key_listener: str | None = None

    lufs_integrated_expected_min: float = -30.0
    lufs_integrated_expected_max: float = 0.0
    lufs_integrated_listener: float | None = None
    lufs_tolerance: float = 0.5

    sub_bass_correlation_expected_min: float = 0.5
    sub_bass_correlation_listener: float | None = None
    stereo_width_listener: float | None = None

    time_signature_listener: str | None = None

    has_acid_listener: bool | None = None
    has_supersaw_listener: bool | None = None
    has_kick_listener: bool | None = None
    has_bass_listener: bool | None = None
    has_vocal_listener: bool | None = None
    has_reverb_listener: bool | None = None
    has_sidechain_listener: bool | None = None

    kick_count_per_sec_listener_low: float | None = None
    kick_count_per_sec_listener_high: float | None = None

    notes: list[str] = field(default_factory=list)


def _get(payload: dict, dotted: str, default: Any = None) -> Any:
    cur: Any = payload
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


# ---------- BPM ----------
def _audit_bpm(p: dict, gt: GroundTruth) -> list[tuple[str, str, str]]:
    bpm = _get(p, "bpm")
    src = _get(p, "bpmSource")
    conf = _get(p, "bpmConfidence")
    pc = _get(p, "bpmPercival")
    rows: list[tuple[str, str, str]] = []
    rows.append(("bpm", f"{bpm:.2f} (src={src}, conf={conf})" if bpm else "None",
                 _bpm_verdict(bpm, gt)))
    if pc is not None:
        rows.append(("bpmPercival cross-check", f"{pc:.2f}", _pc_verdict(bpm, pc)))
    else:
        rows.append(("bpmPercival cross-check", "absent", "N/A"))
    return rows


def _bpm_verdict(bpm: float | None, gt: GroundTruth) -> str:
    if bpm is None:
        return "FAIL — bpm is None"
    if gt.bpm_listener is None:
        return f"NEEDS_LISTENER — {bpm:.2f} in 40-220 plausible range"
    diff = abs(bpm - gt.bpm_listener)
    if diff <= gt.bpm_tolerance:
        return f"PASS — within ±{gt.bpm_tolerance:.1f} of listener {gt.bpm_listener:.2f}"
    if abs(bpm - gt.bpm_listener * 2) <= 2 or abs(bpm * 2 - gt.bpm_listener) <= 2:
        return f"FAIL — possible doubletime: ASA {bpm:.2f} vs listener {gt.bpm_listener:.2f}"
    return f"WARN — {diff:.2f} BPM off from listener {gt.bpm_listener:.2f}"


def _pc_verdict(bpm: float | None, pc: float) -> str:
    if bpm is None:
        return "N/A"
    if abs(bpm - pc) <= 1.5:
        return "PASS — Percival agrees within 1.5 BPM"
    if abs(bpm - pc * 2) <= 2 or abs(bpm * 2 - pc) <= 2:
        return f"WARN — Percival ratio cross-check suggests doubletime ({pc:.2f})"
    return f"WARN — Percival disagreement: {pc:.2f} vs RhythmExtractor {bpm:.2f}"


# ---------- Key ----------
def _audit_key(p: dict, gt: GroundTruth) -> list[tuple[str, str, str]]:
    key = _get(p, "key")
    conf = _get(p, "keyConfidence")
    src = _get(p, "keySource")
    return [
        ("key", f"{key} (src={src})", _key_verdict(key, conf, gt)),
        ("keyConfidence", f"{conf}", _key_conf_verdict(key, conf, gt)),
    ]


def _key_verdict(key: str | None, conf: float | None, gt: GroundTruth) -> str:
    if key is None:
        return "FAIL — key is None"
    if gt.key_listener is None:
        return "NEEDS_LISTENER — listener key not declared"
    if gt.key_listener.lower() in ("modal", "atonal", "modal/atonal"):
        return f"PASS — modal material correctly hedged (conf {conf:.2f} < 0.5)" if conf is not None and conf < 0.5 \
            else f"WARN — modal material but ASA reports confident key {key} (conf {conf})"
    if key.strip().lower() == gt.key_listener.strip().lower():
        return f"PASS — matches listener key {gt.key_listener}"
    return f"FAIL — ASA says {key}, listener says {gt.key_listener}"


def _key_conf_verdict(key: str | None, conf: float | None, gt: GroundTruth) -> str:
    if conf is None:
        return "FAIL — keyConfidence is None"
    if key is None or gt.key_listener is None:
        return "N/A"
    listener = gt.key_listener.strip().lower()
    asa = key.strip().lower()
    if listener in ("modal", "atonal", "modal/atonal"):
        return "PASS" if conf < 0.5 else "FAIL — should be honestly low for modal material"
    if asa == listener:
        return "PASS — confident on a correct match" if conf >= 0.5 else "WARN — correct but unhedged-low"
    return "FAIL — high confidence on a wrong answer" if conf >= 0.6 else "PASS — wrong but honest about it"


# ---------- LUFS ----------
def _audit_lufs(p: dict, gt: GroundTruth) -> list[tuple[str, str, str]]:
    lufs = _get(p, "lufsIntegrated")
    rows: list[tuple[str, str, str]] = [("lufsIntegrated", f"{lufs}", _lufs_verdict(lufs, gt))]
    curve = _get(p, "lufsCurve") or {}
    short = curve.get("shortTerm") or []
    momentary = curve.get("momentary") or []
    if short:
        st_vals = [pt.get("lufs") for pt in short if pt.get("lufs") is not None]
        if st_vals:
            rows.append((
                "lufsCurve.shortTerm range",
                f"min {min(st_vals):.2f}, max {max(st_vals):.2f}, points {len(short)}",
                _lufs_curve_verdict(st_vals, lufs),
            ))
    if momentary:
        rows.append(("lufsCurve.momentary points", f"{len(momentary)}",
                     "PASS" if 50 <= len(momentary) <= 1000 else "WARN — outside 50-1000"))
    return rows


def _lufs_verdict(lufs: float | None, gt: GroundTruth) -> str:
    if lufs is None:
        return "FAIL — lufsIntegrated is None"
    if not (gt.lufs_integrated_expected_min <= lufs <= gt.lufs_integrated_expected_max):
        return f"FAIL — {lufs} outside sane range [{gt.lufs_integrated_expected_min}, {gt.lufs_integrated_expected_max}]"
    if gt.lufs_integrated_listener is not None:
        diff = abs(lufs - gt.lufs_integrated_listener)
        return f"PASS — within ±{gt.lufs_tolerance} of listener {gt.lufs_integrated_listener}" if diff <= gt.lufs_tolerance \
            else f"WARN — {diff:.2f} LU off from listener {gt.lufs_integrated_listener}"
    return "PASS — in sane range (NEEDS_LISTENER for tight tolerance)"


def _lufs_curve_verdict(vals: list[float], integrated: float | None) -> str:
    if integrated is None:
        return "N/A"
    mn, mx = min(vals), max(vals)
    return f"PASS — integrated {integrated:.2f} within short-term range" if mn - 1 <= integrated <= mx + 1 \
        else f"WARN — integrated {integrated:.2f} outside short-term [{mn:.2f}, {mx:.2f}]"


# ---------- Spectral balance ----------
EXPECTED_BANDS = ["subBass", "lowBass", "lowMids", "mids", "upperMids", "highs", "brilliance"]


def _audit_spectral_balance(p: dict) -> list[tuple[str, str, str]]:
    bal = _get(p, "spectralBalance") or {}
    rows: list[tuple[str, str, str]] = []
    for band in EXPECTED_BANDS:
        v = bal.get(band)
        if v is None:
            rows.append((f"spectralBalance.{band}", "None", "FAIL"))
        elif not (-80 < v < 20):
            rows.append((f"spectralBalance.{band}", f"{v:.2f} dB", "FAIL — outside [-80, 20] dB sanity"))
        else:
            rows.append((f"spectralBalance.{band}", f"{v:.2f} dB", "PASS"))
    ts = p.get("spectralBalanceTimeSeries") or []
    if ts:
        rows.append(("spectralBalanceTimeSeries length", f"{len(ts)} points",
                     "PASS" if 100 <= len(ts) <= 500 else "WARN — outside 100-500"))
        first = ts[0] if ts else {}
        missing = [b for b in EXPECTED_BANDS if b not in first]
        rows.append(("spectralBalanceTimeSeries band coverage",
                     f"first-row missing: {missing or 'none'}",
                     "PASS" if not missing else "FAIL"))
    else:
        rows.append(("spectralBalanceTimeSeries", "absent or empty",
                     "FAIL — new Phase 1.A field expected"))
    return rows


# ---------- Stereo ----------
def _audit_stereo(p: dict, gt: GroundTruth) -> list[tuple[str, str, str]]:
    stereo = _get(p, "stereoDetail") or {}
    rows: list[tuple[str, str, str]] = []
    sw = stereo.get("stereoWidth")
    rows.append(("stereoDetail.stereoWidth", f"{sw}", _stereo_width_verdict(sw, gt)))
    sc = stereo.get("stereoCorrelation")
    rows.append(("stereoDetail.stereoCorrelation", f"{sc}",
                 "PASS" if sc is not None and -1.0 <= sc <= 1.0 else "FAIL"))
    sub = stereo.get("subBassCorrelation")
    rows.append(("stereoDetail.subBassCorrelation", f"{sub}", _sub_bass_verdict(sub, gt)))
    bands = stereo.get("bandCorrelations") or {}
    if bands:
        missing = [b for b in EXPECTED_BANDS if b not in bands]
        present_vals = [(b, bands[b]) for b in EXPECTED_BANDS if bands.get(b) is not None]
        sane = all(-1 <= v <= 1 for _, v in present_vals)
        rows.append((
            "stereoDetail.bandCorrelations coverage",
            f"present={len(present_vals)}/7, missing={missing or 'none'}",
            "PASS" if not missing and sane else "WARN",
        ))
    else:
        rows.append(("stereoDetail.bandCorrelations", "absent",
                     "FAIL — new Phase 1.C field expected"))
    curve = stereo.get("correlationCurve") or []
    rows.append(("stereoDetail.correlationCurve", f"{len(curve)} points",
                 "PASS" if 30 <= len(curve) <= 500 else "WARN — outside 30-500"))
    return rows


def _stereo_width_verdict(sw: float | None, gt: GroundTruth) -> str:
    if sw is None:
        return "FAIL — None"
    if not (0 <= sw <= 2.5):
        return "FAIL — outside sane [0, 2.5]"
    if gt.stereo_width_listener is not None:
        diff = abs(sw - gt.stereo_width_listener)
        return "PASS" if diff <= 0.15 else f"WARN — {diff:.2f} off from listener {gt.stereo_width_listener}"
    return "PASS — in sane range (NEEDS_LISTENER tighter)"


def _sub_bass_verdict(sub: float | None, gt: GroundTruth) -> str:
    if sub is None:
        return "FAIL — None"
    if not (-1 <= sub <= 1):
        return "FAIL — outside [-1, 1]"
    if sub < gt.sub_bass_correlation_expected_min:
        return f"WARN — sub-bass correlation {sub:.2f} below {gt.sub_bass_correlation_expected_min} expected for modern mixes"
    return f"PASS — sub-bass correlation {sub:.2f} consistent with mono-centered bass"


# ---------- Kick / Bass ----------
def _audit_kick(p: dict, gt: GroundTruth, duration_sec: float | None) -> list[tuple[str, str, str]]:
    kd = _get(p, "kickDetail") or {}
    rows: list[tuple[str, str, str]] = []
    fund = kd.get("fundamentalHz")
    rows.append(("kickDetail.fundamentalHz", f"{fund}",
                 "PASS — in 30-120 Hz typical" if fund and 30 <= fund <= 120 else "WARN — outside 30-120 Hz typical"))
    kc = kd.get("kickCount")
    if kc is not None and duration_sec:
        density = kc / duration_sec
        rows.append((
            "kickDetail.kickCount density",
            f"{kc} kicks / {duration_sec:.1f}s = {density:.2f} kicks/s",
            _kick_density_verdict(density, gt),
        ))
    else:
        rows.append(("kickDetail.kickCount density", "kc or duration unavailable", "N/A"))
    distorted = kd.get("isDistorted")
    rows.append(("kickDetail.isDistorted (raw flag)", f"{distorted}",
                 "PASS — categorical bool" if isinstance(distorted, bool) else "WARN"))
    return rows


def _kick_density_verdict(density: float, gt: GroundTruth) -> str:
    if gt.kick_count_per_sec_listener_low is None or gt.kick_count_per_sec_listener_high is None:
        if density > 5.0:
            return f"FAIL — {density:.2f} kicks/s unphysically high (likely transient miscount; Codex PDF finding)"
        if 1.5 <= density <= 5.0:
            return "PASS — plausible for typical electronic music"
        return f"WARN — {density:.2f} kicks/s is low; possible miss"
    if gt.kick_count_per_sec_listener_low <= density <= gt.kick_count_per_sec_listener_high:
        return f"PASS — within listener-declared {gt.kick_count_per_sec_listener_low}-{gt.kick_count_per_sec_listener_high} kicks/s"
    return f"FAIL — outside listener-declared {gt.kick_count_per_sec_listener_low}-{gt.kick_count_per_sec_listener_high} kicks/s"


def _audit_bass(p: dict) -> list[tuple[str, str, str]]:
    bd = _get(p, "bassDetail") or {}
    rows: list[tuple[str, str, str]] = []
    fund = bd.get("fundamentalHz")
    rows.append(("bassDetail.fundamentalHz", f"{fund}",
                 "PASS" if fund and 30 <= fund <= 350 else "WARN — outside 30-350 Hz typical"))
    avg_decay_ms = bd.get("averageDecayMs")
    rows.append(("bassDetail.averageDecayMs", f"{avg_decay_ms}", _bass_decay_verdict(avg_decay_ms)))
    tc = bd.get("transientCount")
    tr = bd.get("transientRatio")
    rows.append(("bassDetail.transientCount / transientRatio", f"{tc} / {tr}",
                 "PASS" if tr is not None and 0 <= tr <= 10 else "WARN"))
    return rows


def _bass_decay_verdict(avg_decay_ms: float | None) -> str:
    if avg_decay_ms is None:
        return "FAIL — averageDecayMs is None"
    if avg_decay_ms == 0 or avg_decay_ms == 0.0:
        return "FAIL — Codex PDF finding reproduced: averageDecayMs == 0 ms is unphysical for sustained bass"
    if 30 <= avg_decay_ms <= 3000:
        return f"PASS — {avg_decay_ms} ms decay is plausible"
    return f"WARN — {avg_decay_ms} ms outside typical 30-3000 ms"


# ---------- Sidechain ----------
def _audit_sidechain(p: dict) -> list[tuple[str, str, str]]:
    sd = _get(p, "sidechainDetail") or {}
    rows: list[tuple[str, str, str]] = []
    rate = sd.get("pumpingRate")
    rows.append(("sidechainDetail.pumpingRate", f"{rate}",
                 "PASS — categorical" if rate else "WARN — null (no rhythm assigned)"))
    pump_conf = sd.get("pumpingConfidence")
    rows.append(("sidechainDetail.pumpingConfidence", f"{pump_conf}", _pump_conf_verdict(pump_conf)))
    strength = sd.get("pumpingStrength")
    rows.append(("sidechainDetail.pumpingStrength", f"{strength}",
                 "PASS — numeric" if isinstance(strength, (int, float)) and 0 <= strength <= 1.5 else "WARN"))
    regularity = sd.get("pumpingRegularity")
    rows.append(("sidechainDetail.pumpingRegularity", f"{regularity}",
                 "PASS — numeric" if regularity is None or isinstance(regularity, (int, float)) else "WARN"))
    env = sd.get("envelopeShape") or []
    rows.append(("sidechainDetail.envelopeShape length", f"{len(env)} samples",
                 "PASS" if 12 <= len(env) <= 64 else "WARN — outside 12-64"))
    return rows


def _pump_conf_verdict(pc: float | None) -> str:
    if pc is None:
        return "N/A"
    return f"PASS — {pc:.2f} in [0,1]" if 0.0 <= pc <= 1.0 else f"FAIL — {pc} outside [0,1]"


# ---------- Detectors ----------
DETECTOR_FLAGS = [
    ("acidDetail", "isAcid", "has_acid_listener"),
    ("supersawDetail", "isSupersaw", "has_supersaw_listener"),
    ("kickDetail", "isDistorted", None),  # there's no "is there a kick" flag — only "is the kick distorted"
    ("bassDetail", None, None),  # bassDetail has no presence-flag — its type/grooveType fields imply presence
    ("vocalDetail", "hasVocals", "has_vocal_listener"),
    ("reverbDetail", "isWet", "has_reverb_listener"),
]


def _audit_detectors(p: dict, gt: GroundTruth) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for det_path, flag_field, gt_attr in DETECTOR_FLAGS:
        det = _get(p, det_path) or {}
        if flag_field is None:
            # No presence-flag for this detector; report type/groove only
            type_or_groove = det.get("type") or det.get("grooveType")
            rows.append((f"{det_path} (no presence flag)", f"type/groove={type_or_groove}",
                         "N/A — detector has no boolean presence flag"))
            continue
        flag = det.get(flag_field)
        conf = det.get("confidence")
        observed = f"{flag_field}={flag}, confidence={conf}"
        listener = getattr(gt, gt_attr) if gt_attr else None
        if listener is None:
            rows.append((f"{det_path}.{flag_field}", observed, "NEEDS_LISTENER"))
            continue
        if flag is None:
            rows.append((f"{det_path}.{flag_field}", observed, "FAIL — flag is None"))
            continue
        if bool(flag) == bool(listener):
            rows.append((f"{det_path}.{flag_field}", observed, f"PASS — matches listener ({listener})"))
        else:
            sev = "FAIL" if (conf is None or conf >= 0.5) else "WARN"
            rows.append((f"{det_path}.{flag_field}", observed,
                         f"{sev} — listener says {listener}, conf {conf}"))
    return rows


# ---------- Time signature ----------
def _audit_time_signature(p: dict, gt: GroundTruth) -> list[tuple[str, str, str]]:
    ts = _get(p, "timeSignature")
    src = _get(p, "timeSignatureSource")
    conf = _get(p, "timeSignatureConfidence")
    return [("timeSignature", f"{ts} (src={src}, conf={conf})",
             _time_sig_verdict(ts, src, conf, gt))]


def _time_sig_verdict(ts: str | None, src: str | None, conf: float | None, gt: GroundTruth) -> str:
    if ts is None:
        return "FAIL — None"
    if src == "fallback" or src is None:
        return f"WARN — fallback path active (no real detection); ts={ts}"
    if gt.time_signature_listener is None:
        return f"NEEDS_LISTENER — source={src}, conf={conf}"
    if ts.strip() == gt.time_signature_listener.strip():
        return f"PASS — matches listener {gt.time_signature_listener} (src={src}, conf={conf})"
    return f"FAIL — ASA says {ts}, listener says {gt.time_signature_listener}"


# ---------- Structure ----------
def _audit_structure(p: dict) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    # Top-level `structure.segments` holds the SBic + novelty-fusion segments.
    # `arrangementDetail` holds the novelty curve + peaks (no segments key).
    struct = _get(p, "structure") or {}
    segs = struct.get("segments") or []
    seg_count = struct.get("segmentCount")
    rows.append((
        "structure.segments count",
        f"{len(segs)} segments (segmentCount={seg_count})",
        "PASS — non-trivial structure" if 3 <= len(segs) <= 20 else "WARN — outside 3-20",
    ))

    arr = _get(p, "arrangementDetail") or {}
    peaks = arr.get("noveltyPeaks") or []
    rows.append((
        "arrangementDetail.noveltyPeaks count",
        f"{len(peaks)} peaks",
        "PASS — non-trivial" if 3 <= len(peaks) <= 30 else "WARN",
    ))
    nc = arr.get("noveltyCurve") or []
    rows.append((
        "arrangementDetail.noveltyCurve points",
        f"{len(nc)} points",
        "PASS" if 100 <= len(nc) <= 500 else "WARN — outside 100-500",
    ))
    return rows


# ---------- New-field shape audit ----------
def _audit_new_fields(p: dict) -> list[tuple[str, str, str]]:
    """Phase 1.A / 1.B / 1.C new fields. Existence + shape only — not vs ground truth."""
    rows: list[tuple[str, str, str]] = []

    # Phase 1.A
    rhythm = _get(p, "rhythmDetail") or {}
    tc = rhythm.get("tempoCurve") or []
    rows.append(("rhythmDetail.tempoCurve", f"{len(tc)} points",
                 "PASS" if 10 <= len(tc) <= 500 else "WARN"))

    # Phase 1.B per-stem spectralDetail (raw analyzer names; HTTP-side they're normalized to *Mean)
    stems = _get(p, "stemAnalysis") or {}
    if stems:
        rows.append(("stemAnalysis stems", ", ".join(stems.keys()),
                     "PASS — stems analyzed"))
        for stem_name in ("drums", "bass", "other", "vocals"):
            stem = stems.get(stem_name) or {}
            sd = stem.get("spectralDetail") or {}
            sc = sd.get("spectralCentroid") if sd else None
            rows.append((
                f"stemAnalysis.{stem_name}.spectralDetail.spectralCentroid (raw name)",
                f"{sc}" if sc is None or isinstance(sc, (int, float)) else f"{type(sc).__name__} (non-scalar)",
                "PASS" if isinstance(sc, (int, float)) else "WARN — not scalar at raw layer",
            ))
            sb_keys = stem.get("spectralBalance")
            sb_keys_label = "absent" if sb_keys is None else f"{len(sb_keys)} bands" if isinstance(sb_keys, dict) else f"{type(sb_keys).__name__}"
            rows.append((
                f"stemAnalysis.{stem_name}.spectralBalance",
                sb_keys_label,
                "PASS" if isinstance(sb_keys, dict) and len(sb_keys) == 7 else "WARN",
            ))
    else:
        rows.append(("stemAnalysis", "absent", "WARN — no --separate flag passed"))

    # Phase 1.C #1 (transient density flattened)
    td = _get(p, "transientDensityDetail") or {}
    bands_present = [b for b in EXPECTED_BANDS if td.get(b) is not None]
    rows.append((
        "transientDensityDetail per-band density coverage",
        f"present={len(bands_present)}/7 ({bands_present})",
        "PASS" if len(bands_present) == 7 else f"FAIL — expected 7, got {len(bands_present)}",
    ))

    # Phase 1.C #5 (saturation)
    sat = _get(p, "saturationDetail") or {}
    rows.append(("saturationDetail.clippedSampleCount", f"{sat.get('clippedSampleCount')}",
                 "PASS" if sat.get("clippedSampleCount") is not None else "WARN — null"))
    rows.append(("saturationDetail.peakRatio95to50", f"{sat.get('peakRatio95to50')}",
                 "PASS" if sat.get("peakRatio95to50") is not None else "WARN — null"))
    rows.append(("saturationDetail.saturationLikely", f"{sat.get('saturationLikely')}",
                 "PASS — bool" if isinstance(sat.get("saturationLikely"), bool) else "WARN"))

    # Phase 1.C #4 (snare / hihat)
    for det_name in ("snareDetail", "hihatDetail"):
        det = _get(p, det_name) or {}
        hits = det.get("hitCount")
        band = det.get("bandHz")
        att = det.get("meanAttackSharpness")
        rows.append((
            f"{det_name} shape (hitCount / bandHz / meanAttackSharpness)",
            f"{hits} / {band} / {att}",
            "PASS — populated" if all(v is not None for v in (hits, band, att)) else "WARN — partial null",
        ))

    return rows


# ---------- Rendering ----------
def _section(title: str, rows: list[tuple[str, str, str]]) -> str:
    out = [f"### {title}\n", "| Field | Observed | Verdict |", "|---|---|---|"]
    for f_name, observed, verdict in rows:
        out.append(f"| `{f_name}` | {observed} | {verdict} |")
    return "\n".join(out) + "\n"


def _summarize(rows: list[tuple[str, str, str]]) -> dict:
    c = {"PASS": 0, "WARN": 0, "FAIL": 0, "NEEDS_LISTENER": 0, "N/A": 0}
    for _, _, v in rows:
        for k in c:
            if v.startswith(k):
                c[k] += 1
                break
    return c


VTSS_GT = GroundTruth(
    label="Vtss — Can't Catch Me",
    audio_relpath="tests/fixtures/bench_tracks/Vtss-CantCatchMe.mp3",
    bpm_listener=145.0,
    bpm_tolerance=2.0,
    key_listener="C Minor",
    lufs_integrated_listener=None,
    lufs_integrated_expected_min=-25.0,
    lufs_integrated_expected_max=-4.0,
    sub_bass_correlation_expected_min=0.5,
    stereo_width_listener=None,
    time_signature_listener="4/4",
    has_acid_listener=None,
    has_supersaw_listener=None,
    has_kick_listener=True,
    has_bass_listener=True,
    has_vocal_listener=False,
    has_reverb_listener=None,
    has_sidechain_listener=None,
    kick_count_per_sec_listener_low=None,
    kick_count_per_sec_listener_high=None,
    notes=[
        "Bench reference track for 2026 Phase 1 audit; declared as ~145 BPM, C Minor four-on-the-floor electronic.",
        "Replace `None` ground-truth fields with reference-tool values during a future listener pass.",
        "Confidence calibration is the most product-valuable thing this audit can produce — see PURPOSE.md invariant #4.",
    ],
)


def _report_for(path: Path, gt: GroundTruth, *, label_suffix: str = "") -> str:
    payload = json.loads(path.read_text())
    duration = _get(payload, "duration") or _get(payload, "durationSeconds")

    bpm = _audit_bpm(payload, gt)
    key = _audit_key(payload, gt)
    lufs = _audit_lufs(payload, gt)
    sb = _audit_spectral_balance(payload)
    st = _audit_stereo(payload, gt)
    kk = _audit_kick(payload, gt, duration)
    bs = _audit_bass(payload)
    sc = _audit_sidechain(payload)
    det = _audit_detectors(payload, gt)
    ts = _audit_time_signature(payload, gt)
    sr = _audit_structure(payload)
    nf = _audit_new_fields(payload)

    all_rows = bpm + key + lufs + sb + st + kk + bs + sc + det + ts + sr + nf
    sm = _summarize(all_rows)

    parts = [
        f"## {gt.label}{label_suffix}\n",
        f"Source JSON: `{path}`. Duration: `{duration}s`.",
        "",
        f"**Summary:** PASS={sm['PASS']}  WARN={sm['WARN']}  FAIL={sm['FAIL']}  NEEDS_LISTENER={sm['NEEDS_LISTENER']}  N/A={sm['N/A']}",
        "",
        _section("1. BPM", bpm),
        _section("2. Key", key),
        _section("3. LUFS", lufs),
        _section("4. Spectral balance (7 bands + time series)", sb),
        _section("5. Stereo (width / correlation / per-band / curve)", st),
        _section("6. Kick detail (fundamental Hz + density + distortion flag)", kk),
        _section("7. Bass detail (fundamental Hz, decay, transient ratio)", bs),
        _section("8. Sidechain detail (rate / confidence / strength / regularity / envelope)", sc),
        _section("9. Detectors (acid, supersaw, kick distortion, vocal, reverb wet)", det),
        _section("10. Time signature (real detection vs fallback)", ts),
        _section("11. Structure / arrangement", sr),
        _section("12. Phase 1.A / 1.B / 1.C new-field shape audit", nf),
    ]
    if gt.notes:
        parts.append("### Ground-truth notes\n")
        for n in gt.notes:
            parts.append(f"- {n}")
        parts.append("")
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vtss-nostem", default="/tmp/vtss_post_fix.json")
    parser.add_argument("--vtss-stem", default="/tmp/vtss_full_separate.json")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    reports: list[str] = []
    pnostem = Path(args.vtss_nostem)
    pstem = Path(args.vtss_stem)

    if pnostem.exists():
        reports.append(_report_for(pnostem, VTSS_GT, label_suffix=" (no-stem run)"))
    else:
        reports.append(f"## {VTSS_GT.label} (no-stem run)\n\n_Missing JSON `{pnostem}`._\n")

    if pstem.exists():
        reports.append(_report_for(pstem, VTSS_GT, label_suffix=" (--separate stem run)"))
    else:
        reports.append(f"## {VTSS_GT.label} (--separate stem run)\n\n_Missing JSON `{pstem}`._\n")

    timestamp = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    out_path = Path(args.out) if args.out else Path(__file__).resolve().parent.parent / ".runtime" / "reports" / f"audit_pass1_{timestamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    header = [
        "# Track 2 Audit Pass 1 — Vtss baseline",
        f"Generated: {_dt.datetime.utcnow().isoformat()}Z",
        "",
        "Audits real-track Phase 1 measurements against listener ground-truth + structural sanity checks.",
        "Verdict legend: PASS / WARN / FAIL / NEEDS_LISTENER / N/A.",
        "",
        "Audit-priority ordering matches the approved plan's Track 2 'Audit priorities (in order)' section.",
        "Field names match the raw analyze.py output (pre-HTTP normalization); spectralCentroid → spectralCentroidMean rename happens at the HTTP/Gemini boundary, not in analyze.py.",
        "",
    ]
    out_path.write_text("\n".join(header) + "\n".join(reports))
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
