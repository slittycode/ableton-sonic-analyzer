"""Deterministic scorer for ASA Phase 2 recommendation quality.

EVAL / RESEARCH ONLY. This module scores how well a set of recommendations
recovers the *known* device settings that produced a ground-truth render. It is
the harness core of the recommendation-proof campaign (see ``GOAL.md`` sub-goal
2). It MUST NOT be imported by ``analyze.py`` or ``server.py`` — ASA recommends
Ableton devices, it does not score itself on the product path. Deleting this
module (and ``scripts/evaluate_recommendations.py``) restores the product
exactly, mirroring the other ``*_evaluation.py`` harnesses.

The design follows the GOAL.md "key insight": a human authors a Live 12 project
with known device settings, renders it, ASA analyzes the render, and this scorer
checks whether the recommendations recovered the settings. The answer key is the
fixture manifest (``deviceSpec`` + ``measurableIntent``), authored once per
track.

Scoring is **source-agnostic**: it consumes a list of :class:`NormalizedRec`
(produced by an adapter from any recommendation source — Gemini Phase 2, the
deterministic ``abletonDevices.ts`` path, or a trivial baseline) plus a
:class:`Fixture`. This is what lets sub-goal 3 score three sources on the same
corpus.

Equivalence caveat (GOAL.md): a track has many valid reconstructions. Scoring is
therefore at the level of **device role/family -> parameter -> value direction &
magnitude band**, never byte-exact strings. ``Compressor`` and
``Glue Compressor`` both satisfy a "compression" ground-truth role because they
share an equivalence class (see :data:`DEVICE_EQUIVALENCE`).
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "recommendation-fixture.v1"

# ---------------------------------------------------------------------------
# Canonical production domains (PURPOSE.md invariant #5 — reconstruction must
# cover the full surface). Every recommendation and every ground-truth device
# chain is bucketed into exactly one of these.
# ---------------------------------------------------------------------------

DOMAINS: tuple[str, ...] = (
    "kick",
    "bass",
    "melody",
    "groove",
    "fx",
    "stereo",
    "master",
)

UNKNOWN_DOMAIN = "unknown"


# ---------------------------------------------------------------------------
# Device catalog (the same contract Phase 2 device names are validated against).
# ---------------------------------------------------------------------------

_DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "prompts" / "live12_device_catalog.json"


@dataclass(frozen=True)
class CatalogDevice:
    name: str
    family: str
    cls: str
    allowed_parameters: frozenset[str]
    parameter_aliases: Mapping[str, str]

    def canonical_parameter(self, name: str) -> str | None:
        """Resolve ``name`` to a catalog parameter, honoring aliases.

        Returns the canonical parameter name if it (or an alias of it) is
        allowed on this device, else ``None``.
        """
        if name in self.allowed_parameters:
            return name
        alias_target = self.parameter_aliases.get(name)
        if alias_target and alias_target in self.allowed_parameters:
            return alias_target
        return None


class Catalog:
    """In-memory view of ``live12_device_catalog.json`` for validation/scoring."""

    def __init__(self, devices: Iterable[CatalogDevice]):
        self._by_name = {d.name: d for d in devices}

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Catalog":
        catalog_path = Path(path) if path is not None else _DEFAULT_CATALOG_PATH
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        devices = []
        for entry in raw.get("devices", []):
            devices.append(
                CatalogDevice(
                    name=entry["name"],
                    family=entry.get("family", "NATIVE"),
                    cls=entry.get("class", ""),
                    allowed_parameters=frozenset(entry.get("allowedParameters", [])),
                    parameter_aliases=dict(entry.get("parameterAliases", {})),
                )
            )
        return cls(devices)

    def get(self, name: str) -> CatalogDevice | None:
        return self._by_name.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def names(self) -> frozenset[str]:
        return frozenset(self._by_name)


# ---------------------------------------------------------------------------
# Device equivalence classes — the heart of the "equivalent route earns credit"
# rule. Two devices match at role/family level iff they share a class. Keyed by
# the exact catalog name. Devices absent here only match themselves exactly.
# ---------------------------------------------------------------------------

DEVICE_EQUIVALENCE: dict[str, str] = {
    # Virtual-analog / subtractive / FM synths — interchangeable for most
    # kick/bass/lead tone roles.
    "Operator": "va_synth",
    "Analog": "va_synth",
    "Wavetable": "va_synth",
    "Drift": "va_synth",
    "Meld": "va_synth",
    "Bass": "va_synth",
    # Samplers / drum instruments.
    "Sampler": "sampler",
    "Simpler": "sampler",
    "Drum Rack": "sampler",
    "Impulse": "sampler",
    # Physical modeling.
    "Collision": "physical_model",
    "Tension": "physical_model",
    "Electric": "physical_model",
    "Granulator III": "granular",
    # EQ family.
    "EQ Eight": "eq",
    "EQ Three": "eq",
    "Channel EQ": "eq",
    # Compression family.
    "Compressor": "compressor",
    "Glue Compressor": "compressor",
    "Multiband Dynamics": "compressor",
    # Limiting family.
    "Limiter": "limiter",
    "Color Limiter": "limiter",
    # Saturation / drive family.
    "Saturator": "saturation",
    "Dynamic Tube": "saturation",
    "Amp": "saturation",
    "Cabinet": "saturation",
    "Drum Buss": "saturation",
    # Reverb family.
    "Reverb": "reverb",
    "Hybrid Reverb": "reverb",
    "Corpus": "reverb",
    # Delay family.
    "Delay": "delay",
    "Echo": "delay",
    "Filter Delay": "delay",
    "Gated Delay": "delay",
    # Modulation family.
    "Chorus-Ensemble": "modulation",
    "Flanger": "modulation",
    "Phaser-Flanger": "modulation",
    "Auto Pan-Tremolo": "modulation",
    "Frequency Shifter": "modulation",
    # Filter / movement.
    "Auto Filter": "filter",
    # Gate.
    "Gate": "gate",
    # Stereo / utility.
    "Utility": "stereo_util",
    # Pitch fx.
    "Auto Shift": "pitch_fx",
    "Spectral Resonator": "pitch_fx",
    # Glitch.
    "Beat Repeat": "glitch",
    "Erosion": "glitch",
    # MIDI.
    "Arpeggiator": "arp",
    "Chord": "midi_util",
    "Scale": "midi_util",
    "Note Length": "midi_util",
    "Pitch": "midi_util",
    "Random": "midi_util",
    "Velocity": "midi_util",
    "Note Echo": "midi_util",
    "LFO": "modulator",
    "Shaper": "modulator",
    "Envelope Follower": "modulator",
}


def equivalence_class(device: str) -> str:
    """Return a device's equivalence class, or the device name itself if absent."""
    return DEVICE_EQUIVALENCE.get(device, device)


