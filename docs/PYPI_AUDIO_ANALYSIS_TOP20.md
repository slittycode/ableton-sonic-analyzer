# PyPI Audio-Analysis Candidates — Top 20 Evaluation for ASA

**Status:** Research shortlist only. **Do not product-install any of these** without a corpus bake-off that passes the bars below.  
**Updated:** 2026-07-18  
**Audience:** Human maintainers and coding agents (Claude / Pi / Codex) revisiting non-Gemini measurement improvements.  
**Authority:** `PURPOSE.md` > this doc. This doc never overrides measurement authority, citation chain, or Ableton specificity.  
**Companion (second tier):** [`docs/PYPI_AUDIO_ANALYSIS_NEXT20.md`](PYPI_AUDIO_ANALYSIS_NEXT20.md) — packages #21–#40 (mostly skip/ops/eval; do not reorder P0 work).

---

## Why this document exists

In 2026-07 we scanned the full PyPI classifier

`Topic :: Multimedia :: Sound/Audio :: Analysis`

(~657 unique packages via XML-RPC `browse`; web UI showed ~626). Roughly **85%** are speech, bioacoustics, datasets, hosted API clients, playlist feature toys, or abandoned code. This file freezes the **only packages worth a second look** for ASA’s **non-Gemini** stack (Phase 1 DSP + Layer 2 pitch/note + offline eval).

**This is predicted additivity, not measured additivity.** No package below has been proven better than ASA’s current engine on a producer corpus. Treat every “Expected win” as a hypothesis to falsify.

---

## ASA baseline (what “better” must beat)

| Layer | Product path today | Research path already present |
|---|---|---|
| Measurement | Essentia 2.1b6 (BPM/key/LUFS/spectral/groove/sidechain + detectors) | `scripts/evaluate_phase1.py`, structure sweeps |
| Separation | Hybrid Demucs via torchaudio (`separation_backend.py`); MSST removed in 2026-07 trust diet | optional backends doc |
| Chords | Essentia + librosa chroma Viterbi (`chordDetail`, agreement flags) | — |
| Beat / downbeat | Essentia rhythm + kick-accent downbeat heuristic | **`beat_this` in `requirements-eval.txt`** + `evaluate_beats.py` |
| Pitch / notes | torchcrepe (PENN rejected); MT3 opt-in/frozen | `evaluate_polyphonic.py`, `docs/LAYER2_EVALUATION.md` |
| Loudness | Essentia LUFS/truePeak authority; WASM path archived | loudness rec eval |
| Viz only | librosa spectrograms | not measurement authority |

**Python constraint:** product venv is **3.11.x** (Essentia arm64 wheels). Never put heavy research deps in the product venv — use a separate eval venv like `beat_this` already does.

---

## Evaluation rubric (use for every candidate)

Score each package on:

1. **User-value path** — Does a better number improve reconstruction / Ableton-citable advice? (`PURPOSE.md` decision tree)
2. **Measurement authority fit** — Local, deterministic or honestly uncertain; not a second silent authority
3. **Delta vs baseline** — Concrete field(s) that could move (`kickDetail.*`, `chordDetail.*`, `rhythmDetail.beatGrid`, stems, …)
4. **Operational cost** — Weight size, torch/TF, Python version, license, install fragility on macOS arm64
5. **Integration surface** — Existing seam (`separation_backend.py`, eval scripts, Layer 2 protocol) vs greenfield
6. **Risk** — Dual-authority confusion, trust-diet reversion (MSST), architecture strategy violations (poly AMT productization)

**Pass bar to leave research:**

> On a labeled **electronic / producer** corpus, the candidate improves a **Phase 2–citable** field enough that recommendations get more specific, without contradicting PURPOSE invariants.

---

## Priority tiers (read this first)

| Tier | Meaning | Packages |
|---|---|---|
| **P0** | Highest expected leverage; bake-off first | #1–#5 (for vocals isolation specifically, prioritize MelBand #4 + see `docs/SEPARATION_ROFORMER_PROBE.md`) |
| **P1** | Conditional on P0 outcomes or packaging for existing research | #6–#14 |
| **P2** | Offline cross-check / peer study only | #15–#20 |
| **Do not productize** | Explicit | Hosted APIs, Spleeter, ADTLib, playlist MIR, DR14 meters, speech stacks |

