#!/usr/bin/env python3
"""asa-dsp ↔ Essentia loudness parity harness (WS3a checkpoint).

ASA's authoritative Phase 1 loudness comes from Essentia (``LoudnessEBUR128`` /
``TruePeakDetector``). The ``packages/loudness-spectro-wasm`` core (``asa-dsp``,
an openmeters-derived BS.1770-5 / EBU R128 implementation) is a *candidate*
second source — the same Rust that compiles to WASM. Before we wire it into
either app (WS3b backend, WS3c browser readout) it has to agree with Essentia,
because Phase 1 measurements are ground truth (PURPOSE.md invariant #1) and a
loudness backend that disagrees would silently corrupt that truth.

This harness runs a shared corpus through BOTH paths at each file's NATIVE rate
(no resampling — that alone breaks ±0.1 LU EBU conformance) and reports the
deltas:

  * asa-dsp side: the native ``measure-cli`` binary (source-identical to the
    WASM core; per the plan, WS3a needs no wasm toolchain).
  * Essentia side: ``es.AudioLoader`` → ``es.LoudnessEBUR128`` exactly as
    ``apps/backend/analyze_core.analyze_loudness`` does, plus a dBTP true peak
    from ``es.TruePeakDetector`` (converted ``20·log10`` to match asa-dsp).

Primary gate: **integrated LUFS within ±0.1 LU on every file.** That is the
hard checkpoint — if it fails, WS3b/WS3c are aborted (Essentia stays the only
loudness source). Short-term max, momentary max, LRA and true peak are reported
as secondary signals, not gated.

The corpus is synthetic and generated deterministically (fixed seed), so no
audio is committed — broadband noise stresses the K-weighting filter, where two
independent BS.1770 implementations are most likely to drift.

Setup (run with a Python that has Essentia — i.e. the backend venv):
    apps/backend/venv/bin/python packages/loudness-spectro-wasm/scripts/essentia_parity.py
    # build the asa-dsp side first:
    cargo build -p measure-cli --release   # (or: npm run build:cli)

Usage:
    essentia_parity.py [--corpus DIR] [--report PATH] [--keep-corpus] [--tolerance LU]

With no ``--corpus`` a deterministic synthetic corpus is generated in a temp
dir. ``--report`` writes the markdown report (default: docs/essentia-parity-report.md
inside the package). Exit code is non-zero if any file breaches the integrated
tolerance, the binary is missing, or the corpus is empty.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np

try:
    import soundfile as sf  # type: ignore
    import essentia.standard as es  # type: ignore
except ImportError as exc:  # pragma: no cover - environment guard
    sys.exit(
        f"missing dependency: {exc.name}. Run with a Python that has Essentia "
        "and soundfile (the backend venv: apps/backend/venv/bin/python)."
    )

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
MEASURE_CLI = PACKAGE_ROOT / "target" / "release" / "measure-cli"
DEFAULT_REPORT = PACKAGE_ROOT / "docs" / "essentia-parity-report.md"

# Primary parity gate: integrated LUFS must track Essentia within this many LU.
INTEGRATED_TOLERANCE_LU = 0.1

# Synthetic-corpus geometry. 48 kHz is the EBU reference rate; 12 s comfortably
# clears LoudnessEBUR128's 400 ms momentary / 3 s short-term gating windows.
CORPUS_SR = 48_000
CORPUS_SECONDS = 12.0
CORPUS_SEED = 0xA5A_D5

# ── Synthetic signal generators (deterministic) ───────────────────────────────


def _peak_normalize(x: np.ndarray, peak: float) -> np.ndarray:
    m = float(np.max(np.abs(x)))
    return x * (peak / m) if m > 0 else x


def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f (pink) noise via spectral shaping of white noise."""
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.arange(spectrum.size, dtype=np.float64)
    freqs[0] = 1.0  # avoid div-by-zero at DC
    spectrum /= np.sqrt(freqs)
    out = np.fft.irfft(spectrum, n=n)
    return _peak_normalize(out, 1.0)


