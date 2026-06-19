# Recommendation Ground-Truth Corpus

This is the answer-key corpus for **GOAL.md sub-goal 1**. Each fixture is an
Ableton Live 12 project with **known** device settings, rendered to audio, paired
with a machine-readable manifest. The scorer
(`apps/backend/recommendation_evaluation.py`, run via
`scripts/evaluate_recommendations.py`) checks whether ASA's recommendations
recover those known settings — turning recommendation quality from an ear-test
into a number.

Audio is **never committed** (same policy as `../transcription_tracks/` and
`../polyphonic_tracks/`) — it lives in your local copy only. The committed
artifacts are the `manifest.json` answer keys and these READMEs. A fixture whose
audio you have not rendered yet still validates (catalog-validity) and SKIPs the
parts that need the render.

## The authoring model — "spec-then-dial" (fork 3)

The agent does **not** generate `.als` files and you do **not** design chains from
scratch. Instead:

1. The agent writes an explicit, **catalog-valid device spec** in `manifest.json`
   — exact Live 12 devices, exact parameter names (must exist in
   `apps/backend/prompts/live12_device_catalog.json`), exact values.
2. **You build exactly that spec in Live and render it.** Because the spec is the
   instruction, the answer key is provably the spec — there is no `.als`-parsing
   trust gap.
3. The agent ingests the render (stores a Phase 1 fingerprint) and finalizes the
   fixture.

## Directory layout

```
recommendation_tracks/
  README.md                         ← this file (schema + authoring checklist)
  _TEMPLATE/manifest.template.json  ← copy this to start a new fixture
  <slug>/
    manifest.json                   ← the answer key (committed)
    README.md                       ← what this fixture isolates (committed)
    audio.flac                      ← your render (NOT committed, gitignored)
    phase1_fingerprint.json         ← stored Phase 1 of the render (committed once rendered)
```

## manifest.json schema (`recommendation-fixture.v1`)

| Field | Meaning |
|---|---|
| `schemaVersion` | `"recommendation-fixture.v1"` |
| `id` | fixture slug (matches the directory name) |
| `title`, `genre` | human labels; `genre` should be one the owner actually makes |
| `audioPath` | render filename relative to the fixture dir (e.g. `"audio.flac"`) |
| `phase1FingerprintPath` | sibling file holding the stored Phase 1 of the render |
| `phase1Fingerprint` | inline fingerprint, or `null` until rendered (then prefer the sibling file) |
| `render` | `sampleRateHz` (48000), `bitDepth` (24), `lengthSeconds`, `bpm`, `key`, `notes` |
| `deviceSpec` | **the answer key.** Keyed by production domain; each value is an ordered device chain (see below) |
| `measurableIntent` | Phase 1 dotted-path → `{target, tolerance, direction, unit}` — the *measurable* intent, so equivalent reconstructions earn credit |

### `deviceSpec` — keyed by the seven production domains

The keys are ASA's reconstruction surface (PURPOSE.md invariant #5):
`kick`, `bass`, `melody`, `groove`, `fx`, `stereo`, `master`. Each holds an
**ordered** list of device entries:

```json
{
  "device": "Operator",                 // must be in live12_device_catalog.json
  "family": "NATIVE",                   // NATIVE | MAX_FOR_LIVE (validated)
  "role": "Sub bass",                   // free-text human label
  "parameters": [
    { "name": "Filter Frequency", "value": "200 Hz", "intent": "why this value" }
  ]
}
```

- `name` must be an `allowedParameters` entry (or a `parameterAliases` key) for
  that device in the catalog. Run the ingest check (below) — it fails loudly on a
  typo.
- `value` is free text; the scorer parses numeric magnitudes + units
  (`Hz`, `kHz`, `dB`, `ms`, `s`, `%`, `:1` ratio, `st`). Non-numeric values
  (`"Sine"`, `"Auto"`, `"Lowpass"`) are scored on parameter coverage only.
- `intent` is optional prose for the human builder.

### `measurableIntent` — what the render should measure

The equivalence safety net. A recommendation that reaches the same measured
outcome by a different valid route still earns credit, so the manifest records
the *measurable* intent next to the literal spec. Mirrors the threshold idiom in
`../phase1_eval_manifest.json`:

```json
"measurableIntent": {
  "bpm": { "target": 124, "tolerance": 1, "direction": "exact" },
  "kickDetail.fundamentalHz": { "target": 55, "tolerance": 15, "unit": "Hz" },
  "sidechainDetail.pumpingStrength": { "target": 0.5, "tolerance": 0.25, "direction": "min" }
}
```

Targets you author before rendering are **estimates**; the stored
`phase1_fingerprint.json` is the source of truth once the render exists.

## Authoring checklist (the owner follows this in Live)

1. **Copy the template**: `cp -r _TEMPLATE <slug>` and rename `manifest.template.json` → `manifest.json`. Set `id` to `<slug>`.
2. **Build the spec exactly** in a new Live 12 set. One device chain per domain,
   exactly the devices and parameter values in `deviceSpec`. Keep it a clean,
   sparse loop — a few clear, measurable decisions, not a dense full mix.
3. **Set the project to 48 kHz / 24-bit** (Preferences → Audio; Export → 24-bit,
   48000 Hz). This matches the project default and the `render` block.
4. **Render the loop** (Export Audio/Video) to `audio.flac` (or `.wav`) in the
   fixture dir. **Do not normalize on export** — measured LUFS / true-peak is part
   of the answer key.
5. **Ingest it** with the one-command workflow. This validates the render and
   catalog, stores the canonical Phase 1 fingerprint, checks measurable intent,
   generates Claude + deterministic recommendations, scores all sources, and
   refreshes the verification artifact:
   ```bash
   ./venv/bin/python scripts/intake_recommendation_fixture.py --fixture <slug>
   ```
6. **Confirm** the measured fingerprint plausibly matches `measurableIntent`
   (e.g. BPM, kick fundamental). Adjust the manifest's intent targets to the
   measured values where they were estimates.
7. **Commit** `manifest.json`, `README.md`, and `phase1_fingerprint.json`
   (audio stays gitignored).

## Running the scorer

```bash
# Always-runnable self-test (proves the score moves on a known-bad rec):
./venv/bin/python scripts/evaluate_recommendations.py --self-test

# Score a source over the whole corpus:
./venv/bin/python scripts/evaluate_recommendations.py --source baseline
./venv/bin/python scripts/evaluate_recommendations.py --source gemini --phase2 <phase2.json>
./venv/bin/python scripts/evaluate_recommendations.py --recommendations <normalized.json>
```

See `apps/backend/NEEDS.md` for the needs-fixture / needs-listen queue (the
renders still owed, and the deterministic-source wiring) and for how sub-goals 3
and 4 build on this corpus.