def devices_match(recommended: str, ground_truth: str) -> bool:
    """True if a recommended device satisfies a ground-truth device role.

    Exact name match always wins; otherwise they must share an equivalence
    class. This is what credits ``Glue Compressor`` for a ``Compressor`` spec.
    """
    if recommended == ground_truth:
        return True
    return equivalence_class(recommended) == equivalence_class(ground_truth)


# ---------------------------------------------------------------------------
# Value parsing + per-unit tolerance bands.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedValue:
    """A numeric magnitude extracted from a free-text value string."""

    number: float
    unit: str  # normalized: "hz", "db", "ms", "s", "ratio", "pct", "st", ""

    @property
    def hz(self) -> float | None:
        if self.unit == "hz":
            return self.number
        return None


# Per-unit tolerance bands and the neutral default used for direction scoring.
# tolerance is absolute in the unit unless `rel` is set (fraction of target).
@dataclass(frozen=True)
class UnitBand:
    abs_tol: float | None
    rel_tol: float | None
    neutral: float


UNIT_BANDS: dict[str, UnitBand] = {
    "hz": UnitBand(abs_tol=None, rel_tol=0.20, neutral=1000.0),   # ±20%
    "db": UnitBand(abs_tol=3.0, rel_tol=None, neutral=0.0),       # ±3 dB
    "ms": UnitBand(abs_tol=None, rel_tol=0.30, neutral=20.0),     # ±30%
    "s": UnitBand(abs_tol=None, rel_tol=0.30, neutral=1.0),       # ±30%
    "ratio": UnitBand(abs_tol=1.0, rel_tol=None, neutral=1.0),    # ±1:1
    "pct": UnitBand(abs_tol=15.0, rel_tol=None, neutral=50.0),    # ±15%
    "st": UnitBand(abs_tol=1.0, rel_tol=None, neutral=0.0),       # ±1 semitone
    "": UnitBand(abs_tol=None, rel_tol=0.20, neutral=0.0),        # unitless: ±20%
}


# Longer unit tokens must precede their prefixes in the alternation (`st` before
# `s`, `sec`/`semitones` before `s`, `ms` before `s`) so regex first-match wins
# on the intended unit.
_VALUE_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*"
    r"(k?hz|db|ms|sec|semitones?|st|s|%|:1|x)?",
    re.IGNORECASE,
)


