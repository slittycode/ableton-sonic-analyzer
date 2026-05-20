// SPDX-License-Identifier: GPL-3.0-or-later
// `WindowKind` + `window_coefficients` carved from openmeters src/util/audio.rs
// (Copyright (C) 2026 Maika Namuo), WITHOUT the `settings_enum!`/serde macro and
// the global `LazyLock` cache (offline analysis builds each window only a handful
// of times, so a per-call compute is negligible and drops the `std::sync` surface).

use std::sync::Arc;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum WindowKind {
    Rectangular,
    Hann,
    Hamming,
    Blackman,
    BlackmanHarris,
}

impl WindowKind {
    fn coefficients(self, len: usize) -> Vec<f32> {
        // Guard relied on by the σ_t / reassignment tests.
        if len <= 1 {
            return vec![1.0; len];
        }
        let coeffs: &[f32] = match self {
            Self::Rectangular => return vec![1.0; len],
            Self::Hann => &[0.5, -0.5],
            Self::Hamming => &[25.0 / 46.0, -21.0 / 46.0],
            Self::Blackman => &[0.42, -0.5, 0.08],
            Self::BlackmanHarris => &[0.35875, -0.48829, 0.14128, -0.01168],
        };
        let step = core::f32::consts::TAU / (len - 1) as f32;
        (0..len)
            .map(|n| {
                let phi = n as f32 * step;
                coeffs
                    .iter()
                    .enumerate()
                    .fold(0.0, |sum, (k, &c)| sum + c * (phi * k as f32).cos())
            })
            .collect()
    }
}

pub fn window_coefficients(kind: WindowKind, len: usize) -> Arc<[f32]> {
    if len == 0 {
        return Arc::from([]);
    }
    Arc::from(kind.coefficients(len))
}
