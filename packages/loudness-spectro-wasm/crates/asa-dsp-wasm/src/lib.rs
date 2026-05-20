// SPDX-License-Identifier: GPL-3.0-or-later
//
// wasm-bindgen boundary. Audio is passed in as decoded interleaved f32 PCM at
// the file's native sample rate (do NOT resample via decodeAudioData first, or
// EBU conformance breaks). Undefined results surface as NaN to JS.

use asa_dsp::dsp::{AudioBlock, AudioProcessor};
use asa_dsp::measure::measure_loudness as core_measure_loudness;
use asa_dsp::spectrogram::{SpectrogramColumn, SpectrogramConfig, SpectrogramProcessor};
use asa_dsp::spectrum::averaged_spectrum;
use asa_dsp::window::WindowKind;
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

const DEFAULT_SPECTROGRAM_FFT_SIZE: usize = 2048;
/// Offline default hop (openmeters' live-display default is 64 — far too dense
/// for whole-file analysis).
const DEFAULT_SPECTROGRAM_HOP: usize = 512;
const DEFAULT_MAX_POINTS: usize = 300_000;
const DEFAULT_SPECTRUM_FFT_SIZE: usize = 4096;

/// Sparse spectral-reassignment spectrogram. `points` is a flat
/// `[absTime, freqHz, magDb, …]` triple stream (`point_count` triples).
#[wasm_bindgen]
pub struct SpectrogramResult {
    points: Vec<f32>,
    pub point_count: u32,
    pub num_columns: u32,
    pub hop_seconds: f32,
    pub max_freq_hz: f32,
}

#[wasm_bindgen]
impl SpectrogramResult {
    /// Flat `[absTime, freqHz, magDb]` triples → `Float32Array`.
    #[wasm_bindgen(getter)]
    pub fn points(&self) -> Vec<f32> {
        self.points.clone()
    }
}

/// Compute a spectral-reassignment spectrogram for a whole interleaved buffer
/// (mixed to mono internally). Output is a sparse set of reassigned points,
/// capped to `max_points` via a deterministic single-pass reservoir.
///
/// `fft_size`/`hop`/`max_points` of 0 fall back to 2048 / 512 / 300_000.
#[wasm_bindgen(js_name = reassignedSpectrogram)]
pub fn reassigned_spectrogram(
    samples: &[f32],
    sample_rate: f32,
    channels: usize,
    fft_size: usize,
    hop: usize,
    max_points: usize,
) -> SpectrogramResult {
    let fft_size = if fft_size == 0 {
        DEFAULT_SPECTROGRAM_FFT_SIZE
    } else {
        fft_size
    };
    let hop = if hop == 0 { DEFAULT_SPECTROGRAM_HOP } else { hop };
    let cap = if max_points == 0 {
        DEFAULT_MAX_POINTS
    } else {
        max_points
    };

    let cfg = SpectrogramConfig {
        sample_rate,
        fft_size,
        hop_size: hop,
        window: WindowKind::Hann,
        use_reassignment: true,
        ..Default::default()
    };
    let mut processor = SpectrogramProcessor::new(cfg);
    let block = AudioBlock::new(samples, channels.max(1), sample_rate);
    let update = processor.process_block(&block);

    // Normalized parameters actually used by the processor.
    let cfgn = processor.config();
    let sr = cfgn.sample_rate;
    let hop_used = cfgn.hop_size as f32;
    let hilbert_len = (cfgn.fft_size * 2).next_power_of_two().max(2);
    let half_latency = (hilbert_len as f32 - 1.0) * 0.5; // window-center origin

    let mut points: Vec<f32> = Vec::new();
    let mut seen: u64 = 0;
    let mut rng: u64 = 0x9E37_79B9_7F4A_7C15;
    let mut num_columns: u32 = 0;

    if let Some(update) = update {
        for (col_index, col) in update.new_columns.iter().enumerate() {
            let SpectrogramColumn::Reassigned(pts) = col else {
                continue;
            };
            let col_time = col_index as f32 * hop_used + half_latency;
            for p in pts {
                if !p.magnitude_db.is_finite() {
                    continue; // sentinel (filtered bin)
                }
                let abs_time = (col_time - p.time_offset * hop_used) / sr;
                // Deterministic single-pass reservoir: O(1) memory beyond `cap`.
                if (seen as usize) < cap {
                    points.push(abs_time);
                    points.push(p.freq_hz);
                    points.push(p.magnitude_db);
                } else {
                    let j = (next_rand(&mut rng) % (seen + 1)) as usize;
                    if j < cap {
                        points[j * 3] = abs_time;
                        points[j * 3 + 1] = p.freq_hz;
                        points[j * 3 + 2] = p.magnitude_db;
                    }
                }
                seen += 1;
            }
        }
        num_columns = update.new_columns.len() as u32;
    }

    let point_count = (points.len() / 3) as u32;
    SpectrogramResult {
        points,
        point_count,
        num_columns,
        hop_seconds: hop_used / sr,
        max_freq_hz: sr * 0.5,
    }
}

#[inline]
fn next_rand(state: &mut u64) -> u64 {
    // SplitMix-style LCG step; high bits used to avoid low-bit modulo bias.
    *state = state
        .wrapping_mul(6_364_136_223_846_793_005)
        .wrapping_add(1_442_695_040_888_963_407);
    *state >> 33
}

/// A-weighted average spectrum (whole file). All three arrays are length
/// `fft_size/2 + 1`.
#[wasm_bindgen]
pub struct SpectrumResult {
    frequencies: Vec<f32>,
    magnitudes_db: Vec<f32>,
    magnitudes_unweighted_db: Vec<f32>,
    pub bin_hz: f32,
}

#[wasm_bindgen]
impl SpectrumResult {
    #[wasm_bindgen(getter)]
    pub fn frequencies(&self) -> Vec<f32> {
        self.frequencies.clone()
    }
    #[wasm_bindgen(getter)]
    pub fn magnitudes_db(&self) -> Vec<f32> {
        self.magnitudes_db.clone()
    }
    #[wasm_bindgen(getter)]
    pub fn magnitudes_unweighted_db(&self) -> Vec<f32> {
        self.magnitudes_unweighted_db.clone()
    }
}

/// Whole-file averaged A-weighted spectrum from interleaved PCM. `fft_size` of 0
/// falls back to 4096.
#[wasm_bindgen(js_name = aWeightedSpectrum)]
pub fn a_weighted_spectrum(
    samples: &[f32],
    sample_rate: f32,
    channels: usize,
    fft_size: usize,
) -> SpectrumResult {
    let fft_size = if fft_size == 0 {
        DEFAULT_SPECTRUM_FFT_SIZE
    } else {
        fft_size
    };
    let s = averaged_spectrum(samples, channels.max(1), sample_rate, fft_size);
    let bin_hz = if fft_size > 0 {
        sample_rate / fft_size as f32
    } else {
        0.0
    };
    SpectrumResult {
        frequencies: s.frequency_bins,
        magnitudes_db: s.magnitudes_db,
        magnitudes_unweighted_db: s.magnitudes_unweighted_db,
        bin_hz,
    }
}
