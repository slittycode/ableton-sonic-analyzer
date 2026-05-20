// SPDX-License-Identifier: GPL-3.0-or-later
//
// EBU Tech 3341 / 3342 ABSOLUTE conformance for asa-dsp's loudness path.
//
// The unit tests in `measure.rs` / `integrated.rs` cross-check the DSP against
// the independent `ebur128` crate — they prove two implementations AGREE, but
// never assert the spec's absolute targets (-23.0 / -33.0 LUFS). This file adds
// that: synthesized, network-free signals whose correct EBU reading is known a
// priori (mirroring the backend's proven pattern in
// apps/backend/tests/test_loudness_r128.py — a dual-mono 1 kHz sine at peak
// -X dBFS reads -X LUFS, because K-weighting's ~+0.691 dB gain at 1 kHz exactly
// cancels the -0.691 LUFS offset).
//
// `ebur128` is retained as a second oracle for the gating, LRA, and true-peak
// paths (where the absolute target is harder to reason about by hand).
//
// An OPTIONAL path runs against the official EBU compliance set when
// `ASA_EBU_TESTSET_DIR` points at it; unset, the suite stays network-free.

use asa_dsp::measure::measure_loudness;
use ebur128::{EbuR128, Mode};

/// EBU "EBU Mode" loudness-meter compliance tolerance for integrated/momentary/
/// short-term LUFS.
const LUFS_TOL: f64 = 0.1;

/// Dual-mono interleaved-stereo sine at a given peak dBFS. Both channels carry
/// the same signal — the EBU Tech 3341 cases 1 and 2 are defined this way.
fn stereo_sine(rate: f32, secs: f32, freq: f32, peak_dbfs: f32) -> Vec<f32> {
    let amp = 10f32.powf(peak_dbfs / 20.0);
    let n = (rate * secs) as usize;
    let mut out = Vec::with_capacity(n * 2);
    for i in 0..n {
        let s = (2.0 * std::f32::consts::PI * freq * i as f32 / rate).sin() * amp;
        out.push(s);
        out.push(s);
    }
    out
}

/// Tech 3341 Case 1: dual-mono 1 kHz sine at peak -23 dBFS, 20 s, must read
/// -23.0 LUFS integrated. For a constant-power tone the momentary (400 ms) and
/// short-term (3 s) maxima converge to the same value.
#[test]
fn tech3341_case1_minus23_absolute() {
    for rate in [44_100.0_f32, 48_000.0] {
        let buf = stereo_sine(rate, 20.0, 1000.0, -23.0);
        let m = measure_loudness(&buf, 2, rate);

        let integrated = m.integrated_lufs.expect("integrated defined");
        assert!(
            (integrated - (-23.0)).abs() < LUFS_TOL,
            "{rate}Hz integrated {integrated:.4} != -23.0 ±{LUFS_TOL}"
        );
        assert!(
            (f64::from(m.momentary_max_lufs) - (-23.0)).abs() < LUFS_TOL,
            "{rate}Hz momentary_max {:.4} != -23.0 ±{LUFS_TOL}",
            m.momentary_max_lufs
        );
        assert!(
            (f64::from(m.short_term_max_lufs) - (-23.0)).abs() < LUFS_TOL,
            "{rate}Hz short_term_max {:.4} != -23.0 ±{LUFS_TOL}",
            m.short_term_max_lufs
        );
    }
}

/// Tech 3341 Case 2: same as Case 1 but at peak -33 dBFS -> -33.0 LUFS. A pass
/// on Case 1 but a fail here would point at a non-linearity in the path.
#[test]
fn tech3341_case2_minus33_absolute() {
    for rate in [44_100.0_f32, 48_000.0] {
        let buf = stereo_sine(rate, 20.0, 1000.0, -33.0);
        let m = measure_loudness(&buf, 2, rate);

        let integrated = m.integrated_lufs.expect("integrated defined");
        assert!(
            (integrated - (-33.0)).abs() < LUFS_TOL,
            "{rate}Hz integrated {integrated:.4} != -33.0 ±{LUFS_TOL}"
        );
        assert!(
            (f64::from(m.momentary_max_lufs) - (-33.0)).abs() < LUFS_TOL,
            "{rate}Hz momentary_max {:.4} != -33.0 ±{LUFS_TOL}",
            m.momentary_max_lufs
        );
        assert!(
            (f64::from(m.short_term_max_lufs) - (-33.0)).abs() < LUFS_TOL,
            "{rate}Hz short_term_max {:.4} != -33.0 ±{LUFS_TOL}",
            m.short_term_max_lufs
        );
    }
}

/// Gating cross-check: loud (-23, 6 s) + quiet (-33, 6 s) + silence (3 s).
/// asa-dsp's two-stage-gated integrated loudness must track `ebur128`'s
/// `Mode::I` within 0.1 LU (both apply the same absolute/relative gates).
#[test]
fn gating_integrated_matches_ebur128() {
    let rate = 48_000.0_f32;
    let mut buf = stereo_sine(rate, 6.0, 1000.0, -23.0);
    buf.extend(stereo_sine(rate, 6.0, 1000.0, -33.0));
    buf.extend(std::iter::repeat(0.0).take((rate * 3.0) as usize * 2)); // below abs gate

    let got = measure_loudness(&buf, 2, rate)
        .integrated_lufs
        .expect("integrated defined");

    let mut reference = EbuR128::new(2, rate as u32, Mode::I).unwrap();
    reference.add_frames_f32(&buf).unwrap();
    let expected = reference.loudness_global().unwrap();

    assert!(
        (got - expected).abs() < LUFS_TOL,
        "integrated {got:.4} vs ebur128 {expected:.4} LUFS"
    );
}

