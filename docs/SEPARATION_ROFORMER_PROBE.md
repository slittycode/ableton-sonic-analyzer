# Separation RoFormer Probe (research only)

**Status:** Offline experiment. Does **not** change product Demucs default.  
**Updated:** 2026-07-18  
**Why:** ASA’s Hybrid Demucs is weak on vocals (ghost stems, lead bleed into `vocals`/`other`). RoFormer-class models may fix vocals and/or multi-stem quality. Prior BS-RoFormer optional path was cut in the 2026-07 trust diet for “no recorded win” — this probe re-opens **ear + field** comparison on real tracks before any product seam work.

**Authority:** `PURPOSE.md`. Measurement authority stays Demucs until a bake-off proves otherwise.

---

## Two RoFormers (both worth playing with)

| Role | Package / model | What you get | When it wins |
|---|---|---|---|
| **A. Multi-stem** | `bs-roformer-infer` default `roformer-model-bs-roformer-sw-by-jarredou` | Up to **6 stems** (vocals, drums, bass, guitar, piano, other) | Better drums/bass/other isolation; maps closer to ASA’s 4-stem world (fold guitar+piano→other) |
| **B. Vocals specialist** | `melband-roformer-infer` default `melband-roformer-kim-vocals` | **Vocals + residual** (instrumental) | Cleaner vocal isolate for `vocalDetail` / vocal pitch — ASA’s known pain |
| **C. Kitchen sink** | `audio-separator` | Huge UVR model zoo (BS-RoFormer Viperx, MelBand Kim, ensembles) | Shopping models without swapping packages; heavier deps |

**Product baseline (always run for A/B):** ASA Demucs via `analyze_audio_io.separate_stems` → `drums` / `bass` / `other` / `vocals`.

Suggested first play set (3 runs, not 30):

1. **Demucs** (baseline)  
2. **BS-RoFormer-SW** (multi-stem)  
3. **MelBand Kim vocals** (vocal specialist)  

Optional 4th: `audio-separator` default BS-RoFormer Viperx vocals model if you want a second vocal take.

---

## Setup (separate eval venv — never product `apps/backend/venv`)

```bash
# From repo root (asa/)
python3.11 -m venv /tmp/asa-roformer-eval
source /tmp/asa-roformer-eval/bin/activate
pip install -U pip

# Pick one or both RoFormer packages (lighter than full audio-separator):
pip install 'bs-roformer-infer>=0.1.5' 'melband-roformer-infer>=0.1.5'

# Optional model zoo (heavier; numpy pins may fight product stack — keep isolated):
# pip install 'audio-separator[cpu]'   # or [gpu] on CUDA

# Product Demucs baseline uses apps/backend venv (already has torch/torchaudio):
#   apps/backend/venv/bin/python
```

First inference downloads ~700MB–1GB checkpoints into:

- `~/.cache/bs-roformer-infer/`
- `~/.cache/melband-roformer-infer/`

List models:

```bash
bs-roformer-download --list-models
melband-roformer-download --list-models
# audio-separator -l --list_filter=vocals --list_limit=10
```

---

## Driver script

```bash
# From apps/backend (product venv for Demucs; RoFormer CLIs from eval venv on PATH)
cd apps/backend
source venv/bin/activate

# Put RoFormer CLIs on PATH if they live in the eval venv:
export PATH="/tmp/asa-roformer-eval/bin:$PATH"

./venv/bin/python scripts/probe_roformer_separation.py /path/to/track.wav \
  --backends demucs,bs_roformer,melband_vocals \
  --out .runtime/separation_probe
```

Outputs:

```
.runtime/separation_probe/<track_stem>/
  demucs/drums.wav
  demucs/bass.wav
  demucs/other.wav
  demucs/vocals.wav
  bs_roformer/...          # whatever the model emits (may be 6 stems)
  melband_vocals/vocals... # + instrumental residual
  manifest.json            # paths, timings, listen checklist
```

---

## How to listen (pass/fail for vocals)

On **vocal tracks**:

1. Solo Demucs `vocals` vs MelBand `vocals` — which has less instrumental bleed?  
2. Solo Demucs `other` — is the lead still half there?  
3. Check instrumental residual (MelBand) — are vocals gone cleanly?

On **instrumentals**:

1. Demucs `vocals` often has ghost energy — MelBand should be quieter/near-empty.  
2. Note for `vocalDetail.stemEnergyRatio` / false `hasVocals`.

On **multi-stem (BS-RoFormer)**:

1. Kick/snare definition in `drums` vs Demucs  
2. Bass mono-compatibility / sub leak into other  
3. Whether 6-stem fold-down to ASA’s 4 names is obvious (guitar+piano→other)

---

## What would justify product work later

Not “sounds cooler.” Need at least one of:

1. Clear vocal isolate win on ≥3 real vocal tracks **and** fewer ghost vocals on ≥2 instrumentals  
2. Measurable lift on `vocalDetail` confidence calibration (or lower false positives)  
3. Optional: better kick/bass stems that move `kickDetail` / bass notes  

Then: thin research backend behind `separation_backend.py` (or vocals-only override), still default Demucs until owner flips.

---

## Trust-diet note

Former MSST/BS-RoFormer product-optional path: removed 2026-07 (`plans/trust-diet-2026-07.md`). This probe is **offline only** — restore product wiring only with corpus evidence, not nostalgia.
