import { describe, expect, it } from 'vitest';

import {
  getAppViewHref,
  resolveAppView,
} from '../../src/utils/appView';

describe('app view selection', () => {
  it('defaults to the current application when no view is requested', () => {
    expect(resolveAppView('')).toBe('app');
    expect(resolveAppView('?view=unknown')).toBe('app');
  });

  it('activates the dense DAW concept when requested by query string', () => {
    expect(resolveAppView('?view=daw')).toBe('daw-concept');
    expect(resolveAppView('view=daw')).toBe('daw-concept');
  });

  it('builds stable links for switching between the live app and the concept', () => {
    expect(getAppViewHref('app')).toBe('/');
    expect(getAppViewHref('daw-concept')).toBe('/?view=daw');
  });
});
