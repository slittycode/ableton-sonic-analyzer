// SPDX-License-Identifier: GPL-3.0-or-later
//
// EBU R128 gated integrated loudness + loudness range (LRA).
//
// openmeters implements BS.1770-5 K-weighting, momentary, short-term, and
// true-peak, but NOT program-integrated loudness, gating, or LRA (it is a live
// meter). This module adds that layer on top of the SAME K-weighting filter
// lifted in `loudness.rs`.
//
// Integrated loudness (ITU-R BS.1770): 400 ms gating blocks at 100 ms step
// (75% overlap); absolute gate -70 LUFS; relative gate -10 LU below the
// absolute-gated energy mean; result = -0.691 + 10*log10(mean gated energy).
//
// Loudness range (EBU Tech 3342): 3 s blocks at 1 s step; absolute gate
// -70 LUFS; relative gate -20 LU; LRA = P95 - P10 of the gated short-term
// loudnesses.

use crate::dsp::AudioBlock;
use crate::loudness::{KWeightingFilter, LOUDNESS_OFFSET, MAX_CHANNELS, channel_weight};

const SUBBLOCK_SECS: f64 = 0.1;
const GATE_SUBBLOCKS: usize = 4; // 400 ms
const ST_SUBBLOCKS: usize = 30; // 3 s
const ST_STEP_SUBBLOCKS: usize = 10; // 1 s
const ABS_GATE_LUFS: f64 = -70.0;
const REL_GATE_LU: f64 = -10.0;
const LRA_REL_GATE_LU: f64 = -20.0;

#[derive(Debug, Clone, Copy, Default)]
pub struct IntegratedResult {
    /// Gated integrated loudness (LUFS), or `None` if no block passed the gates.
    pub integrated_lufs: Option<f64>,
    /// Loudness range (LU), or `None` if undefined (too little gated material).
    pub lra: Option<f64>,
    /// Number of 400 ms gating blocks observed.
    pub gating_blocks: usize,
}

/// Streaming gated-loudness accumulator. Feed interleaved f32 frames via
/// [`IntegratedLoudness::add_interleaved`] (any chunking), then call
/// [`IntegratedLoudness::result`].
#[derive(Debug, Clone)]
pub struct IntegratedLoudness {
    channels: usize,
    samples_per_sub: usize,
    filters: Vec<KWeightingFilter>,
    cur_sumsq: [f64; MAX_CHANNELS],
    cur_frames: usize,
    // Per full sub-block: per-channel sum of squared K-weighted samples.
    subblocks: Vec<[f64; MAX_CHANNELS]>,
}

impl IntegratedLoudness {
    pub fn new(sample_rate: f32, channels: usize) -> Self {
        let channels = channels.clamp(1, MAX_CHANNELS);
        let rate = f64::from(sample_rate.max(1.0));
        let samples_per_sub = ((rate * SUBBLOCK_SECS).round() as usize).max(1);
        Self {
            channels,
            samples_per_sub,
            filters: (0..channels)
                .map(|_| KWeightingFilter::new(rate))
                .collect(),
            cur_sumsq: [0.0; MAX_CHANNELS],
            cur_frames: 0,
            subblocks: Vec::new(),
        }
    }

    /// Convenience for the whole-buffer path used by the block-based API.
    pub fn add_block(&mut self, block: &AudioBlock<'_>) {
        if block.channels == self.channels {
            self.add_interleaved(block.samples);
        } else {
            self.add_interleaved_with_channels(block.samples, block.channels);
        }
    }

    pub fn add_interleaved(&mut self, samples: &[f32]) {
        self.add_interleaved_with_channels(samples, self.channels);
    }