def parse_value(text: str | float | int | None) -> ParsedValue | None:
    """Extract a numeric magnitude + normalized unit from a value string.

    Handles ``"4 kHz"``, ``"-15 dB"``, ``"200 ms"``, ``"3:1"``, ``"30%"``,
    ``"0.6"``, ``"+12st"``. Returns ``None`` for non-numeric values (e.g.
    ``"Sine"``, ``"Auto"``) — those are scored on parameter coverage only.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        if not math.isfinite(float(text)):
            return None
        return ParsedValue(number=float(text), unit="")
    s = str(text).strip()
    if not s:
        return None
    # Ratio form "3:1" -> 3.0 ratio.
    ratio_match = re.search(r"(-?\d+(?:\.\d+)?)\s*:\s*1\b", s)
    if ratio_match:
        return ParsedValue(number=float(ratio_match.group(1)), unit="ratio")
    match = _VALUE_RE.search(s)
    if not match:
        return None
    number = float(match.group(1))
    raw_unit = (match.group(2) or "").lower()
    unit = _normalize_unit(raw_unit)
    if unit == "hz" and raw_unit.startswith("k"):
        number *= 1000.0
    return ParsedValue(number=number, unit=unit)


def _normalize_unit(raw: str) -> str:
    if raw in ("khz", "hz"):
        return "hz"
    if raw == "db":
        return "db"
    if raw == "ms":
        return "ms"
    if raw in ("s", "sec"):
        return "s"
    if raw == "%":
        return "pct"
    if raw in ("st", "semitone", "semitones"):
        return "st"
    if raw in (":1", "x"):
        return "ratio"
    return ""


def score_value(recommended: ParsedValue | None, target: ParsedValue | None) -> float:
    """Score a recommended value against the ground-truth target in [0, 1].

    - 1.0  within the per-unit tolerance band
    - 0.5  outside the band but on the correct side of the neutral default
            (right *direction* — e.g. both are boosts, or both are short)
    - 0.0  wrong direction, or either value is non-numeric / unit-mismatched

    Direction matters because GOAL.md scores "value in the right direction and
    magnitude band". A rec that says "boost" when the truth is "cut" is wrong
    even if the magnitude is close.
    """
    if recommended is None or target is None:
        return 0.0
    # Unit mismatch (e.g. comparing Hz to dB) is not comparable.
    if recommended.unit != target.unit:
        return 0.0
    band = UNIT_BANDS.get(target.unit, UNIT_BANDS[""])
    if band.abs_tol is not None:
        tol = band.abs_tol
    else:
        tol = abs(target.number) * (band.rel_tol or 0.0)
    if abs(recommended.number - target.number) <= tol + 1e-9:
        return 1.0
    # Direction relative to neutral default.
    rec_side = recommended.number - band.neutral
    tgt_side = target.number - band.neutral
    if rec_side == 0 or tgt_side == 0:
        return 0.0
    return 0.5 if (rec_side > 0) == (tgt_side > 0) else 0.0


# ---------------------------------------------------------------------------
# Fixture (answer key) model.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpecParameter:
    name: str
    value: str
    intent: str | None = None

    @property
    def parsed(self) -> ParsedValue | None:
        return parse_value(self.value)


@dataclass(frozen=True)
class SpecDevice:
    device: str
    family: str | None
    parameters: tuple[SpecParameter, ...]
    role: str | None = None


@dataclass(frozen=True)
class IntentTarget:
    """A measurable-intent entry: a Phase 1 path with a target range.

    Mirrors the threshold idiom in ``phase1_eval_manifest.json``
    (``{target, tolerance}``) plus an optional direction.
    """

    path: str
    target: float | str | bool
    tolerance: float | None = None
    direction: str | None = None  # "min" | "max" | "exact" | None
    unit: str | None = None


@dataclass(frozen=True)
class Fixture:
    slug: str
    title: str
    genre: str
    audio_path: str | None
    device_spec: Mapping[str, tuple[SpecDevice, ...]]  # domain -> ordered chain
    measurable_intent: tuple[IntentTarget, ...]
    phase1_fingerprint: Mapping[str, Any] | None
    render: Mapping[str, Any]
    source_path: Path | None = None

    def domains_with_spec(self) -> tuple[str, ...]:
        return tuple(d for d in DOMAINS if self.device_spec.get(d))


def load_fixture(manifest_path: Path | str) -> Fixture:
    """Parse a ``manifest.json`` into a :class:`Fixture`.

    The optional Phase 1 fingerprint is loaded from an embedded
    ``phase1Fingerprint`` object or, if a ``phase1FingerprintPath`` is given and
    the file exists, from that sibling file. A missing fingerprint is allowed —
    scoring degrades gracefully (the citation path-validity sub-check SKIPs, the
    same way the transcription harness SKIPs missing audio).
    """
    path = Path(manifest_path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    version = raw.get("schemaVersion")
    if version != SCHEMA_VERSION:
        # Soft-warn (eval tooling, never fail ingest on a version skew) so a
        # future schema bump is visible rather than silently mis-parsed.
        print(
            f"[warn] {path}: schemaVersion {version!r} != expected {SCHEMA_VERSION!r}",
            file=sys.stderr,
        )

    device_spec: dict[str, tuple[SpecDevice, ...]] = {}
    for domain, chain in (raw.get("deviceSpec") or {}).items():
        devices = []
        for dev in chain:
            params = tuple(
                SpecParameter(
                    name=p["name"],
                    value=str(p.get("value", "")),
                    intent=p.get("intent"),
                )
                for p in dev.get("parameters", [])
            )
            devices.append(
                SpecDevice(
                    device=dev["device"],
                    family=dev.get("family"),
                    parameters=params,
                    role=dev.get("role"),
                )
            )
        device_spec[domain] = tuple(devices)

    intents = []
    for path_key, spec in (raw.get("measurableIntent") or {}).items():
        if isinstance(spec, Mapping):
            target = spec.get("target", spec.get("equals"))
            intents.append(
                IntentTarget(
                    path=path_key,
                    target=target,
                    tolerance=spec.get("tolerance"),
                    direction=spec.get("direction"),
                    unit=spec.get("unit"),
                )
            )

    fingerprint = raw.get("phase1Fingerprint")
    fp_path = raw.get("phase1FingerprintPath")
    if fingerprint is None and fp_path:
        candidate = path.parent / fp_path
        if candidate.exists():
            fingerprint = json.loads(candidate.read_text(encoding="utf-8"))

    return Fixture(
        slug=raw.get("id", path.parent.name),
        title=raw.get("title", ""),
        genre=raw.get("genre", ""),
        audio_path=raw.get("audioPath"),
        device_spec=device_spec,
        measurable_intent=tuple(intents),
        phase1_fingerprint=fingerprint,
        render=raw.get("render", {}),
        source_path=path,
    )


# ---------------------------------------------------------------------------
# Normalized recommendation model + adapters (source-agnostic seam).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedRec:
    """A single recommendation reduced to the fields the scorer needs.

    Adapters map each source's native shape onto this. The scorer never sees a
    source-specific type, which is what makes "deterministic vs Gemini vs
    baseline" a one-line swap (GOAL.md sub-goal 3).
    """

    domain: str
    device: str
    parameter: str | None = None
    value: str | None = None
    citations: tuple[str, ...] = ()
    family: str | None = None


# Keyword -> domain inference for free-text track-context strings.
_DOMAIN_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("kick", "kick"),
    ("sub bass", "bass"),
    ("bassline", "bass"),
    ("bass", "bass"),
    ("808", "bass"),
    ("lead", "melody"),
    ("melod", "melody"),
    ("arp", "melody"),
    ("pluck", "melody"),
    ("chord", "melody"),
    ("pad", "melody"),
    ("synth", "melody"),
    ("harmon", "melody"),
    ("hat", "groove"),
    ("hi-hat", "groove"),
    ("hihat", "groove"),
    ("perc", "groove"),
    ("snare", "groove"),
    ("clap", "groove"),
    ("drum", "groove"),
    ("groove", "groove"),
    ("width", "stereo"),
    ("stereo", "stereo"),
    ("pan", "stereo"),
    ("imaging", "stereo"),
    ("master", "master"),
    ("mix bus", "master"),
)

# Recommendation category (Phase2 enum) -> domain, when track-context is silent.
_CATEGORY_DOMAIN: dict[str, str] = {
    "STEREO": "stereo",
    "MASTERING": "master",
    "MIDI": "groove",
}


def infer_domain(track_context: str | None, category: str | None) -> str:
    """Best-effort production-domain inference for a recommendation.

    Track context wins (it is specific — "Kick bus", "Bass", "Master"), then
    category. Falls back to :data:`UNKNOWN_DOMAIN` so the scorer can count
    unattributable recs as precision noise rather than silently dropping them.

    Domain reading (chosen deliberately): a device is attributed to **the signal
    it shapes**, matching how producers speak — "the bass is sidechained" puts a
    sidechain Compressor on the bass under ``bass``, not ``fx``. ``fx`` is for
    effect/texture devices a rec does not tie to a single instrument.

    KNOWN LIMITATION (revisit with real renders, see NEEDS.md): a fixture spec
    may list an instrument-processing effect under ``fx`` while a rec naming the
    processed instrument (``trackContext: "Bass"``) scores under ``bass`` — a
    cross-domain attribution mismatch that can under-credit otherwise-correct
    recs. Author fixtures so a device's spec domain matches the trackContext a
    producer would give it, and resolve the inference heuristics against actual
    Gemini/deterministic output in sub-goal 3 rather than tuning them blind now.
    """
    if track_context:
        low = track_context.lower()
        for keyword, domain in _DOMAIN_KEYWORDS:
            if keyword in low:
                return domain
    if category:
        mapped = _CATEGORY_DOMAIN.get(category.upper())
        if mapped:
            return mapped
    return UNKNOWN_DOMAIN


def coerce_phase2_payload(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept either a bare ``Phase2Result`` or a ``phase2-export.v1`` envelope.

    The backend's ``GET /api/analysis-runs/{run_id}/export/phase2`` route
    (``phase2_export.py``) wraps the interpretation result in a versioned
    handoff envelope ``{schemaVersion: "phase2-export.v1", ..., phase2: {...}}``
    so one downloaded file feeds both this harness and the sibling
    ``asa-ableton`` repo. Unwrap it here so ``--phase2`` (and a fixture-dir
    ``phase2.json``) can be that file directly; a bare result passes through
    unchanged.
    """
    schema_version = raw.get("schemaVersion")
    if (
        isinstance(schema_version, str)
        and schema_version.startswith("phase2-export.")
        and isinstance(raw.get("phase2"), Mapping)
    ):
        return raw["phase2"]
    return raw


