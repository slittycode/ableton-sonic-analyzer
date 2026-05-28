#!/usr/bin/env python3
"""Generate the Live 12 addressable-target catalogue from an upstream clone.

The upstream is the decompiled `gluon/AbletonLive12_MIDIRemoteScripts` repository,
which mirrors Ableton's MIDI Remote Scripts directory. The single source file
`Push2/custom_bank_definitions.py` contains a `BANK_DEFINITIONS` dict that maps
Live's internal device class names (e.g. `Saturator`, `Eq8`, `GlueCompressor`) to
banked parameter lists.

We parse that file via the stdlib `ast` module — never executing it — and walk
the BANK_DEFINITIONS dict to collect, per device class, every parameter name
referenced by any bank. The output is written to `data/live12_catalogue.json`
and validated against `data/live12_catalogue.schema.json` semantics.

Static source does NOT carry parameter ranges, types, units, or defaults: those
live on runtime `Live.DeviceParameter` objects. The schema reserves space for
them but the generator emits names only.

Usage
-----
    scripts/build_live12_catalogue.py \\
        --source /path/to/gluon/AbletonLive12_MIDIRemoteScripts \\
        --output data/live12_catalogue.json

If `--source` is omitted, the script reads $SONIC_ANALYZER_LIVE12_SOURCE. If
neither is set, it errors out — the catalogue must be deterministic, with no
implicit clone-at-request-time behavior.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SOURCE_FILES_REL: tuple[str, ...] = (
    "Push2/custom_bank_definitions.py",
    "Move/custom_bank_definitions.py",
)
PRIMARY_SOURCE_FILE_REL = SOURCE_FILES_REL[0]
SOURCE_URL = "https://github.com/gluon/AbletonLive12_MIDIRemoteScripts"
LICENSE_NOTE = (
    "Upstream is a decompiled redistribution of Ableton's MIDI Remote Scripts. "
    "ASA does not ship any upstream source; this catalogue records only the "
    "device-class and parameter-name metadata extracted via static AST parsing, "
    "used as a Phase 2 output-validation gate."
)
EXTRACTION_NOTES = (
    "Generated from the upstream Live 12 MIDI Remote Scripts via stdlib ast. "
    "Push2/custom_bank_definitions.py contributes the BANK_DEFINITIONS dict "
    "literal; Move/custom_bank_definitions.py contributes additional "
    "CUSTOM_BANK_DEFINITIONS[<class>] = IndexedDict(...) subscript assignments "
    "(including Live 12-new devices like AutoShift). Per-class parameter sets "
    "are the union across all source files. Parameter names are taken from "
    "BANK_PARAMETERS_KEY and OPTIONS_KEY tuples and from use(...)/else_use(...)/"
    "if_parameter(...) call arguments. type/min/max/unit/default are intentionally "
    "omitted because they are not present in static source; they live on runtime "
    "Live.DeviceParameter objects."
)
SCHEMA_VERSION = "1"

PARAM_NAME_METHODS: frozenset[str] = frozenset({
    "use",
    "else_use",
    "if_parameter",
    "and_parameter",
    "or_parameter",
})


# Hand-mapped display names: Live's internal class -> the label Ableton's UI shows.
# Any class not in this map gets `displayName == class`. Mapping is the single
# bridge between curated UI-name recommendations (what Gemini cites) and
# canonical-class catalogue keys (what the upstream source uses).
DISPLAY_NAMES: dict[str, str] = {
    "UltraAnalog": "Analog",
    "ChannelEq": "Channel EQ",
    "Compressor2": "Compressor",
    "Chorus2": "Chorus-Ensemble",
    "Drift": "Drift",
    "DrumBuss": "Drum Buss",
    "DrumCell": "Drum Sampler",
    "Echo": "Echo",
    "Eq8": "EQ Eight",
    "FilterEQ3": "EQ Three",
    "Erosion": "Erosion",
    "FilterDelay": "Filter Delay",
    "FrequencyShifter": "Frequency Shifter",
    "Gate": "Gate",
    "GlueCompressor": "Glue Compressor",
    "GrainDelay": "Grain Delay",
    "Hybrid": "Hybrid Reverb",
    "InstrumentImpulse": "Impulse",
    "InstrumentMeld": "Meld",
    "InstrumentVector": "Wavetable",
    "Limiter": "Limiter",
    "Looper": "Looper",
    "LoungeLizard": "Electric",
    "MidiArpeggiator": "Arpeggiator",
    "MidiCcControl": "MIDI CC Control",
    "MidiChord": "Chord",
    "MidiNoteLength": "Note Length",
    "MidiPitcher": "Pitch",
    "MidiRandom": "Random",
    "MidiScale": "Scale",
    "MidiVelocity": "Velocity",
    "MultiSampler": "Sampler",
    "MultibandDynamics": "Multiband Dynamics",
    "Operator": "Operator",
    "OriginalSimpler": "Simpler",
    "Overdrive": "Overdrive",
    "Pedal": "Pedal",
    "Phaser": "Phaser",
    "PhaserNew": "Phaser-Flanger",
    "Redux2": "Redux",
    "Resonator": "Resonators",
    "Reverb": "Reverb",
    "Roar": "Roar",
    "Saturator": "Saturator",
    "Shifter": "Shifter",
    "Spectral": "Spectral Resonator",
    "StereoGain": "Utility",
    "StringStudio": "Tension",
    "Transmute": "Spectral Time",
    "Tube": "Dynamic Tube",
    "Vinyl": "Vinyl Distortion",
    "Vocoder": "Vocoder",
    "Cabinet": "Cabinet",
    "Amp": "Amp",
    "AutoFilter": "Auto Filter",
    "AutoPan": "Auto Pan-Tremolo",
    "BeatRepeat": "Beat Repeat",
    "Chorus": "Chorus",
    "Collision": "Collision",
    "Corpus": "Corpus",
    "Delay": "Delay",
    "Flanger": "Flanger",
    "Redux": "Redux Legacy",
    "AudioEffectGroupDevice": "Audio Effect Rack",
    "MidiEffectGroupDevice": "MIDI Effect Rack",
    "InstrumentGroupDevice": "Instrument Rack",
    "DrumGroupDevice": "Drum Rack",
    "ProxyAudioEffectDevice": "Audio Effect (Proxy)",
    # Move-only additions (Live 12 device classes that only appear in
    # Move/custom_bank_definitions.py CUSTOM_BANK_DEFINITIONS subscripts).
    "AutoShift": "Auto Shift",
    "AutoFilter2": "Auto Filter (Move)",
    "AutoPan2": "Auto Pan-Tremolo (Move)",
    "Erosion2": "Erosion (Move)",
}


# Coarse category classifier. Falls back to "audio_effect" for any class not
# explicitly listed — that matches Live's grouping for most leftover entries
# (most of `BANK_DEFINITIONS` is audio effects).
CATEGORIES: dict[str, str] = {
    # Instruments
    "UltraAnalog": "instrument",
    "Collision": "instrument",
    "DrumCell": "instrument",
    "Drift": "instrument",
    "Hybrid": "audio_effect",  # Hybrid Reverb is an audio effect, not an instrument
    "InstrumentImpulse": "instrument",
    "InstrumentMeld": "instrument",
    "InstrumentVector": "instrument",
    "LoungeLizard": "instrument",
    "MultiSampler": "instrument",
    "Operator": "instrument",
    "OriginalSimpler": "instrument",
    "StringStudio": "instrument",
    # MIDI effects
    "MidiArpeggiator": "midi_effect",
    "MidiCcControl": "midi_effect",
    "MidiChord": "midi_effect",
    "MidiNoteLength": "midi_effect",
    "MidiPitcher": "midi_effect",
    "MidiRandom": "midi_effect",
    "MidiScale": "midi_effect",
    "MidiVelocity": "midi_effect",
    # Racks
    "AudioEffectGroupDevice": "rack",
    "MidiEffectGroupDevice": "rack",
    "InstrumentGroupDevice": "rack",
    "DrumGroupDevice": "rack",
}


# Inside a BANK_PARAMETERS_KEY / OPTIONS_KEY tuple, these section/separator
# strings appear and are NOT parameter names. They are bank-section headings,
# blank-encoder placeholders, etc.
KNOWN_NON_PARAMETER_STRINGS: frozenset[str] = frozenset({
    "",
})


def _resolve_source_root(args: argparse.Namespace) -> Path:
    if args.source:
        return Path(args.source).expanduser().resolve()
    env_source = os.environ.get("SONIC_ANALYZER_LIVE12_SOURCE")
    if env_source:
        return Path(env_source).expanduser().resolve()
    raise SystemExit(
        "ERROR: pass --source <path-to-upstream-clone> or set "
        "SONIC_ANALYZER_LIVE12_SOURCE. Catalogue generation is deterministic; "
        "the upstream clone is never fetched at request time."
    )


def _git_head_sha(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"ERROR: could not read upstream HEAD SHA at {repo_root}: {exc}"
        ) from exc
    sha = result.stdout.strip()
    if not sha:
        raise SystemExit(f"ERROR: upstream HEAD SHA at {repo_root} is empty.")
    return sha


def _read_source(source_root: Path, source_rel: str, required: bool) -> tuple[str | None, Path]:
    source_path = source_root / source_rel
    if not source_path.is_file():
        if required:
            raise SystemExit(
                f"ERROR: expected upstream file {source_rel} not found at {source_path}."
            )
        return None, source_path
    return source_path.read_text(encoding="utf-8"), source_path


def _extract_param_names_from_call(call: ast.Call) -> list[str]:
    """Walk a chained call like
    `use("X").if_parameter("P").has_value("V").else_use("Y").with_name("Z")`
    and collect parameter names from `use/else_use/if_parameter/and_parameter/
    or_parameter` arg-zero only. `has_value` and `with_name` carry display or
    value strings, never parameter names, and are skipped.
    """
    names: list[str] = []
    current: ast.AST = call
    while isinstance(current, ast.Call):
        method = None
        receiver: ast.AST | None = None
        if isinstance(current.func, ast.Attribute):
            method = current.func.attr
            receiver = current.func.value
        elif isinstance(current.func, ast.Name):
            method = current.func.id

        if method in PARAM_NAME_METHODS and current.args:
            arg0 = current.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                stripped = arg0.value.strip()
                if stripped and stripped not in KNOWN_NON_PARAMETER_STRINGS:
                    names.append(arg0.value)

        if receiver is None or not isinstance(receiver, ast.Call):
            break
        current = receiver
    return names


def _extract_param_names_from_elt(elt: ast.AST) -> list[str]:
    """Element inside a parameter tuple. Either a string constant or a chained
    `use(...)` expression."""
    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
        stripped = elt.value.strip()
        if stripped and stripped not in KNOWN_NON_PARAMETER_STRINGS:
            return [elt.value]
        return []
    if isinstance(elt, ast.Call):
        return _extract_param_names_from_call(elt)
    return []


def _collect_param_names_from_value(value: ast.AST) -> list[str]:
    """The value bound to BANK_PARAMETERS_KEY or OPTIONS_KEY. Usually a tuple
    of items; occasionally a bare string constant (e.g. `'Resonator': '"Select"'`
    in the upstream — a bare string serving as a one-element bank)."""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return _extract_param_names_from_elt(value)
    if isinstance(value, ast.Tuple):
        names: list[str] = []
        for elt in value.elts:
            names.extend(_extract_param_names_from_elt(elt))
        return names
    if isinstance(value, ast.Call):
        return _extract_param_names_from_call(value)
    return []


def _is_parameter_key_node(node: ast.AST) -> bool:
    """Match either the Name `BANK_PARAMETERS_KEY`/`OPTIONS_KEY` or the
    equivalent string constants (in case the upstream ever inlines them)."""
    if isinstance(node, ast.Name):
        return node.id in ("BANK_PARAMETERS_KEY", "OPTIONS_KEY")
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value in ("BANK_PARAMETERS_KEY", "OPTIONS_KEY")
    return False


def _extract_params_from_indexeddict_call(node: ast.Call) -> list[str]:
    """Walk `IndexedDict(((bank_name, bank_dict), ...))`. Each bank_dict has
    BANK_PARAMETERS_KEY (and sometimes OPTIONS_KEY) entries whose values
    enumerate parameter names referenced by that bank."""
    if not (isinstance(node.func, ast.Name) and node.func.id == "IndexedDict"):
        return []
    if not node.args or not isinstance(node.args[0], ast.Tuple):
        return []
    names: list[str] = []
    for entry in node.args[0].elts:
        if not isinstance(entry, ast.Tuple) or len(entry.elts) < 2:
            continue
        bank_body = entry.elts[1]
        if not isinstance(bank_body, ast.Dict):
            continue
        for key, value in zip(bank_body.keys, bank_body.values):
            if _is_parameter_key_node(key):
                names.extend(_collect_param_names_from_value(value))
    return names


def _find_top_level_assign(tree: ast.Module, name: str) -> ast.AST | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    return None


def _collect_subscript_assignments(
    tree: ast.Module, target_name: str
) -> dict[str, ast.AST]:
    """Collect `<target_name>['ClassName'] = <expr>` subscript assignments.

    Returns {device_class: value_node}. Used to harvest entries from
    `Move/custom_bank_definitions.py` (`CUSTOM_BANK_DEFINITIONS['AutoShift'] = IndexedDict(...)`)
    on top of the `BANK_DEFINITIONS` dict literal from `Push2/...`.
    """
    result: dict[str, ast.AST] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Subscript):
                continue
            if not (isinstance(target.value, ast.Name) and target.value.id == target_name):
                continue
            slice_node = target.slice
            if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                result[slice_node.value] = node.value
                break
    return result


def _collect_device_parameters_from_tree(
    tree: ast.Module,
    is_primary: bool,
) -> dict[str, list[str]]:
    """Walk a parsed bank-definitions module and return {class: param names}.

    `is_primary=True` parses a Push2-style `BANK_DEFINITIONS = {...}` dict
    literal. `is_primary=False` parses a Move-style sequence of
    `CUSTOM_BANK_DEFINITIONS['<class>'] = IndexedDict(...)` subscript
    assignments. Both flavors share the inner `IndexedDict(...)` shape.
    """
    rack_banks_value = _find_top_level_assign(tree, "RACK_BANKS")
    rack_banks_params: list[str] = []
    if isinstance(rack_banks_value, ast.Call):
        rack_banks_params = _extract_params_from_indexeddict_call(rack_banks_value)

    result: dict[str, list[str]] = {}

    if is_primary:
        bank_definitions_value = _find_top_level_assign(tree, "BANK_DEFINITIONS")
        if not isinstance(bank_definitions_value, ast.Dict):
            raise SystemExit(
                "ERROR: expected `BANK_DEFINITIONS = {...}` top-level dict assignment in primary upstream."
            )
        for key, value in zip(bank_definitions_value.keys, bank_definitions_value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            device_class = key.value
            if isinstance(value, ast.Name) and value.id == "RACK_BANKS":
                result[device_class] = list(rack_banks_params)
                continue
            if isinstance(value, ast.Call):
                result[device_class] = _extract_params_from_indexeddict_call(value)
                continue

    subscripts = _collect_subscript_assignments(tree, "CUSTOM_BANK_DEFINITIONS")
    for device_class, value in subscripts.items():
        if isinstance(value, ast.Name) and value.id == "RACK_BANKS":
            result.setdefault(device_class, list(rack_banks_params))
            continue
        if isinstance(value, ast.Call):
            new_names = _extract_params_from_indexeddict_call(value)
            if device_class in result:
                result[device_class] = list(set(result[device_class]) | set(new_names))
            else:
                result[device_class] = new_names

    return result


def _merge_device_parameters(
    *sources: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Per-device union across multiple source files. Per-device parameter
    lists are deduped and sorted at the end so the catalogue output is
    canonical regardless of file order."""
    merged: dict[str, set[str]] = {}
    for source in sources:
        for device_class, names in source.items():
            merged.setdefault(device_class, set()).update(names)
    return {device_class: sorted(names) for device_class, names in merged.items()}


