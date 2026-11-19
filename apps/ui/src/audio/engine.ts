/**
 * The page's single audiorective engine: one AudioContext, one KeySynth.
 *
 * CLIENT-ONLY. `createEngine` builds the AudioContext when this module is
 * evaluated, and the Node unit suite renders components with
 * renderToStaticMarkup, where there is no AudioContext. So nothing may import
 * this module statically from a component tree that tests render. Reach it
 * only through a dynamic `import()`:
 *   - components/keyCheck/KeyCheckPanel.tsx → React.lazy(KeyCheckKeyboard)
 *   - services/midi/midiPreview.ts → import() inside previewNotes()
 * Both only run after a user gesture in the browser. Do not "fix" an
 * EngineEnvironmentError with a typeof-window guard or a nullable engine —
 * find the static import that leaked and make it dynamic.
 */

import { createEngine } from '@audiorective/core';
import { createEngineContext } from '@audiorective/react';

import { KeySynth } from './keySynth';

export const engine = createEngine((ctx, { defineGraph }) => {
  const synth = new KeySynth(ctx);
  defineGraph(() => [[synth, ctx.destination]]);
  return { synth };
});

export const { EngineProvider, useEngine } = createEngineContext(engine);
