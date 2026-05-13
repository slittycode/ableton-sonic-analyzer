# Track 1 verification spike outcome — 2026-05-13

**Scope:** verify the review's premise (in [`external-repo-review-2026-05-13.md`](external-repo-review-2026-05-13.md))
that ASA's existing loudness path is already correct on its operating
sample rate, so no port of openmeters' BS.1770-5 implementation is needed.

**Result (pending CI):** The added test
[`apps/backend/tests/test_loudness_r128.py`](../apps/backend/tests/test_loudness_r128.py)
exercises EBU Tech 3341 Cases 1 and 2 — the canonical sine-tone
conformance signals — through ASA's `analyze_loudness` at 44.1 kHz.
If those assert green, the premise check is positive and Track 1's
loudness-port subtrack closes with no algorithm work, per the review.

## What the spike verifies

Three procedurally-generated tests; no fixture downloads.

| Test | Signal | Expected integrated LUFS | Path under test |
| --- | --- | --- | --- |
| `test_case1_minus23_dbfs_sine_yields_minus23_lufs` | Stereo 1 kHz sine, -23 dB FS peak, 20 s @ 44.1 kHz | -23.0 ±0.1 | `analyze_core.analyze_loudness(stereo)` |
| `test_case2_minus33_dbfs_sine_yields_minus33_lufs` | Stereo 1 kHz sine, -33 dB FS peak, 20 s @ 44.1 kHz | -33.0 ±0.1 | `analyze_core.analyze_loudness(stereo)` |
| `test_case1_at_48khz_with_explicit_sample_rate` | Stereo 1 kHz sine, -23 dB FS peak, 20 s @ 48 kHz | -23.0 ±0.1 | `es.LoudnessEBUR128(sampleRate=48000)` directly |

The third test calls Essentia directly with the sample rate threaded
through. It separates "algorithm correct at non-44.1 rates" from "ASA's
call site threads sample rate." If it passes, Essentia's algorithm is
fine at 48 kHz when given the right sample rate; the call-site question
is then orthogonal to BS.1770 compliance.

## ~~Open finding~~ Resolved: sample-rate threading in `analyze_loudness`

**Resolution:** fixed in a follow-up PR on branch
`claude/fix-loudness-sample-rate-5XA5r`. `analyze_loudness` now takes
`sample_rate: int = 44_100`; the full pipeline at `analyze.py:1503`
threads `sr` from `load_stereo`; the stem path at `analyze.py:1242`
hardcodes 44_100 (matching Demucs's stem write rate, which is independent
of the source). A new regression test
`TestLoudnessR128ThroughAnalyzeLoudnessAt48kHz` in
`tests/test_loudness_r128.py` asserts -23.0 ±0.1 LUFS through
`analyze_loudness` at 48 kHz.

The original finding is preserved below for context.

---


While tracing the loudness path, the spike surfaced an asymmetry between
ASA's two call sites for `LoudnessEBUR128`:

- [`analyze_core.py:197`](../apps/backend/analyze_core.py) — `analyze_loudness(stereo)` instantiates `es.LoudnessEBUR128()` with **no** `sampleRate` argument (Essentia's default is 44100).
- [`analyze_fast.py:100`](../apps/backend/analyze_fast.py) — `analyze_fast` instantiates `es.LoudnessEBUR128(sampleRate=sample_rate)` with the actual sample rate.

The full pipeline (`analyze.py:1448`) loads stereo via `load_stereo`, which
preserves the **source file's native sample rate** (no upstream resample).
So any source that isn't already 44.1 kHz — e.g. a 48 kHz FLAC reference
track — gets its loudness measured against K-weighting filters tuned for
44.1 kHz. For BS.1770's K-filter, this is small at 1 kHz but grows with
frequency; the resulting integrated-LUFS error on broadband program
material is bounded but non-zero.

This is **not** an algorithm bug. It is a call-site bug. It does not
invalidate the spike — the verification tests run at 44.1 kHz precisely
because that is `analyze_loudness`'s assumption, so they probe ASA's
actual operating point. But it is worth fixing in a separate, small PR:

```python
# apps/backend/analyze_core.py
def analyze_loudness(stereo: np.ndarray, sample_rate: int = 44_100) -> dict:
    ...
    loudness = es.LoudnessEBUR128(sampleRate=sample_rate)
    ...
```

Plus call-site updates at `analyze.py:1242` (stem analysis path),
`analyze.py:1497` (full pipeline), and any other invocation.

I deliberately did not include the fix in this spike PR — the spike's
scope per the user's selection was "verify only." Filed as a follow-up.

## What this means for the review's Track 1

Assuming both 44.1 kHz tests pass:

- [ ] Cancel the openmeters port. The review already rejected that on
      license, premise, and runtime-target grounds; this verification is
      the empirical close-out.
- [x] Keep this regression test in place as the loudness-correctness gate.
- [ ] File the sample-rate threading fix as a separate small PR.
- [ ] Consider `librosa.reassigned_spectrogram` as a separate ~1-day add
      for sharper spectrograms (unchanged from the review's recommendation).
