// SPDX-License-Identifier: GPL-3.0-or-later
// Vendored from openmeters src/dsp.rs, Copyright (C) 2026 Maika Namuo.
//
// Modified for wasm32-unknown-unknown: the original `AudioBlock` carried a
// `timestamp: Instant` set via `Instant::now()`, which PANICS on
// wasm32-unknown-unknown (no clock). The DSP never reads it, so it is removed.

#[derive(Debug, Clone, Copy)]
pub struct AudioBlock<'a> {
    pub samples: &'a [f32],
    pub channels: usize,
    pub sample_rate: f32,
}

impl<'a> AudioBlock<'a> {
    pub fn new(samples: &'a [f32], channels: usize, sample_rate: f32) -> Self {
        Self {
            samples,
            channels,
            sample_rate,
        }
    }

    pub fn frame_count(&self) -> usize {
        self.samples.len() / self.channels.max(1)
    }
}

pub trait AudioProcessor {
    type Output;

    fn process_block(&mut self, block: &AudioBlock<'_>) -> Option<Self::Output>;
    fn reset(&mut self);
}

pub trait Reconfigurable<Cfg> {
    fn update_config(&mut self, config: Cfg);
}
