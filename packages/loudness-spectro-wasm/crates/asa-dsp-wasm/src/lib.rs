// SPDX-License-Identifier: GPL-3.0-or-later
//
// wasm-bindgen boundary. Audio is passed in as decoded interleaved f32 PCM at
// the file's native sample rate (do NOT resample via decodeAudioData first, or
// EBU conformance breaks). Undefined results surface as NaN to JS.

use asa_dsp::measure::measure_loudness as core_measure_loudness;
use wasm_bindgen::prelude::*;

/// BS.1770-5 / EBU R128 loudness summary. `NaN` means "undefined"
/// (e.g. integrated loudness when no gating block passed the gates).
#[wasm_bindgen]
#[derive(Clone, Copy)]
pub struct LoudnessResult {
    pub integrated_lufs: f64,
    pub loudness_range: f64,
    pub momentary_max_lufs: f64,
    pub short_term_max_lufs: f64,
    pub true_peak_dbtp: f64,
    pub channels: u32,
    pub sample_rate: f32,
}

/// Measure BS.1770-5 loudness for a whole interleaved PCM buffer.
///
/// `samples` is interleaved f32 (`[L,R,L,R,...]` for stereo). `channels` and
/// `sample_rate` describe that buffer. Returns integrated LUFS, LRA,
/// momentary/short-term maxima, and max true-peak (dBTP).
#[wasm_bindgen(js_name = measureLoudness)]
pub fn measure_loudness(samples: &[f32], channels: usize, sample_rate: f32) -> LoudnessResult {
    let m = core_measure_loudness(samples, channels, sample_rate);
    LoudnessResult {
        integrated_lufs: m.integrated_lufs.unwrap_or(f64::NAN),
        loudness_range: m.loudness_range.unwrap_or(f64::NAN),
        momentary_max_lufs: f64::from(m.momentary_max_lufs),
        short_term_max_lufs: f64::from(m.short_term_max_lufs),
        true_peak_dbtp: f64::from(m.true_peak_dbtp),
        channels: m.channels as u32,
        sample_rate: m.sample_rate,
    }
}
