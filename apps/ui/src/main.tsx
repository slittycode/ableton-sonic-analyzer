import { createRoot } from 'react-dom/client';

import App from './App.tsx';
import DenseDawConcept from './components/DenseDawConcept';
import './index.css';
import { resolveAppView } from './utils/appView';

const activeView = resolveAppView(window.location.search);
const RootComponent = activeView === 'daw-concept' ? DenseDawConcept : App;

createRoot(document.getElementById('root')!).render(
  <RootComponent />,
);