    fn add_interleaved_with_channels(&mut self, samples: &[f32], src_channels: usize) {
        if src_channels == 0 {
            return;
        }
        for frame in samples.chunks_exact(src_channels) {
            for ch in 0..self.channels {
                // If the source has fewer channels than configured, reuse the last.
                let sample = frame[ch.min(src_channels - 1)];
                let y = f64::from(self.filters[ch].process(sample));
                self.cur_sumsq[ch] += y * y;
            }
            self.cur_frames += 1;
            if self.cur_frames >= self.samples_per_sub {
                self.subblocks.push(self.cur_sumsq);
                self.cur_sumsq = [0.0; MAX_CHANNELS];
                self.cur_frames = 0;
            }
        }
    }

    /// Weighted mean-square energy (Σ_i G_i · z_i) over `count` sub-blocks
    /// starting at `start`.
    fn weighted_energy(&self, start: usize, count: usize) -> f64 {
        let denom = (count * self.samples_per_sub) as f64;
        if denom <= 0.0 {
            return 0.0;
        }
        let mut energy = 0.0;
        for ch in 0..self.channels {
            let mut sum = 0.0;
            for sb in &self.subblocks[start..start + count] {
                sum += sb[ch];
            }
            energy += channel_weight(ch, self.channels) * (sum / denom);
        }
        energy
    }

    pub fn result(&self) -> IntegratedResult {
        let n = self.subblocks.len();

        // --- Integrated: 400 ms blocks, 100 ms step ---
        let mut blocks: Vec<(f64, f64)> = Vec::new(); // (energy, loudness LUFS)
        let mut i = 0;
        while i + GATE_SUBBLOCKS <= n {
            let energy = self.weighted_energy(i, GATE_SUBBLOCKS);
            if energy > 0.0 {
                blocks.push((energy, LOUDNESS_OFFSET + 10.0 * energy.log10()));
            }
            i += 1;
        }

        let integrated_lufs = gated_mean_loudness(&blocks, REL_GATE_LU);

        // --- LRA: 3 s blocks, 1 s step ---
        let mut st: Vec<(f64, f64)> = Vec::new();
        let mut j = 0;
        while j + ST_SUBBLOCKS <= n {
            let energy = self.weighted_energy(j, ST_SUBBLOCKS);
            if energy > 0.0 {
                st.push((energy, LOUDNESS_OFFSET + 10.0 * energy.log10()));
            }
            j += ST_STEP_SUBBLOCKS;
        }

        IntegratedResult {
            integrated_lufs,
            lra: loudness_range(&st),
            gating_blocks: blocks.len(),
        }
    }
}

/// Two-stage gating (absolute -70 LUFS, then relative) → energy mean → LUFS.
fn gated_mean_loudness(blocks: &[(f64, f64)], rel_gate_lu: f64) -> Option<f64> {
    let abs_energies: Vec<f64> = blocks
        .iter()
        .filter(|(_, l)| *l >= ABS_GATE_LUFS)
        .map(|(e, _)| *e)
        .collect();
    if abs_energies.is_empty() {
        return None;
    }
    let abs_mean = abs_energies.iter().sum::<f64>() / abs_energies.len() as f64;
    let rel_threshold = LOUDNESS_OFFSET + 10.0 * abs_mean.log10() + rel_gate_lu;
    let gated_energies: Vec<f64> = blocks
        .iter()
        .filter(|(_, l)| *l >= ABS_GATE_LUFS && *l >= rel_threshold)
        .map(|(e, _)| *e)
        .collect();
    if gated_energies.is_empty() {
        return None;
    }
    let mean = gated_energies.iter().sum::<f64>() / gated_energies.len() as f64;
    Some(LOUDNESS_OFFSET + 10.0 * mean.log10())
}

/// EBU Tech 3342 loudness range from gated short-term blocks.
fn loudness_range(st_blocks: &[(f64, f64)]) -> Option<f64> {
    let abs: Vec<&(f64, f64)> = st_blocks
        .iter()
        .filter(|(_, l)| *l >= ABS_GATE_LUFS)
        .collect();
    if abs.len() < 2 {
        return None;
    }
    let abs_mean = abs.iter().map(|(e, _)| *e).sum::<f64>() / abs.len() as f64;
    let rel_threshold = LOUDNESS_OFFSET + 10.0 * abs_mean.log10() + LRA_REL_GATE_LU;
    let mut loud: Vec<f64> = abs
        .iter()
        .map(|(_, l)| *l)
        .filter(|l| *l >= rel_threshold)
        .collect();
    if loud.len() < 2 {
        return None;
    }
    loud.sort_by(|a, b| a.partial_cmp(b).unwrap());
    Some(percentile(&loud, 95.0) - percentile(&loud, 10.0))
}