def normalize_phase2(phase2: Mapping[str, Any]) -> list[NormalizedRec]:
    """Adapter: ``Phase2Result`` JSON -> normalized recs.

    Pulls from the two structured buckets the citation contract covers:
    ``abletonRecommendations`` (carry ``category`` + ``trackContext``) and
    ``mixAndMasterChain`` (the mastering pipeline; domain defaults to master
    unless track-context says otherwise). ``sonicElements`` are free prose, not
    device cards, so they are intentionally not scored here.
    """
    recs: list[NormalizedRec] = []
    for item in phase2.get("abletonRecommendations") or []:
        recs.append(
            NormalizedRec(
                domain=infer_domain(item.get("trackContext"), item.get("category")),
                device=item.get("device", ""),
                parameter=item.get("parameter"),
                value=_stringify(item.get("value")),
                citations=_citations(item.get("phase1Fields")),
                family=item.get("deviceFamily"),
            )
        )
    for item in phase2.get("mixAndMasterChain") or []:
        domain = infer_domain(item.get("trackContext"), "MASTERING")
        recs.append(
            NormalizedRec(
                domain=domain,
                device=item.get("device", ""),
                parameter=item.get("parameter"),
                value=_stringify(item.get("value")),
                citations=_citations(item.get("phase1Fields")),
                family=item.get("deviceFamily"),
            )
        )
    return recs


