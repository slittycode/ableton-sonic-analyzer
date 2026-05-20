// SPDX-License-Identifier: GPL-3.0-or-later
//
// Native CLI: decode a WAV at its NATIVE sample rate (no resampling — that
// would break ±0.1 LU EBU conformance) and print asa-dsp's loudness summary as
// a single JSON line. Used by scripts/pyloudnorm_crosscheck.py as the ASA side
// of an independent second-implementation cross-check.

use std::env;
use std::process;

use asa_dsp::measure::measure_loudness;

/// `Some(finite)` -> 4-decimal number; everything else (None / NaN / ±Inf) ->
/// JSON `null`, matching the wasm boundary's "undefined surfaces as null".
fn fmt(v: Option<f64>) -> String {
    match v {
        Some(x) if x.is_finite() => format!("{x:.4}"),
        _ => "null".to_string(),
    }
}

fn main() {
    let path = match env::args().nth(1) {
        Some(p) => p,
        None => {
            eprintln!("usage: measure-cli <path-to.wav>");
            process::exit(2);
        }
    };

    match run(&path) {
        Ok(line) => println!("{line}"),
        Err(e) => {
            eprintln!("measure-cli: {path}: {e}");
            process::exit(1);
        }
    }
}

fn run(path: &str) -> Result<String, Box<dyn std::error::Error>> {
    let mut reader = hound::WavReader::open(path)?;
    let spec = reader.spec();
    let channels = (spec.channels as usize).max(1);
    let sample_rate = spec.sample_rate as f32;

    // Decode to interleaved f32 at the file's native rate.
    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().collect::<Result<Vec<_>, _>>()?,
        hound::SampleFormat::Int => {
            // hound sign-extends each integer sample into i32; full scale for
            // the declared bit depth is 2^(bits-1).
            let divisor = (1i64 << spec.bits_per_sample.saturating_sub(1)) as f32;
            reader
                .samples::<i32>()
                .map(|s| s.map(|v| v as f32 / divisor))
                .collect::<Result<Vec<_>, _>>()?
        }
    };

    let m = measure_loudness(&samples, channels, sample_rate);

    Ok(format!(
        "{{\"integrated\":{},\"momentaryMax\":{},\"shortTermMax\":{},\"truePeak\":{},\"lra\":{}}}",
        fmt(m.integrated_lufs),
        fmt(Some(f64::from(m.momentary_max_lufs))),
        fmt(Some(f64::from(m.short_term_max_lufs))),
        fmt(Some(f64::from(m.true_peak_dbtp))),
        fmt(m.loudness_range),
    ))
}
