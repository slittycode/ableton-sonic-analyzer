import { describe, expect, it, vi } from 'vitest';

describe('resolveAppConfig', () => {
  it('defaults the Phase 2 config gate to on when the env flag is unset', async () => {
    const {
      canRunGeminiPhase2,
      hasGeminiPhase2ApiKey,
      isGeminiPhase2ConfigEnabled,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig({
      VITE_API_BASE_URL: undefined,
      VITE_ENABLE_PHASE2_GEMINI: undefined,
      VITE_GEMINI_API_KEY: undefined,
    });

    expect(config.enablePhase2Gemini).toBe(true);
    expect(isGeminiPhase2ConfigEnabled(config)).toBe(true);
    expect(hasGeminiPhase2ApiKey(config)).toBe(false);
    expect(canRunGeminiPhase2(config)).toBe(false);
  });

  it('treats a configured API key independently from the env kill switch', async () => {
    const {
      canRunGeminiPhase2,
      hasGeminiPhase2ApiKey,
      isGeminiPhase2ConfigEnabled,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig({
      VITE_ENABLE_PHASE2_GEMINI: 'false',
      VITE_GEMINI_API_KEY: 'gemini-key',
    });

    expect(isGeminiPhase2ConfigEnabled(config)).toBe(false);
    expect(hasGeminiPhase2ApiKey(config)).toBe(true);
    expect(canRunGeminiPhase2(config)).toBe(false);
  });

  it('allows runtime overrides to replace build-time env values', async () => {
    const {
      canRunGeminiPhase2,
      hasGeminiPhase2ApiKey,
      isGeminiPhase2ConfigEnabled,
      resolveAppConfig,
    } = await vi.importActual<typeof import('../../src/config')>('../../src/config');

    const config = resolveAppConfig(
      {
        VITE_ENABLE_PHASE2_GEMINI: 'true',
        VITE_GEMINI_API_KEY: 'build-key',
      },
      {
        VITE_ENABLE_PHASE2_GEMINI: 'false',
        VITE_GEMINI_API_KEY: '',
      },
    );

    expect(isGeminiPhase2ConfigEnabled(config)).toBe(false);
    expect(hasGeminiPhase2ApiKey(config)).toBe(false);
    expect(canRunGeminiPhase2(config)).toBe(false);
  });
});