def normalize_baseline(_fixture: Fixture) -> list[NormalizedRec]:
    """Adapter: trivial baseline source — emits nothing.

    GOAL.md sub-goal 3 needs a no-op baseline as the floor of the three-source
    comparison. An empty rec set scores ~0 on coverage; any real source must
    clear it to justify its existence.
    """
    return []


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _citations(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    out = []
    for entry in raw:
        if isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
    return tuple(out)


# ---------------------------------------------------------------------------
# Chain-of-custody penalty — Python port of the phase2Validator.ts semantics so
# the harness and the runtime guardrail share one definition of "broke the
# chain". Keep in sync with apps/ui/src/services/phase2Validator.ts.
# ---------------------------------------------------------------------------


def collect_phase1_field_paths(phase1: Mapping[str, Any]) -> set[str]:
    """Every dotted path that resolves to a non-null value in a Phase 1 payload.

    Mirrors ``collectPhase1FieldPaths`` in phase2Validator.ts: both intermediate
    keys and leaf scalars are included, and for arrays of objects the
    ``path.field`` shapes are surfaced so a citation can name an array item's
    field without indexing.
    """
    paths: set[str] = set()
    _walk_paths(phase1, "", paths)
    return paths


def _walk_paths(value: Any, prefix: str, paths: set[str]) -> None:
    if value is None:
        return
    if isinstance(value, list):
        if prefix:
            paths.add(prefix)
        for item in value:
            if isinstance(item, Mapping):
                for key in item:
                    sub = f"{prefix}.{key}" if prefix else key
                    _walk_paths(item[key], sub, paths)
        return
    if not isinstance(value, Mapping):
        if prefix:
            paths.add(prefix)
        return
    if prefix:
        paths.add(prefix)
    for key in value:
        sub = f"{prefix}.{key}" if prefix else key
        _walk_paths(value[key], sub, paths)


def path_covers_tracked(citation: str, tracked: str) -> bool:
    """Bidirectional + wildcard path match. Port of ``pathCoversTracked``."""
    if citation == tracked:
        return True
    if citation.startswith(f"{tracked}."):
        return True
    if tracked.startswith(f"{citation}."):
        return True
    if "*" not in citation and "*" not in tracked:
        return False
    cs = citation.split(".")
    ts = tracked.split(".")
    if len(ts) <= len(cs):
        if all(ts[i] == cs[i] or ts[i] == "*" or cs[i] == "*" for i in range(len(ts))):
            return True
    if len(cs) <= len(ts):
        if all(cs[i] == ts[i] or cs[i] == "*" or ts[i] == "*" for i in range(len(cs))):
            return True
    return False


@dataclass
class CustodyResult:
    total_recs: int
    cited_recs: int          # recs with >= 1 non-empty citation
    valid_path_recs: int     # recs whose citations all resolve in the fingerprint
    path_check_ran: bool     # False when no fingerprint is available (SKIP)
    penalty: float           # multiplier in [0, 1] applied to the raw score

    @property
    def presence_rate(self) -> float:
        return self.cited_recs / self.total_recs if self.total_recs else 1.0


def evaluate_custody(
    recs: Sequence[NormalizedRec],
    fingerprint: Mapping[str, Any] | None,
) -> CustodyResult:
    """Chain-of-custody assessment over a rec set.

    Two sub-checks, mirroring phase2Validator.ts:
      1. Presence — every rec must carry >= 1 citation (always checkable).
      2. Path validity — every citation must resolve to a path present in the
         Phase 1 fingerprint (only runs when a fingerprint is available; SKIPs
         cleanly otherwise, like the transcription harness SKIPs missing audio).

    The penalty is the mean of the checkable rates. A high-coverage rec set that
    breaks the chain must not outscore a cited one (GOAL.md sub-goal 2.d), so
    the penalty multiplies the raw score downstream.
    """
    total = len(recs)
    if total == 0:
        return CustodyResult(0, 0, 0, fingerprint is not None, 1.0)

    cited = 0
    valid_path = 0
    allowed = collect_phase1_field_paths(fingerprint) if fingerprint else set()
    path_check_ran = bool(fingerprint)

    for rec in recs:
        has_citation = len(rec.citations) > 0
        if has_citation:
            cited += 1
        if path_check_ran and has_citation:
            if all(
                any(path_covers_tracked(c, t) or path_covers_tracked(t, c) for t in allowed)
                for c in rec.citations
            ):
                valid_path += 1

    presence_rate = cited / total
    if path_check_ran:
        # Path validity is conditioned on citations existing; combine presence
        # with the share of cited recs whose paths are valid.
        path_rate = (valid_path / cited) if cited else 0.0
        penalty = (presence_rate + path_rate) / 2.0
    else:
        penalty = presence_rate

    return CustodyResult(
        total_recs=total,
        cited_recs=cited,
        valid_path_recs=valid_path,
        path_check_ran=path_check_ran,
        penalty=penalty,
    )


# ---------------------------------------------------------------------------
# Scoring.
# ---------------------------------------------------------------------------


@dataclass
class DomainScore:
    domain: str
    truth_device_count: int
    rec_device_count: int
    matched_devices: int          # ground-truth devices covered by >=1 rec
    role_recall: float
    role_precision: float
    parameter_coverage: float
    value_accuracy: float
    score: float                  # blended per-domain score in [0, 1]

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "truthDeviceCount": self.truth_device_count,
            "recDeviceCount": self.rec_device_count,
            "matchedDevices": self.matched_devices,
            "roleRecall": round(self.role_recall, 4),
            "rolePrecision": round(self.role_precision, 4),
            "parameterCoverage": round(self.parameter_coverage, 4),
            "valueAccuracy": round(self.value_accuracy, 4),
            "score": round(self.score, 4),
        }


