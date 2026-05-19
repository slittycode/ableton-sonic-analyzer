import { createRoot } from 'react-dom/client';
import { MotionConfig } from 'motion/react';

import App from './App.tsx';
import DenseDawConcept from './components/DenseDawConcept';
import './index.css';
import { resolveAppView } from './utils/appView';

const activeView = resolveAppView(window.location.search);
const RootComponent = activeView === 'daw-concept' ? DenseDawConcept : App;

// reducedMotion="user" makes every motion.* component honor the OS-level
// prefers-reduced-motion setting: transform/layout animations are disabled
// while opacity fades are kept. The CSS @media block in index.css covers the
// CSS keyframes + Tailwind transitions; this covers the JS-driven Motion
// entrance animations the CSS rule can't reach.
createRoot(document.getElementById('root')!).render(
  <MotionConfig reducedMotion="user">
    <RootComponent />
  </MotionConfig>,
);