**Recommended order of work:**

1. Finish **`beat_this` gate** (already scaffolded) — do not shop for more beat CLIs first.  
2. **Demucs vs multi-stem RoFormer/UVR** separation bake-off → downstream field deltas.  
3. **`lv-chordia` vs current dual chord engines**.  
4. Only then: structure (`allin1`), poly AMT packaging (`muscriptor` / `mt3-infer`), refiners.

---

## Top 20 — detailed evaluations

### 1. `beat-this` / CPJKU `beat_this` — **P0 (already in repo)**

| | |
|---|---|
| **PyPI** | [`beat-this`](https://pypi.org/project/beat-this/) v1.1.0 (also installed from git in ASA eval) |
| **Home** | https://github.com/CPJKU/beat_this |
| **Requires** | Python ≥3; torch, torchaudio, numpy, soxr |
| **License** | Check repo (research-friendly; confirm before bundling) |
| **Last activity** | 2026-04 |

**What it does:** Neural beat **and downbeat** tracking. Strong modern baseline in MIR.

**ASA overlap:** `apps/backend/requirements-eval.txt`, `beat_evaluation.py`, `scripts/evaluate_beats.py`. Changelog already notes it may beat the shipping kick-accent downbeat heuristic.

**Expected win:** `rhythmDetail.beatGrid`, downbeats, `fundamentalsQuality.domains.downbeats` / meter evidence, arrangement snap quality.

**Not a win if:** Beat F1 gains but downbeat/meter still fail on half-time EDM; or latency makes full-track product path unusable without staging.

**Agent instructions:**

1. Do **not** re-discover this as a “new” dependency.  
2. Run the existing gate on a real producer corpus.  
3. Product adoption only via explicit architecture decision + staged run design (not silent swap).  
4. madmom was **intentionally omitted** from the eval venv (`dbn=False` path) — don’t re-add casually.

**Verdict:** **Highest ROI unfinished work.** Finish before any other beat package.

---

### 2. `bs-roformer-infer` — **P0 separation challenger**

| | |
|---|---|
| **PyPI** | [`bs-roformer-infer`](https://pypi.org/project/bs-roformer-infer/) v0.1.5 |
| **Home** | https://github.com/openmirlab/bs-roformer-infer |
| **Requires** | ≥3.10; torch≥2, soundfile, einops, … |
| **License** | MIT |
| **Last activity** | 2026-07 |

**What it does:** Inference-only **Band-Split RoFormer** music source separation toolkit (model registry + CLI/API).

**ASA overlap:** Competes with Hybrid Demucs in `separation_backend.py`. Stem quality feeds kick/bass/snare/hihat, monophonic transcription, `chordSource: harmonic_stems`.

**Expected win:** Cleaner drums/bass/other → better `kickDetail.fundamentalHz`, bass note stability, chord agreement, lower transcription octave noise.

**Risks:**

1. Trust diet already removed MSST — another separator needs a **higher** evidence bar.  
2. Model download size / GPU assumptions.  
3. Must map to ASA’s canonical stems: `drums` / `bass` / `other` / `vocals` at 44.1 kHz.  
4. Must not change stem schema or silently swap default without eval.

**Agent instructions:**

1. Eval venv only; wire through a **research** separation backend or offline script — not default product.  
2. Metrics: SI-SDR / PEASS (#6–#7) **and** downstream Phase 1 field deltas on same fixtures.  
3. Prefer multi-stem models over vocal-only.

**Verdict:** **Best separation *family* to challenge Demucs.** Research first.

---

### 3. `audio-separator` — **P0 separation runner (off-classifier)**

| | |
|---|---|
| **PyPI** | [`audio-separator`](https://pypi.org/project/audio-separator/) v0.44.3 |
| **Home** | https://github.com/karaokenerds/python-audio-separator |
| **Requires** | ≥3.10; heavy (librosa, onnx, torch ecosystem); note numpy≥2 may fight ASA pins |
| **License** | MIT |
| **Last activity** | 2026-07 |

**What it does:** Practical runner for **UVR-trained** models (many RoFormer / MDX / Demucs-class weights). Not tagged under the Analysis classifier — easy to miss in classifier-only scans.

**ASA overlap:** Same as #2 — stem pipeline. Stronger **packaging/model zoo** than many one-off infer packages.

**Expected win:** Access to community multi-stem weights that beat stock Demucs on electronic material (hypothesis).

**Risks:** Dependency sprawl (numpy 2, onnx variants), karaoke-centric defaults, version conflicts with Essentia 3.11 stack. Treat as **eval harness dependency**, never merge into product `requirements.txt` without a pin strategy.

**Agent instructions:** Use for model shopping + offline compares. Promote a **winning model family** into a thin ASA backend, not the whole kitchen-sink package, if anything graduates.

**Verdict:** **Best “model zoo” vehicle** for separation bake-offs. Prefer over random UVR CLIs (`uvr-headless-runner`, `chuja`).

---

### 4. `melband-roformer-infer` — **P0/P1 (vocal-skewed)**

| | |
|---|---|
| **PyPI** | [`melband-roformer-infer`](https://pypi.org/project/melband-roformer-infer/) v0.1.5 |
| **Home** | https://github.com/openmirlab/melband-roformer-infer |
| **Requires** | ≥3.10; torch, librosa, … |
| **License** | MIT |
| **Last activity** | 2026-07 |

**What it does:** Mel-Band RoFormer inference; strong **vocals / instrumental** separation; large model registry (karaoke, denoise, etc.).

**ASA overlap:** `vocalDetail`, vocals stem, optional vocal-aware analysis. Weaker default fit for **drums/bass** character measurements.

**Expected win:** Cleaner vocals stem for vocal detectors and “other” harmonic isolation **if** residual models help. Unlikely to replace Demucs for full 4-stem product alone.

**Verdict:** Include in separation bake-off as **vocal specialist**, not as sole Demucs replacement.

---

### 5. `moises-light` — **P1 separation (efficiency)**

| | |
|---|---|
| **PyPI** | [`moises-light`](https://pypi.org/project/moises-light/) v0.1.5 |
| **Home** | https://github.com/crlandsc/moises-light |
| **Requires** | ≥3.9; torch, einops |
| **License** | MIT |
| **Last activity** | 2026-04 |

**What it does:** Resource-efficient band-split U-Net for music source separation.

**ASA overlap:** Same stem seam; interesting if quality ≈ Demucs at lower CPU/RAM (local product path cares about this).

**Expected win:** Latency/memory, not necessarily accuracy. Only product-relevant if quality is non-regressive on EDM stems.

**Verdict:** Efficiency challenger **after** RoFormer quality picture is clear.

---

### 6. `python-peass` — **P1 eval-only (separation scoring)**

| | |
|---|---|
| **PyPI** | [`python-peass`](https://pypi.org/project/python-peass/) v2.0.1.4 |
| **Home** | https://github.com/averykhoo/python-peass |
| **Requires** | ≥3.10; numpy, scipy, soundfile |
| **License** | **GPLv3** (license contagion — keep out of product) |
| **Last activity** | 2026-07 |

**What it does:** PEASS perceptual evaluation scores for source separation (OPS/TPS/IPS/APS).

**ASA overlap:** Offline separator bake-off only. **Never** a user-facing Phase 1 field.

**Expected win:** Principled ranking of Demucs vs RoFormer/UVR when ground-truth stems exist (or approximate protocols).

**Risks:** GPLv3 — eval venv isolation mandatory. Not a substitute for “does kick fundamental get more accurate?”

**Verdict:** **Use in eval venv** alongside SI-SDR (`fast-bss-eval`). Do not ship.

---

### 7. `fast-bss-eval` — **P1 eval-only (SI-SDR family)**

| | |
|---|---|
| **PyPI** | [`fast-bss-eval`](https://pypi.org/project/fast-bss-eval/) v0.1.4 |
| **Home** | https://github.com/fakufaku/fast_bss_eval |
| **Requires** | Python ≥3.6 |
| **License** | MIT |
| **Last activity** | 2022 (stable metrics lib) |

**What it does:** Fast BSS Eval / SI-SDR-style metrics for separation.

**ASA overlap:** Companion to #6 for objective stem scores. Off the Analysis classifier.

**Verdict:** Standard metric tool for separation research. Prefer MIT path in shared scripts; PEASS optional.

---

### 8. `allin1` — **P1 structure + beat (canonical)**

| | |
|---|---|
| **PyPI** | [`allin1`](https://pypi.org/project/allin1/) v1.1.0 |
| **Home** | https://github.com/mir-aidj/all-in-one |
| **Requires** | ≥3.8; demucs, librosa, natten, hydra, … |
| **License** | Check repo |
| **Last activity** | 2023-10 (canonical package older than Apple ports) |

**What it does:** All-In-One Music Structure Analyzer — segments, beats/downbeats-related structure analysis used widely in MIR demos.

**ASA overlap:** `structure`, `arrangementDetail`, rhythm/phrase grids. Heavier than ASA’s current structure path; pulls Demucs again.

**Expected win:** More reliable section boundaries / functional labels for arrangement-aware Phase 2.

**Risks:** Stale packaging vs forks; natten install pain; duplicates Demucs work; may not beat ASA structure on EDM if novelty/energy already good.

**Agent instructions:** Prefer evaluating **this** algorithm family before MLX/MPS ports. Compare segment boundary F-measure / usefulness vs ASA `structure.segments`.

**Verdict:** Structure bake-off candidate **after** beats + separation priorities.

---

### 9. `all-in-one-mlx` (and `all-in-one-mps`) — **P1 Apple ports**

| | |
|---|---|
| **PyPI** | [`all-in-one-mlx`](https://pypi.org/project/all-in-one-mlx/) v1.0.5; [`all-in-one-mps`](https://pypi.org/project/all-in-one-mps/) v1.0.0 |
| **Home** | https://github.com/ssmall256/all-in-one-mlx (and mps sibling) |
| **Requires** | ≥3.10; MLX or torch MPS stacks |
| **Last activity** | 2026-02/03 |

**What they do:** Apple Silicon ports of All-In-One.

**ASA overlap:** Same as #8; only relevant on macOS arm64 local dev (which is ASA’s primary machine class).

**Expected win:** Speed/usability of #8 on M-series — **not** a different algorithm thesis.

**Verdict:** Use **only if** allin1-class quality wins and product wants local acceleration. Don’t treat as a separate scientific bet.

---

### 10. `metricon` — **P1 beat decoder**

| | |
|---|---|
| **PyPI** | [`metricon`](https://pypi.org/project/metricon/) v0.1.0 |
| **Home** | https://github.com/auvux/metricon |
| **Requires** | ≥3.9; numpy |
| **Last activity** | 2026-06 |

**What it does:** Fast state-space decoder for **beats, downbeats, bars from neural logits**.

**ASA overlap:** Post-model decoding stage for `beat_this`-class systems; meter/bar structure.

**Expected win:** Better bar phase / downbeat decode than naive peak-picking — **if** plugged into a logit-producing model ASA already runs in eval.

**Verdict:** Interesting **after** `beat_this` baseline numbers exist. Not a standalone tracker.

---

### 11. `livechord-beat-refiner` — **P1 post-processor**

| | |
|---|---|
| **PyPI** | [`livechord-beat-refiner`](https://pypi.org/project/livechord-beat-refiner/) v0.1.0 |
| **Home** | https://livechord.org |
| **Requires** | ≥3.9; torch, librosa, huggingface_hub |
| **License** | Apache-2.0 |
| **Last activity** | 2026-05 |

**What it does:** Bidirectional Transformer that **denoises** beat/downbeat/chord-boundary outputs from `beat_this`, madmom, or librosa using full audio context.

**ASA overlap:** Exactly the “neural beats are close but messy on electronic” problem.

**Expected win:** Cleaner grids without replacing the base tracker.

**Risks:** Extra model + HF download; may smooth away true half-time ambiguity (must preserve honest uncertainty).

**Verdict:** Only after a base tracker is chosen. Measure downbeat F1 **and** half-time honesty.

---

### 12. `livechord-bar-arbitrator` — **P1 meter / double-time fixer**

| | |
|---|---|
| **PyPI** | [`livechord-bar-arbitrator`](https://pypi.org/project/livechord-bar-arbitrator/) v0.1.0 |
| **Home** | https://livechord.org |
| **Requires** | ≥3.9; numpy, huggingface_hub |
| **License** | Apache-2.0 |
| **Last activity** | 2026-05 |

**What it does:** Post-processor for **bar/downbeat phase drift**, beats-per-bar confusion, and **double-time** — without re-running audio models.

**ASA overlap:** Maps directly to ASA pain: `bpmDoubletime`, meter candidates, half-time electronic material (`PURPOSE.md` Phase 1 quality notes).

**Expected win:** Corrected meter/phase feeding arrangement grids and chord timelines.

**Risks:** Must not invent confidence; integrate with `fundamentalsQuality` hedging.

**Verdict:** High conceptual fit; validate on ASA’s half-time fixtures after beat grid exists.

---

### 13. `lv-chordia` — **P1 chord recognition**

| | |
|---|---|
| **PyPI** | [`lv-chordia`](https://pypi.org/project/lv-chordia/) v1.1.0 |
| **Home** | https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition |
| **Requires** | ≥3.8; torch, librosa, pretty-midi, … |
| **License** | MIT |
| **Last activity** | 2026-07 (packaged inference) |
| **Paper** | ISMIR 2019 large-vocabulary chord structure decomposition |

**What it does:** Ensemble deep chord recognition with large vocabulary (incl. complex qualities).

**ASA overlap:** `chordDetail.chordSequence`, `chordTimeline`, `chordTimelineAgreement`, sample audition chord plans.

**Expected win:** Better progressions / qualities than triad-limited Viterbi + Essentia on harmonic electronic and live-instrument hybrids.

**Risks:** Full-mix EDM (pads, sidechain, mono bass) still hard; heavy ensemble; must not override key; keep agreement/hedge UX.

**Agent instructions:**

1. Offline compare labels + timeline vs current dual engines on producer fixtures.  
2. Report agreement with key, bass roots, and audition usefulness — not only MIREX scores.  
3. If promoted: additional estimator behind `chordDetail` + `fundamentalsQuality.domains.chords`, never silent sole authority.

**Verdict:** **Best chord-specific research bet** in the top 20.

---

### 14. `muscriptor` — **P1 Layer 2 poly research only**

| | |
|---|---|
| **PyPI** | [`muscriptor`](https://pypi.org/project/muscriptor/) v0.2.1 |
| **Home** | https://github.com/muscriptor/muscriptor |
| **Requires** | ≥3.10; torch, HF hub, mido, … |
| **Last activity** | 2026-07 |
| **Models** | small / medium / large transformer AMT (Kyutai/Mirelo lineage) |

**What it does:** Large-scale audio→MIDI transcription (classical through metal training claims).

**ASA overlap:** Same problem space as MT3 / `docs/POLYPHONIC_TRANSCRIPTION_SPIKE.md` / `docs/ARCHITECTURE_STRATEGY.md` Session Musician honesty rules.

**Expected win:** Usable bass/other note hypotheses on some electronic material; better packaging than ad-hoc MT3.

**Hard constraints from architecture strategy:**

1. **Do not productize full-mix poly AMT** as “Ableton audio-to-MIDI.”  
2. Measurement remains authoritative (PURPOSE #1).  
3. Compare only inside `evaluate_polyphonic.py` / research harness.  
4. Prefer stem-aware evaluation.

**Verdict:** Legitimate modern AMT competitor for **research**. Not a Phase 1 measurement replacement.

---

### 15. `mt3-infer` — **P1 MT3 packaging**

| | |
|---|---|
| **PyPI** | [`mt3-infer`](https://pypi.org/project/mt3-infer/) v0.2.0 |
| **Home** | https://github.com/openmirlab/mt3-infer |
| **Requires** | ≥3.9; torch, librosa, pretty-midi, mir-eval, … |
| **License** | MIT |
| **Last activity** | 2026-07 |

**What it does:** Unified inference-only toolkit for Magenta MT3 / MR-MT3 / MT3-PyTorch / YourMT3 family.

**ASA overlap:** ASA already has opt-in MT3 (`mt3_transcription.py`, `ASA_ENABLE_MT3`). This may reduce maintenance if the in-repo path is painful.

**Expected win:** Ops/packaging, not a new scientific claim.

**Verdict:** Consider only if current MT3 path is costly to maintain. Still research/opt-in.

---

### 16. `pyloudnorm` — **P2 loudness cross-check**

| | |
|---|---|
| **PyPI** | [`pyloudnorm`](https://pypi.org/project/pyloudnorm/) v0.2.0 |
| **Home** | https://github.com/csteinmetz1/pyloudnorm |
| **Requires** | ≥3.9; numpy, scipy |
| **Last activity** | 2026-01 |

**What it does:** Clean Python ITU-R BS.1770-4 loudness implementation (industry reference often used in research).

**ASA overlap:** Essentia is **authority** for LUFS/truePeak (ADR / phase1.v2). WASM alternative archived.

**Expected win:** Offline parity probe (“does Essentia disagree with pyloudnorm by >X LU on fixture set?”). Not a second product meter.

**Verdict:** Eval-only second opinion. Do not dual-publish LUFS.

---

### 17. `madmom-onnx` — **P2 historical beat baseline**

| | |
|---|---|
| **PyPI** | [`madmom-onnx`](https://pypi.org/project/madmom-onnx/) v0.17.dev0 |
| **Home** | https://github.com/alumkal/madmom-onnx |
| **Requires** | numpy, scipy, mido, onnxruntime |
| **License** | BSD |
| **Last activity** | 2026-02 |

**What it does:** madmom algorithms via ONNX Runtime (avoids classic madmom install hell). Upstream `madmom` last release 2018.

**ASA overlap:** Beat/onset/downbeat baselines; ASA eval docs **intentionally skip** madmom today.

**Expected win:** Cheap classical baseline next to `beat_this` for “are we better than 2016-era DBN?”

**Verdict:** Optional eval baseline only. Prefer `beat_this` as the neural candidate.

---

### 18. `mixref` — **P2 peer product (study, don’t embed)**

| | |
|---|---|
| **PyPI** | [`mixref`](https://pypi.org/project/mixref/) v0.4.0 |
| **Requires** | **≥3.12** (conflicts with ASA 3.11 product target) |
| **Deps** | librosa, pyloudnorm, numpy&lt;2, … |
| **Last activity** | 2026-02 |

**What it does:** CLI analyzer aimed at **DnB / Techno / House** producers — peer positioning to ASA’s audience.

**ASA overlap:** Conceptual competitor for “producer-facing numbers,” not a library ASA should vendor.

**Expected win:** **Product inspiration** — which fields producers care about; naming; report shape. Not drop-in DSP.

**Risks:** Python 3.12+; shallower than ASA Phase 1; embedding creates dual product logic.

**Verdict:** Read outputs on shared tracks; do **not** add as dependency.

---

### 19. `openunmix` — **P2 weak separation baseline**

| | |
|---|---|
| **PyPI** | [`openunmix`](https://pypi.org/project/openunmix/) v1.3.0 |
| **Home** | https://github.com/sigsep/open-unmix-pytorch |
| **Requires** | ≥3.9; torch, torchaudio |
| **License** | MIT |
| **Last activity** | 2024-04 |

**What it does:** Classic open music separation baseline (UMX).

**ASA overlap:** Historical comparator; generally behind Demucs/RoFormer on modern material.

**Verdict:** Include in a separation matrix only as **legacy baseline**. Do not consider for product.

---

### 20. `libf0` (+ note on `swift-f0`) — **P2 F0 research only**

| | |
|---|---|
| **PyPI** | [`libf0`](https://pypi.org/project/libf0/) v1.1.1; also see [`swift-f0`](https://pypi.org/project/swift-f0/) |
| **Requires** | libf0: ≥3.10, librosa, numba, numpy≥2 (pin risk); swift-f0: onnxruntime |
| **Last activity** | 2026-01 / 2025-07 |

**What they do:** Classical + ML monophonic F0 estimators for music recordings.

**ASA overlap:** torchcrepe already won the Layer 2 monophonic slot after PENN evaluation (`docs/LAYER2_EVALUATION.md`, architecture strategy).

**Expected win:** Only if stem-aware EDM corpus shows clear RPA/cents improvement **and** operational cost is lower. Unlikely given prior bake-offs.

**Verdict:** Do **not** reopen pitch backend shopping without new corpus evidence. Listed so agents don’t “rediscover” F0 packages as greenfield.

---

## Explicit non-recommendations (seen in the 657, not in top 20)

| Package / class | Why rejected |
|---|---|
| `spleeter*` | Superseded, TF weight |
| `audd`, `beatlyze*`, `stemsplit-python` | Hosted APIs — not local measurement authority |
| `sonara`, `orbit-dsp`, playlist feature extractors | Shallower than Essentia Phase 1 |
| `ADTLib` | 2018 drum AMT, unmaintained |
| `ambiscape` | Ambisonic soundscapes |
| `soundlevelmeter` | IEC SPL + Python ≥3.13; not BS.1770 music LUFS |
| `amt-augmentor` | Training augmentation only |
| `dr14meter` / `drcheck` | DR14 loudness-war metric ≠ reconstruction surface |
| `chord-extractor` | Vamp/Chordino wrapper; Python &lt;3.12; weaker research bet than `lv-chordia` |
| `msaf` alone | Prefer allin1-class structure study first; ASA already has structure |
| `chuja`, `uvr-headless-runner` | Prefer `audio-separator` / `bs-roformer-infer` |
| Speech / emotion / bio / forensics (~majority of classifier) | Wrong domain |

---

## How an agent should use this file

```
IF user asks to improve non-Gemini analysis with new libraries:
  1. Read PURPOSE.md + this file.
  2. Do not pip-install into apps/backend product venv.
  3. Prefer existing harnesses:
       - apps/backend/scripts/evaluate_beats.py
       - apps/backend/scripts/evaluate_polyphonic.py
       - apps/backend/scripts/evaluate_phase1.py
  4. For separation: add offline compare → separation_backend seam only if corpus wins.
  5. For chords: offline compare → chordDetail + fundamentalsQuality hedges.
  6. Refuse product default changes without owner sign-off on measured deltas.
```

**Suggested first three commands mindset (not auto-run):**

1. Beat gate corpus status / `evaluate_beats.py` readiness  
2. Design Demucs vs `bs-roformer-infer` + `audio-separator` fixture protocol  
3. Design `lv-chordia` vs current `chordDetail` agreement report  

---

## Scan methodology (reproducibility)

1. `xmlrpc.client.ServerProxy('https://pypi.org/pypi').browse(['Topic :: Multimedia :: Sound/Audio :: Analysis'])`  
2. Unique package names → `https://pypi.org/pypi/<name>/json` metadata for all  
3. Keyword/domain scoring against ASA surfaces  
4. Manual expert triage against `ARCHITECTURE_STRATEGY.md`, trust diet, and existing eval paths  
5. Off-classifier high-value packages added when known (`audio-separator`, `allin1`, `pyloudnorm`, `fast-bss-eval`, …)

**Raw intermediates from the 2026-07 scan** (local machine, not committed):  
`/tmp/pypi_audio_analysis_names.json`, `meta.json`, `scored.json` — regenerate if needed; do not treat `/tmp` as source of truth.

---

## Changelog

| Date | Note |
|---|---|
| 2026-07-18 | Initial top-20 evaluation after full classifier scan (~657 pkgs). Research-only; no product deps added. |
