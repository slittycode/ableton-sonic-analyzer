/**
 * The page's single audiorective engine: one AudioContext shared by the Key
 * Check synth, Session Musician previews and the Beat Check player — so the
 * tonic drone, a note preview and the track all run on one sample clock.
 *
 * CLIENT-ONLY. `createEngine` builds the AudioContext when this module is
 * evaluated, and the Node unit suite renders components with
 * renderToStaticMarkup, where there is no AudioContext. So nothing may import
 * this module statically from a component tree that tests render. Reach it
 * only through a dynamic `import()`:
 *   - components/keyCheck/KeyCheckPanel.tsx → React.lazy(KeyCheckKeyboard)
 *   - components/beatCheck/BeatCheckPanel.tsx → React.lazy(BeatCheckPlayer)
 *   - services/midi/midiPreview.ts → import() inside previewNotes()
 * All of these only run after a user gesture in the browser. Do not "fix" an
 * EngineEnvironmentError with a typeof-window guard or a nullable engine —
 * find the static import that leaked and make it dynamic.
 */

import { createEngine } from '@audiorective/core';
import { createEngineContext } from '@audiorective/react';

import { BeatChecker } from './beatChecker';
import { KeySynth } from './keySynth';

export const engine = createEngine((ctx, { defineGraph }) => {
  const synth = new KeySynth(ctx);
  const beatCheck = new BeatChecker(ctx);
  defineGraph(() => [
    [synth, ctx.destination],
    [beatCheck, ctx.destination],
  ]);
  return { synth, beatCheck };
});

export const { EngineProvider, useEngine } = createEngineContext(engine);
