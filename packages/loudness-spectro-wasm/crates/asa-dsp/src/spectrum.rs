// SPDX-License-Identifier: GPL-3.0-or-later
//
// A-weighted average spectrum. `a_weight()` is carved verbatim from openmeters
// src/visuals/spectrum/processor.rs (Copyright (C) 2026 Maika Namuo); the
// whole-file mean-power averaging here REPLACES openmeters' timestamped live
// `AveragingMode` machinery (which depended on the `Instant` removed for wasm32).
//
// Averaging is done in the POWER domain (energy-correct) and converted to dB
// once; A-weighting is applied once at the end, gated to bins above the floor
// (matching upstream's per-window `if raw > floor` gate).

use crate::util::{
    DEFAULT_SAMPLE_RATE, apply_window, compute_fft_bin_normalization, copy_dc_removed_from_deque,
    mixdown_into_deque, power_to_db,
};
use crate::window::{WindowKind, window_coefficients};
use realfft::RealFftPlanner;
use std::collections::VecDeque;

pub const DEFAULT_SPECTRUM_FFT_SIZE: usize = 4096;
pub const DEFAULT_SPECTRUM_FLOOR_DB: f32 = -80.0;
const MIN_SPECTRUM_FFT_SIZE: usize = 128;
const HOP_DIVISOR: usize = 8;

#[derive(Debug, Clone)]
pub struct AveragedSpectrum {
    pub frequency_bins: Vec<f32>,
    /// A-weighted (IEC 61672), dB.
    pub magnitudes_db: Vec<f32>,
    /// Unweighted, dB.
    pub magnitudes_unweighted_db: Vec<f32>,
}

/// Whole-file averaged spectrum from interleaved f32 PCM (mixed down to mono).
pub fn averaged_spectrum(
    samples: &[f32],
    channels: usize,
    sample_rate: f32,
    fft_size: usize,
) -> AveragedSpectrum {
    let fft_size = fft_size.max(MIN_SPECTRUM_FFT_SIZE);
    let sample_rate = if sample_rate.is_finite() && sample_rate > 0.0 {
        sample_rate
    } else {
        DEFAULT_SAMPLE_RATE
    };
    let hop = (fft_size / HOP_DIVISOR).max(1);
    let bins = fft_size / 2 + 1;
    let floor = DEFAULT_SPECTRUM_FLOOR_DB;

    let window = window_coefficients(WindowKind::BlackmanHarris, fft_size);
    let bin_norm = compute_fft_bin_normalization(&window, fft_size);

    let mut planner = RealFftPlanner::<f32>::new();
    let fft = planner.plan_fft_forward(fft_size);
    let mut real = fft.make_input_vec();
    let mut spectrum = fft.make_output_vec();
    let mut scratch = fft.make_scratch_vec();

    let mut pcm: VecDeque<f32> = VecDeque::new();
    mixdown_into_deque(&mut pcm, samples, channels.max(1));

    let mut power_sum = vec![0.0_f64; bins];
    let mut window_count: u64 = 0;

    while pcm.len() >= fft_size {
        copy_dc_removed_from_deque(&mut real[..fft_size], &pcm);
        apply_window(&mut real, &window);
        if fft
            .process_with_scratch(&mut real, &mut spectrum, &mut scratch)
            .is_err()
        {
            break;
        }
        for (i, c) in spectrum.iter().enumerate() {
            let power = (c.re * c.re + c.im * c.im) * bin_norm[i];
            power_sum[i] += f64::from(power);
        }
        window_count += 1;
        pcm.drain(..hop);
    }

    let frequency_bins: Vec<f32> = (0..bins)
        .map(|i| i as f32 * sample_rate / fft_size as f32)
        .collect();
    let mut magnitudes_unweighted_db = vec![floor; bins];
    let mut magnitudes_db = vec![floor; bins];

    if window_count > 0 {
        for i in 0..bins {
            let mean_power = (power_sum[i] / window_count as f64) as f32;
            let unweighted = power_to_db(mean_power, floor);
            magnitudes_unweighted_db[i] = unweighted;
            let weight = if unweighted > floor {
                a_weight(frequency_bins[i])
            } else {
                0.0
            };
            magnitudes_db[i] = (unweighted + weight).max(floor);
        }
    }

    AveragedSpectrum {
        frequency_bins,
        magnitudes_db,
        magnitudes_unweighted_db,
    }
}

fn a_weight(freq_hz: f32) -> f32 {
    const MIN_DB: f32 = -80.0;
    if freq_hz <= 0.0 {
        return MIN_DB;
    }

    // IEC 61672-1:2013 reference frequencies.
    const C1: f64 = 20.598_997 * 20.598_997;
    const C2: f64 = 107.652_65 * 107.652_65;
    const C3: f64 = 737.862_23 * 737.862_23;
    const C4: f64 = 12_194.217 * 12_194.217;

    let f = freq_hz as f64;
    let f2 = f * f;
    let numerator = C4 * f2 * f2;
    let denom = (f2 + C1) * ((f2 + C2) * (f2 + C3)).sqrt() * (f2 + C4);

    if denom <= 0.0 || numerator <= 0.0 {
        return MIN_DB;
    }

    let ra = numerator / denom;
    let db = 20.0 * ra.log10() + 2.0;
    db.max(MIN_DB as f64) as f32
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sine(rate: f32, secs: f32, freq: f32, amp: f32) -> Vec<f32> {
        (0..(rate * secs) as usize)
            .map(|n| (2.0 * std::f32::consts::PI * freq * n as f32 / rate).sin() * amp)
            .collect()
    }

    #[test]
    fn a_weight_matches_iec_reference_points() {
        let reference_points: &[(f32, f32)] = &[
            (31.5, -39.4),
            (63.0, -26.2),
            (100.0, -19.1),
            (200.0, -10.9),
            (500.0, -3.2),
            (1000.0, 0.0),
            (2000.0, 1.2),
            (4000.0, 1.0),
            (8000.0, -1.1),
            (16000.0, -6.6),
        ];

        for &(freq, expected_db) in reference_points {
            let actual = a_weight(freq);
            let delta = (actual - expected_db).abs();
            assert!(
                delta <= 0.15,
                "A-weight mismatch at {freq} Hz: expected {expected_db} dB, got {actual} dB (delta={delta})"
            );
        }
    }

    #[test]
    fn spectrum_peaks_at_sine_frequency() {
        let rate = 48000.0_f32;
        let fft_size = 4096;
        let mono = sine(rate, 1.0, 1000.0, 0.5);
        let stereo: Vec<f32> = mono.iter().flat_map(|&s| [s, s]).collect();

        let spec = averaged_spectrum(&stereo, 2, rate, fft_size);
        let bins = fft_size / 2 + 1;
        assert_eq!(spec.frequency_bins.len(), bins);
        assert_eq!(spec.magnitudes_db.len(), bins);

        let (peak_idx, _) = spec
            .magnitudes_unweighted_db
            .iter()
            .enumerate()
            .max_by(|a, b| a.1.total_cmp(b.1))
            .unwrap();
        let peak_hz = spec.frequency_bins[peak_idx];
        assert!(
            (peak_hz - 1000.0).abs() < 20.0,
            "spectrum peak {peak_hz:.1} Hz, expected ~1000 Hz"
        );
        // A-weight at 1 kHz is ~0 dB, so weighted ≈ unweighted at the peak.
        assert!(
            (spec.magnitudes_db[peak_idx] - spec.magnitudes_unweighted_db[peak_idx]).abs() < 0.5,
            "A-weight at 1 kHz should be ~0 dB"
        );
    }
}