def _collect_device_parameters(tree: ast.Module) -> dict[str, list[str]]:
    """Back-compat wrapper for callers that pass a single primary tree (used by
    the in-memory `build_catalogue_from_text` entry point)."""
    return _merge_device_parameters(
        _collect_device_parameters_from_tree(tree, is_primary=True)
    )


def _build_catalogue(
    *,
    devices: dict[str, list[str]],
    source_commit: str,
    generated_at: str,
    source_files: tuple[str, ...] = (PRIMARY_SOURCE_FILE_REL,),
) -> dict:
    catalogue_devices: list[dict] = []
    for device_class in sorted(devices):
        param_names = devices[device_class]
        display_name = DISPLAY_NAMES.get(device_class, device_class)
        category = CATEGORIES.get(device_class, "audio_effect")
        catalogue_devices.append(
            {
                "class": device_class,
                "category": category,
                "displayName": display_name,
                "parameters": [
                    {"name": name} for name in sorted(set(param_names))
                ],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "source_commit": source_commit,
        "source_url": SOURCE_URL,
        "source_files": list(source_files),
        "license_note": LICENSE_NOTE,
        "generated_at": generated_at,
        "extraction_notes": EXTRACTION_NOTES,
        "devices": catalogue_devices,
    }


def _utc_iso8601_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_catalogue_from_source(
    *,
    source_root: Path,
    source_commit: str | None = None,
    generated_at: str | None = None,
) -> dict:
    """Library entry point used by tests and the CLI. Reads the upstream
    bank-definitions files and returns the catalogue dict.

    Walks every file in `SOURCE_FILES_REL` against `source_root`. The first
    entry is the primary file (BANK_DEFINITIONS dict literal); subsequent
    entries are optional supplementary files containing
    `CUSTOM_BANK_DEFINITIONS[<class>] = IndexedDict(...)` subscript
    assignments. The catalogue is the union of all per-device parameter sets.
    """
    per_file_devices: list[dict[str, list[str]]] = []
    found_files: list[str] = []
    for index, source_rel in enumerate(SOURCE_FILES_REL):
        text, path = _read_source(source_root, source_rel, required=(index == 0))
        if text is None:
            continue
        tree = ast.parse(text, filename=source_rel)
        per_file_devices.append(
            _collect_device_parameters_from_tree(tree, is_primary=(index == 0))
        )
        found_files.append(source_rel)
    devices = _merge_device_parameters(*per_file_devices)
    if source_commit is None:
        source_commit = _git_head_sha(source_root)
    if generated_at is None:
        generated_at = _utc_iso8601_now()
    return _build_catalogue(
        devices=devices,
        source_commit=source_commit,
        generated_at=generated_at,
        source_files=tuple(found_files) or (PRIMARY_SOURCE_FILE_REL,),
    )


def build_catalogue_from_text(
    *,
    bank_definitions_text: str,
    source_commit: str,
    generated_at: str,
) -> dict:
    """Generate a catalogue from in-memory source text (used by the generator
    unit test against the vendored fixture)."""
    tree = ast.parse(bank_definitions_text, filename=PRIMARY_SOURCE_FILE_REL)
    devices = _collect_device_parameters(tree)
    return _build_catalogue(
        devices=devices,
        source_commit=source_commit,
        generated_at=generated_at,
    )


def _write_catalogue(catalogue: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n"
    output_path.write_text(serialized, encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=None,
        help=(
            "Path to the local clone of gluon/AbletonLive12_MIDIRemoteScripts. "
            "Falls back to $SONIC_ANALYZER_LIVE12_SOURCE."
        ),
    )
    parser.add_argument(
        "--output",
        default="data/live12_catalogue.json",
        help=(
            "Where to write the generated catalogue. Path is relative to the repo "
            "root unless absolute. Default: data/live12_catalogue.json."
        ),
    )
    parser.add_argument(
        "--source-commit",
        default=None,
        help=(
            "Override the recorded source commit SHA. By default the script reads "
            "git HEAD from --source."
        ),
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help=(
            "Override the recorded generation timestamp (ISO-8601 UTC). Use this "
            "for deterministic regenerations during review."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    source_root = _resolve_source_root(args)
    catalogue = build_catalogue_from_source(
        source_root=source_root,
        source_commit=args.source_commit,
        generated_at=args.generated_at,
    )

    repo_root = Path(__file__).resolve().parents[1]
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    _write_catalogue(catalogue, output_path)
    print(
        f"Wrote {len(catalogue['devices'])} devices to {output_path} "
        f"(source {catalogue['source_commit'][:12]})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