/// Linear-interpolated percentile of an ascending-sorted slice.
fn percentile(sorted: &[f64], p: f64) -> f64 {
    if sorted.is_empty() {
        return 0.0;
    }
    if sorted.len() == 1 {
        return sorted[0];
    }
    let rank = (p / 100.0) * (sorted.len() - 1) as f64;
    let lo = rank.floor() as usize;
    let hi = rank.ceil() as usize;
    if lo == hi {
        sorted[lo]
    } else {
        sorted[lo] + (rank - lo as f64) * (sorted[hi] - sorted[lo])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ebur128::{EbuR128, Mode};

    fn sine(rate: f32, secs: f32, freq: f32, amp: f32) -> Vec<f32> {
        (0..(rate * secs) as usize)
            .map(|n| (2.0 * std::f32::consts::PI * freq * n as f32 / rate).sin() * amp)
            .collect()
    }

    // Loud segment + quiet segment + silence, duplicated to stereo, interleaved.
    fn multi_level_stereo(rate: f32) -> Vec<f32> {
        let mut mono = sine(rate, 6.0, 1000.0, 0.5);
        mono.extend(sine(rate, 6.0, 1000.0, 0.05)); // ~20 dB down -> relative-gated out
        mono.extend(std::iter::repeat(0.0).take((rate * 3.0) as usize)); // below abs gate
        mono.iter().flat_map(|&s| [s, s]).collect()
    }

    #[test]
    fn integrated_matches_ebur128() {
        for rate in [44100.0_f32, 48000.0] {
            let interleaved = multi_level_stereo(rate);

            let mut ours = IntegratedLoudness::new(rate, 2);
            ours.add_interleaved(&interleaved);
            let got = ours
                .result()
                .integrated_lufs
                .expect("integrated should be defined");

            let mut reference = EbuR128::new(2, rate as u32, Mode::I).unwrap();
            reference.add_frames_f32(&interleaved).unwrap();
            let expected = reference.loudness_global().unwrap();

            assert!(
                (got - expected).abs() < 0.1,
                "{rate}Hz integrated: {got:.4} vs ebur128 {expected:.4} LUFS"
            );
        }
    }

    #[test]
    fn lra_matches_ebur128_within_tolerance() {
        let rate = 48000.0_f32;
        let interleaved = multi_level_stereo(rate);

        let mut ours = IntegratedLoudness::new(rate, 2);
        ours.add_interleaved(&interleaved);
        let got = ours.result().lra.expect("lra should be defined");

        let mut reference = EbuR128::new(2, rate as u32, Mode::I | Mode::LRA).unwrap();
        reference.add_frames_f32(&interleaved).unwrap();
        let expected = reference.loudness_range().unwrap();

        assert!(
            (got - expected).abs() < 1.0,
            "LRA: {got:.4} vs ebur128 {expected:.4} LU"
        );
    }

    #[test]
    fn streaming_chunks_match_single_shot() {
        let rate = 48000.0_f32;
        let interleaved = multi_level_stereo(rate);

        let mut single = IntegratedLoudness::new(rate, 2);
        single.add_interleaved(&interleaved);

        let mut chunked = IntegratedLoudness::new(rate, 2);
        for chunk in interleaved.chunks(1024 * 2) {
            chunked.add_interleaved(chunk);
        }

        let a = single.result().integrated_lufs.unwrap();
        let b = chunked.result().integrated_lufs.unwrap();
        assert!((a - b).abs() < 1e-9, "streaming mismatch: {a} vs {b}");
    }
}
