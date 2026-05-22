# Forking & Incorporation Plans — 2026-05-14

**Subject:** Five upstreams from the 2026-05-13 and 2026-05-14 discovery
passes, planned for incorporation into **ASA** (this repo — Phase 1
measurement pipeline + Phase 2 advisor) and **Harmonia** (sibling
project — React + Tonal.js chord-progression / reharmonization tool).

**Anchor:** [PURPOSE.md](../PURPOSE.md) — every plan ties back to one of
its three "build it" criteria or the "stop and reconsider" branch.

**Companion review:** [`docs/external-repo-review-2026-05-13.md`](../docs/external-repo-review-2026-05-13.md)
already covers openmeters, soundscope, Partiels, and forever-jukebox
(Tracks 1–3 there). This batch deliberately avoids those upstreams and
opens five new tracks — three ASA-facing, two Harmonia-facing — numbered
4–8 to continue the count.

**Environment note.** The task was framed against a `routine-discoveries`
repository with `discoveries/*.md` source-of-truth files and a template at
`incorporations/asa-2026-05-13.md`. None of those files are present in
this checkout (the repo I'm scoped to is `ableton-sonic-analyzer`). I
proceeded using the task description as the spec, the actual upstream
repos as the authoritative source for license / API / schema, and the
prior `external-repo-review-2026-05-13.md` for house style.

> **CORRECTION (2026-05-22): "Harmonia" is a phantom — it does not exist.**
> A later investigation (4 independent agents + first-hand repo/web
> forensics, including an adversarial pass tasked with proving it real)
> found no Harmonia project anywhere. `github.com/slittycode/harmonia`
> returns 404; the owner's account lists no such repo and none matching the
> "React + Tonal.js reharmonization" signature; there is no repo, submodule,
> dependency, directory, or code tying Harmonia to anything real
> (`@tonaljs/*` is only a *transitive* dep of ASA, via `midi-writer-js`).
> "Harmonia" appears nowhere in `CLAUDE.md`, `PURPOSE.md`, or `BACKLOG.md`,
> and the earliest mention (in `external-repo-review-2026-05-13.md`) cited a
> "Harmonia track" in `BACKLOG.md` that has never existed — a dangling
> citation. The name entered ASA's docs from the out-of-repo
> `routine-discoveries` task framing (see the Environment note above) and
> propagated by re-description: a citation loop with no primary source.
>
> **Consequence for this document:** every "Harmonia-facing" framing below
> is void, and the Harmonia asides in Plans 4–6 are moot. **Plans 7
> (ChordMiniApp) and 8 (chordonomicon) have been re-scoped to ASA** — see
> the re-scope note at the head of each plan; their detailed
> adopt/adapt/reject tables were written against Harmonia's symbolic-first
> premise and need ASA-specific re-evaluation before any action. The
> `routine-discoveries` repository needs the same correction in a session
> scoped to it.

---

## License Map (read before reading any upstream source)

| Project | License | Implication for the plan |
| --- | --- | --- |
| **ASA** (this repo) | MIT ([LICENSE](../LICENSE)) | Can vendor MIT / BSD / Apache code with attribution. Cannot vendor GPL code. |
| **Harmonia** | Assumed MIT (confirm — out of repo) | Same constraints; the Harmonia plans below assume MIT. If Harmonia turns out to be GPL-compatible, Plan 6 expands. |
| **audio-analyzer-rs** | MIT ([verified — README](https://github.com/JuzzyDee/audio-analyzer-rs)) | Code-compatible. Fork-and-extract is permitted with attribution. |
| **resonators** | Dual MIT / Apache-2.0 ([verified — README](https://github.com/jhartquist/resonators)) | Code-compatible at either license. Picking MIT keeps the chain uniform with ASA. |
| **jivetalking** | **GPL-3.0-only** ([verified — LICENSE file](https://github.com/linuxmatters/jivetalking/blob/main/LICENSE)) | **Cannot vendor or translate the source.** Read the README's prose specification (which is descriptive enough to act on) and clean-room any reimplementation. Algorithms are not copyrightable; copied or paraphrased *code* is. |
| **ChordMiniApp** | MIT ([verified — repo metadata](https://github.com/ptnghia-j/ChordMiniApp)) | Code-compatible. The plan here is reference-only, so the license matters mostly for snippet attribution. |
| **chordonomicon (repo)** | Apache-2.0 ([verified — repo metadata](https://github.com/spyroskantarelis/chordonomicon)) | Code-compatible (preprocessing scripts, vocab builders, baseline trainers). |
| **chordonomicon (HF dataset)** | **CC-BY-NC-4.0** (reported via HF dataset listing; direct fetch of the dataset card was auth-gated — *confirming on the card itself is checklist item 1 of Plan 8*) | **NonCommercial.** If Harmonia is or will become commercial, the dataset cannot ship inside the product. Training a model and shipping weights derived from NC data is debated; treat conservatively. |

**Cross-cutting license discipline.** Plans 6 (jivetalking, GPL-3.0) and
8 (chordonomicon HF dataset, CC-BY-NC-4.0) are the only ones with
license risk. Both call this out as item 1 of their Definition of done.

---

## TL;DR

| Plan | Upstream | Serves | Stack of upstream | Recommended approach | One-line verdict |
| --- | --- | --- | --- | --- | --- |
| 4 | audio-analyzer-rs | ASA + Harmonia | Rust binary MCP server | **Cross-check oracle first; fork-to-WASM gated on a real in-browser need** | The discovery framing assumes ASA is in-browser; ASA's measurement layer is server-side Python. Oracle is cheap and high-value; fork-to-WASM solves a problem ASA doesn't have today. |
| 5 | resonators | ASA | Rust → published npm WASM | **Incorporate as a dependency** (`npm install resonators`) for a new in-browser preview surface | The near-drop-in. Zero toolchain burden. Opens a real-time-feedback channel ASA doesn't have, without touching the server-side measurement contract. |
| 6 | jivetalking | ASA | Go CLI, GPL-3.0 | **Port the *pattern* (measure → derive parameters → cite the measurement) into Phase 2 recommendation logic; clean-room from the README** | The pattern is exactly ASA's chain of custody. The constants are voice/podcast-tuned; ASA needs music-domain calibration. GPL blocks any code path. |
| 7 | ChordMiniApp | Harmonia | Next.js + Flask + Firebase | **Reference-only / UX + architecture incorporation** — classify each surface adopt / adapt / reject | Closest neighbor to Harmonia's product surface. Their stack is heavier; their UX surfaces are concrete and gradable. |
| 8 | chordonomicon | Harmonia | Hugging Face dataset (Apache-2.0 scripts, CC-BY-NC-4.0 data) | **Incorporate as a dataset dependency** (HF `datasets` lib) for a reharmonization eval harness; do *not* ship the data inside Harmonia | Best benchmark Harmonia can get. The NC license forbids commercial inclusion of the data; weights-derived-from-NC is a separate, contested question. |

---

## Plan 4 — audio-analyzer-rs (ASA + Harmonia)

### Source

- **URL:** https://github.com/JuzzyDee/audio-analyzer-rs
- **Language:** Rust (99.3%), edition 2024
- **Stars:** 21
- **Creation date:** Not exposed without GitHub API auth; main branch last
  pushed **2026-03-15**, `feature/lufs` branch pushed 2026-03-11. Repo
  is plainly recent (early 2026); precise creation date is checklist
  item under DoD.
- **Latest version:** v1.0.0
- **License:** **MIT** ([verified — README, project root](https://github.com/JuzzyDee/audio-analyzer-rs))

### What to lift

The crate exposes an MCP server with six tools — `audio_info`,
`spectral_features`, `harmonic_analysis`, `rhythm_analysis`,
`full_analysis`, `compare` — backed by:

- Spectral: centroid, bandwidth, rolloff, flatness, 13 MFCCs.
- Frequency bands: 7 producer-oriented bands (sub-bass through brilliance)
  with RMS energy and spectral contrast per band.
- Loudness: integrated LUFS, true peak (dBTP), loudness range (LRA),
  per-platform normalization targets.
- Dynamics: crest factor, 95th–5th-percentile LR, peak dBFS.
- Stereo: phase correlation, mono-compatibility score, width
  (mid/side ratio), L/R balance.
- Harmonic: chromagram, Krumhansl-Schmuckler key detection, tonnetz.
- Rhythm: tempo estimation, beat tracking, onset detection, tempo
  stability.
- Percussive: harmonic/percussive source separation, attack sharpness,
  onset density.
- Structural: multi-feature novelty for section-boundary detection.

The output is structured JSON with downsampled time series (`low` ~0.5/s,
`medium` ~1/s, `high` ~4/s, or a custom rate). Full analysis of a
60-second track completes in roughly 2 seconds (per the README).

**Crate shape — important caveat.** `Cargo.toml` declares **no `[lib]`
target**; the crate has two `[[bin]]` targets (`cli` at `src/main.rs`,
`mcp-server` at `src/mcp_server.rs`). Dependencies: `symphonia 0.5`,
`rustfft 6.2`, `rmcp 1.1`, `tokio 1` (full features), `serde`,
`serde_json`, `schemars 1.0`, `tracing`. To consume the DSP as a library
you must fork and add a `[lib]` target that exposes the internal modules
shared by the two bins.

### Why

The discovery scan framed this as "essentially ASA's entire feature set
in one dependency-free crate." That framing has two layers:

1. **As a cross-check oracle:** every output dimension above has a direct
   counterpart in ASA's existing Python pipeline. A second, independent
   implementation of the same measurement stack is exactly what PURPOSE.md
   Quality Invariant 1 (measurement authority) needs — a way to detect
   drift between releases of Essentia, librosa, our own code.
2. **As an in-browser analysis core:** the discovery doc assumes ASA runs
   in-browser via Essentia.js / WASM. **It does not.** ASA's measurement
   layer is server-side Python (Essentia via `analyze_core.py`), per the
   prior external review. So "fork → WASM" solves an in-browser need that
   ASA doesn't have *today*. Without a concrete in-browser DSP feature on
   the roadmap, this layer is engineering for engineering's sake
   (PURPOSE.md decision-framework branch 5).

For Harmonia, the harmonic outputs (key, chromagram, tonnetz, pitch-class
distribution) are directly useful: a guitar-track input → key estimate is
exactly the analysis Harmonia needs to seed reharmonization choices. But
Harmonia is React + Tonal.js — a JS app — so consuming a Rust binary MCP
server from Harmonia means either (a) a tiny Node-side child process
running the `mcp-server` binary, or (b) the same fork-to-WASM that ASA
would need.

### Approach

**Two-phase plan, both phases small.**

- **Phase 4a — Cross-check oracle (recommended pickup first).** Add a
  test-only path in `apps/backend/tests/` that runs the upstream binary
  (downloaded to a fixture location, or built from source in CI) against
  ASA's existing fixture audio and asserts each comparable output is
  within tolerance of ASA's Phase 1. Tolerances vary by field; start
  loose (key match ±0 semitones, BPM ±1, integrated LUFS ±0.3) and
  tighten as drift is characterized. **No fork, no port.** This is
  consume-the-binary-as-an-oracle, the same shape as ASA already does
  with subprocess invocations of `analyze.py`.
- **Phase 4b — Fork-to-WASM (gated).** Only if a concrete in-browser DSP
  need lands on the roadmap (e.g. a hosted-mode browser preview that
  doesn't roundtrip the server, or a Harmonia capture-and-analyze flow
  that runs in the user's tab). The fork adds a `[lib]` target with
  `crate-type = ["cdylib"]`, swaps the `tokio`/`rmcp` server layer for a
  `wasm-bindgen` surface, keeps `symphonia` + `rustfft` (both
  WASM-compatible), and ships an npm package. **Estimated cost:** real —
  ~1–2 engineer-weeks. **Estimated value before that need exists:** zero
  (it duplicates a working Python pipeline against the wrong runtime).

**Stack-fit reasoning.** ASA is Python-server-side for measurement and
React for the UI; the most stack-compatible interface to a Rust crate is
*the binary*, not a WASM port. The binary fits naturally into
`apps/backend/`'s existing pattern of `subprocess` shelling out (the
exact pattern `server.py` already uses to call `analyze.py --yes`). The
WASM port fits a future state that doesn't exist today.

### Cross-reference to Plan 5 (resonators)

Both audio-analyzer-rs and resonators are Rust → WASM stories on paper.
They do **not** overlap functionally — resonators is one algorithm (the
Resonate per-sample resonator bank, alternative to STFT/CQT);
audio-analyzer-rs is a generic feature stack on top of FFT. If
Phase 4b is ever taken, ASA can carry both: resonators as a published
npm artifact (zero toolchain burden — see Plan 5) plus the
audio-analyzer-rs fork as its own npm package. The plans only conflict
if both try to *replace* ASA's existing Python pipeline simultaneously,
which neither should — the recommendation in both plans is additive,
not substitutive.

### Adopt / Adapt / Reject — output schema (only if Phase 4b is taken)

| Item | Decision | Rationale |
| --- | --- | --- |
| The six MCP tool names as ASA function names | **Reject** | ASA's API surface is run-oriented (`/api/analysis-runs`), not tool-oriented. The naming would leak the upstream's MCP framing. |
| The `resolution: "low" | "medium" | "high"` parameter | **Adopt** | Matches ASA's existing time-series downsampling conventions (`_downsample_lufs_array`). |
| The 7 producer-oriented band names (sub-bass … brilliance) | **Adopt** | Identical to ASA's `spectralBalance` band names ([`apps/ui/src/types/measurement.ts`](../apps/ui/src/types/measurement.ts)). Pure win — confirms the convention. |
| The `compare` two-track diff tool | **Adapt** | ASA has no first-class A/B comparison endpoint; Harmonia might. Worth keeping as an idea, not a copy. |
| The MFCC count of 13 | **Adopt** | Standard. ASA doesn't expose MFCCs in Phase 1 today; adding them would be additive and would feed Phase 2 timbre prompts. |
| The KS key-detection algorithm choice | **Adopt as a cross-check, not a replacement** | ASA's chord/key path uses librosa + Viterbi smoothing. KS is a different family; running both and comparing is the oracle pattern, not a swap. |

### Cross-check oracle

audio-analyzer-rs *is* the cross-check oracle for Plan 4 itself. Beyond
that: for the loudness sub-path, the prior review's Track 1 EBU R128
test set ([`apps/backend/tests/test_loudness_r128.py`](../apps/backend/tests/test_loudness_r128.py))
is a third independent oracle. Three-way agreement is the desirable
signal.

### Definition of done — Phase 4a (cross-check oracle)

- [ ] Confirm MIT in the upstream's LICENSE file (one HTTP read; today
      only the repo-card / README badge has been verified — sufficient to
      proceed, but the file itself is the canonical signal).
- [ ] Confirm the upstream's first-commit date for the Source line.
- [ ] Pin a release version (`v1.0.0` today) and document the pin in
      `BACKLOG.md` and the test file header.
- [ ] CI step that fetches or builds the `cli` binary into a cached
      location.
- [ ] `tests/test_external_oracle_audio_analyzer.py` that runs the binary
      against three fixture tracks (already in `tests/fixtures/`) and
      asserts each comparable field (BPM, key, integrated LUFS,
      truePeak, crestFactor, the 7 spectral-balance band energies) is
      within a documented tolerance of ASA's Phase 1.
- [ ] Failure surfaces as a non-blocking CI annotation (drift indicator),
      not a hard fail — third-party drift shouldn't break ASA's release
      train, but it should be visible.

### Definition of done — Phase 4b (fork to WASM, gated)

- [ ] An ADR justifying the in-browser DSP need that triggered Phase 4b.
      Without that ADR, do not start.
- [ ] Fork at `slittycode/audio-analyzer-rs` with attribution and an
      explicit divergence note.
- [ ] Add `[lib]` target with `crate-type = ["cdylib"]`; carve out the
      DSP modules from the two bins.
- [ ] Replace `tokio` / `rmcp` with `wasm-bindgen` at the public surface.
- [ ] Publish to npm under a scoped name.
- [ ] An ASA browser-side smoke test that imports the package and
      reproduces one bench against the same fixture's server-side
      result.

### Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Phase 4b is taken without a concrete in-browser need | High | Gate Phase 4b on an ADR — see DoD. The default state is "don't fork." |
| Upstream is small (21 ★, single maintainer) and may stall | Medium | The oracle path doesn't require active upstream development. Pin a version; oracle works against the pinned binary indefinitely. |
| Numerical disagreement between audio-analyzer-rs and ASA is a *false* positive (different but both valid implementations) | Medium | Document expected tolerances per field; treat drift outside tolerance as a flag-and-investigate, not a hard fail. |
| Edition 2024 / fresh dependencies churn breaks the binary build in CI | Low | Cache the built binary as a CI artifact; rebuild on version bump only. |
| Cargo.toml has no `[lib]` target — Phase 4b is bigger than "add wasm-bindgen" | Medium | Acknowledged. The fork has to split modules before exposing them. Plan accordingly. |

---

## Plan 5 — resonators (ASA)

### Source

- **URL:** https://github.com/jhartquist/resonators
- **Language:** Rust (76.6%), Python (20.8%), Just (2.6%)
- **Stars:** 86
- **Creation date:** Not exposed without GitHub API auth; latest release
  **v0.1.1 dated 2026-04-25**. Repo is new (q2 2026). First-commit date
  is checklist item under DoD.
- **License:** **Dual MIT / Apache-2.0** ([verified — README](https://github.com/jhartquist/resonators))
- **Published artifacts:** crates.io (`cargo add resonators`), PyPI
  (`pip install resonators`), **npm (`npm install resonators`)** — the
  one that matters for ASA.

### What to lift

The `ResonatorBank` class (same name in all three target languages):

```javascript
const bank = new ResonatorBank(freqs, sampleRate);
const out = bank.resonate(signal, hopSize);
// Float32Array, interleaved [real, imag, real, imag, ...]
```

The algorithm is Alexandre François's Resonate — a bank of independent
phasor-like oscillators tuned to fixed frequencies, with **per-sample
updates, no windowing, no buffering, and a fixed memory footprint
independent of signal length.** Per-bin time-frequency tradeoff control
is the practical differentiator from STFT/CQT. The published WASM build
runs inside an `AudioWorkletNode` in the browser; the README's
demonstration is a live-microphone-fed 440-resonator bank with sub-budget
worklet callbacks at typical bin counts (88 / 264 / 440 / 880).

Performance: ~1.6× the noFFT reference implementation; 5.44 M
samples/sec at 440 bins on Apple M2 Max.

### Why

ASA's measurement layer is server-side Python — covered. What ASA does
**not** have today is any in-browser DSP at all. Two concrete browser-side
needs that resonators directly addresses:

1. **Live audition preview.** Before submitting a full analysis run,
   give the user a real-time spectral readout of what they uploaded —
   "this is roughly the spectral shape you're sending in." Sub-budget
   AudioWorklet operation is exactly the latency profile this needs.
2. **Phase 3 audition feedback.** Phase 3 *audition* shipped in
   PR #45 (heuristic WAV/MIDI rendering — see
   [`docs/SAMPLE_GENERATION.md`](../docs/SAMPLE_GENERATION.md); this is
   distinct from Phase 3 *synth-patch generation* in `patchSmith.ts`,
   which remains open per [`BACKLOG.md`](../BACKLOG.md)). A pre-render
   spectral preview before the user commits to an audition would close
   a loop currently served only by the rendered file.

Neither use case asks ASA to re-do its *measurement* in the browser
(which would violate the prior review's discipline). Both are new
visualization-layer features that depend on a WASM DSP that ASA doesn't
currently carry.

For Harmonia, resonators is less compelling — Harmonia is symbolic
(chord-progression / Tonal.js), not audio-first. If Harmonia grows an
audio-input capability, Plan 5's WASM bank becomes relevant there too,
but treat that as a future-state branch.

### Approach

**Incorporate as a dependency.** `npm install resonators` into
`apps/ui/`; thin wrapper around `ResonatorBank` in `apps/ui/src/services/dsp/`;
new component for the preview surface. **No fork.** Pin the version,
treat the API as external contract.

**Stack-fit reasoning.** resonators *is* the smoothest possible
stack-fit for ASA's browser layer — a published WASM package with a
React-compatible API surface and an explicit AudioWorklet demo path. No
Rust toolchain in ASA; no build complexity; no `wasm-pack` step. This is
the inverse of audio-analyzer-rs's binary-MCP shape (Plan 4).

### Cross-reference to Plan 4 (audio-analyzer-rs)

Plans 4 and 5 are both Rust → WASM on paper. They differ in shape:

- **Plan 5 — incorporate-as-dependency.** The WASM is *already
  published* on npm. ASA carries zero Rust toolchain. Friction: minimal.
- **Plan 4b — fork-and-publish.** ASA would maintain a fork and publish
  its own WASM. Real ongoing burden.

If both are taken, ASA ends up with **one** opinionated Rust toolchain
(the audio-analyzer-rs fork) and **one** vendored published-WASM
dependency (resonators). They do not conflict. The reverse — having
resonators's WASM as the only Rust-derived artifact in ASA — is the
strict subset and the cheapest end state.

### Adopt / Adapt / Reject — API surface

| Item | Decision | Rationale |
| --- | --- | --- |
| `ResonatorBank` constructor (`freqs`, `sampleRate`) | **Adopt as-is** | Native API; the JS wrapper passes through. |
| Interleaved `Float32Array` complex output `[r, i, r, i, ...]` | **Adapt at the wrapper boundary** | ASA's downstream React code wants `{magnitude, phase}[]` or `{re, im}[]`. The wrapper provides one transform; downstream sees the named-field shape. |
| Per-bin time-frequency tradeoff parameters | **Adopt as a configuration object** | These are the differentiator from STFT — exposing them lets the preview surface differentiate from a vanilla spectrogram. |
| The AudioWorkletNode example wiring | **Adopt** | Direct copy of the README's worklet pattern is the cleanest browser integration. |
| `hopSize` semantics | **Adopt** | Standard. Document the choice in the wrapper for downstream calibration. |

### Cross-check oracle

The natural oracle is ASA's existing server-side spectral path: render
the same audio through ASA's Phase 1 `spectralBalanceTimeSeries`,
downsample to the same time grid, and compare band-energy curves.
Disagreement above tolerance flags a calibration issue in the new
client-side preview, not a measurement bug. (Phase 1 is ground truth.)

A second oracle is Plan 4's audio-analyzer-rs `spectral_features` output
on the same audio.

### Definition of done

- [ ] Confirm dual MIT / Apache-2.0 in the upstream's LICENSE files.
- [ ] Confirm the upstream's first-commit date for the Source line.
- [ ] `apps/ui/package.json` adds `resonators` pinned to a specific
      version; the README's `v0.1.1` (2026-04-25) is the current head.
- [ ] `apps/ui/src/services/dsp/resonatorPreview.ts` wraps the
      `ResonatorBank` API and exposes a named-field result shape.
- [ ] One new component (placement TBD with UI team) renders the
      preview on the upload surface, behind a feature flag.
- [ ] One Playwright smoke test loads the upload surface, mocks an
      audio stream, and asserts the preview component renders bin
      counts > 0.
- [ ] The preview UI is labeled as an approximate live preview, not
      the cited Phase 1 measurement; a Vitest unit test asserts the
      "approximate" / "preview" copy is present in the rendered output
      and that no Phase 1 field name (e.g. `spectralBalance.subBass`)
      appears as the cited source.
- [ ] A Vitest unit test asserts the wrapper transforms interleaved
      Float32Array → named-field output correctly on a synthetic input.
- [ ] Cross-check spike: on one fixture, compare worklet output to
      ASA's `spectralBalanceTimeSeries` band energies; document the
      observed delta.

### Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Upstream is at v0.1.1 — pre-1.0 API may break | Medium | Pin the version; treat API as external contract until 1.x. |
| AudioWorklet has browser-specific quirks (Safari especially) | Medium | The wrapper degrades to a no-op preview when the worklet isn't available; the analysis path doesn't depend on it. |
| User expectation drift — "preview is wrong, therefore ASA's measurement is wrong" | Medium | The preview is labeled as approximate. Phase 1 stays the cited number throughout the UI. |
| Bundle-size regression from the WASM payload | Low | Lazy-load the preview component; the WASM only ships when the user enables the surface. |
| The Resonate algorithm has different time-frequency behavior than STFT, so the preview *will* look different from any spectrogram users have seen elsewhere | Low | Acknowledged feature, not bug. The README is explicit about per-bin tradeoff control; the wrapper exposes default settings calibrated to look familiar. |

---

## Plan 6 — jivetalking (ASA)

### Source

- **URL:** https://github.com/linuxmatters/jivetalking
- **Language:** Go (92%)
- **Stars:** 71
- **Creation date:** Not exposed without GitHub API auth; latest release
  **v0.3.2 dated 2026-05-02**. Repo is new (q2 2026).
- **License:** **GPL-3.0-only** ([verified — full LICENSE file](https://github.com/linuxmatters/jivetalking/blob/main/LICENSE) is the GNU GPL v3, 29 June 2007, no "or later")

### What to lift

**Not code.** The lift is the *pattern*. The README describes a four-pass
architecture in which **measurements drive parameter choices**, not the
other way around:

- **Pass 1 — measure.** Integrated LUFS, true peak, LRA (EBU R128); noise
  floor + spectral signature; speech-segment RMS + crest + spectral
  content; kurtosis + spectral flux for transient behavior.
- **Pass 2 — adaptive filter chain.** Highpass cutoff adapts to spectral
  content. Denoiser intensity adapts to noise-floor measurements. Gate
  threshold positioned between noise floor and quiet-speech RMS.
  Compressor ratio/release adapt to kurtosis + spectral flux. De-esser
  intensity (0.0–0.6) adapts to spectral centroid + rolloff.
- **Passes 3 & 4 — two-stage normalization.** Pre-gain and ceiling
  derived from Pass 2 measurements; CBS-Volumax-inspired limiter creates
  headroom; linear gain reaches the -16 LUFS target without dynamic
  processing.

The product of Pass 2 is, for each filter, a **function from measurement
to parameter** — for example, the de-esser's intensity is a deterministic
projection of spectral centroid and rolloff into [0.0, 0.6]. The exact
functions live in jivetalking's Go source, which is GPL-3.0 and
**off-limits for translation**.

### Why

PURPOSE.md Quality Invariant 2 (citation chain): every Phase 2
recommendation must cite the specific Phase 1 measurement(s) that justify
it. jivetalking's pipeline *is* that invariant, made operational, for
voice/podcast processing. The discovery doc framed this as "exactly what
ASA's loudness + dynamics stage should output as recommendations."

The gap in ASA today: the Phase 2 system prompt at
[`apps/backend/prompts/phase2_system.txt`](../apps/backend/prompts/phase2_system.txt)
+ device catalog at
[`apps/backend/prompts/live12_device_catalog.json`](../apps/backend/prompts/live12_device_catalog.json)
asks the Gemini interpreter to produce specific Ableton device + parameter
recommendations grounded in Phase 1 measurements. The interpreter has the
measurements; what it *doesn't* always have is **a measurement →
parameter heuristic table**. jivetalking's prose specification *is* such
a table, for voice. Re-deriving it for music gives Phase 2 a concrete
heuristic for compressor / limiter / de-esser / gate / highpass
recommendations that traces back to a measurement, every time.

### Approach

**Port the pattern. Clean-room. Reimplement on-stack (prompt + Python).**

1. **Identify the measurement inputs from existing Phase 1.** ASA already
   measures: integrated LUFS, true peak, LRA, crest factor (per the
   prior external review's Track 1 close-out — the EBU R128 test set
   confirmed ASA's loudness is correct on stereo), spectral centroid
   (within `spectralBalance`), kurtosis (in dynamics detail). What's
   missing for the jivetalking pattern: an explicit **noise-floor
   estimate** and **spectral flux**. Spectral flux is computable from
   ASA's existing librosa STFT; noise-floor is a small new measurement
   (low-percentile RMS of silent frames).
2. **Re-derive the parameter heuristics for music.** jivetalking's
   constants are voice/podcast-tuned (its target is "narrator audio at
   -16 LUFS"). ASA's domain is music recreation at producer-determined
   loudness targets. The *shape* of each heuristic (de-esser intensity
   as a function of spectral centroid + rolloff; compressor ratio as a
   function of kurtosis + flux) survives the domain shift; the
   *constants* must be recalibrated against music-domain reference
   tracks.
3. **Encode the heuristics in the Phase 2 prompt + catalog.** Add a
   `parameterHeuristics` section to `live12_device_catalog.json` keyed
   by measurement → device → parameter, with a one-line citation rule
   per row. The Phase 2 prompt's existing `validateGenreDSPConsistency`
   guardrail
   ([`apps/ui/src/services/phase2Validator.ts`](../apps/ui/src/services/phase2Validator.ts))
   gets a new sibling validator that enforces "every parameter
   recommendation cites the measurement that produced it."

**Stack-fit reasoning.** jivetalking is Go; ASA is Python + TS. There is
no path that "compiles the math" cleanly — Go is the wrong source runtime
for a port, *and* the license forbids it anyway. The intellectually
honest answer is to consume the README's prose specification as
inspiration, write our own implementation, and let it live in the prompt
+ catalog layer (which is where ASA already encodes
measurement→recommendation discipline).

### Composition with the existing review (where the measurements come from)

The discovery doc explicitly flagged this: "Decide where its measurement
inputs come from — openmeters' Track 1 output, or plan 1's analyzer — so
this plan composes with what's already planned rather than duplicating
measurement."

- **Track 1 (prior review, openmeters):** the openmeters port was
  rejected; ASA's existing Essentia `LoudnessEBUR128` was verified
  correct on stereo at 44.1 kHz and 48 kHz via the EBU R128 spike
  ([`docs/track1-spike-outcome-2026-05-13.md`](../docs/track1-spike-outcome-2026-05-13.md)).
- **Plan 4 (this batch, audio-analyzer-rs):** a cross-check oracle, not a
  measurement source. ASA's Phase 1 remains canonical (Quality
  Invariant 1).

So Plan 6's measurement inputs are **ASA's existing Phase 1 outputs**
([`analyze_core.analyze_loudness`](../apps/backend/analyze_core.py),
spectral balance, dynamics) plus the two small additions (noise-floor
estimate, spectral flux). No new measurement layer.

### Adopt / Adapt / Reject — jivetalking's parameter mapping

| Mapping (from jivetalking prose) | Decision for ASA Phase 2 | Rationale |
| --- | --- | --- |
| Highpass cutoff adapts to spectral content | **Adapt** — same dimension (spectral centroid), music-domain calibration | A hi-hat-heavy track and a sub-bass-heavy track want different LF cleanup; the shape transfers, the cutoff range shifts. |
| Denoiser intensity adapts to noise floor | **Reject for music** | ASA's target is reference-track recreation, not source cleanup. Producers don't denoise reference material. |
| Gate threshold positioned between noise floor and quiet-signal RMS | **Adapt for percussion only** | Ableton Gate on kick / clap channels uses exactly this shape. Bass / pads don't gate. The mapping survives in a narrowed device context. |
| LA-2A-style compressor ratio/release adapts to kurtosis + spectral flux | **Adopt** | Kurtosis and flux are exactly the measurements ASA's Phase 1 produces or can produce; the mapping is genre-agnostic and music-relevant. |
| De-esser intensity 0.0–0.6 based on spectral centroid + rolloff | **Adapt** | The voice-tuned sibilance bands (5–8 kHz) don't apply to music; the *function shape* (more high-frequency content → more attenuation) does, recalibrated to the music context (e.g., hi-hat-heavy or open-cymbal-heavy material). |
| Two-stage normalization: limiter for headroom, linear gain for target | **Adopt** | Ableton Limiter + Utility gain stage is the direct counterpart. The target loudness in ASA's case is user-determined or genre-determined, not a fixed -16 LUFS. |
| Hard target of -16 LUFS | **Reject** | Voice-specific; music targets vary by genre (streaming -14 LUFS, dance / club louder, broadcast quieter). |

### Cross-check oracle

The honest answer: **there isn't a clean numerical oracle** for
parameter-selection outputs. Parameter choice is a value judgment
(parameters that *sound* right for this material), not a measured
quantity. Two partial validations:

1. **Round-trip A/B:** apply ASA's recommended Phase 2 parameters to the
   reference track (using Ableton or a headless `librosa`-based render);
   measure the resulting LUFS / spectral balance / dynamics; check
   whether the result moves *toward* the reference's measurements.
2. **Phase 2 validator (existing):** the
   [`phase2Validator.ts`](../apps/ui/src/services/phase2Validator.ts)
   suite already checks chain-of-custody. Extend it with a "every
   parameter cites a measurement" assertion (the heuristic-table
   version of the chain-of-custody guardrail).

### Definition of done

- [ ] Confirm GPL-3.0-only in the upstream's LICENSE file. (Done — file
      read.) Document the decision not to read jivetalking's source for
      any code path; cite the prose README only.
- [ ] Confirm the upstream's first-commit date for the Source line.
- [ ] Add two small Phase 1 measurements: noise-floor estimate
      (low-percentile RMS of silent frames) and spectral flux. Update
      [`apps/backend/JSON_SCHEMA.md`](../apps/backend/JSON_SCHEMA.md),
      `EXPECTED_TOP_LEVEL_KEYS` in
      [`apps/backend/tests/test_analyze.py`](../apps/backend/tests/test_analyze.py),
      and the matching `Phase1Result` fields in
      [`apps/ui/src/types/measurement.ts`](../apps/ui/src/types/measurement.ts)
      (CLAUDE.md tripwire #3 — Python emits camelCase JSON directly with
      no conversion layer, so a Python-side addition without the TS
      counterpart disappears silently from the UI).
- [ ] Add `parameterHeuristics` block to
      [`apps/backend/prompts/live12_device_catalog.json`](../apps/backend/prompts/live12_device_catalog.json),
      keyed by (measurement, device, parameter), with one row per
      heuristic adopted from the table above.
- [ ] Update
      [`apps/backend/prompts/phase2_system.txt`](../apps/backend/prompts/phase2_system.txt)
      to require Phase 2 to apply heuristics via the new block.
- [ ] New validator `validateHeuristicChainOfCustody` in
      [`apps/ui/src/services/phase2Validator.ts`](../apps/ui/src/services/phase2Validator.ts)
      that asserts every parameter recommendation cites the measurement
      that produced it.
- [ ] Live Gemini smoke test on a known track shows at least three
      parameter recommendations grounded by the new heuristic block.

### Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| GPL contamination from reading jivetalking source while doing the port | **High** | Read the README only. Document algorithmic provenance per heuristic. The README is descriptive enough; no source-reading is required. |
| Voice-tuned heuristics ported wholesale to music | High | The Adopt / Adapt / Reject table above is the discipline. Music-domain calibration is the work; the prose pattern is the input, not the output. |
| -16 LUFS hard target gets imported by accident | Medium | Explicitly Rejected in the table. Phase 2's existing LUFS-consistency validator catches a hard-coded target if it slips in. |
| Heuristic block grows large and brittle | Medium | Start with 5–7 heuristics drawn from the Adapt rows above. Add more only as Phase 2 audits show a recurring "I don't have a parameter heuristic for this" gap. |
| The "cross-check oracle" round-trip A/B requires Ableton or a headless renderer that ASA doesn't currently have | Low–Medium | A small headless render via `librosa` + `pyloudnorm` is enough for LUFS / dynamics / spectral-balance round-trip checks. Treat as a separate small spike if needed. |

---

## Plan 7 — ChordMiniApp (ASA — re-scoped)

> **Re-scoped to ASA (2026-05-22).** Originally framed for the (phantom)
> Harmonia sibling — see the correction banner at the top of this file.
> Retained as an **optional ASA-facing reference**: ChordMiniApp is a real,
> MIT-licensed UX precedent for *presenting* chord analysis, relevant to how
> ASA could display its **existing Phase 1 chord detection** (`chordDetail.*`,
> `chroma`) — not to any reharmonization feature, which ASA does not have.
> The adopt/adapt/reject tables below were written against Harmonia's
> symbolic-first, client-side premise; against ASA's audio-first reality
> several calls change, so treat the tables as raw input requiring
> ASA-specific re-evaluation, not as decisions. Read "Harmonia" below as
> "the originally-assumed consumer."

### Source

- **URL:** https://github.com/ptnghia-j/ChordMiniApp
- **Language:** TypeScript (85.1%), Python (10.8%)
- **Stars:** 284
- **Creation date:** Not exposed without GitHub API auth; 424 commits on
  main, repo is active. First-commit date is checklist item under DoD.
- **License:** **MIT** ([verified — repo metadata; full LICENSE file
  confirmation is checklist item](https://github.com/ptnghia-j/ChordMiniApp))

### What to lift

**Reference-only.** Harmonia's stack (React + Tonal.js, symbolic) does
not adopt ChordMiniApp's stack (Next.js + Flask + Firebase, audio-first).
What transfers is **UX and architecture choices**, classified
adopt / adapt / reject below.

ChordMiniApp surfaces, from the README and docs index:

- **Beat & chord grid** with roman-numeral analysis, key-modulation
  signals, and song-segmentation labels (intro, verse, chorus, bridge,
  outro).
- **Interactive guitar chord diagrams** from
  [@tombatossals/chords-db](https://github.com/tombatossals/chords-db).
- **Piano visualizer** with real-time MIDI rendering and
  chord-playback sync; MIDI export.
- **Experimental melody transcription** (SheetSage) with separate
  playback and caching.
- **Lead sheet rendering** via
  [OpenSheetMusicDisplay](https://opensheetmusicdisplay.org/).
- **AI assistant** with synced lyrics ([LRClib](https://lrclib.net/))
  and Gemini-powered chatbot for analysis and translation.
- **YouTube integration** — direct URL input + YouTube search, with
  yt-dlp (local) or yt-mp3-go (production) extraction.

ChordMiniApp's architecture:

- **Frontend:** Next.js + TypeScript + Tailwind. Frontend BFF in
  `src/app/api/` (Next.js route handlers), main UI in `src/app/`.
- **Backend:** Flask, port 5001 (avoiding macOS AirPlay's 5000).
  Blueprints in `python_backend/`: health, beats (`/detect_beats`),
  chords (`/chord-recognition`), lyrics, docs, youtube, audio, debug.
- **ML models:** Chord-CNN-LSTM, BTC-SL, BTC-PL (chord recognition);
  Beat-Transformer + madmom (beat tracking); SheetSage (melody,
  experimental); Spleeter (optional source separation).
- **Persistence:** Firebase (Firestore + Cloud Storage) for auth,
  caching transcriptions, segmentation jobs, and audio file storage.
- **Containerization:** Docker with separate services for SongFormer
  (segmentation) and SheetSage (melody).

### Why

The discovery doc framed this as "the closest public neighbor to
Harmonia's product surface." The existing incorporation work for ASA
explicitly deferred all Harmonia consideration; this plan opens that
track without forcing Harmonia to adopt ChordMiniApp's stack.

What Harmonia gets from the reference review:

- **Real UX precedents** for chord-grid presentation, roman-numeral
  overlay, segmentation labels, key-modulation signaling — every one of
  which is a question Harmonia has to answer.
- **An architectural decision sample** for an audio-input feature, if
  Harmonia ever grows one. The Next.js + Flask split is one way to
  serve Tonal.js's pure-symbolic core with an optional audio-input
  service alongside.
- **A reference for what external services to integrate** —
  OpenSheetMusicDisplay for notation, chord-db for guitar diagrams,
  LRClib for lyrics, all permissively licensed.

### Approach

**Reference-only.** No code lift. Output: an architecture-and-UX review
doc inside Harmonia's repo, structured as adopt / adapt / reject per
surface and per architectural choice, mirroring the discipline of
[`docs/external-repo-review-2026-05-13.md`](../docs/external-repo-review-2026-05-13.md)'s
Track 3.

**Stack-fit reasoning.** Harmonia is React + Tonal.js, symbolic-first,
client-side. ChordMiniApp is Next.js + Flask + Firebase, audio-first,
server-side ML. The stacks have one thing in common: the React UI.
Everything else is incompatible by design. The only honest incorporation
is to look at *which user-facing surfaces are good ideas* and decide
whether Harmonia wants the same idea in its own stack.

### Adopt / Adapt / Reject — UX surfaces

| Surface | Decision | Rationale |
| --- | --- | --- |
| Chord grid with roman-numeral analysis overlay | **Adopt** | Tonal.js can do roman-numeral analysis natively — `Tonal.RomanNumeral.get(chord, key)`. Drop-in for Harmonia. |
| Key-modulation signals on the timeline | **Adopt** | Identifying modulations is exactly the analysis Harmonia exists to support; surface them as a first-class timeline event. |
| Song-segmentation labels (intro/verse/chorus/bridge/outro) on chord rows | **Adapt** | Harmonia is symbolic — section labels are user-provided or imported, not detected from audio. Adopt the *visual treatment*, source the data from the user's input. |
| Interactive guitar chord diagrams via chords-db | **Adopt** | chords-db is MIT, framework-agnostic data. Harmonia ships React components; integration is straightforward. |
| Piano visualizer with real-time MIDI rendering | **Adapt** | The visualizer surface is well-shaped; Harmonia's MIDI playback is symbolic-source (no audio capture needed). Use the visual layout, simplify the data path. |
| MIDI export | **Adopt** | Harmonia's audience overlaps DAW users. MIDI export is table-stakes. |
| Experimental melody transcription | **Reject** | Audio-input feature; out of Harmonia's symbolic scope unless audio-input gets added later. Park as future-state. |
| Lead-sheet rendering via OpenSheetMusicDisplay | **Adopt** | OSMD is MIT, MusicXML-driven, framework-agnostic. Harmonia can render a reharmonized progression as engraved notation with this dependency alone. |
| Synced lyrics via LRClib | **Reject for now** | LRClib is a useful service, but lyrics are tangential to reharmonization. Park. |
| Gemini-powered chatbot for analysis / translation | **Adapt cautiously** | Useful idea, but tying Harmonia to a single LLM provider is a product-architecture decision, not a UX choice. If adopted, build the interface model-agnostic from day one. |
| YouTube URL ingestion via yt-dlp | **Reject** | Audio-input feature; not Harmonia's lane. Same parking lot as melody transcription. |
| YouTube search | **Reject** | Out of scope and TOS-fraught (the prior review's Track 3 rejected the analogous endpoint in forever-jukebox for ASA on the same grounds). |

### Adopt / Adapt / Reject — architecture choices

| Choice | Decision | Rationale |
| --- | --- | --- |
| Next.js as the frontend framework (vs Harmonia's React + Vite or similar) | **Reject** | Stack swap for swap's sake. Tonal.js + React is sufficient; no SSR need motivates Next.js. |
| Frontend BFF layer (Next.js route handlers proxying Flask) | **Reject** unless audio-input lands | Harmonia is symbolic; the BFF pattern solves a problem (server-side ML) Harmonia doesn't have. |
| Firebase for auth + caching + file storage | **Reject** | A symbolic app of Harmonia's scope doesn't need server-side storage. If sharing/persistence becomes a feature, evaluate as its own product decision. |
| Flask backend in blueprints (health / beats / chords / …) | **Reject** | Audio-first; not Harmonia's shape. |
| Caching ML inference results in Firestore | **Reject** unless audio-input lands | Harmonia's symbolic results are cheap to recompute; no cache layer needed. |
| Docker with separated SongFormer / SheetSage services | **Reject** | Same reason — Harmonia has no ML services to separate. |
| Async polling pattern for long-running jobs (segmentationJobs collection) | **Adapt as a future pattern, not adopted now** | If Harmonia ever grows audio input, the polling shape mirrors ASA's prior-review Track 3 analysis (forever-jukebox), which converged on the same shape. Document the lineage. |

### Cross-check oracle

For Harmonia's chord-presentation outputs, **Plan 8 (chordonomicon)** is
the natural cross-check: take a chordonomicon-tokenized progression,
display it in Harmonia, assert the displayed roman numerals and section
labels match the dataset's annotations. The two plans compose: Plan 7
sets the UX bar; Plan 8 provides the ground truth.

### Definition of done

- [ ] Confirm MIT in ChordMiniApp's LICENSE file.
- [ ] Confirm ChordMiniApp's first-commit date for the Source line.
- [ ] One review doc (commit it to *Harmonia*, not ASA — this plan
      output is the input to Harmonia's incorporation backlog) titled
      `docs/external-ui-review-chordminiapp-2026-MM-DD.md` containing
      the two adopt / adapt / reject tables above with Harmonia-specific
      file pointers.
- [ ] An ADR per "adopt" row that requires a non-trivial dependency
      (chord-db, OpenSheetMusicDisplay, MIDI-export library).
- [ ] Decision recorded for the Gemini-vs-model-agnostic question
      (architecture-level decision, not a UX one).
- [ ] BACKLOG entry in Harmonia for the future audio-input branch with
      the "Reject for now" rows as the entry conditions.

### Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Harmonia adopts ChordMiniApp's *architecture* by accident (Next.js / Firebase / Flask split) | High | The Reject column in the architecture table is the explicit guardrail. Architecture is a separate decision from UX; treat them separately. |
| The Gemini chatbot becomes a load-bearing dependency before the model-agnostic decision is made | Medium | "Adapt cautiously" with the model-agnostic ADR up front. |
| OpenSheetMusicDisplay's MusicXML data path doesn't match Harmonia's internal model | Medium | Confirm via a short spike before committing to the Adopt decision. OSMD is MusicXML-driven; Tonal.js is JSON-objects. A converter exists in the ecosystem; verify maintenance status. |
| chord-db diagrams are aesthetically inconsistent with Harmonia's design system | Low | chord-db ships data, not styled components. Style is Harmonia's responsibility. |
| Reference-only is interpreted as "go look at the upstream and copy parts of it" rather than the discipline of adopt / adapt / reject | Medium | The DoD requires the *review doc* as the deliverable, not selectively copied code. The doc is the gating artifact. |

---

## Plan 8 — chordonomicon (ASA — re-scoped)

> **Re-scoped to ASA (2026-05-22).** Originally framed for the (phantom)
> Harmonia sibling — see the correction banner at the top of this file.
> Retained as an **optional ASA-facing reference**: chordonomicon is a real
> labeled chord-progression dataset that could serve as an **evaluation set
> for ASA's existing chord/key detection** (cross-checking `chordDetail.*`
> and `key` against labeled progressions) — not for a reharmonization model,
> which ASA does not build. The CC-BY-NC-4.0 license discipline below still
> applies. The adopt/adapt/reject table was written against Harmonia's
> premise and needs ASA-specific re-evaluation before action. Read "Harmonia"
> below as "the originally-assumed consumer."

### Source

- **URL:** https://github.com/spyroskantarelis/chordonomicon
- **Dataset URL:** https://huggingface.co/datasets/ailsntua/Chordonomicon
- **Language:** Python (79.4%) + Jupyter (20.6%) — for the preprocessing
  / training / eval scripts.
- **Stars:** 143
- **Creation date:** Not exposed without GitHub API auth; paper at
  arXiv:2410.22046 dates to October 2024. First-commit date is checklist
  item under DoD.
- **License:**
  - **Repo (scripts):** **Apache-2.0** ([verified — repo metadata](https://github.com/spyroskantarelis/chordonomicon)).
  - **HF dataset (the actual data):** **CC-BY-NC-4.0** (reported via HF
    listing; *direct fetch of the dataset card was auth-gated* — confirming
    on the card itself is checklist item 1 of DoD).
- **Citation requirement:** Kantarelis et al. (2024),
  [arXiv:2410.22046](https://arxiv.org/abs/2410.22046). Mandatory if the
  data is used.

### What to lift

Two distinct artifacts:

1. **The data.** 666,000+ song-level symbolic chord progressions,
   annotated with **structural parts** (verse / chorus / bridge / etc.),
   **genre**, **release date**, **Spotify IDs**, and **song
   identifiers** (the last used for stratified splitting). Primary file:
   `chordonomicon_v2.csv`.
2. **The encoding & preprocessing.** Three representations, written to
   `*.pkl` files by the upstream's `Chord_Embeddings.py`:
   - `chord`: single 0-indexed chord ID (`*_1token.pkl`).
   - `triad`: `[root_id, qualex_id, bass_id]` (`*_3tokens.pkl`).
   - `tetrad`: `[root_id, quality_id, extension_id, bass_id]`
     (`*_4tokens.pkl`).
   `vocabs.pkl` carries 20 lookup tables for chord↔index, root↔index,
   quality↔index, extensions↔index, bass↔index, qualex↔index, plus the
   inverse decoding maps and the composite 3-token / 4-token chord↔parts
   mappings.
3. **The split methodology.** "Songs are split by id — no song appears
   in more than one split," with stratification by section label;
   default 80% train / 10% val / 10% test, controlled by `--sample_size`.
4. **The baselines.** RNN, GRU, and LSTM architectures evaluated on
   next-chord prediction; the README notes "structural part annotations
   consistently improve prediction performance" but doesn't include the
   absolute accuracy numbers — those are in the arXiv paper.

### Why

Harmonia is a reharmonization tool. A reharmonization model — whether
a learned model or a hand-crafted rule set — needs:

- A **labeled benchmark** to evaluate against. "Did the reharm preserve
  the section's harmonic function?" is exactly what chordonomicon's
  per-section labels enable.
- A **shared encoding** so external models can be loaded and tested
  side-by-side with Harmonia's own logic. The triad / tetrad
  factorization is a sensible canonical shape for symbolic chords; it
  decomposes "Cmaj7/E" into (root=C, quality=maj7, extension=∅, bass=E),
  which is roughly how Tonal.js already thinks about chords.
- A **genre and release-date distribution** that exposes whether
  Harmonia's recommendations are universally applicable or genre-biased.
  The release-date field also lets the eval harness measure performance
  drift across eras.

ChordMiniApp (Plan 7) sets the UX bar for chord presentation;
chordonomicon (Plan 8) provides the ground truth those presentations
should be evaluated against. The plans compose.

### Approach

**Incorporate as a dependency.** Hugging Face `datasets` library;
load on demand in an eval harness; **do not vendor the data into
Harmonia's repository.**

Two integration paths, in order:

1. **Phase 8a — Evaluation harness.** A standalone scripts directory in
   Harmonia (`scripts/eval/chordonomicon/`) that loads the dataset via
   `datasets.load_dataset("ailsntua/Chordonomicon")`, runs Harmonia's
   reharmonization logic on each progression, and reports a precision /
   recall / next-chord-perplexity number against the published baselines
   from the arXiv paper. This is decoupled from Harmonia's app code;
   it lives next to it.
2. **Phase 8b — Section-aware tokenizer adoption.** Harmonia's own
   internal chord representation gets reviewed against the triad /
   tetrad shape. Adopt where the shapes match; adapt where they don't
   (Tonal.js's chord-object schema vs chordonomicon's
   `[root_id, qualex_id, bass_id]`). This is the smaller, schema-only
   piece.

**Stack-fit reasoning.** Hugging Face `datasets` is a Python dependency;
Harmonia is React + Tonal.js (JS). The eval harness lives Python-side
because the dataset tooling is Python-side. Harmonia itself stays JS;
the eval harness pulls Harmonia's reharmonization logic via a small
adapter (or, if Tonal.js's logic is JS-only and not portable, by
exporting the relevant logic to a small Node script that the Python
harness shells out to). This is the cleanest path; it does not require
a JS reimplementation of `datasets`.

### Adopt / Adapt / Reject — dataset encoding

| Encoding piece | Decision for Harmonia | Rationale |
| --- | --- | --- |
| 0-indexed chord IDs (`chord` representation) | **Reject** | Harmonia's internal model is symbolic-named (Tonal.js); a 0-indexed token table is a model-training convention, not a runtime convention. |
| Triad `[root_id, qualex_id, bass_id]` factorization | **Adopt as the eval-harness encoding** | The mapping to Tonal.js's `{root, quality, bass}` is straightforward; canonical shape is a benefit when comparing implementations. |
| Tetrad `[root_id, quality_id, extension_id, bass_id]` factorization | **Adopt as the eval-harness encoding** | Same reasoning. Extensions get their own slot; matches Tonal.js's separate handling of 7ths / extensions. |
| Genre field | **Adopt** | Cheap to carry; supports genre-stratified evaluation. |
| Release-date field | **Adopt** | Same — era-stratified eval is a useful sanity check on whether Harmonia is era-biased. |
| Spotify IDs | **Adapt — strip before any export** | Useful internally for joining; a privacy/attribution risk if exported back into Harmonia's persisted state. Don't store them. |
| Section labels (verse / chorus / bridge / outro / …) | **Adopt** | This is the unique value-add. Section-aware reharm is the headline capability the dataset enables. |
| 80/10/10 split methodology with song-id-based stratification | **Adopt for the eval harness** | Standard methodology. Don't change it; use the upstream's split if it's published, otherwise apply the same procedure with a documented random seed. |

### Cross-check oracle

The published RNN / GRU / LSTM baselines from the arXiv paper are
themselves the cross-check oracle: Harmonia's eval-harness result, on
the same split, against the same dataset, should be in a believable
range against published baselines. A second oracle, if available: an
independent chord-progression dataset (e.g. McGill Billboard,
Isophonics) — neither is in this discovery batch; pulling them is a
future spike.

### Definition of done

- [ ] **Confirm the HF dataset license on the dataset card itself**
      (CC-BY-NC-4.0 is reported via HF listing search; the card's YAML
      frontmatter is the canonical signal). If the actual license
      differs, this entire plan re-scopes.
- [ ] Confirm Apache-2.0 on the scripts repo's LICENSE file.
- [ ] Confirm the upstream's first-commit date for the Source line.
- [ ] Cite the paper (arXiv:2410.22046) in any code or doc that uses the
      dataset.
- [ ] Decide and record Harmonia's commercial posture (commercial /
      non-commercial / undecided) before going further. If commercial,
      Phase 8a is the *only* phase that runs — the data is loaded
      transiently in an eval harness, never shipped.
- [ ] `scripts/eval/chordonomicon/load.py` loads the dataset via HF
      `datasets`, with a `--sample_size` flag matching the upstream's.
- [ ] `scripts/eval/chordonomicon/eval.py` runs Harmonia's
      reharmonization on each test-split progression and reports a
      precision / recall / next-chord-perplexity number.
- [ ] One comparison row in the eval report against the arXiv paper's
      published RNN / GRU / LSTM baselines.
- [ ] An ADR in Harmonia recording: the eval harness exists, the data
      is not vendored, the commercial-posture decision, and the
      attribution string used in any output.

### Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| CC-BY-NC-4.0 misread as CC-BY (commercial-permitted) | **High** | Step 1 of the DoD is to read the card. Treat the value as a hard gate. |
| Harmonia goes commercial and the dataset is already embedded in product code | **High** | The "eval-harness-only" framing is the structural mitigation. The data is loaded at eval time, not shipped at build time. |
| Weights derived from CC-BY-NC-4.0 data ship inside a commercial Harmonia | **Medium** | The derivative-work question for NC datasets is debated. Treat conservatively: if Harmonia ever trains a model and ships weights, the model is *also* NC. Document in the ADR. |
| The Tonal.js → triad/tetrad mapping has lossy edge cases (e.g., slash chords with non-chord-tone bass, polychords) | Low–Medium | The eval-harness encoding is *adapted*, not adopted as-is. Edge cases are mapped with a documented fallback. |
| The arXiv baselines are not directly reproducible without the upstream's training scripts | Low | The repo's Apache-2.0 `Model_Training.py` + `Model_Evaluation.py` are reproducibility aids; cite them in the eval doc. |
| Spotify IDs are PII-adjacent or licensing-sensitive | Low | Don't store them; strip on load. |
| Dataset is auth-gated on HF (today the dataset card itself returned 403 to anonymous fetches) | Low–Medium | `datasets.load_dataset` typically handles HF auth via `HF_TOKEN`; document the token requirement in the eval doc. |

---

## Sequencing

Recommended pickup order by ROI (return = user value or risk reduction;
investment = engineer-days).

1. **Plan 5 — resonators.** ~1–2 days. Lowest friction; lowest risk;
   opens a new in-browser surface (live spectral preview) that ASA
   currently can't offer. Published WASM dependency; no toolchain
   burden; no measurement contract touched.
2. **Plan 4a — audio-analyzer-rs as cross-check oracle.** ~1–2 days.
   Directly serves PURPOSE.md Quality Invariant 1 (measurement
   authority). Pin a binary; run it in CI; surface drift. No
   user-visible UI change. Defer Plan 4b until and unless an in-browser
   DSP need shows up.
3. **Plan 6 — jivetalking pattern port.** ~3–4 days. Higher upside —
   directly improves Phase 2 specificity per PURPOSE.md Quality
   Invariant 3 (Ableton specificity) — but requires music-domain
   calibration of voice-tuned heuristics and a new validator. The
   payoff is recommendations that cite measurements *every time*, not
   just *most of the time*.
4. **Plan 7 — ChordMiniApp UX review for Harmonia.** ~2 days, but
   Harmonia-side and depends on Harmonia priorities. Pure reference
   work; output is a review doc, not code. Useful as the framing
   document before Harmonia takes its next UX bet.
5. **Plan 8 — chordonomicon eval harness for Harmonia.** ~3–4 days.
   Highest gating on the commercial-posture decision (CC-BY-NC-4.0).
   Once the posture is decided, the eval harness is a one-shot build;
   the benchmark then compounds as Harmonia's reharmonization logic
   evolves.

**Total estimated effort if all five adopted:** 10–14 working days,
dominated by Plans 6 and 8.

**Cross-plan dependencies:**

- Plan 5 ↔ Plan 4b: both Rust → WASM. Plan 5 is the cheap end state; Plan
  4b is gated on a need that doesn't exist today. Don't pre-fork.
- Plan 7 ↔ Plan 8: Plan 7 sets the chord-presentation UX bar; Plan 8
  evaluates against that bar with labeled ground truth. Compose.
- Plan 6 ↔ existing review's Track 1 (openmeters): Plan 6's measurement
  inputs come from ASA's existing Phase 1 (which Track 1's R128 spike
  confirmed correct), *not* from a new measurement layer. Plan 6 does
  not duplicate Track 1.

---

## Source note

The framing of each upstream's relevance comes from the
2026-05-13 / 2026-05-14 audio-MIR discovery passes (the
`routine-discoveries` repository referenced in the task brief — not
present in this checkout). The license / API / schema / dataset facts in
each plan come from direct fetches of the upstream repositories and the
Hugging Face dataset listing; where a fetch was auth-gated (the GitHub
REST API, the HF dataset card itself), this is called out inline and
made the first checklist item under the affected plan's Definition of
done. The house style — License Map up front, adopt / adapt / reject
tables, per-plan DoD, closing Sequencing section — mirrors
[`docs/external-repo-review-2026-05-13.md`](../docs/external-repo-review-2026-05-13.md),
which covers the three preceding tracks (openmeters, Partiels,
forever-jukebox) that this batch deliberately does not re-cover.

The "considered but not selected" bench for this batch — songsee,
EssentiaTD, AudioAuditor, clamp3 (ASA-leaning); rawl, noteDigger,
chromatone.center (Harmonia-leaning) — is held for a later batch and
not re-litigated here. If any of the five plans above turns out to be
a dead end on a deeper read (license shift, project archived,
mischaracterization), the bench is the natural replacement pool.
