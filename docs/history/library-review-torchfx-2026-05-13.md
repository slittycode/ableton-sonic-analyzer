# Library review — `matteospanio/torchfx`

**Date:** 2026-05-13
**Reviewer:** automated audit on `claude/review-torchfx-inspiration-LpSZq`
**Verdict:** **Do not adopt as a dependency.** Borrow the API ergonomics if a future GPU batched-filter pass is ever justified.

---

## What torchfx is

- PyTorch-native audio DSP. All filters subclass `torch.nn.Module`, so they participate in autograd and ride PyTorch's device placement.
- Composition via overloaded operators: `wave | f1 | f2` for sequential, `f1 + f2` for parallel-then-mix.
- `Wave` object carries a sample-rate (`.fs`) alongside the tensor, with `Wave.from_file()` / `.save()` (soundfile-backed).
- Filter inventory is **thin**: `LoButterworth`, `HiButterworth` (implied/example), `ParametricEQ`. No MIR, no loudness, no onset/key/BPM, no spectrogram primitives.
- Created March 2025, 12 releases, 205 commits, arXiv companion paper (2504.08624). Active but young.
- **License: GPL v3.**
- Deps: torch, numpy, scipy, soundfile. Python ≥ 3.10.

## What ASA does in this neighborhood

ASA's Phase 1 currently lives in Essentia + scipy + librosa. Specifically the spots that look like "filters as nn.Modules" would touch:

| Site | What it does | How |
|---|---|---|
| `analyze_detection.py:38` `_bandpass_signal` | 4th-order Butterworth bandpass for per-band RT60 (`_REVERB_BANDS`, 4 octave bands). | `scipy.signal.butter(... output="sos")` + `sosfiltfilt`. |
| `analyze_detection.py:97-120` `analyze_per_band_transient_density` | 7-band bandpass → `librosa.onset.onset_strength` for hi-hat / kick density across spectralBalance bands. | Same scipy SOS pipeline, then librosa per band. |
| `analyze_core.py:894-903` | Per-band stereo bandpass via Essentia's `BandPass`. | Essentia's IIR bandpass, applied L/R. |
| `analyze_detection.py:481+, ~554` | Bandpass before envelope follower for effects detail. | Same scipy bandpass path. |

Total ≈11 bandpasses per analysis run, each over a single mono (or stereo-paired) numpy array. The audio is bounded above by the 100 MiB upload cap.

## Where torchfx's pattern *could* help

If — and only if — these per-band passes ever become a visible cost driver:

1. **Batched filter bank.** Today's 7-band transient-density pass is a serial Python loop of `sosfiltfilt`. A torchfx-style `BatchedFilterBank` (one `nn.Module` that stacks `(n_bands, sos)` and dispatches `torchaudio.functional.lfilter` across the batch dim) collapses 7 CPU passes into one GPU launch. The audio already lives on GPU during Demucs in `analyze_transcription.py` — re-using that device placement instead of round-tripping through numpy is the actual win, not the GPU itself.
2. **Stem-time co-location.** Demucs writes tensors on GPU. The current Layer-1 stem analysis pulls them back to CPU/numpy for Essentia+scipy. A torchaudio-based per-stem feature pass would keep the device. Borrowing torchfx's `Wave(tensor, fs, device)` carrier — *not* the class — is what makes that ergonomic.
3. **Readability.** `mono | hp(20) | lp(8000) | onset_env` reads better than four explicit numpy intermediates. The `|`/`+` overloading is the one piece of torchfx's API that's worth stealing wholesale if any of the above lands.

## Why we should *not* depend on torchfx

1. **License incompatibility.** ASA is MIT (`/LICENSE`). torchfx is GPL v3. Linking torchfx into the backend forces the combined work to GPL v3 on redistribution. This is a one-way door against any future hosted/commercial path and against permissive contributions back to ASA. **This is the blocking issue.** The next four are secondary.
2. **Filter inventory is too sparse to matter.** Two filter primitives shipped. ASA would write its own Butterworth bandpass anyway; the only thing borrowed would be `nn.Module` plumbing — which is a 30-line wrapper around `torchaudio.functional.lfilter`.
3. **Differentiability is unused.** ASA's filters are analysis tools, not training targets. Autograd through the filter is dead weight.
4. **No MIR/loudness offset.** torchfx does not replace any Essentia path. It is strictly upstream of measurement (signal conditioning), not a measurement tool itself.
5. **Quality invariant friction.** PURPOSE invariant #1: "Phase 1 measurements are ground truth." Switching the bandpass implementation under existing measurements (subBass, lowBass, …, brilliance) changes filter phase / transient response and would shift downstream onset counts and RT60 fits. Any swap needs a snapshot-diff regression test (`EXPECTED_TOP_LEVEL_KEYS` is not enough — values change, not keys).

## Concrete recommendation

**Do nothing in the dependency graph.** Keep Essentia + scipy as-is. The 11-bandpass-per-run cost is invisible next to Demucs and Phase 2 latency. Working the chain of custody is the higher-leverage path.

**If — at some future point — a profile shows per-band filtering is a top-three Phase 1 cost on long tracks:**

- Add `apps/backend/dsp_utils.py::TorchFilterBank` as a thin internal class. ~50 LOC. Stack SOS coefficients as `(n_bands, n_sections, 6)`, dispatch via `torchaudio.functional.lfilter`, return `(n_bands, n_samples)` tensor.
- Adopt the `|` operator for chains only if it lands in a hot loop. Avoid `+` (parallel-mix) — ASA does not mix bands back together; it analyzes each separately.
- Place the new module behind a feature flag so the scipy path remains the snapshot-test baseline. Diff old vs new outputs on a representative corpus before flipping the default.
- Do *not* import torchfx. Implement the pattern, not the library.

## Borrowed-pattern checklist (for when/if we ever do this)

1. Filters carry their own `fs` so callers don't pass it at every call site. (torchfx convention; correct.)
2. Filters are stateless once constructed; coefficients are buffers (`register_buffer`), not parameters. (Avoids accidental autograd attachment in eval contexts.)
3. The carrier object holds `(tensor, fs, device)` not `(np.ndarray, fs)`. The device field is what enables co-location with Demucs.
4. Operators wrap explicit method calls, not the other way around — `wave | filt` should be `filt.forward(wave)`. Keeps the call graph debuggable.
5. Round-trip parity test against scipy baseline before swapping any production code path.

## Bottom line

torchfx is a reasonable proof of concept for a pattern. It is not a dependency we should take, and the pattern itself only pays off if and when per-band CPU filtering becomes a measured bottleneck. Until then: file under "library to remember, not library to install."
