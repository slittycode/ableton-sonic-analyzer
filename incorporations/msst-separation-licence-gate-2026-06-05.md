# MSST / BS-RoFormer separation backend — licence gate

**Date:** 2026-06-05 · **Status:** GATE — documented blocker, default stays Demucs · **Scope:** the optional `ASA_SEPARATION_BACKEND=msst` path landed in [PR #141](https://github.com/slittycode/ableton-sonic-analyzer/pull/141) (`separation_backend.py`, `scripts/msst_separate_runner.py`, the A/B harness).

> *Not legal advice.* This records the licences as distributed and ASA's containment posture so a promotion decision is made with eyes open — it is not a legal opinion.

## Why this doc exists

The separation-backend campaign's first instruction was *"confirm the repo AND per-model weight licences first."* The infrastructure (PR #141) shipped before that confirmation was on record, and MSST-WebUI was never entered in the repo's existing licence-map discipline ([`forking-plans-2026-05-14.md`](forking-plans-2026-05-14.md)). This closes that gap. **Bottom line: the MSST backend as currently wired is research / personal / NonCommercial-only and must not be promoted to a commercial default.**

## Licence map (verified 2026-06-05)

| Component | Licence *as distributed* | Source | Implication for ASA |
|---|---|---|---|
| **ASA** (this repo) | MIT ([LICENSE](../LICENSE)) | repo | May *shell out* to AGPL tools at arms length; may **not** vendor or import AGPL code. |
| **MSST-WebUI** code | **AGPL-3.0** | [raw LICENSE](https://raw.githubusercontent.com/SUC-DriverOld/MSST-WebUI/main/LICENSE) — "GNU AFFERO GENERAL PUBLIC LICENSE Version 3" | Strong network-copyleft. ASA ships **zero** MSST code; the operator installs it into its own venv and ASA invokes it as a subprocess. See "AGPL containment" below. |
| **`model_scnet_sdr_9.3244.ckpt`** (registry id `scnet_4stem`) | **CC-BY-NC-SA-4.0** (explicit) | [`Sucial/MSST-WebUI`](https://huggingface.co/Sucial/MSST-WebUI) HF repo tag + per-file; trained on **MUSDB18-HQ** (`config_musdb18_scnet.yaml`) | **NonCommercial.** Attribution + ShareAlike. NC is inherited twice — explicit repo licence *and* MUSDB18 training data. Not promotable to a commercial default. |
| **`model_bs_roformer_ep_368_sdr_12.9628.ckpt`** (registry id `bs_roformer_vocals`) | **CC-BY-NC-SA-4.0** (explicit) | same HF repo (lucidrains BS-RoFormer *code* is MIT; these *weights* are not) | **NonCommercial.** Research / A-B only regardless (2-stem; leaves bass/drums empty). |
| **Demucs incumbent** — torchaudio `HDEMUCS_HIGH_MUSDB_PLUS` (what `analyze_audio_io.separate_stems` actually loads) | code **MIT/BSD**; weights carry **no explicit licence**, trained on MUSDB18-HQ + Meta-internal data | [facebookresearch/demucs README](https://github.com/facebookresearch/demucs) ("released under the MIT license"); [torchaudio pipeline doc](https://docs.pytorch.org/audio/stable/generated/torchaudio.pipelines.HDEMUCS_HIGH_MUSDB_PLUS.html) | The grey baseline MSST would replace — see the comparison below. |

## The finding that actually matters: this is a downgrade, not an upgrade (on licence terms)

It is tempting to frame the gate as "MSST is NonCommercial, Demucs is clean." **That is wrong and would mislead by omission.** The incumbent Demucs weights are *also* MUSDB18-derived — neither backend rests on commercially-clean weights. The real, honest difference is in how *explicit and binding* the encumbrance is:

| Axis | Demucs (incumbent) | MSST (candidate) | Direction |
|---|---|---|---|
| Driver-code licence | MIT / BSD (permissive) | **AGPL-3.0** (network copyleft) | ⬇ worse |
| Weights licence *as distributed* | **no explicit licence** (upstream licenses only the code) | **explicit CC-BY-NC-SA-4.0** | ⬇ worse |
| Training-data provenance | MUSDB18-HQ + Meta internal (NC provenance, unforegrounded) | MUSDB18-HQ (NC) | ≈ same |

So adopting MSST trades an *implicit, unforegrounded* NC-provenance risk for an **explicit, contractually-binding NonCommercial + ShareAlike licence**, and swaps a permissive driver for an AGPL one. On licence posture it is **strictly worse on both axes.** The quality win (higher published SDR) may still justify it for **NonCommercial use**, but it cannot be the answer to "make ASA's separation commercially shippable."

**Corollary (the strategic conclusion):** there is no commercially-promotable separation upgrade *in this repo's model set*. A genuinely commercial default would need weights trained on open/cleared data and distributed under a permissive or commercial licence — not these checkpoints, and not the current Demucs weights either. That is a sourcing problem, not a wiring problem.

## AGPL containment (why the AGPL *code* is acceptable, default-off)

ASA's MIT licence is preserved because the AGPL boundary is a process boundary, not a link:
1. **Zero AGPL code is shipped or vendored.** `requirements-msst.txt` is a *setup pointer*, not a dependency; the operator clones MSST-WebUI themselves into a separate venv.
2. **Invocation is arms-length** — `separation_backend.py` shells out to `scripts/msst_separate_runner.py` under `ASA_MSST_PYTHON` (a different interpreter), exchanging only a file path in and a one-line JSON manifest out. No import, no linking. This is the mainstream reading of "mere aggregation / separate program."
3. **Hosted + networked use** (the `hosted` runtime profile, were MSST ever enabled there) triggers AGPL §13's obligation to offer the running source to users. Because ASA runs **unmodified** upstream MSST-WebUI, that obligation is satisfied by pointing users at the upstream repo — but it must be a conscious operator decision, not a silent default.

This containment is exactly why PR #141's subprocess-in-its-own-venv design is load-bearing and must not be "simplified" into an in-process import.

## Decision

1. **Default stays Demucs.** `ASA_SEPARATION_BACKEND=demucs` remains the only product-path default (PURPOSE.md invariant #1: measurement is authoritative; the stems contract is unchanged either way).
2. **MSST stays a default-off, research / personal / NonCommercial-only experiment.** Acceptable for an operator analysing audio they own, for quality research, and for the A/B harness. Not acceptable as a shipped/commercial default.
3. **Do not promote any MSST model to default on quality grounds alone.** Promotion is licence-gated, not quality-gated, and the gate is closed.
4. **Durable in-code guardrail added** so the gate travels with the code, not just this doc: licence warnings on each `_MSST_MODEL_REGISTRY` entry (`separation_backend.py`) and a Licence section in `requirements-msst.txt`.

## What would unblock promotion (definition of done for a future "commercial separation" effort)

- [ ] Identify a separation model whose **weights** are distributed under a permissive or commercial licence (not CC-BY-NC, not MUSDB-only-trained). Candidates to investigate: models trained on cleared/commissioned or fully-open stem corpora.
- [ ] Re-run this licence map against that model's *weights* (not just its code) and its training-data provenance.
- [ ] Only then is an SDR + runtime A/B vs Demucs a *promotion* input rather than a *research* input.

## A/B results — NonCommercial research run (2026-06-05)

The owner approved a NonCommercial-research install, so MSST was stood up on the local Apple-Silicon box and the A/B was run for real:

- **Install:** MSST-WebUI checkout + a *minimal* SCNet-inference venv (CPU/MPS torch; the CUDA-only `sageattention` / `bitsandbytes` / `asteroid` in MSST's full `requirements.txt` are not needed for inference and were omitted — a much smaller, arm64-friendly install). Weights: `model_scnet_sdr_9.3244.ckpt` (CC-BY-NC-SA-4.0) from the `Sucial/MSST-WebUI` HF repo.
- **Reference set:** the first 5 MUSDB18 **test-split** tracks (7-second previews via the `musdb` package — both backends were trained on MUSDB *train*, so a fair A/B must use the test split), ground-truth stems, both backends on **CPU**.
- **Metric:** gain-aligned SI-SDR on a mono downmix (the harness's new `--ref-dir` mode). Internally consistent for Demucs-vs-MSST, but **NOT** museval/BSSEval-v4 — not comparable to published MUSDB leaderboard numbers.

| Backend | mean SI-SDR (dB) | mean runtime (s/clip) |
|---|---|---|
| **Demucs** (`HDEMUCS_HIGH_MUSDB_PLUS`, incumbent) | **8.08** | **1.26** |
| **MSST** (`scnet_4stem`) | 6.22 | 40.78 |

Per-stem mean SI-SDR (dB): vocals **D 8.62 / M 10.77**, bass D 9.87 / M 6.21, drums D 9.13 / M 8.33, other D 4.72 / M −0.42. Per-track, Demucs won 3/5 (one big swing on *Arise* — 12.0 vs 3.0), MSST won 2/5 (both narrow). Full report: `apps/backend/.runtime/separation_ab/report.json` (git-ignored runtime artifact).

**Reading it — caveats first:**
1. **Runtime: MSST is ~32× slower than Demucs on CPU** (40.8 s vs 1.3 s per 7 s clip; model load is trivial at ~0.2 s — the cost is all chunked CPU inference). For ASA's CPU-local deployment that is a serious practical cost.
2. **Quality: `scnet_4stem` did NOT beat Demucs overall on this proxy** (6.22 vs 8.08 mean). MSST's **vocals are better** (10.77 vs 8.62 — consistent with the model family's reputation), but its **`other` collapses** (−0.42) and bass trails.
3. **This contradicts the published museval SDR** (`scnet` ~9.32 vs `htdemucs` ~9.0) — which means the **proxy, not necessarily the model, is the limiter**: 7-second clips are too short for chunked SCNet to shine, mono SI-SDR ≠ museval, and N=5 is tiny. Treat this as a **preliminary signal, not a verdict.** The full-length 30 s re-run (full MUSDB18 download was in progress) is the honest basis for any strong quality claim.

**What it changes:** nothing about the gate — promotion stays licence-blocked regardless of SDR. But it removes any *urgency*: on this box `scnet_4stem` is both far slower and not clearly better, so even a NonCommercial "quality upgrade" rationale is unproven here. The vocals win is the one thread worth pulling later (a NonCommercial vocals-focused BS-RoFormer for a vocals-only research path).

**Reproduce:** with the MSST venv + checkout + weights in place (see `requirements-msst.txt`):
```
ASA_MSST_PYTHON=<msst-venv>/bin/python ASA_MSST_ROOT=<msst-checkout> ASA_MSST_DEVICE=cpu \
  ./venv/bin/python scripts/ab_separation_backends.py --ref-dir <musdb_ref> --repeats 1
```

## Sources

- MSST-WebUI code licence: [GNU AGPL-3.0, raw LICENSE](https://raw.githubusercontent.com/SUC-DriverOld/MSST-WebUI/main/LICENSE)
- Model weights licence: [`Sucial/MSST-WebUI` model card — `cc-by-nc-sa-4.0`](https://huggingface.co/Sucial/MSST-WebUI); per-file confirmation for `model_scnet_sdr_9.3244.ckpt` and `model_bs_roformer_ep_368_sdr_12.9628.ckpt`
- Demucs: [facebookresearch/demucs README (code MIT)](https://github.com/facebookresearch/demucs); [torchaudio `HDEMUCS_HIGH_MUSDB_PLUS`](https://docs.pytorch.org/audio/stable/generated/torchaudio.pipelines.HDEMUCS_HIGH_MUSDB_PLUS.html) (training: MUSDB-HQ + 150 internal songs)
- MUSDB18 dataset terms: NonCommercial ([source-separation.github.io](https://source-separation.github.io/tutorial/data/musdb18.html))
