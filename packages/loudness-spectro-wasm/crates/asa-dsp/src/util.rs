// SPDX-License-Identifier: GPL-3.0-or-later
// Carved from openmeters src/util/audio.rs, Copyright (C) 2026 Maika Namuo.
//
// Only the loudness-path primitives are lifted here; the original module also
// carries serde-backed settings enums, a window-coefficient cache, ERB scaling,
// etc., none of which the loudness path needs.

pub const DEFAULT_SAMPLE_RATE: f32 = 48_000.0;

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
