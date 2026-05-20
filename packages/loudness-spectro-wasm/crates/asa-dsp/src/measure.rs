// SPDX-License-Identifier: GPL-3.0-or-later
//
// Whole-buffer loudness convenience: one pass that yields integrated loudness +
// LRA (via the gated `IntegratedLoudness`) together with momentary-max,
// short-term-max, and true-peak (via the lifted `LoudnessProcessor`, fed in
// 100 ms hops so the maxima are sampled at EBU's momentary cadence).
//
// Kept in `asa-dsp` (not the wasm crate) so the orchestration is testable
// natively against the ebur128 oracle.

use crate::dsp::{AudioBlock, AudioProcessor};
use crate::integrated::IntegratedLoudness;
use crate::loudness::{LoudnessConfig, LoudnessProcessor};

#[derive(Debug, Clone, Copy)]
pub struct LoudnessMeasurement {
    pub integrated_lufs: Option<f64>,
    pub loudness_range: Option<f64>,
    pub momentary_max_lufs: f32,
    pub short_term_max_lufs: f32,
    pub true_peak_dbtp: f32,
    pub channels: usize,
    pub sample_rate: f32,
}

pub fn measure_loudness(samples: &[f32], channels: usize, sample_rate: f32) -> LoudnessMeasurement {
    let channels = channels.max(1);

    let mut integ = IntegratedLoudness::new(sample_rate, channels);
    integ.add_interleaved(samples);
    let ires = integ.result();

    let mut processor = LoudnessProcessor::new(LoudnessConfig {
        sample_rate,
        ..Default::default()
    });
    let frames_per_hop = ((f64::from(sample_rate.max(1.0)) * 0.1).round() as usize).max(1);
    let hop = frames_per_hop * channels;

    let mut momentary_max = f32::NEG_INFINITY;
    let mut short_term_max = f32::NEG_INFINITY;
    let mut true_peak = f32::NEG_INFINITY;

    for chunk in samples.chunks(hop) {
        if let Some(snap) = processor.process_block(&AudioBlock::new(chunk, channels, sample_rate)) {
            momentary_max = momentary_max.max(snap.momentary_loudness);
            short_term_max = short_term_max.max(snap.short_term_loudness);
            for c in 0..snap.channel_count {
                true_peak = true_peak.max(snap.true_peak_db[c]);
            }
        }
    }

    LoudnessMeasurement {
        integrated_lufs: ires.integrated_lufs,
        loudness_range: ires.lra,
        momentary_max_lufs: momentary_max,
        short_term_max_lufs: short_term_max,
        true_peak_dbtp: true_peak,
        channels,
        sample_rate,
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

    #[test]
    fn measure_loudness_matches_ebur128_integrated() {
        let rate = 48000.0_f32;
        let mut mono = sine(rate, 6.0, 1000.0, 0.5);
        mono.extend(sine(rate, 6.0, 1000.0, 0.05));
        let interleaved: Vec<f32> = mono.iter().flat_map(|&s| [s, s]).collect();

        let m = measure_loudness(&interleaved, 2, rate);
        let got = m.integrated_lufs.expect("integrated defined");

        let mut reference = EbuR128::new(2, rate as u32, Mode::I | Mode::TRUE_PEAK).unwrap();
        reference.add_frames_f32(&interleaved).unwrap();
        let expected = reference.loudness_global().unwrap();
        assert!(
            (got - expected).abs() < 0.1,
            "integrated {got:.4} vs {expected:.4}"
        );

        // Sanity: maxima finite, true peak near the reference's true peak.
        assert!(m.momentary_max_lufs.is_finite() && m.short_term_max_lufs.is_finite());
        let ref_tp = 20.0 * reference.true_peak(0).unwrap().log10();
        assert!(
            (f64::from(m.true_peak_dbtp) - ref_tp).abs() < 0.2,
            "true peak {:.3} vs {:.3} dBTP",
            m.true_peak_dbtp,
            ref_tp
        );
    }
}
