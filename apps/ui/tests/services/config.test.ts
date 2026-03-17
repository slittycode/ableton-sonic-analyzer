import { describe, expect, it, vi } from 'vitest';

describe('resolveAppConfig', () => {
  it('defaults the Phase 2 config gate to on when the env flag is unset', async () => {
    const {
      isGeminiPhase2ConfigEnabled,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig({
      VITE_API_BASE_URL: undefined,
      VITE_ENABLE_PHASE2_GEMINI: undefined,
    });

    expect(config.enablePhase2Gemini).toBe(true);
    expect(isGeminiPhase2ConfigEnabled(config)).toBe(true);
  });

  it('disables Phase 2 when the env kill-switch is set to false', async () => {
    const {
      isGeminiPhase2ConfigEnabled,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig({
      VITE_ENABLE_PHASE2_GEMINI: 'false',
    });

    expect(isGeminiPhase2ConfigEnabled(config)).toBe(false);
  });

  it('allows runtime overrides to replace build-time env values', async () => {
    const {
      isGeminiPhase2ConfigEnabled,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig(
      {
        VITE_ENABLE_PHASE2_GEMINI: 'true',
      },
      {
        VITE_ENABLE_PHASE2_GEMINI: 'false',
      },
    );

    expect(isGeminiPhase2ConfigEnabled(config)).toBe(false);
  });
});
