// SPDX-License-Identifier: GPL-3.0-or-later
//
// asa-dsp: BS.1770-5 loudness + true-peak (lifted from openmeters) plus a
// purpose-built EBU R128 gated-integrated-loudness / LRA layer (openmeters is a
// live meter and computes neither integrated loudness nor LRA).
//
// Portions vendored from openmeters (https://github.com/httpsworldview/openmeters),
// Copyright (C) 2026 Maika Namuo, GPL-3.0-or-later. See per-file headers.

pub mod dsp;
pub mod integrated;
pub mod loudness;
pub mod measure;
pub mod util;