/// Tech 3342 LRA (absolute): 6 s at -23 then 6 s at -33 — both above the -20 LU
/// relative gate, so P95 lands at -23 and P10 at -33 -> LRA ≈ 10 LU. Also
/// cross-checked against `ebur128` `Mode::LRA`.
#[test]
fn tech3342_lra_absolute_and_matches_ebur128() {
    let rate = 48_000.0_f32;
    let mut buf = stereo_sine(rate, 6.0, 1000.0, -23.0);
    buf.extend(stereo_sine(rate, 6.0, 1000.0, -33.0));

    let lra = measure_loudness(&buf, 2, rate)
        .loudness_range
        .expect("lra defined");
    assert!((lra - 10.0).abs() < 1.0, "LRA {lra:.4} != ~10 LU (±1)");

    let mut reference = EbuR128::new(2, rate as u32, Mode::I | Mode::LRA).unwrap();
    reference.add_frames_f32(&buf).unwrap();
    let expected = reference.loudness_range().unwrap();
    assert!(
        (lra - expected).abs() < 1.0,
        "LRA {lra:.4} vs ebur128 {expected:.4} LU"
    );
}

/// True-peak: a near-Nyquist sine (17 kHz @ 48 kHz, amp 0.9) exposes inter-
/// sample peaks. asa-dsp's dBTP must track `ebur128`'s true-peak within 0.2 dB.
#[test]
fn true_peak_matches_ebur128() {
    let rate = 48_000.0_f32;
    let peak_dbfs = 20.0 * 0.9_f32.log10(); // amp 0.9
    let buf = stereo_sine(rate, 1.0, 17_000.0, peak_dbfs);

    let got = f64::from(measure_loudness(&buf, 2, rate).true_peak_dbtp);

    let mut reference = EbuR128::new(2, rate as u32, Mode::TRUE_PEAK).unwrap();
    reference.add_frames_f32(&buf).unwrap();
    let expected = 20.0 * reference.true_peak(0).unwrap().log10();

    assert!(
        (got - expected).abs() < 0.2,
        "true peak {got:.4} vs ebur128 {expected:.4} dBTP"
    );
}

/// OPTIONAL: run against the official EBU Tech 3341/3342 compliance set when
/// `ASA_EBU_TESTSET_DIR` is set (see scripts/fetch-ebu-testset.sh). Unset, the
/// default `cargo test` stays network-free.
#[test]
fn official_ebu_testset_when_present() {
    let Ok(dir) = std::env::var("ASA_EBU_TESTSET_DIR") else {
        eprintln!(
            "[skip] ASA_EBU_TESTSET_DIR unset — official EBU set not run \
             (synth conformance above covers the absolute -23/-33 targets)."
        );
        return;
    };

    // filename-substring -> expected integrated LUFS, transcribed from a PRIMARY
    // source (EBU Tech 3341 §2.1). Intentionally EMPTY: do NOT guess these
    // values or filenames. Populate from the spec when running the official set;
    // an unmatched WAV is reported as a skip, never a phantom pass/fail.
    const EXPECTED: &[(&str, f64)] = &[
        // e.g. ("seq-3341-1-16bit.wav", -23.0),
    ];

    let mut checked = 0usize;
    let mut skipped = 0usize;
    for entry in std::fs::read_dir(&dir).expect("read ASA_EBU_TESTSET_DIR") {
        let path = entry.expect("dir entry").path();
        if path.extension().and_then(|e| e.to_str()) != Some("wav") {
            continue;
        }
        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or_default()
            .to_string();

        let Some(&(_, expected)) = EXPECTED.iter().find(|(n, _)| name.contains(n)) else {
            eprintln!("[skip] {name}: no expected value in table (add it from EBU Tech 3341 §2.1)");
            skipped += 1;
            continue;
        };

        let (samples, channels, rate) = read_wav(&path);
        let got = measure_loudness(&samples, channels, rate)
            .integrated_lufs
            .unwrap_or_else(|| panic!("{name}: integrated undefined"));
        assert!(
            (got - expected).abs() < LUFS_TOL,
            "{name}: integrated {got:.4} != {expected:.4} ±{LUFS_TOL}"
        );
        checked += 1;
    }

    if checked == 0 {
        eprintln!(
            "[skip] official EBU set at {dir}: {skipped} WAV(s) found but the \
             EXPECTED table has no matching entries — nothing asserted. \
             Populate EXPECTED from EBU Tech 3341 §2.1 to enable this path."
        );
    }
}

/// Decode a WAV to interleaved f32 at its NATIVE rate (no resampling).
fn read_wav(path: &std::path::Path) -> (Vec<f32>, usize, f32) {
    let mut reader = hound::WavReader::open(path).expect("open wav");
    let spec = reader.spec();
    let channels = (spec.channels as usize).max(1);
    let rate = spec.sample_rate as f32;
    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => {
            reader.samples::<f32>().map(|s| s.expect("sample")).collect()
        }
        hound::SampleFormat::Int => {
            let divisor = (1i64 << spec.bits_per_sample.saturating_sub(1)) as f32;
            reader
                .samples::<i32>()
                .map(|s| s.expect("sample") as f32 / divisor)
                .collect()
        }
    };
    (samples, channels, rate)
}
