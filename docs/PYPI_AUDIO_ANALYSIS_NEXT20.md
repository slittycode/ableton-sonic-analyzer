# PyPI Audio-Analysis Candidates — Next 20 Evaluation for ASA (#21–#40)

**Status:** Research shortlist only (second tier). **Do not product-install** without a corpus bake-off.  
**Updated:** 2026-07-18  
**Audience:** Human maintainers and coding agents revisiting non-Gemini measurement improvements.  
**Authority:** `PURPOSE.md` > this doc.  
**Companion:** [`docs/PYPI_AUDIO_ANALYSIS_TOP20.md`](PYPI_AUDIO_ANALYSIS_TOP20.md) (#1–#20, higher priority).  
**Scan origin:** Full PyPI classifier `Topic :: Multimedia :: Sound/Audio :: Analysis` (~657 packages) plus known off-classifier MIR tools.

---

## How this tier differs from the Top 20

| | Top 20 (#1–#20) | Next 20 (#21–#40) |
|---|---|---|
| Expected leverage | Plausible field wins or unfinished ASA work | Mostly **redundancy**, **ops packaging**, **eval plumbing**, or **explicit rejections** agents re-discover |
| Default action | Design bake-offs | Read verdict; usually **skip** or use only as baseline/infra |
| Risk of false “add this” | Medium | **High** — automated scores look good; product value is thin |

**Still true:** predicted additivity ≠ measured additivity. Product venv stays **Python 3.11.x**. Research deps go in an **eval venv**.

**Read order for agents:**

1. Finish Top 20 P0 work (`beat_this` gate → separation → chords).  
2. Only then open this file if a package name appears in a PR/search and you need a settled opinion.  
3. Do not start a greenfield integration from this tier without owner push.

---

## Rubric (same as Top 20)

1. User-value path (PURPOSE decision tree)  
2. Measurement authority fit  
3. Delta vs ASA baseline fields  
4. Operational cost (pins, license, arm64, model size)  
5. Integration surface  
6. Risk (dual authority, trust-diet reversion, architecture strategy)

**Pass bar:** Improves a Phase 2–citable field on a producer corpus without violating PURPOSE invariants.

---

## Snapshot table (#21–#40)

| # | Package | Domain | Tier verdict |
|---|---|---|---|
| 21 | `essentia-tensorflow` | Essentia + TF models | **Stay adjacent** — not a second engine |
| 22 | `chord-extractor` | Chords via Vamp/Chordino | **Skip** — prefer `lv-chordia` (#13) |
| 23 | `keyfinder` | Key detection | **Eval second-opinion only** |
| 24 | `msaf` | Structure segmentation | **Low** — after `allin1` (#8) |
| 25 | `as-seg` | Autosimilarity segmentation | **MSAF plugin / low** |
| 26 | `demucs-onnx` | Demucs without PyTorch | **Ops experiment only** |
| 27 | `chuja` | Demucs CLI wrapper | **Skip** — packaging not algorithm |
| 28 | `uvr-headless-runner` | UVR CLI | **Skip** — prefer `audio-separator` (#3) |
| 29 | `jaxmsst` | MSST-family separation | **Do not re-open** (trust diet) |
| 30 | `mixxx-analyzer` | DJ BPM/key/gain | **Peer / cross-check only** |
| 31 | `aubio` | Classic MIR | **Low baseline** — Essentia wins |
| 32 | `coremlcrepe` | CREPE on Apple ANE | **Perf only** if latency is the issue |
| 33 | `basic-pitch` | AMT | **Already rejected** by ASA |
| 34 | `omnizart` | Multi-instrument AMT | **Research-only, weak EDM fit** |
| 35 | `pyebur128` | libebur128 LUFS | **Parity probe only** |
| 36 | `katana-meter` | LUFS / TP / ΔE | **Eval only; license caution** |
| 37 | `rs-audio-stats` | Rust EBU R128 | **Parity / speed probe only** |
| 38 | `matchering` | Reference mastering transfer | **Wrong problem** (processing) |
| 39 | `musicnn` | Music tagging CNN | **Low** — tags ≠ Ableton params |
| 40 | `jams` (+ `mirdata` note) | Annotation / dataset I/O | **Eval infrastructure yes** |

---

## Detailed evaluations

### 21. `essentia-tensorflow` — Essentia with TF model support

| | |
|---|---|
| **PyPI** | [`essentia-tensorflow`](https://pypi.org/project/essentia-tensorflow/) 2.1b6.dev1438 |
| **Home** | http://essentia.upf.edu |
| **Requires** | Same Essentia line; TensorFlow stack |
| **Last activity** | 2026-05 |

**What it does:** Essentia build/flavor that can run **TensorFlow models** inside the Essentia graph (tagging, some learned extractors), not only classical DSP.

**ASA overlap:** Product already pins **`essentia`** (classical DSP authority). This is the same family with optional learned models.

**Expected win:** Access to Essentia’s model zoo (genre/mood/instrument tags, etc.) without inventing a parallel feature stack.

**Risks:**

1. TF weight + binary complexity on macOS arm64.  
2. Soft labels (genre/mood) rarely become Ableton device/param citations.  
3. Dual install confusion (`essentia` vs `essentia-tensorflow` wheels).

**Agent instructions:** Do **not** replace product `essentia` with TF flavor “to get more fields.” If a specific Essentia TF model is hypothesized to help a **cited** field, evaluate that model offline first.

**Verdict:** **Adjacent, not additive by default.** Stay on classical Essentia unless a named model has a PURPOSE-backed use case.

---

### 22. `chord-extractor` — Vamp/Chordino wrapper

| | |
|---|---|
| **PyPI** | [`chord-extractor`](https://pypi.org/project/chord-extractor/) 0.1.3 |
| **Home** | https://github.com/ohollo/chord-extractor |
| **Requires** | Python **≥3.8,&lt;3.12**; librosa; **vamp** |
| **License** | **GPLv2** |
| **Last activity** | 2025-08 |

**What it does:** Thin Python API over **Chordino** (via Vamp) for chord labels from audio.

**ASA overlap:** Competes with dual engines in `chordDetail` and research candidate **`lv-chordia` (#13)**.

**Expected win:** Classic Chordino baseline for offline comparison.

**Risks:** Python &lt;3.12 fights future toolchains; Vamp native plugin install friction; GPLv2; generally weaker research bet than large-vocab deep models on complex harmony.

**Verdict:** **Skip for product.** Optional chord bake-off **baseline only** if Vamp is already installed; prefer `lv-chordia` as the serious challenger.

---

### 23. `keyfinder` — second key estimator

| | |
|---|---|
| **PyPI** | [`keyfinder`](https://pypi.org/project/keyfinder/) 1.1.0 |
| **Home** | https://github.com/evanpurkhiser/keyfinder-py |
| **Requires** | Native keyfinder lib (packaging aged) |
| **Last activity** | **2019-04** |

**What it does:** Bindings around Ibrahim/Ismail-style **key detection** used in DJ tooling.

**ASA overlap:** `key`, `keyConfidence`, `keyEnsemble`, `keyProfile` from Essentia `KeyExtractor`.

**Expected win:** Disagreement signal for modal/ambiguous tracks (hedging), not a better sole authority.

**Risks:** Stale packaging; native dependency pain; DJ-oriented key systems can disagree with musical key in electronic productions.

**Verdict:** **Eval second-opinion only.** Do not ship dual keys without `fundamentalsQuality` hedging design. Prefer extending ASA’s existing key ensemble before adding KeyFinder.

---

### 24. `msaf` — music structure analysis framework

| | |
|---|---|
| **PyPI** | [`msaf`](https://pypi.org/project/msaf/) 0.1.80 |
| **Home** | https://github.com/urinieto/msaf |
| **Requires** | librosa, jams, mir-eval, cvxopt, … |
| **License** | MIT |
| **Last activity** | 2023-06 |

**What it does:** Classic academic framework for **structural segmentation** (boundary detection + labeling algorithms: Foote, OLDA, Scluster, etc.).

**ASA overlap:** `structure`, `arrangementDetail`, segment loudness/spectral/key blocks.

**Expected win:** Better section boundaries on some corpora; standard MIR algorithms for offline structure eval.

**Risks:** Maintenance chill; heavy scientific deps; may not beat ASA’s production-oriented structure on EDM; Top 20 **`allin1` (#8)** is the stronger modern single-package structure bet.

**Verdict:** **Low priority.** Use as algorithm library in structure research **after** allin1 comparison, not as product dependency.

---

### 25. `as-seg` — autosimilarity segmentation (MSAF-related)

| | |
|---|---|
| **PyPI** | [`as-seg`](https://pypi.org/project/as-seg/) 0.1.12 |
| **Home** | https://gitlab.imt-atlantique.fr/a23marmo/autosimilarity_segmentation |
| **License** | BSD |
| **Last activity** | 2026-04 |

**What it does:** Segmentation of **autosimilarity matrices** — component used with MSAF-style pipelines.

**ASA overlap:** Same structure domain as #24.

**Expected win:** Niche algorithm improvement inside an offline structure experiment.

**Verdict:** **Not standalone.** Only relevant if you are already deep in MSAF-style research. Related: `zigify-msaf` (Python ≥3.12) is a pipeline wrapper — skip for ASA 3.11 product.

---

### 26. `demucs-onnx` — Demucs via ONNX Runtime

| | |
|---|---|
| **PyPI** | [`demucs-onnx`](https://pypi.org/project/demucs-onnx/) 0.3.4 |
| **Home** | https://stemsplit.github.io/demucs-onnx/ |
| **Requires** | ≥3.11; onnxruntime; **no PyTorch** at inference |
| **License** | MIT |
| **Last activity** | 2026-05 |

**What it does:** Export/run **HT-Demucs / Demucs** as ONNX (incl. htdemucs_ft 4-stem bag). Same algorithm family ASA already uses, different runtime.

**ASA overlap:** `separation_backend.py` currently torchaudio Hybrid Demucs path. This is an **ops/runtime** alternative, not a quality leap.

**Expected win:** Smaller deploy footprint, faster cold start, or easier packaging **if** stem parity with current Demucs is proven bit-close / SI-SDR-close.

**Risks:**

1. Numerical drift vs torch path → silent measurement drift (PURPOSE #1).  
2. Another moving part without quality upside.  
3. Must pass stem-identity tests before any default flip.

**Agent instructions:** Treat as **parity experiment**, not “new separator.” If pursuing, require fixture SI-SDR/L1 vs current backend + no Phase 1 field regressions.

**Verdict:** **Ops-only research.** Zero scientific priority vs RoFormer (#2–#3).

---

### 27. `chuja` — local Demucs CLI wrapper

| | |
|---|---|
| **PyPI** | [`chuja`](https://pypi.org/project/chuja/) 0.1.2 |
| **Home** | https://github.com/dnakitare/chuja |
| **Requires** | demucs, typer, soundfile |
| **License** | MIT |
| **Last activity** | 2026-06 |

**What it does:** Friendly CLI: file (or URL) → drums/bass/other/vocals via **Demucs**.

**ASA overlap:** ASA already separates stems in-process. This adds **no new algorithm**.

**Verdict:** **Skip.** Packaging sugar only. Do not add a subprocess Demucs CLI when `separation_backend` exists.

---

### 28. `uvr-headless-runner` — UVR CLI

| | |
|---|---|
| **PyPI** | [`uvr-headless-runner`](https://pypi.org/project/uvr-headless-runner/) 1.1.0 |
| **Home** | https://github.com/chyinan/uvr-headless-runner |
| **Requires** | **Python ≥3.9,&lt;3.11** — **conflicts with ASA 3.11** |
| **License** | MIT |
| **Last activity** | 2026-02 |

**What it does:** Headless Ultimate Vocal Remover-style separation CLI.

**ASA overlap:** Same model zoo space as **`audio-separator` (#3)** with worse Python pin and less mature packaging story.

**Verdict:** **Skip.** Use `audio-separator` / `bs-roformer-infer` for UVR/RoFormer experiments.

---

### 29. `jaxmsst` — JAX MSST toolkit

| | |
|---|---|
| **PyPI** | [`jaxmsst`](https://pypi.org/project/jaxmsst/) 0.1.0 |
| **Home** | https://github.com/your-username/jax-Music-Source-Separation (placeholder-looking upstream) |
| **Requires** | ≥3.8; JAX stack |
| **License** | MIT |
| **Last activity** | 2025-06 |

**What it does:** Music Source Separation Toolkit in **JAX** (MSST family).

**ASA overlap:** **MSST paths were removed in the 2026-07 trust diet.** Re-opening MSST requires extraordinary evidence.

**Expected win:** Unproven; packaging/upstream look immature relative to Demucs/RoFormer ecosystem.

**Verdict:** **Do not re-open.** Trust-diet decision stands unless owner revisits with a full quality + ops case. Prefer RoFormer-class (#2–#3).

---

### 30. `mixxx-analyzer` — Mixxx-identical DJ analysis

| | |
|---|---|
| **PyPI** | [`mixxx-analyzer`](https://pypi.org/project/mixxx-analyzer/) 0.1.2 |
| **License** | **GPL-2.0-or-later** |
| **Requires** | ≥3.8 |
| **Last activity** | 2026-03 |

**What it does:** BPM, key, gain, intro/outro using **Mixxx-identical algorithms** (DJ library analysis).

**ASA overlap:** Coarse track features ASA already measures more deeply for production reconstruction.

**Expected win:** Interesting **cross-check** against DJ-world BPM/key (how club tools hear the track). Not Ableton device recipes.

**Risks:** GPL; shallow vs Phase 1 detectors; intro/outro heuristics ≠ arrangementDetail quality bar.

**Verdict:** **Peer/cross-check only.** Do not embed. Optional offline “Mixxx vs Essentia BPM/key disagreement” study for hedging UX ideas.

---

### 31. `aubio` — classic C MIR library

| | |
|---|---|
| **PyPI** | [`aubio`](https://pypi.org/project/aubio/) 0.4.9 |
| **Home** | https://aubio.org/ |
| **License** | **GPLv3+** |
| **Last activity** | **2019-02** |

**What it does:** Onset, pitch, tempo, beat, spectral descriptors — battle-tested classical MIR.

**ASA overlap:** Entirely inside Essentia’s job description (and more of it).

**Expected win:** Historical baseline for onset/tempo unit tests. Unlikely to beat Essentia on EDM full mixes.

**Risks:** GPL; aged wheels; install pain; dual-authority noise.

**Verdict:** **Low.** Do not add. Related packages (`aubio-ledfx`, `aubio-beatcheck`) are forks/wrappers — ignore.

---

### 32. `coremlcrepe` — CREPE on Apple Neural Engine

| | |
|---|---|
| **PyPI** | [`coremlcrepe`](https://pypi.org/project/coremlcrepe/) 0.2.0 |
| **Home** | https://github.com/sakamoto-poteko/coremlcrepe |
| **Requires** | ≥3.9,&lt;3.13; torchcrepe-compatible API |
| **License** | MIT |
| **Last activity** | 2026-07 |

**What it does:** **CoreML/ANE** port of CREPE with API compatibility toward torchcrepe.

**ASA overlap:** Layer 2 monophonic path is **torchcrepe** after PENN rejection. This is a **runtime/perf** variant of the same estimator family.

**Expected win:** Lower latency / energy on M-series Macs **if** pitch outputs match torchcrepe within cents tolerances on stems.

**Risks:** Numerical drift → different notes → different Session Musician MIDI without user-visible “why.” Must pass parity tests before any default.

**Verdict:** **Perf experiment only.** Not an accuracy program. Do not touch until latency is a proven product pain.

---

### 33. `basic-pitch` — Spotify AMT (already removed)

| | |
|---|---|
| **PyPI** | [`basic-pitch`](https://pypi.org/project/basic-pitch/) 0.4.0 |
| **Last activity** | 2024-08 |

**What it does:** Lightweight audio-to-MIDI with pitch-bend; popular general AMT.

**ASA overlap:** **Explicitly removed** from ASA. Architecture strategy + backend AGENTS: do not add Basic Pitch as production backend; torchcrepe is monophonic canonical; poly is research-gated.

**Expected win:** None for product. Research comparison only if someone insists — still weaker thesis than `muscriptor` / MT3 for ASA’s stated path.

**Verdict:** **Already rejected.** Do not reintroduce. Cite `docs/ARCHITECTURE_STRATEGY.md` and backend AGENTS if asked.

---

### 34. `omnizart` — multi-instrument transcription suite

| | |
|---|---|
| **PyPI** | [`omnizart`](https://pypi.org/project/omnizart/) 0.6.3 |
| **Home** | https://sites.google.com/view/mctl/home |
| **Requires** | ≥3.8; heavy ML stack |
| **License** | MIT |
| **Last activity** | 2026-05 |

**What it does:** Academic multi-module AMT (voice, pitch, beat, chord-ish modules depending on version — “transcribe everything” branding).

**ASA overlap:** Layer 2 / Session Musician research; overlaps MT3, muscriptor, chord, beat domains in one kitchen sink.

**Expected win:** Unlikely on dense electronic masters; architecture strategy is skeptical of producer-grade poly AMT.

**Risks:** Heavy deps; scattered quality; encourages productizing poly MIDI against strategy.

**Verdict:** **Research curiosity only.** Prefer focused tools: `beat_this`, `lv-chordia`, `muscriptor`/`mt3-infer`. Related piano-centric: `piano-transcription-inference` — even less EDM-relevant.

---

### 35. `pyebur128` — libebur128 Cython bindings

| | |
|---|---|
| **PyPI** | [`pyebur128`](https://pypi.org/project/pyebur128/) 0.1.1 |
| **Home** | https://github.com/jodhus/pyebur128/ |
| **Requires** | ≥3.8 |
| **License** | MIT |
| **Last activity** | 2024-09 |

**What it does:** Cython wrapper of **libebur128** (canonical C library for EBU R128 / BS.1770 loudness).

**ASA overlap:** Essentia is product **authority** for LUFS/truePeak. Top 20 **`pyloudnorm` (#16)** is the pure-Python research reference.

**Expected win:** Offline parity vs Essentia with a C-library ground truth.

**Verdict:** **Parity probe only.** Same rule as pyloudnorm: never dual-publish LUFS. Sibling CLIs: `sacrifunk-loudness` (batch reports) — eval convenience, not product.

---

### 36. `katana-meter` — LUFS / true peak / ΔE meter

| | |
|---|---|
| **PyPI** | [`katana-meter`](https://pypi.org/project/katana-meter/) 0.1.2 |
| **Requires** | ≥3.9 |
| **License** | **Research / proprietary-class** (“Research License”) |
| **Last activity** | 2026-01 |

**What it does:** Analyzer-only meter: LUFS, true peak, and **ΔE**-style difference energy (useful for A/B of two signals).

**ASA overlap:** Loudness parity + possible **before/after** comparison for audition samples or separation residuals.

**Expected win:** Handy offline meter; ΔE could help separation/sample QC scripts.

**Risks:** Non-MIT research license — legal review before any bundling; not needed if pyloudnorm/pyebur128 cover LUFS.

**Verdict:** **Eval-only with license caution.** Do not vendor into product.

---

### 37. `rs-audio-stats` — Rust EBU R128 stats

| | |
|---|---|
| **PyPI** | [`rs-audio-stats`](https://pypi.org/project/rs-audio-stats/) 1.4.1 |
| **Requires** | ≥3.10,&lt;3.13 |
| **License** | MIT |
| **Last activity** | 2025-12 |

**What it does:** High-performance **EBU R128** loudness and related stats via Rust.

**ASA overlap:** Same loudness parity domain as #35–#36 and Top 20 #16.

**Expected win:** Faster batch loudness scanning for eval corpora.

**Verdict:** **Parity/speed tool only.** No product dual meter. Related: `lupy`, `PALA`, `dr14meter`/`drcheck` (DR14) — DR14 is **not** ASA’s reconstruction surface; ignore for Ableton blueprint work.

---

### 38. `matchering` — reference mastering transfer

| | |
|---|---|
| **PyPI** | [`matchering`](https://pypi.org/project/matchering/) 2.0.6 |
| **Home** | https://github.com/sergree/matchering |
| **Requires** | ≥3.8 |
| **License** | **GPLv3** |
| **Last activity** | 2022-10 |

**What it does:** Matches EQ/dynamics of a target track to a **reference** — mastering **processing**, not measurement-for-Ableton-recommendations.

**ASA overlap:** Superficially “reference track” workflow; actually outputs processed audio, not device/param blueprints. Conflicts with ASA’s measure→advise chain.

**Expected win:** None for Phase 1/2 product thesis. Could confuse users into thinking ASA should auto-master.

**Verdict:** **Wrong problem.** Out of scope. Do not integrate.

---

### 39. `musicnn` — music audio tagging CNN

| | |
|---|---|
| **PyPI** | [`musicnn`](https://pypi.org/project/musicnn/) 0.1.0 |
| **Home** | https://github.com/jordipons/musicnn |
| **License** | ISC |
| **Last activity** | **2019-08** |

**What it does:** Pretrained CNNs for **music tagging** (genre, mood, instrumentation tags).

**ASA overlap:** `genreDetail` and detector stack already target production-relevant categories with measurement hooks.

**Expected win:** Soft tags that rarely become Glue Compressor attack times. Weak citation chain (PURPOSE #2–#3).

**Verdict:** **Low / skip.** Tags without measurement authority are Phase 2 filler risk.

---

### 40. `jams` — annotation container (+ `mirdata` note)

| | |
|---|---|
| **PyPI** | [`jams`](https://pypi.org/project/jams/) 0.3.5 |
| **Home** | https://github.com/marl/jams |
| **License** | ISC |
| **Last activity** | 2025-06 |

**What it does:** **JSON Annotated Music Specification** — standard container for beats, chords, segments, notes, etc.

**ASA overlap:** Offline evaluation harnesses (beat gate, structure, chords). Not a runtime analyzer.

**Expected win:** Interoperability with MIR corpora; cleaner eval manifests.

**Related:** [`mirdata`](https://pypi.org/project/mirdata/) 1.0.0 — dataset loaders (BSD). Excellent for **building fixtures**, useless on the product request path.

**Verdict:** **Yes for eval infrastructure** if harnesses grow. **Never** a product dependency for user analysis.

---

## Honorable mentions (not #21–#40, settled quickly)

| Package | One-line verdict |
|---|---|
| `libretta`, `orbit-dsp`, `sonara`, `analyzeAudio`, `beatlyze-analyzer` | Kitchen-sink / playlist MIR — shallower than Phase 1; don’t embed |
| `acidcat` | File/preset **metadata** inspector — useful for sample librarians, not mix DSP |
| `galdr` | Agent “listener-state” traces — interesting, not Ableton-citable authority |
| `auditok` | Energy VAD/segmentation — minor; ASA structure/silence paths cover need |
| `splifft`, `remucs`, `stem-separator`, `spleeter*` | Separator wrappers/legacy — prefer Top 20 #2–#5 |
| `yourmt3`, `piano-transcription-inference` | Prefer `mt3-infer` / `muscriptor` for poly research |
| `pedalboard`, `nanodsp`, `nnAudio`, `specux` | Processing / feature frontends — not measurement authority |
| `auraloss`, `torch-l1-snr`, `amt-augmentor` | Training losses / aug — out of product scope |
| `soundlevelmeter` | IEC SPL + Python ≥3.13 — wrong metric + wrong Python |
| Hosted APIs (`beatlyze`, `stemsplit-python`, `musiciwant`, `audd`) | Not local deterministic measurement |

---

## Agent decision tree (Next 20)

```
Package name appears in search / user request
  │
  ├─ Is it in TOP20? → follow TOP20 doc
  │
  ├─ Is it #33 basic-pitch or #29 jaxmsst/MSST?
  │     → refuse product path; cite architecture / trust diet
  │
  ├─ Is it #27/#28/#38 or honorable-mention wrapper/API/playlist?
  │     → skip; explain redundancy
  │
  ├─ Is it #35–#37 loudness meter?
  │     → eval parity only; Essentia remains authority
  │
  ├─ Is it #40 jams / mirdata?
  │     → OK for eval harness plumbing
  │
  ├─ Is it #26 demucs-onnx or #32 coremlcrepe?
  │     → ops/perf parity experiment only, with numeric guards
  │
  └─ Else (#22–#25, #30–#31, #34, #39)
        → only as offline baseline after TOP20 P0 work is done
```

---

## Relationship to Top 20 bake-off order

Do **not** let Next 20 reorder priorities:

1. `beat_this` gate (Top #1)  
2. Demucs vs RoFormer/UVR (Top #2–#5) + PEASS/SI-SDR (#6–#7)  
3. `lv-chordia` (Top #13) — **not** `chord-extractor` (#22)  
4. Structure: `allin1` (Top #8) before `msaf` (#24)  
5. Poly AMT: `muscriptor` / `mt3-infer` before `omnizart` / `basic-pitch`  

---

## Changelog

| Date | Note |
|---|---|
| 2026-07-18 | Initial Next 20 (#21–#40) after full classifier scan. Companion to `PYPI_AUDIO_ANALYSIS_TOP20.md`. |
