"""A/B separation harness — EVAL / RESEARCH ONLY.

Compares the default Demucs separation backend against the optional MSST backend
(``ASA_SEPARATION_BACKEND=msst``) on separation quality and runtime. This module
is intentionally separate from ``analyze.py`` and ``server.py`` — deleting it
restores the product exactly.

Two complementary signals, because there is no honest SDR on real tracks without
ground-truth isolated stems (which we can't bundle — copyright):

1. **Synthetic smoke-test (always available).** A deterministic synthetic
   multitrack with KNOWN stems (sine/sub bass, click drums, chord pad -> other,
   formant vocal) is summed to a mix, separated by both backends, and scored with
   gain-aligned SI-SDR against the known stems. This is a PLUMBING / SANITY check
   — "did each backend produce non-silent, correctly-named, roughly-correct-energy
   stems on a known input" — NOT a real-music quality ranking. BS-RoFormer/SCNet
   are trained on real spectra and can score poorly on toy synthetic sources, so
   the synthetic SDR must not be read as "Demucs is better than MSST". The harness
   carries this caveat in its report.

2. **Real-track reference-free proxies (optional, ``-i``).** On real audio with no
   reference stems we report per-stem RMS/peak/spectral-centroid, the
   mix-reconstruction residual (sum of stems vs mix), and cross-backend deltas.
   These measure self-consistency and plausibility, not correctness — but they're
   the more trustworthy signal for a real Demucs-vs-MSST comparison.

Runtime is reported as end-to-end wall-clock per backend (the cost the product
actually pays — neither backend caches the model across calls), after a warm-up
pass, taking the min over repeats, with the device recorded.
"""

from __future__ import annotations

import math
import os
import tempfile
import time
import wave
from typing import Any

import numpy as np

SAMPLE_RATE = 44100
_CANONICAL_STEMS = ("vocals", "bass", "drums", "other")


# --------------------------------------------------------------------------- #
# Synthetic multitrack with known stems
# --------------------------------------------------------------------------- #
def build_synthetic_multitrack(seconds: float = 6.0) -> dict[str, np.ndarray]:
    """Return KNOWN mono stems keyed by canonical name (deterministic).

    The sources are deliberately simple and well-separated in frequency so a
    working separator can recover them; they are NOT a substitute for real music.
    """
    n = int(seconds * SAMPLE_RATE)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    rng = np.random.default_rng(20260603)

    # Bass: 55 Hz sine + 110 Hz harmonic.
    bass = 0.5 * np.sin(2 * np.pi * 55.0 * t) + 0.2 * np.sin(2 * np.pi * 110.0 * t)

    # Drums: periodic noise bursts (a 2 Hz "kick" of decaying white noise).
    drums = np.zeros(n)
    burst_period = SAMPLE_RATE // 2
    burst_len = SAMPLE_RATE // 8
    env = np.exp(-np.linspace(0, 8, burst_len))
    for start in range(0, n - burst_len, burst_period):
        drums[start : start + burst_len] += rng.standard_normal(burst_len) * env * 0.6

    # Other (pad): a sustained major triad in the mid range.
    pad = sum(
        0.18 * np.sin(2 * np.pi * f * t) for f in (261.63, 329.63, 392.0)
    )

    # Vocals: a formant-ish tone (440 Hz carrier with 5 Hz vibrato + 2nd formant).
    vibrato = 1.0 + 0.01 * np.sin(2 * np.pi * 5.0 * t)
    vocals = 0.35 * np.sin(2 * np.pi * 440.0 * t * vibrato) + 0.12 * np.sin(
        2 * np.pi * 1200.0 * t
    )

    return {
        "bass": bass.astype(np.float32),
        "drums": drums.astype(np.float32),
        "other": pad.astype(np.float32),
        "vocals": vocals.astype(np.float32),
    }


