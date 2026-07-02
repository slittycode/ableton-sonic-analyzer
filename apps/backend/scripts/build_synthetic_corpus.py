#!/usr/bin/env python3
"""Build the generated-on-demand fundamentals synthetic audio corpus.

Audio is intentionally not committed. This script emits deterministic WAV files
under tests/fixtures/fundamentals_tracks plus a JSON manifest that activates the
fundamentals evaluation harness without relying on owner-provided audio.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import sample_drums  # noqa: E402
from sample_drums import SAMPLE_RATE, synth_hat, synth_kick, synth_snare  # noqa: E402
from sample_synthesis import render_clip, write_wav  # noqa: E402
from sample_theory import (  # noqa: E402
    ClipPlan,
    NoteEvent,
    build_context,
    plan_bass_root,
    plan_chord_progression,
)

SCHEMA_VERSION = "fundamentals-eval.v1"
TARGET_PROFILE = "electronic_ableton_v1"


@dataclass(frozen=True)
class RenderedClip:
    samples: np.ndarray
    truth: dict[str, Any]


def _meter_beats_per_bar(meter: str) -> int:
    numerator, _slash, denominator = meter.partition("/")
    if denominator == "8" and numerator == "6":
        return 6
    return int(numerator or 4)


def _duration_for(bpm: float, beats: float) -> float:
    return float(beats) * 60.0 / float(bpm)


def _overlay(target: np.ndarray, source: np.ndarray, start_sec: float, gain: float = 1.0) -> None:
    start = int(round(start_sec * SAMPLE_RATE))
    end = min(target.size, start + source.size)
    if start < target.size and end > start:
        target[start:end] += source[: end - start] * gain


def render_drum_pattern(
    bpm: float,
    meter: str,
    bars: int,
    kick_positions: Iterable[float],
    snare_positions: Iterable[float],
    hat_positions: Iterable[float],
    swing_percent: float = 50.0,
) -> RenderedClip:
    beats_per_bar = _meter_beats_per_bar(meter)
    total_beats = bars * beats_per_bar
    duration = _duration_for(bpm, total_beats) + 0.7
    samples = np.zeros(int(round(duration * SAMPLE_RATE)), dtype=np.float32)
    kick = synth_kick().samples
    snare = synth_snare().samples
    hat = synth_hat().samples

    beat_seconds = 60.0 / bpm
    swing_offset = max(0.0, (float(swing_percent) - 50.0) / 100.0) * beat_seconds

    def beat_to_seconds(beat: float) -> float:
        # Delay off eighths for swung hats while preserving downbeat truth.
        eighth_index = round(beat * 2.0)
        is_off_eighth = eighth_index % 2 == 1 and abs(beat * 2.0 - eighth_index) < 1e-6
        return beat * beat_seconds + (swing_offset if is_off_eighth else 0.0)

    kick_positions = list(kick_positions)
    snare_positions = list(snare_positions)
    hat_positions = list(hat_positions)
    for beat in kick_positions:
        _overlay(samples, kick, beat_to_seconds(beat), 0.95)
    for beat in snare_positions:
        _overlay(samples, snare, beat_to_seconds(beat), 0.65)
    for beat in hat_positions:
        _overlay(samples, hat, beat_to_seconds(beat), 0.35)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 0.98:
        samples *= 0.98 / peak
    beat_grid = [round(index * beat_seconds, 6) for index in range(total_beats)]
    downbeats = [round(index * beats_per_bar * beat_seconds, 6) for index in range(bars)]
    truth = {
        "bpm": bpm,
        "timeSignature": meter,
        "beatGrid": beat_grid,
        "downbeats": downbeats,
        "percussion": {
            "kickCount": len(kick_positions),
            "snareCount": len(snare_positions),
            "hihatCount": len(hat_positions),
        },
        "hitTimes": {
            "kick": [round(beat_to_seconds(beat), 6) for beat in kick_positions],
            "snare": [round(beat_to_seconds(beat), 6) for beat in snare_positions],
            "hihat": [round(beat_to_seconds(beat), 6) for beat in hat_positions],
        },
        "swingPercent": swing_percent,
    }
    return RenderedClip(samples.astype(np.float32), truth)


def _label_for_degree(root_name: str, mode: str, degree: int) -> str:
    major = {
        "C": ["C", "Am", "F", "G"], "Db": ["Db", "Bbm", "Gb", "Ab"],
        "D": ["D", "Bm", "G", "A"], "Eb": ["Eb", "Cm", "Ab", "Bb"],
        "E": ["E", "C#m", "A", "B"], "F": ["F", "Dm", "Bb", "C"],
        "F#": ["F#", "D#m", "B", "C#"], "G": ["G", "Em", "C", "D"],
        "Ab": ["Ab", "Fm", "Db", "Eb"], "A": ["A", "F#m", "D", "E"],
        "Bb": ["Bb", "Gm", "Eb", "F"], "B": ["B", "G#m", "E", "F#"],
    }
    minor = {
        "C": ["Cm", "Ab", "Bb", "Gm"], "Db": ["Dbm", "A", "B", "Abm"],
        "D": ["Dm", "Bb", "C", "Am"], "Eb": ["Ebm", "B", "Db", "Bbm"],
        "E": ["Em", "C", "D", "Bm"], "F": ["Fm", "Db", "Eb", "Cm"],
        "F#": ["F#m", "D", "E", "C#m"], "G": ["Gm", "Eb", "F", "Dm"],
        "Ab": ["Abm", "E", "Gb", "Ebm"], "A": ["Am", "F", "G", "Em"],
        "Bb": ["Bbm", "Gb", "Ab", "Fm"], "B": ["Bm", "G", "A", "F#m"],
    }
    order = [1, 6, 4, 5] if mode == "major" else [1, 6, 7, 5]
    table = major if mode == "major" else minor
    return table[root_name][order.index(degree)]


def render_chord_progression(
    key_root: str,
    mode: str,
    degrees: list[int],
    bpm: float,
    beats_per_chord: float,
) -> RenderedClip:
    ctx = build_context(key=f"{key_root} {mode}", bpm=bpm)
    plan = plan_chord_progression(ctx, bars=max(2, int(len(degrees) * beats_per_chord / 4)))
    # Keep the existing renderer path as the audio source of truth.
    rendered = render_clip(plan, allow_soundfont_backends=False)
    beat_seconds = 60.0 / bpm
    timeline = []
    for index, degree in enumerate(degrees):
        start = index * beats_per_chord * beat_seconds
        end = (index + 1) * beats_per_chord * beat_seconds
        timeline.append({"startSec": round(start, 6), "endSec": round(end, 6), "label": _label_for_degree(key_root, mode, degree)})
    return RenderedClip(rendered.samples, {"bpm": bpm, "key": f"{key_root} {mode}", "chordTimeline": timeline})


def render_multi_layer(key_root: str, mode: str, bpm: float) -> RenderedClip:
    chords = render_chord_progression(key_root, mode, [1, 6, 4 if mode == "major" else 7, 5], bpm, 4.0)
    ctx = build_context(key=f"{key_root} {mode}", bpm=bpm)
    bass = render_clip(plan_bass_root(ctx, bars=4), allow_soundfont_backends=False).samples
    drums = render_drum_pattern(bpm, "4/4", 4, range(0, 16, 1), [2, 6, 10, 14], [i * 0.5 for i in range(32)])
    n = max(chords.samples.size, bass.size, drums.samples.size)
    mix = np.zeros(n, dtype=np.float32)
    mix[: chords.samples.size] += chords.samples * 0.55
    mix[: bass.size] += bass * 0.28
    mix[: drums.samples.size] += drums.samples * 0.45
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0.98:
        mix *= 0.98 / peak
    truth = {**chords.truth, "timeSignature": "4/4", "percussion": drums.truth["percussion"]}
    return RenderedClip(mix, truth)


def _default_specs() -> list[dict[str, Any]]:
    return [
        {"id": "four_on_floor_clear_128", "kind": "drums", "bpm": 128, "meter": "4/4", "bars": 4},
        {"id": "tonal_minor_static_chords", "kind": "chords", "root": "A", "mode": "minor", "bpm": 120, "degrees": [1, 6], "beats_per_chord": 8},
        {"id": "drum_stem_known_counts", "kind": "drums", "bpm": 128, "meter": "4/4", "bars": 4},
        {"id": "mono_bass_transcription", "kind": "bass", "bpm": 120},
    ]


def _synthetic_specs() -> list[dict[str, Any]]:
    specs = list(_default_specs())
    for bpm, meter in [(70, "4/4"), (90, "3/4"), (110, "6/8"), (128, "4/4"), (140, "7/8"), (174, "4/4")]:
        specs.append({"id": f"grid_{meter.replace('/', '_')}_{bpm}", "kind": "drums", "bpm": bpm, "meter": meter, "bars": 4})
    roots = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    for i, root in enumerate(roots):
        mode = "major" if i % 2 == 0 else "minor"
        degrees = [1, 6, 4, 5] if mode == "major" else [1, 6, 7, 5]
        specs.append({"id": f"chords_{root.replace('#','sharp').replace('b','flat')}_{mode}", "kind": "chords", "root": root, "mode": mode, "bpm": 96 + i * 4, "degrees": degrees, "beats_per_chord": 4})
    for swing in [50, 54, 58, 62, 66]:
        specs.append({"id": f"swing_hats_{swing}", "kind": "swing", "bpm": 124, "meter": "4/4", "bars": 4, "swing": swing})
    for root, mode, bpm in [("A", "minor", 128), ("F", "major", 122)]:
        specs.append({"id": f"multi_{root}_{mode}", "kind": "multi", "root": root, "mode": mode, "bpm": bpm})
    return specs[:29]


def _render_spec(spec: dict[str, Any]) -> RenderedClip:
    kind = spec["kind"]
    if kind == "drums":
        meter = spec.get("meter", "4/4")
        bars = int(spec.get("bars", 4))
        beats = bars * _meter_beats_per_bar(meter)
        kicks = list(range(0, beats, 1)) if spec["id"] == "drum_stem_known_counts" else list(range(0, beats, max(1, _meter_beats_per_bar(meter))))
        snares = [beat for beat in range(beats) if beat % max(2, _meter_beats_per_bar(meter)) == 2]
        hats = [i * 0.5 for i in range(beats * 2)]
        return render_drum_pattern(float(spec["bpm"]), meter, bars, kicks, snares, hats)
    if kind == "swing":
        beats = int(spec.get("bars", 4)) * 4
        return render_drum_pattern(float(spec["bpm"]), "4/4", int(spec["bars"]), range(0, beats, 4), [2, 6, 10, 14], [i * 0.5 for i in range(beats * 2)], float(spec["swing"]))
    if kind == "chords":
        return render_chord_progression(spec["root"], spec["mode"], list(spec["degrees"]), float(spec["bpm"]), float(spec["beats_per_chord"]))
    if kind == "multi":
        return render_multi_layer(spec["root"], spec["mode"], float(spec["bpm"]))
    if kind == "bass":
        plan = ClipPlan(tempo_bpm=float(spec["bpm"]), duration_beats=2.0, notes=[NoteEvent(48, 0.0, 0.5), NoteEvent(51, 1.0, 0.5), NoteEvent(55, 2.0, 0.5)], program=38)
        rendered = render_clip(plan, allow_soundfont_backends=False)
        return RenderedClip(rendered.samples, {"transcriptionNotes": [{"pitchMidi": 48, "onsetSeconds": 0.0, "durationSeconds": 0.5}, {"pitchMidi": 51, "onsetSeconds": 0.5, "durationSeconds": 0.5}, {"pitchMidi": 55, "onsetSeconds": 1.0, "durationSeconds": 0.5}]})
    raise ValueError(f"unknown spec kind: {kind}")


def _manifest_track(spec: dict[str, Any], rendered: RenderedClip, *, synthetic_subdir: bool) -> dict[str, Any]:
    audio_name = f"{spec['id']}.wav"
    expected = dict(rendered.truth)
    track = {
        "id": spec["id"],
        "audioPath": f"synthetic/{audio_name}" if synthetic_subdir else audio_name,
        "category": spec["kind"],
        "description": "Deterministic NumPy-rendered synthetic fundamentals fixture.",
        "expected": expected,
        "thresholds": {"bpmTolerance": 1.0, "beatF1": 0.9, "downbeatF1": 0.75, "chordSegmentAccuracy": 0.65, "percussionCountTolerance": 1, "transcriptionNoteF1": 0.75},
    }
    if spec["kind"] == "multi":
        track["analyzeFlags"] = ["--separate"]
    return track


def emit_manifest(manifest_path: Path, tracks: list[dict[str, Any]]) -> None:
    manifest = {"schemaVersion": SCHEMA_VERSION, "targetProfile": TARGET_PROFILE, "gates": {"clearTempoWithinBpm": 1.0, "beatF1": 0.9, "downbeatF1": 0.75, "chordSegmentAccuracy": 0.65}, "tracks": tracks}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _reset_drum_rng() -> None:
    sample_drums._RNG = np.random.default_rng(seed=42)


def build_corpus(out_dir: Path, manifest_path: Path, *, check: bool = False) -> dict[str, Any]:
    _reset_drum_rng()
    synthetic_manifest = manifest_path.name.endswith(".synthetic.json")
    specs = _synthetic_specs() if synthetic_manifest else _default_specs()
    audio_root = out_dir / "synthetic" if synthetic_manifest else out_dir
    tracks: list[dict[str, Any]] = []
    fingerprints: dict[str, bytes] = {}
    for spec in specs:
        rendered = _render_spec(spec)
        path = audio_root / f"{spec['id']}.wav"
        write_wav(rendered.samples, path=path, sample_rate=SAMPLE_RATE)
        fingerprints[spec["id"]] = rendered.samples.tobytes()
        tracks.append(_manifest_track(spec, rendered, synthetic_subdir=synthetic_manifest))
    emit_manifest(manifest_path, tracks)
    if check:
        _reset_drum_rng()
        for spec in specs:
            second = _render_spec(spec)
            if second.samples.tobytes() != fingerprints[spec["id"]]:
                raise SystemExit(f"non-deterministic render for {spec['id']}")
    return {"tracks": len(tracks), "manifest": str(manifest_path), "outDir": str(out_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ASA's deterministic synthetic fundamentals corpus.")
    parser.add_argument("--out-dir", type=Path, default=BACKEND_DIR / "tests" / "fixtures" / "fundamentals_tracks")
    parser.add_argument("--manifest", type=Path, default=BACKEND_DIR / "tests" / "fixtures" / "fundamentals_eval_manifest.synthetic.json")
    parser.add_argument("--check", action="store_true", help="Double-render every clip and fail if bytes differ.")
    args = parser.parse_args()
    print(json.dumps(build_corpus(args.out_dir, args.manifest, check=args.check), indent=2))


if __name__ == "__main__":
    main()
