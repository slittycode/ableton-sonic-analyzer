# sonic-analyzer

Local DSP audio analysis engine for music production workflows, focused on reconstructing tracks in Ableton Live 12 from measurable audio descriptors.

The tool analyses an input master or stem and emits structured JSON for downstream use (for example, LLM-assisted production notes, arrangement reconstruction, and mix diagnostics).

## Project Overview

`sonic-analyzer` is a single-script analysis pipeline (`analyze.py`) built around Essentia algorithms, with optional source separation for cleaner melody extraction.

Core design goals:
- deterministic local analysis (no cloud inference required)
- robust error-safe execution (`null` on failure, no hard crashes in feature functions)
- practical production-oriented descriptors (loudness, groove, harmony, structure, sidechain, stereo)

## Tech Stack

- Python 3.13 (tested)
- Essentia 2.1b6 (dev build in current environment)
- Demucs (optional source separation via `--separate`)
- mido (optional MIDI export from melody notes)

## Requirements

- macOS ARM64 (tested)
- Python 3.10-3.13

## Installation

```bash
python3.13 -m venv venv
./venv/bin/pip install essentia demucs mido
```

## Basic Usage

```bash
./venv/bin/python analyze.py <audio_file>
./venv/bin/python analyze.py <audio_file> --separate
./venv/bin/python analyze.py <audio_file> --fast
```

Notes:
- `--separate` runs Demucs stem separation first (CPU-heavy; typically adds ~30-60s).
- `--fast` is currently a parser stub/no-op for future optimisation work.

## Supported Input Formats

- MP3
- FLAC
- WAV

FLAC is recommended for best pitch and melody accuracy.

## Output Behaviour

- JSON analysis is written to `stdout`
- warnings/errors/progress logs are written to `stderr`

This split is intentional so you can pipe JSON cleanly:

```bash
./venv/bin/python analyze.py track.flac > analysis.json
```

## Output Schema Reference

See [JSON_SCHEMA.md](JSON_SCHEMA.md) for exhaustive field documentation and interpretation notes.

## Quick Example (Real Output — Vtss, Can't Catch Me)

- `bpm`: `144.3` (Percival cross-check: `144.6`, agreement: `true`)
- `key`: `"Ab Major"` (confidence: `0.65`)
- `lufsIntegrated`: `-7.5` (club-loud master, true peak `+1.0 dBTP`)
- `stereoDetail.subBassMono`: `true` (subBassCorrelation: `0.98`)
- `sidechainDetail.pumpingConfidence`: `0.25` (low — ambiguous kick/sub overlap expected on this genre)
- `segmentKey`: `["Ab Major", "F Major", "Ab Major"]` (harmonic shift detected in transition segment)
- `structure.segmentCount`: `3` (main body → 5s transition → outro)
