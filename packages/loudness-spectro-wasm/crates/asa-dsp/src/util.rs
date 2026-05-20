// SPDX-License-Identifier: GPL-3.0-or-later
// Carved from openmeters src/util/audio.rs, Copyright (C) 2026 Maika Namuo.
//
// Only the loudness/spectrum/spectrogram-path primitives are lifted here; the
// original module also carries serde-backed settings enums, a window-coefficient
// cache, ERB scaling, etc., none of which these paths need.

use std::collections::VecDeque;

pub const DEFAULT_SAMPLE_RATE: f32 = 48_000.0;

/// dB floor used by the spectrogram (distinct from the spectrum's -80 floor).
pub const DB_FLOOR: f32 = -140.0;

const POWER_EPSILON: f32 = 1.0e-20;

pub const LN_TO_DB: f32 = 4.342_944_8;

#[inline]
pub fn power_to_db(power: f32, floor: f32) -> f32 {
    if power > POWER_EPSILON {
        (power.ln() * LN_TO_DB).max(floor)
    } else {
        floor
    }
}

#[inline]
pub fn db_to_power(db: f32) -> f32 {
    const DB_TO_LOG2: f32 = 0.1 * core::f32::consts::LOG2_10;
    (db * DB_TO_LOG2).exp2()
}

#[inline]
pub fn apply_window(buffer: &mut [f32], window: &[f32]) {
    debug_assert_eq!(buffer.len(), window.len());
    for (sample, coeff) in buffer.iter_mut().zip(window.iter()) {
        *sample *= *coeff;
    }
}

pub fn compute_fft_bin_normalization(window: &[f32], fft_size: usize) -> Vec<f32> {
    let bins = fft_size / 2 + 1;
    let window_sum: f32 = window.iter().sum();
    let inv_sum = if window_sum.abs() > f32::EPSILON {
        1.0 / window_sum
    } else if fft_size > 0 {
        1.0 / fft_size as f32
    } else {
        0.0
    };

    let dc_scale = inv_sum * inv_sum;
    let ac_scale = 4.0 * dc_scale;
    let mut norms = vec![ac_scale; bins];
    norms[0] = dc_scale;
    if bins > 1 {
        norms[bins - 1] = dc_scale;
    }
    norms
}

/// Copies the front of `src` into `dst` and removes the copied window's DC offset.
#[inline]
pub fn copy_dc_removed_from_deque(dst: &mut [f32], src: &VecDeque<f32>) {
    debug_assert!(dst.len() <= src.len());
    if dst.is_empty() {
        return;
    }

    let len = dst.len();
    let (head, tail) = src.as_slices();
    let sum = if head.len() >= len {
        let head = &head[..len];
        dst[..len].copy_from_slice(head);
        head.iter().sum::<f32>()
    } else {
        let split = head.len();
        let tail = &tail[..len - split];
        dst[..split].copy_from_slice(head);
        dst[split..len].copy_from_slice(tail);
        let mut sum = 0.0;
        for &sample in head {
            sum += sample;
        }
        for &sample in tail {
            sum += sample;
        }
        sum
    };

    let mean = sum / len as f32;
    if mean.abs() > f32::EPSILON {
        for sample in &mut dst[..len] {
            *sample -= mean;
        }
    }
}

/// Mixes interleaved frames into mono and appends them to `buffer`.
pub fn mixdown_into_deque(buffer: &mut VecDeque<f32>, samples: &[f32], channels: usize) {
    if channels == 0 || samples.is_empty() {
        return;
    }

    if channels == 1 {
        buffer.extend(samples);
        return;
    }

    buffer.reserve(samples.len() / channels);

    let inv = 1.0 / channels as f32;
    for frame in samples.chunks_exact(channels) {
        let sum: f32 = frame.iter().sum();
        buffer.push_back(sum * inv);
    }
}