@dataclass
class RecommendationScore:
    fixture_slug: str
    source: str
    domain_scores: dict[str, DomainScore]
    custody: CustodyResult
    intent_coverage: float        # fraction of measurableIntent paths a rec cites
    raw_aggregate: float          # blend of domain scores + intent coverage (pre-penalty)
    aggregate: float              # raw_aggregate * custody.penalty

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture_slug,
            "source": self.source,
            "aggregate": round(self.aggregate, 4),
            "rawAggregate": round(self.raw_aggregate, 4),
            "intentCoverage": round(self.intent_coverage, 4),
            "custody": {
                "totalRecs": self.custody.total_recs,
                "citedRecs": self.custody.cited_recs,
                "validPathRecs": self.custody.valid_path_recs,
                "pathCheckRan": self.custody.path_check_ran,
                "penalty": round(self.custody.penalty, 4),
            },
            "domains": {d: s.as_dict() for d, s in self.domain_scores.items()},
        }


# Relative weights for the per-domain blend. Role recall is the spine of
# reconstruction completeness (invariant #5); parameter/value sharpen it.
_WEIGHT_RECALL = 0.45
_WEIGHT_PRECISION = 0.15
_WEIGHT_PARAM = 0.20
_WEIGHT_VALUE = 0.20


def _score_one_domain(
    domain: str,
    truth_chain: Sequence[SpecDevice],
    domain_recs: Sequence[NormalizedRec],
) -> DomainScore:
    truth_count = len(truth_chain)
    rec_count = len(domain_recs)

    # Role recall: ground-truth devices covered by at least one rec.
    matched_truth = 0
    matched_truth_devices: list[tuple[SpecDevice, list[NormalizedRec]]] = []
    for truth_dev in truth_chain:
        covering = [r for r in domain_recs if devices_match(r.device, truth_dev.device)]
        if covering:
            matched_truth += 1
        matched_truth_devices.append((truth_dev, covering))
    role_recall = matched_truth / truth_count if truth_count else 0.0

    # Role precision: recs that map onto some ground-truth device.
    matched_recs = sum(
        1
        for r in domain_recs
        if any(devices_match(r.device, t.device) for t in truth_chain)
    )
    role_precision = matched_recs / rec_count if rec_count else (1.0 if truth_count == 0 else 0.0)

    # Parameter coverage + value accuracy over matched devices only.
    param_scores: list[float] = []
    value_scores: list[float] = []
    for truth_dev, covering in matched_truth_devices:
        if not covering:
            continue
        recommended_params: dict[str, NormalizedRec] = {}
        for r in covering:
            if r.parameter:
                recommended_params[_norm_param(r.parameter)] = r
        for spec_param in truth_dev.parameters:
            key = _norm_param(spec_param.name)
            hit = recommended_params.get(key)
            if hit is None:
                hit = _alias_lookup(spec_param.name, truth_dev.device, recommended_params)
            if hit is not None:
                param_scores.append(1.0)
                value_scores.append(score_value(parse_value(hit.value), spec_param.parsed))
            else:
                param_scores.append(0.0)
                # No value to score when the parameter was never named.

    parameter_coverage = sum(param_scores) / len(param_scores) if param_scores else 0.0
    value_accuracy = sum(value_scores) / len(value_scores) if value_scores else 0.0

    score = (
        _WEIGHT_RECALL * role_recall
        + _WEIGHT_PRECISION * role_precision
        + _WEIGHT_PARAM * parameter_coverage
        + _WEIGHT_VALUE * value_accuracy
    )

    return DomainScore(
        domain=domain,
        truth_device_count=truth_count,
        rec_device_count=rec_count,
        matched_devices=matched_truth,
        role_recall=role_recall,
        role_precision=role_precision,
        parameter_coverage=parameter_coverage,
        value_accuracy=value_accuracy,
        score=score,
    )


