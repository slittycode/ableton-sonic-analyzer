"""BatchedBandpass — 4th-order Butterworth bandpass bank with zero-phase filtfilt.

Drop-in replacement for the inline ``butter(4, ..., output='sos') + sosfiltfilt``
pattern that ASA's detection module uses for per-band RT60. The pattern was
repeating across multiple call sites with slightly different glue; this module
gives them one shared primitive.

Output is bit-identical to the inline code (np.allclose atol=1e-12, rtol=1e-12).
The ``backend`` argument is reserved for a future torch path — the audit at
``docs/history/library-review-torchfx-2026-05-13.md`` flagged that as a
candidate if profiling ever shows per-band scipy filtering is hot.
"""

from collections.abc import Iterable, Mapping
from typing import Union

import numpy as np

try:
    from scipy import signal as scipy_signal  # type: ignore[import-not-found]
except ImportError:
    scipy_signal = None  # type: ignore[assignment]


class BatchedBandpass:
    """Per-instance bandpass bank with cached SOS coefficients.

    Matches ``analyze_detection._bandpass_signal`` byte-for-byte: Nyquist
    clamps via ``max(1.0, lo_hz)`` and ``min(sample_rate * 0.49, hi_hz)``,
    4th-order Butterworth via ``output='sos'``, then ``sosfiltfilt``. Any
    deviation is a Phase 1 regression — see ``BatchedBandpassTests``.
    """

    def __init__(self, sample_rate: int, *, order: int = 4, backend: str = "scipy") -> None:
        if backend != "scipy":
            raise ValueError(
                f"BatchedBandpass: backend={backend!r} not supported (PR 1 ships scipy only)"
            )
        self.sample_rate = int(sample_rate)
        self.order = int(order)
        self.backend = backend
        # Memoised SOS coefficients per (lo_hz, hi_hz). sample_rate and order
        # are fixed per instance. Failed designs (out-of-range etc.) are
        # cached as None so the second caller short-circuits without retry.
        self._sos_cache: dict[tuple[float, float], np.ndarray | None] = {}

    def _design(self, lo_hz: float, hi_hz: float) -> np.ndarray | None:
        key = (float(lo_hz), float(hi_hz))
        if key in self._sos_cache:
            return self._sos_cache[key]
        if scipy_signal is None:
            self._sos_cache[key] = None
            return None
        nyquist = 0.5 * self.sample_rate
        lo = max(1.0, lo_hz) / nyquist
        hi = min(self.sample_rate * 0.49, hi_hz) / nyquist
        if not (0.0 < lo < hi < 1.0):
            self._sos_cache[key] = None
            return None
        try:
            sos = scipy_signal.butter(self.order, [lo, hi], btype="bandpass", output="sos")
        except Exception:
            sos = None
        self._sos_cache[key] = sos
        return sos

    def filter_one(
        self, mono: np.ndarray, lo_hz: float, hi_hz: float
    ) -> np.ndarray | None:
        """Bit-identical replacement for ``analyze_detection._bandpass_signal``.

        Returns ``float32`` on success; ``None`` on empty input, missing
        scipy, Nyquist-clamp failure, or sosfiltfilt error.
        """
        if scipy_signal is None or mono is None or getattr(mono, "size", 0) == 0:
            return None
        sos = self._design(lo_hz, hi_hz)
        if sos is None:
            return None
        try:
            return scipy_signal.sosfiltfilt(sos, mono).astype(np.float32, copy=False)
        except Exception:
            return None

    def filter_many(
        self,
        mono: np.ndarray,
        bands: Union[Mapping[str, tuple[float, float]], Iterable[tuple[str, float, float]]],
        *,
        dtype=np.float64,
    ) -> dict[str, np.ndarray]:
        """Run the bandpass over many bands and return ``{band_name: filtered}``.

        Accepts two shapes for ``bands``:
          - ``Mapping[str, (lo, hi)]`` — matches ``SPECTRAL_BALANCE_BANDS``
            in ``analyze_core``.
          - ``Iterable[(name, lo, hi)]`` — matches ``_REVERB_BANDS`` in
            ``analyze_detection``.

        Skipped bands (empty input, out-of-range, sosfiltfilt error) are
        absent from the returned dict — preserves the omit-on-skip behavior
        of the per-band reverb loop today.
        """
        if scipy_signal is None or mono is None or getattr(mono, "size", 0) == 0:
            return {}

        if isinstance(bands, Mapping):
            entries: Iterable[tuple[str, float, float]] = [
                (str(name), float(lo), float(hi)) for name, (lo, hi) in bands.items()
            ]
        else:
            entries = [(str(name), float(lo), float(hi)) for name, lo, hi in bands]

        out: dict[str, np.ndarray] = {}
        for name, lo_hz, hi_hz in entries:
            sos = self._design(lo_hz, hi_hz)
            if sos is None:
                continue
            try:
                filtered = scipy_signal.sosfiltfilt(sos, mono)
            except Exception:
                continue
            out[name] = filtered.astype(dtype, copy=False)
        return out
