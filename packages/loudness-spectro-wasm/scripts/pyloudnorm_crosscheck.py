#!/usr/bin/env python3
"""Independent second-implementation cross-check for asa-dsp loudness.

Runs every ``*.wav`` in a corpus directory through BOTH:
  1. pyloudnorm (ITU-R BS.1770 integrated loudness, a separate codebase), and
  2. the native ``measure-cli`` binary (this package's asa-dsp path),
then asserts the integrated-LUFS readings agree within 0.5 LU.

This is a dev/CI helper, NOT a hard gate: no corpus is committed (the absolute
EBU targets in crates/asa-dsp/tests/ebu_conformance.rs are the committed gate).
Point it at your own WAVs, or at the official EBU set fetched via
scripts/fetch-ebu-testset.sh.

Setup:
    pip install pyloudnorm soundfile numpy
    cargo build -p measure-cli --release      # or: npm run build:cli

Usage:
    python scripts/pyloudnorm_crosscheck.py <corpus-dir>

Exit code is non-zero if any file breaches the 0.5 LU tolerance, the binary is
missing, or no WAVs are found.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    import pyloudnorm  # type: ignore
    import soundfile  # type: ignore
except ImportError as exc:  # pragma: no cover - environment guard
    sys.exit(
        f"missing dependency: {exc.name}. "
        "Install with: pip install pyloudnorm soundfile numpy"
    )

# asa-dsp's reading must track pyloudnorm within this many LU.
TOLERANCE_LU = 0.5

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
MEASURE_CLI = PACKAGE_ROOT / "target" / "release" / "measure-cli"


def measure_cli_integrated(wav: Path) -> float:
    """Run measure-cli and return its integrated LUFS (raises on null)."""
    proc = subprocess.run(
        [str(MEASURE_CLI), str(wav)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout.strip())
    value = payload.get("integrated")
    if value is None:
        raise ValueError(f"measure-cli returned null integrated for {wav.name}")
    return float(value)


def pyloudnorm_integrated(wav: Path) -> float:
    data, rate = soundfile.read(str(wav))  # native rate, no resampling
    meter = pyloudnorm.Meter(rate)
    return float(meter.integrated_loudness(data))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2

    corpus = Path(argv[1])
    if not corpus.is_dir():
        sys.exit(f"not a directory: {corpus}")
    if not MEASURE_CLI.exists():
        sys.exit(
            f"measure-cli not built at {MEASURE_CLI}\n"
            "Build it first: cargo build -p measure-cli --release  (or npm run build:cli)"
        )

    wavs = sorted(corpus.glob("*.wav"))
    if not wavs:
        sys.exit(f"no *.wav files found in {corpus}")

    print(f"{'file':<40} {'pyloudnorm':>12} {'measure-cli':>12} {'Δ LU':>8}  status")
    print("-" * 84)

    failures = 0
    for wav in wavs:
        try:
            ours = measure_cli_integrated(wav)
            theirs = pyloudnorm_integrated(wav)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"{wav.name:<40} {'ERROR':>12} {'ERROR':>12} {'':>8}  {exc}")
            failures += 1
            continue

        delta = ours - theirs
        ok = abs(delta) < TOLERANCE_LU
        failures += not ok
        print(
            f"{wav.name:<40} {theirs:>12.4f} {ours:>12.4f} "
            f"{delta:>+8.4f}  {'ok' if ok else 'FAIL'}"
        )

    print("-" * 84)
    print(
        f"{len(wavs)} file(s), {failures} breach(es) "
        f"(tolerance ±{TOLERANCE_LU} LU)"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