def _norm_param(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _alias_lookup(
    spec_param_name: str,
    device: str,
    recommended_params: Mapping[str, NormalizedRec],
) -> NormalizedRec | None:
    """Resolve catalog parameter aliases when matching recommended -> spec.

    e.g. Auto Filter's "Filter Frequency" aliases to "Frequency"; a rec naming
    either should satisfy a spec naming the other.
    """
    catalog = _shared_catalog()
    cat_dev = catalog.get(device)
    if cat_dev is None:
        return None
    # Build the set of names that are equivalent to spec_param_name on this device.
    canonical = cat_dev.canonical_parameter(spec_param_name) or spec_param_name
    candidates = {canonical}
    for alias, target in cat_dev.parameter_aliases.items():
        if target == canonical:
            candidates.add(alias)
    for cand in candidates:
        hit = recommended_params.get(_norm_param(cand))
        if hit is not None:
            return hit
    return None


_CATALOG_SINGLETON: Catalog | None = None


def _shared_catalog() -> Catalog:
    global _CATALOG_SINGLETON
    if _CATALOG_SINGLETON is None:
        _CATALOG_SINGLETON = Catalog.load()
    return _CATALOG_SINGLETON


# Weight of the measurable-intent term in the raw aggregate (the rest is the
# per-domain device score). This is GOAL.md's equivalence mechanism: "the key
# stores measurable intent beside the literal spec, so equivalent routes earn
# credit" — a recommendation that grounds itself in the measurements the spec
# deemed essential earns credit even when it names a different (or processing,
# not source) device than the literal spec. Source-instrument recall is partly
# unrecoverable from a finished render anyway (a synth kick and a sampled kick
# measure identically), so measurable intent is the honest equivalence signal.
_WEIGHT_INTENT = 0.25


def intent_coverage(recs: Sequence[NormalizedRec], fixture: Fixture) -> float:
    """Fraction of the fixture's measurableIntent paths cited by >=1 recommendation.

    A path counts as covered when some recommendation citation matches it under
    the same bidirectional/wildcard rule the custody check uses. Returns 1.0 when
    the fixture declares no measurable intent (nothing to miss).
    """
    intents = fixture.measurable_intent
    if not intents:
        return 1.0
    cited: set[str] = set()
    for rec in recs:
        cited.update(rec.citations)
    if not cited:
        return 0.0
    covered = 0
    for target in intents:
        if any(
            path_covers_tracked(c, target.path) or path_covers_tracked(target.path, c)
            for c in cited
        ):
            covered += 1
    return covered / len(intents)


def score_recommendations(
    fixture: Fixture,
    recs: Sequence[NormalizedRec],
    source: str = "unknown",
) -> RecommendationScore:
    """Score a normalized rec set against a fixture's answer key.

    The aggregate is the mean of the per-domain scores over the domains that the
    fixture's ``deviceSpec`` actually defines (so a fixture that only exercises
    kick+bass is not penalized for "missing" a master chain it never specified),
    multiplied by the chain-of-custody penalty.
    """
    by_domain: dict[str, list[NormalizedRec]] = {d: [] for d in DOMAINS}
    by_domain[UNKNOWN_DOMAIN] = []
    for rec in recs:
        by_domain.setdefault(rec.domain, []).append(rec)

    domain_scores: dict[str, DomainScore] = {}
    scored_domains = fixture.domains_with_spec()
    for domain in scored_domains:
        domain_scores[domain] = _score_one_domain(
            domain, fixture.device_spec[domain], by_domain.get(domain, [])
        )

    domain_mean = (
        sum(s.score for s in domain_scores.values()) / len(domain_scores)
        if domain_scores
        else 0.0
    )

    # Blend the literal-device domain score with measurable-intent coverage
    # (GOAL.md's equivalence mechanism). When the fixture declares no intent,
    # intent_coverage is 1.0 and the blend leaves the domain score unchanged
    # only if we skip the term — so apply the intent weight solely when the
    # fixture actually carries measurable intent.
    intent = intent_coverage(recs, fixture)
    if fixture.measurable_intent:
        raw_aggregate = (1 - _WEIGHT_INTENT) * domain_mean + _WEIGHT_INTENT * intent
    else:
        raw_aggregate = domain_mean

    custody = evaluate_custody(recs, fixture.phase1_fingerprint)
    aggregate = raw_aggregate * custody.penalty

    return RecommendationScore(
        fixture_slug=fixture.slug,
        source=source,
        domain_scores=domain_scores,
        custody=custody,
        intent_coverage=intent,
        raw_aggregate=raw_aggregate,
        aggregate=aggregate,
    )


# ---------------------------------------------------------------------------
# Spec catalog-validity (ingest gate for sub-goal 1).
# ---------------------------------------------------------------------------


@dataclass
class SpecValidationIssue:
    domain: str
    device: str
    parameter: str | None
    message: str


def validate_fixture_spec(fixture: Fixture, catalog: Catalog | None = None) -> list[SpecValidationIssue]:
    """Validate every device/parameter in a fixture's deviceSpec is catalog-valid.

    This is the always-runnable half of ingest (the Phase 1 fingerprint sanity
    check is the other half and SKIPs without rendered audio). An empty list
    means the spec is buildable in Live 12 exactly as written, with device and
    parameter names that match the contract Phase 2 is held to.
    """
    cat = catalog or _shared_catalog()
    issues: list[SpecValidationIssue] = []
    for domain, chain in fixture.device_spec.items():
        if domain not in DOMAINS:
            issues.append(SpecValidationIssue(domain, "", None, f"unknown domain '{domain}'"))
        for dev in chain:
            cat_dev = cat.get(dev.device)
            if cat_dev is None:
                issues.append(
                    SpecValidationIssue(domain, dev.device, None, f"device '{dev.device}' not in catalog")
                )
                continue
            if dev.family and dev.family != cat_dev.family:
                issues.append(
                    SpecValidationIssue(
                        domain,
                        dev.device,
                        None,
                        f"family '{dev.family}' != catalog '{cat_dev.family}'",
                    )
                )
            for param in dev.parameters:
                if cat_dev.canonical_parameter(param.name) is None:
                    issues.append(
                        SpecValidationIssue(
                            domain,
                            dev.device,
                            param.name,
                            f"parameter '{param.name}' not allowed on {dev.device}",
                        )
                    )
    return issues


# ---------------------------------------------------------------------------
# Report rendering.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Corpus-verification artifact (sub-goal 4 data source).
#
# Aggregates per-fixture scores into per-domain match rates + support counts —
# "how often a recommendation in this domain recovered ground truth across the
# corpus." The UI badge in AnalysisResults.tsx reads this to show *which* recs
# are corpus-verified and *how strongly*. Honest per PURPOSE.md invariant #4:
# support drives the confidence band, so a domain the corpus has barely
# exercised never earns a confident badge.
# ---------------------------------------------------------------------------

# Number of contributing fixtures below which a domain's verification is hedged.
_VERIFICATION_LOW_SUPPORT = 3
_VERIFICATION_HIGH_SUPPORT = 6


def _confidence_band(support: int, mean_score: float) -> str:
    """Confidence band from BOTH corpus support and observed match quality.

    Support alone is not enough (invariant #4): a domain the corpus exercised many
    times but where recommendations rarely matched ground truth must NOT earn a
    confident badge — it earned the opposite. So a near-zero match rate caps the
    band at NONE regardless of support, and the band rises with match quality only
    once there is enough support to trust it.
    """
    if support <= 0 or mean_score <= 0.05:
        return "NONE"
    if support < _VERIFICATION_LOW_SUPPORT:
        return "LOW"
    if mean_score < 0.4:
        return "LOW"
    if mean_score < 0.7:
        return "MED"
    return "HIGH"


def aggregate_corpus_verification(scores: Sequence[RecommendationScore]) -> dict[str, Any]:
    """Per-domain corpus match rates + support for the UI verification badge.

    ``support`` is the number of fixtures that specified the domain (and were
    scored); ``meanRecall``/``meanScore`` are averaged across them. ``confidence``
    maps support to a band so the badge degrades gracefully: zero corpus evidence
    for a domain → ``NONE`` (the badge shows "not yet corpus-verified"), never a
    confident claim. The artifact is intentionally well-defined when ``scores`` is
    empty — every domain reports support 0 / confidence NONE, which is the
    pre-render state.
    """
    by_domain: dict[str, list[DomainScore]] = {d: [] for d in DOMAINS}
    for sc in scores:
        for domain, ds in sc.domain_scores.items():
            by_domain[domain].append(ds)

    per_domain: dict[str, Any] = {}
    for domain in DOMAINS:
        observations = by_domain[domain]
        support = len(observations)
        mean_recall = (sum(o.role_recall for o in observations) / support) if support else 0.0
        mean_score = (sum(o.score for o in observations) / support) if support else 0.0
        per_domain[domain] = {
            "support": support,
            "meanRecall": round(mean_recall, 4),
            "meanScore": round(mean_score, 4),
            "confidence": _confidence_band(support, mean_score),
        }

    return {
        "fixtures": len(scores),
        "sources": sorted({sc.source for sc in scores}),
        "perDomain": per_domain,
    }


def render_markdown_report(scores: Sequence[RecommendationScore]) -> str:
    """Render a per-fixture, per-domain markdown report.

    Keeps the per-domain breakdown visible (GOAL.md sub-goal 2.3 — "melody is
    under-covered" must stay legible) plus a headline aggregate per fixture.
    """
    lines: list[str] = ["# Recommendation Evaluation Report", ""]
    for sc in scores:
        lines.append(f"## {sc.fixture_slug}  (source: {sc.source})")
        lines.append("")
        lines.append(f"- **Aggregate:** {sc.aggregate:.3f}  (raw {sc.raw_aggregate:.3f})")
        custody_note = (
            f"penalty {sc.custody.penalty:.3f} — "
            f"{sc.custody.cited_recs}/{sc.custody.total_recs} cited"
        )
        if sc.custody.path_check_ran:
            custody_note += f", {sc.custody.valid_path_recs} path-valid"
        else:
            custody_note += ", path-validity SKIPPED (no fingerprint)"
        lines.append(f"- **Chain of custody:** {custody_note}")
        lines.append("")
        lines.append("| Domain | Recall | Precision | Params | Values | Score |")
        lines.append("|---|---|---|---|---|---|")
        for domain in DOMAINS:
            ds = sc.domain_scores.get(domain)
            if ds is None:
                continue
            lines.append(
                f"| {domain} | {ds.role_recall:.2f} | {ds.role_precision:.2f} | "
                f"{ds.parameter_coverage:.2f} | {ds.value_accuracy:.2f} | {ds.score:.3f} |"
            )
        lines.append("")
    return "\n".join(lines)