def _write_stereo_wav(path: str, mono: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    data = np.clip(np.asarray(mono, dtype=np.float32), -1.0, 1.0)
    stereo = np.stack([data, data], axis=1)  # (N, 2)
    interleaved = (stereo * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(interleaved.tobytes())


def _load_wav_mono(path: str) -> np.ndarray | None:
    try:
        with wave.open(path, "rb") as wav_file:
            channels = wav_file.getnchannels()
            frames = wav_file.readframes(wav_file.getnframes())
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32768.0
        if channels > 1:
            data = data.reshape(-1, channels).mean(axis=1)
        return data
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def si_sdr(reference: np.ndarray, estimate: np.ndarray) -> float:
    """Scale-invariant SDR (dB). Gain-aligns the estimate before the residual.

    SI-SDR = 10*log10( ||alpha*ref||^2 / ||alpha*ref - est||^2 ),
    alpha = <est,ref>/<ref,ref>. Returns -inf for a silent reference/estimate.
    """
    ref = np.asarray(reference, dtype=np.float64)
    est = np.asarray(estimate, dtype=np.float64)
    length = min(ref.size, est.size)
    if length == 0:
        return float("-inf")
    ref = ref[:length]
    est = est[:length]
    ref_energy = float(np.dot(ref, ref))
    if ref_energy <= 1e-12 or float(np.dot(est, est)) <= 1e-12:
        return float("-inf")
    alpha = float(np.dot(est, ref)) / ref_energy
    projection = alpha * ref
    noise = projection - est
    noise_energy = float(np.dot(noise, noise))
    if noise_energy <= 1e-12:
        return float("inf")
    return 10.0 * math.log10(float(np.dot(projection, projection)) / noise_energy)


def buffer_stats(mono: np.ndarray) -> dict[str, Any]:
    """Reference-free per-stem stats: RMS/peak dBFS + spectral centroid (Hz)."""
    data = np.asarray(mono, dtype=np.float64).reshape(-1)
    if data.size == 0:
        return {"rmsDbfs": None, "peakDbfs": None, "spectralCentroidHz": None, "nonzero": False}
    rms = float(np.sqrt(np.mean(data * data)))
    peak = float(np.max(np.abs(data)))
    if peak <= 0:
        return {"rmsDbfs": None, "peakDbfs": None, "spectralCentroidHz": 0.0, "nonzero": False}
    spectrum = np.abs(np.fft.rfft(data * np.hanning(data.size)))
    freqs = np.fft.rfftfreq(data.size, d=1.0 / SAMPLE_RATE)
    total = float(spectrum.sum())
    centroid = float((freqs * spectrum).sum() / total) if total > 0 else 0.0
    return {
        "rmsDbfs": round(20.0 * math.log10(max(rms, 1e-12)), 3),
        "peakDbfs": round(20.0 * math.log10(max(peak, 1e-12)), 3),
        "spectralCentroidHz": round(centroid, 2),
        "nonzero": True,
    }


# --------------------------------------------------------------------------- #
# Backend execution
# --------------------------------------------------------------------------- #
def run_backend_separation(
    backend: str,
    mix_path: str,
    out_dir: str,
    *,
    repeats: int = 2,
    warmup: bool = True,
) -> dict[str, Any]:
    """Separate ``mix_path`` with ``backend`` (demucs|msst); time it fairly.

    With ``warmup`` (default), does an untimed warm-up pass (amortizes model
    download/load) then takes the min wall-clock over ``repeats`` timed runs.
    Set ``warmup=False`` for the subprocess MSST backend, which reloads its model
    on every call — a warm-up there buys nothing and just doubles a slow run, so
    the single timed run honestly includes the per-call cold cost both backends
    actually pay. Returns the stems + runtime + status.
    """
    from separation_backend import separate_stems_backend

    prev = os.environ.get("ASA_SEPARATION_BACKEND")
    os.environ["ASA_SEPARATION_BACKEND"] = backend
    try:
        device = "cuda" if _torch_cuda_available() else "cpu"
        # Warm-up (untimed) — pulls weights / builds the graph.
        if warmup:
            warm = separate_stems_backend(mix_path, output_dir=os.path.join(out_dir, "warmup"))
            if not warm:
                return {"status": "error", "error": "separation returned no stems", "stems": {}}

        timings: list[float] = []
        stems: dict[str, str] = {}
        for i in range(max(1, repeats)):
            run_out = os.path.join(out_dir, f"run{i}")
            start = time.perf_counter()
            stems = separate_stems_backend(mix_path, output_dir=run_out) or {}
            timings.append(time.perf_counter() - start)
            if not stems:
                return {"status": "error", "error": "separation returned no stems", "stems": {}}

        return {
            "status": "completed",
            "stems": stems,
            "runtimeSeconds": round(min(timings), 3),
            "device": device,
        }
    finally:
        if prev is None:
            os.environ.pop("ASA_SEPARATION_BACKEND", None)
        else:
            os.environ["ASA_SEPARATION_BACKEND"] = prev


def _torch_cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _msst_configured() -> bool:
    py = os.environ.get("ASA_MSST_PYTHON")
    root = os.environ.get("ASA_MSST_ROOT")
    return bool(py and os.path.exists(py) and root and os.path.isdir(root))


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def _score_against_known(
    stems: dict[str, str],
    known: dict[str, np.ndarray],
) -> dict[str, Any]:
    """SI-SDR per canonical stem against the known synthetic sources."""
    per_stem: dict[str, Any] = {}
    sdrs: list[float] = []
    for name in _CANONICAL_STEMS:
        path = stems.get(name)
        est = _load_wav_mono(path) if isinstance(path, str) else None
        if est is None or name not in known:
            per_stem[name] = {"siSdrDb": None, "present": False}
            continue
        value = si_sdr(known[name], est)
        per_stem[name] = {
            "siSdrDb": round(value, 3) if math.isfinite(value) else None,
            "present": True,
        }
        if math.isfinite(value):
            sdrs.append(value)
    per_stem["meanSiSdrDb"] = round(sum(sdrs) / len(sdrs), 3) if sdrs else None
    return per_stem


def evaluate_synthetic(out_dir: str, *, repeats: int = 2) -> dict[str, Any]:
    """Run the always-available synthetic smoke-test for both backends."""
    known = build_synthetic_multitrack()
    mix = sum(known.values())
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = (mix / peak * 0.9).astype(np.float32)

    work = tempfile.mkdtemp(prefix="asa_sep_ab_synth_", dir=out_dir)
    mix_path = os.path.join(work, "mix.wav")
    _write_stereo_wav(mix_path, mix)

    result: dict[str, Any] = {"perBackend": {}}
    for backend in ("demucs", "msst"):
        if backend == "msst" and not _msst_configured():
            result["perBackend"][backend] = {"status": "skipped_no_msst"}
            continue
        backend_dir = os.path.join(work, backend)
        os.makedirs(backend_dir, exist_ok=True)
        run = run_backend_separation(backend, mix_path, backend_dir, repeats=repeats)
        if run["status"] != "completed":
            result["perBackend"][backend] = run
            continue
        result["perBackend"][backend] = {
            "status": "completed",
            "runtimeSeconds": run["runtimeSeconds"],
            "device": run["device"],
            "quality": _score_against_known(run["stems"], known),
        }
    return result


def evaluate_real_track(audio_path: str, out_dir: str, *, repeats: int = 2) -> dict[str, Any]:
    """Reference-free proxies on a real track for both backends."""
    work = tempfile.mkdtemp(prefix="asa_sep_ab_real_", dir=out_dir)
    entry: dict[str, Any] = {"track": os.path.basename(audio_path), "perBackend": {}}
    for backend in ("demucs", "msst"):
        if backend == "msst" and not _msst_configured():
            entry["perBackend"][backend] = {"status": "skipped_no_msst"}
            continue
        backend_dir = os.path.join(work, backend)
        os.makedirs(backend_dir, exist_ok=True)
        run = run_backend_separation(backend, audio_path, backend_dir, repeats=repeats)
        if run["status"] != "completed":
            entry["perBackend"][backend] = run
            continue
        stems_stats = {}
        recovered = None
        for name, path in run["stems"].items():
            mono = _load_wav_mono(path)
            if mono is None:
                continue
            stems_stats[name] = buffer_stats(mono)
            recovered = mono if recovered is None else _sum_to(recovered, mono)
        mix = _load_wav_mono(audio_path)
        residual_db = _reconstruction_residual_db(mix, recovered)
        entry["perBackend"][backend] = {
            "status": "completed",
            "runtimeSeconds": run["runtimeSeconds"],
            "device": run["device"],
            "stemStats": stems_stats,
            "mixReconstructionResidualDb": residual_db,
        }
    return entry


def _sum_to(acc: np.ndarray, add: np.ndarray) -> np.ndarray:
    length = min(acc.size, add.size)
    return acc[:length] + add[:length]


def _reconstruction_residual_db(mix: np.ndarray | None, recovered: np.ndarray | None):
    if mix is None or recovered is None:
        return None
    length = min(mix.size, recovered.size)
    if length == 0:
        return None
    residual = mix[:length] - recovered[:length]
    res_energy = float(np.dot(residual, residual))
    mix_energy = float(np.dot(mix[:length], mix[:length]))
    if mix_energy <= 1e-12:
        return None
    return round(10.0 * math.log10(max(res_energy, 1e-12) / mix_energy), 3)


# --------------------------------------------------------------------------- #
# Ground-truth reference-set evaluation (true per-stem SI-SDR)
# --------------------------------------------------------------------------- #
# A "reference set" is a directory of per-track subdirectories, each laid out
# MUSDB-style with WAV files:
#
#     <ref_dir>/<track>/mixture.wav   (the input the backend separates)
#     <ref_dir>/<track>/vocals.wav    (ground-truth stems, any subset of the
#     <ref_dir>/<track>/bass.wav       canonical four; missing stems are skipped)
#     <ref_dir>/<track>/drums.wav
#     <ref_dir>/<track>/other.wav
#
# Unlike the synthetic smoke-test (toy sources), this scores each backend on
# REAL music with REAL isolated stems, so the SI-SDR is a genuine quality
# signal for a Demucs-vs-MSST comparison. Two honesty caveats remain:
#   * It is gain-aligned SI-SDR on a mono downmix, NOT museval/BSSEval-v4 SDR —
#     so the absolute numbers are NOT comparable to published MUSDB leaderboards.
#     They ARE internally consistent (same metric, same tracks, both backends),
#     which is exactly what an A/B needs.
#   * WAV only (reuses _load_wav_mono); the MUSDB extraction writes WAVs.
_MIX_BASENAMES = ("mixture", "mix")


def _load_reference_track(track_dir: str) -> tuple[str, dict[str, np.ndarray]] | None:
    """Load a MUSDB-style track dir: ``(mixture_path, {stem: mono ground-truth})``.

    Returns ``None`` if no mixture file or no ground-truth stems are present.
    """
    mixture_path: str | None = None
    for base in _MIX_BASENAMES:
        candidate = os.path.join(track_dir, f"{base}.wav")
        if os.path.isfile(candidate):
            mixture_path = candidate
            break
    if mixture_path is None:
        return None

    known: dict[str, np.ndarray] = {}
    for stem in _CANONICAL_STEMS:
        stem_path = os.path.join(track_dir, f"{stem}.wav")
        if os.path.isfile(stem_path):
            mono = _load_wav_mono(stem_path)
            if mono is not None:
                known[stem] = mono
    if not known:
        return None
    return mixture_path, known


def evaluate_reference_track(track_dir: str, out_dir: str, *, repeats: int = 2) -> dict[str, Any]:
    """True per-stem SI-SDR + runtime for both backends on one ground-truth track."""
    name = os.path.basename(os.path.normpath(track_dir))
    loaded = _load_reference_track(track_dir)
    if loaded is None:
        return {"track": name, "status": "skipped_no_reference"}
    mixture_path, known = loaded

    work = tempfile.mkdtemp(prefix="asa_sep_ab_ref_", dir=out_dir)
    entry: dict[str, Any] = {"track": name, "perBackend": {}}
    for backend in ("demucs", "msst"):
        if backend == "msst" and not _msst_configured():
            entry["perBackend"][backend] = {"status": "skipped_no_msst"}
            continue
        backend_dir = os.path.join(work, backend)
        os.makedirs(backend_dir, exist_ok=True)
        # warmup=False: one honest cold-start timed run (MSST reloads per call).
        run = run_backend_separation(
            backend, mixture_path, backend_dir, repeats=repeats, warmup=False
        )
        if run["status"] != "completed":
            entry["perBackend"][backend] = run
            continue
        entry["perBackend"][backend] = {
            "status": "completed",
            "runtimeSeconds": run["runtimeSeconds"],
            "device": run["device"],
            "quality": _score_against_known(run["stems"], known),
        }
    return entry


def _aggregate_reference(tracks: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-backend mean SI-SDR (overall + per stem) and mean runtime across tracks."""
    aggregate: dict[str, Any] = {}
    for backend in ("demucs", "msst"):
        means: list[float] = []
        runtimes: list[float] = []
        per_stem: dict[str, list[float]] = {stem: [] for stem in _CANONICAL_STEMS}
        for track in tracks:
            block = track.get("perBackend", {}).get(backend, {})
            if block.get("status") != "completed":
                continue
            quality = block.get("quality", {}) if isinstance(block.get("quality"), dict) else {}
            if isinstance(quality.get("meanSiSdrDb"), (int, float)):
                means.append(float(quality["meanSiSdrDb"]))
            for stem in _CANONICAL_STEMS:
                value = quality.get(stem, {}).get("siSdrDb") if isinstance(quality.get(stem), dict) else None
                if isinstance(value, (int, float)):
                    per_stem[stem].append(float(value))
            if isinstance(block.get("runtimeSeconds"), (int, float)):
                runtimes.append(float(block["runtimeSeconds"]))
        aggregate[backend] = {
            "meanSiSdrDb": round(sum(means) / len(means), 3) if means else None,
            "perStemMeanSiSdrDb": {
                stem: (round(sum(v) / len(v), 3) if v else None) for stem, v in per_stem.items()
            },
            "meanRuntimeSeconds": round(sum(runtimes) / len(runtimes), 3) if runtimes else None,
            "tracksScored": len(means),
        }
    return aggregate


def evaluate_reference_set(ref_dir: str, out_dir: str, *, repeats: int = 2) -> dict[str, Any]:
    """Evaluate every track subdirectory under ``ref_dir`` and aggregate."""
    track_dirs = sorted(
        os.path.join(ref_dir, name)
        for name in os.listdir(ref_dir)
        if os.path.isdir(os.path.join(ref_dir, name))
    )
    tracks = [evaluate_reference_track(td, out_dir, repeats=repeats) for td in track_dirs]
    return {
        "refDir": ref_dir,
        "trackCount": len(track_dirs),
        "tracks": tracks,
        "aggregate": _aggregate_reference(tracks),
    }


def run_ab(
    *,
    input_dir: str | None,
    out_dir: str,
    model: str | None = None,
    repeats: int = 2,
    ref_dir: str | None = None,
) -> dict[str, Any]:
    """Top-level A/B run: ground-truth reference set (if given) + synthetic smoke-test + optional real-track proxies."""
    from datetime import datetime, timezone

    os.makedirs(out_dir, exist_ok=True)
    if model:
        os.environ["ASA_MSST_MODEL"] = model

    report: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "status": "completed",
        "config": {
            "model": os.environ.get("ASA_MSST_MODEL", "scnet_4stem"),
            "msstConfigured": _msst_configured(),
            "repeats": repeats,
        },
        "caveats": [
            "Reference-set SI-SDR (when a --ref-dir is given) is the HEADLINE "
            "signal: gain-aligned SI-SDR on a mono downmix vs real ground-truth "
            "stems. Internally consistent for Demucs-vs-MSST, but NOT comparable "
            "to published museval/BSSEval-v4 MUSDB leaderboard numbers.",
            "Synthetic SI-SDR is a PLUMBING smoke-test, not a real-music quality "
            "ranking: RoFormer/SCNet are trained on real spectra and may score "
            "poorly on toy synthetic sources. Do not read it as Demucs>MSST.",
            "Real-track proxies measure self-consistency/plausibility, not "
            "correctness (no ground-truth stems). Runtime is end-to-end wall-clock "
            "(min of repeats after a warm-up); compare same-device rows only.",
        ],
        "referenceSet": (
            evaluate_reference_set(ref_dir, out_dir, repeats=repeats)
            if ref_dir and os.path.isdir(ref_dir)
            else None
        ),
        "syntheticSmokeTest": evaluate_synthetic(out_dir, repeats=repeats),
        "realTracks": [],
    }

    if input_dir and os.path.isdir(input_dir):
        for name in sorted(os.listdir(input_dir)):
            path = os.path.join(input_dir, name)
            if os.path.isfile(path) and name.lower().endswith(
                (".wav", ".flac", ".mp3", ".m4a", ".ogg", ".aiff", ".aif")
            ):
                report["realTracks"].append(evaluate_real_track(path, out_dir, repeats=repeats))

    return report