def _log_sweep(n: int, sr: int, f0: float = 20.0, f1: float = 20_000.0) -> np.ndarray:
    """Exponential (log) sine sweep f0→f1."""
    t = np.arange(n) / sr
    duration = n / sr
    k = (f1 / f0) ** (1.0 / duration)
    phase = 2.0 * np.pi * f0 * ((k**t - 1.0) / math.log(k))
    return np.sin(phase)


def _sine(n: int, sr: int, freq: float) -> np.ndarray:
    return np.sin(2.0 * np.pi * freq * np.arange(n) / sr)


def generate_corpus(out_dir: Path) -> list[Path]:
    """Write the deterministic synthetic corpus as 24-bit WAVs; return paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    n = int(CORPUS_SR * CORPUS_SECONDS)
    rng = np.random.default_rng(CORPUS_SEED)

    def stereo(left: np.ndarray, right: np.ndarray | None = None) -> np.ndarray:
        right = left if right is None else right
        return np.column_stack([left, right]).astype(np.float64)

    # Draw all randomness up front in a fixed order so the corpus is stable.
    pink_a = _pink(n, rng)
    pink_l = _pink(n, rng)
    pink_r = _pink(n, rng)
    white = _peak_normalize(rng.standard_normal(n), 1.0)

    signals: dict[str, np.ndarray] = {
        # Tonal references — K-weighting gain is small and well-defined here.
        "sine_1k": stereo(_peak_normalize(_sine(n, CORPUS_SR, 1_000.0), 0.5)),
        "hot_sine_3k": stereo(_peak_normalize(_sine(n, CORPUS_SR, 3_000.0), 0.95)),
        "quiet_sine_1k": stereo(_peak_normalize(_sine(n, CORPUS_SR, 1_000.0), 0.03)),
        "two_tone_100_3k": stereo(
            _peak_normalize(
                _sine(n, CORPUS_SR, 100.0) + _sine(n, CORPUS_SR, 3_000.0), 0.7
            )
        ),
        # Broadband — where two BS.1770 implementations diverge most.
        "pink_noise": stereo(_peak_normalize(pink_a, 0.7)),
        "white_noise": stereo(_peak_normalize(white, 0.5)),
        "stereo_decorrelated_pink": stereo(
            _peak_normalize(pink_l, 0.7), _peak_normalize(pink_r, 0.7)
        ),
        "log_sweep_20_20k": stereo(_peak_normalize(_log_sweep(n, CORPUS_SR), 0.7)),
    }

    paths: list[Path] = []
    for name, data in signals.items():
        wav = out_dir / f"{name}.wav"
        sf.write(str(wav), data, CORPUS_SR, subtype="PCM_24")
        paths.append(wav)
    return paths


# ── Measurement (the two paths) ───────────────────────────────────────────────


def measure_asa_dsp(wav: Path) -> dict:
    """asa-dsp loudness via the native measure-cli binary."""
    proc = subprocess.run(
        [str(MEASURE_CLI), str(wav)], capture_output=True, text=True, check=True
    )
    return json.loads(proc.stdout.strip())


def _linear_to_dbtp(peak_linear: float) -> float | None:
    return 20.0 * math.log10(peak_linear) if peak_linear > 0.0 else None


def measure_essentia(wav: Path) -> dict:
    """Essentia loudness, mirroring apps/backend/analyze_core.analyze_loudness.

    AudioLoader decodes at the file's native rate (no resample); LoudnessEBUR128
    is fed the same Nx2 array the backend uses. True peak is the per-channel max
    from TruePeakDetector, converted to dBTP to match asa-dsp's units.
    """
    audio, sr, _channels, _md5, _bitrate, _codec = es.AudioLoader(filename=str(wav))()
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = np.column_stack([audio, audio])
    elif audio.shape[1] == 1:
        audio = np.column_stack([audio[:, 0], audio[:, 0]])

    momentary, short_term, integrated, lra = es.LoudnessEBUR128(sampleRate=sr)(audio)
    momentary = np.asarray(momentary, dtype=np.float64)
    short_term = np.asarray(short_term, dtype=np.float64)

    def _finite_max(arr: np.ndarray) -> float | None:
        finite = arr[np.isfinite(arr)]
        return float(np.max(finite)) if finite.size else None

    detector = es.TruePeakDetector(sampleRate=int(sr))
    peaks: list[float] = []
    for ch in range(audio.shape[1]):
        _oversampled, peak_value = detector(audio[:, ch])
        if hasattr(peak_value, "__len__"):
            peaks.append(float(np.max(peak_value)) if len(peak_value) else 0.0)
        else:
            peaks.append(float(peak_value))
    true_peak_dbtp = _linear_to_dbtp(max(peaks)) if peaks else None

    return {
        "integrated": float(integrated) if math.isfinite(integrated) else None,
        "momentaryMax": _finite_max(momentary),
        "shortTermMax": _finite_max(short_term),
        "truePeak": true_peak_dbtp,
        "lra": float(lra) if math.isfinite(lra) else None,
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

METRICS = [
    ("integrated", "Integrated LUFS"),
    ("shortTermMax", "Short-term max LUFS"),
    ("momentaryMax", "Momentary max LUFS"),
    ("lra", "LRA (LU)"),
    ("truePeak", "True peak dBTP"),
]


def _delta(ours: float | None, theirs: float | None) -> float | None:
    if ours is None or theirs is None:
        return None
    return ours - theirs


def _fmt(v: float | None, places: int = 2) -> str:
    return "null" if v is None else f"{v:.{places}f}"


def build_report(rows: list[dict], tolerance: float) -> tuple[str, bool]:
    """Render the markdown report; return (text, passed)."""
    worst_integrated = 0.0
    breaches: list[str] = []
    for row in rows:
        d = _delta(row["asa"].get("integrated"), row["ess"].get("integrated"))
        if d is None:
            breaches.append(f"{row['name']} (null integrated)")
            continue
        worst_integrated = max(worst_integrated, abs(d))
        if abs(d) > tolerance:
            breaches.append(f"{row['name']} (Δ {d:+.3f} LU)")
    passed = not breaches

    lines: list[str] = []
    lines.append("# asa-dsp ↔ Essentia loudness parity report")
    lines.append("")
    lines.append(f"_Generated {date.today().isoformat()} by "
                 "`scripts/essentia_parity.py` (WS3a checkpoint)._")
    lines.append("")
    verdict = "✅ PASS" if passed else "❌ FAIL"
    lines.append(f"**Verdict: {verdict}** — primary gate is integrated LUFS "
                 f"within ±{tolerance} LU on every file.")
    lines.append("")
    lines.append(f"- Worst integrated delta: **{worst_integrated:.3f} LU** "
                 f"(tolerance ±{tolerance}).")
    lines.append(f"- Corpus: {len(rows)} deterministic synthetic signal(s) "
                 f"@ {CORPUS_SR} Hz, {CORPUS_SECONDS:g}s stereo (seed "
                 f"0x{CORPUS_SEED:X}).")
    if breaches:
        lines.append(f"- Breaches: {', '.join(breaches)}.")
    lines.append("")
    lines.append("## Integrated LUFS (the gate)")
    lines.append("")
    lines.append("| file | Essentia | asa-dsp | Δ (asa−ess) | status |")
    lines.append("|---|---:|---:|---:|---|")
    for row in rows:
        ess = row["ess"].get("integrated")
        asa = row["asa"].get("integrated")
        d = _delta(asa, ess)
        status = (
            "ok" if d is not None and abs(d) <= tolerance
            else "FAIL" if d is not None else "null"
        )
        dd = "null" if d is None else f"{d:+.3f}"
        lines.append(f"| {row['name']} | {_fmt(ess)} | {_fmt(asa)} | {dd} | {status} |")
    lines.append("")
    lines.append("## Secondary metrics (reported, not gated)")
    lines.append("")
    header = "| file | " + " | ".join(label for _k, label in METRICS[1:]) + " |"
    lines.append(header)
    lines.append("|---|" + "---:|" * (len(METRICS) - 1))
    for row in rows:
        cells = [row["name"]]
        for key, _label in METRICS[1:]:
            d = _delta(row["asa"].get(key), row["ess"].get(key))
            cells.append(
                f"{_fmt(row['ess'].get(key))} / {_fmt(row['asa'].get(key))} "
                f"(Δ {('null' if d is None else f'{d:+.2f}')})"
            )
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("> Cells show `Essentia / asa-dsp (Δ asa−ess)`. True peak is "
                 "converted from Essentia's linear TruePeakDetector output via "
                 "`20·log10` to match asa-dsp's dBTP; it is a sanity signal, not "
                 "a gate.")
    lines.append("")
    lines.append("## Method & caveats")
    lines.append("")
    lines.append("- Both paths decode each WAV at its **native rate** with no "
                 "resampling. Essentia uses `AudioLoader` → `LoudnessEBUR128` "
                 "(identical to `analyze_core.analyze_loudness`); asa-dsp uses "
                 "the `measure-cli` binary (source-identical to the WASM core).")
    lines.append("- The corpus is **synthetic** (tones, sweep, white/pink noise, "
                 "decorrelated stereo). Broadband noise is the most demanding "
                 "case for K-weighting agreement; tones are easy. Real-program "
                 "parity should be re-confirmed before flipping any default.")
    lines.append("- This is the WS3a checkpoint. A PASS clears WS3b/WS3c to "
                 "proceed *behind a default-off flag*; the loudness default only "
                 "flips to asa-dsp after real-program parity is also proven.")
    lines.append("")
    return "\n".join(lines), passed


# ── Entry point ───────────────────────────────────────────────────────────────


def run(corpus: list[Path], tolerance: float) -> tuple[list[dict], bool]:
    rows: list[dict] = []
    for wav in corpus:
        asa = measure_asa_dsp(wav)
        ess = measure_essentia(wav)
        rows.append({"name": wav.stem, "asa": asa, "ess": ess})
    _text, passed = build_report(rows, tolerance)
    return rows, passed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="asa-dsp ↔ Essentia loudness parity.")
    parser.add_argument("--corpus", type=Path, default=None,
                        help="directory of *.wav (default: generate synthetic corpus)")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT,
                        help=f"markdown report path (default: {DEFAULT_REPORT})")
    parser.add_argument("--keep-corpus", action="store_true",
                        help="keep the generated synthetic corpus instead of a temp dir")
    parser.add_argument("--tolerance", type=float, default=INTEGRATED_TOLERANCE_LU,
                        help=f"integrated-LUFS gate in LU (default: {INTEGRATED_TOLERANCE_LU})")
    args = parser.parse_args(argv[1:])

    if not MEASURE_CLI.exists():
        sys.exit(
            f"measure-cli not built at {MEASURE_CLI}\n"
            "Build it first: cargo build -p measure-cli --release  (or npm run build:cli)"
        )

    tmp: tempfile.TemporaryDirectory | None = None
    if args.corpus is not None:
        if not args.corpus.is_dir():
            sys.exit(f"not a directory: {args.corpus}")
        corpus = sorted(args.corpus.glob("*.wav"))
    elif args.keep_corpus:
        corpus = generate_corpus(PACKAGE_ROOT / "target" / "parity-corpus")
    else:
        tmp = tempfile.TemporaryDirectory(prefix="asa-parity-")
        corpus = generate_corpus(Path(tmp.name))

    if not corpus:
        sys.exit("no *.wav files in corpus")

    try:
        rows, passed = run(corpus, args.tolerance)
    finally:
        if tmp is not None:
            tmp.cleanup()

    text, passed = build_report(rows, args.tolerance)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(text, encoding="utf-8")

    # Console summary.
    print(f"{'file':<28} {'Essentia':>10} {'asa-dsp':>10} {'Δ LU':>9}  status")
    print("-" * 70)
    worst = 0.0
    for row in rows:
        ess = row["ess"].get("integrated")
        asa = row["asa"].get("integrated")
        d = _delta(asa, ess)
        if d is not None:
            worst = max(worst, abs(d))
        ds = "null" if d is None else f"{d:+.3f}"
        ok = "ok" if (d is not None and abs(d) <= args.tolerance) else "FAIL"
        print(f"{row['name']:<28} {_fmt(ess):>10} {_fmt(asa):>10} {ds:>9}  {ok}")
    print("-" * 70)
    print(f"{len(rows)} file(s); worst integrated Δ = {worst:.3f} LU "
          f"(±{args.tolerance}); verdict: {'PASS' if passed else 'FAIL'}")
    print(f"report written to {args.report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
