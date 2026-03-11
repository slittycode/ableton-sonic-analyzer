import { test, expect } from '@playwright/test';

test('landing shell locks the intended Ableton palette and opaque root surfaces', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/', { waitUntil: 'networkidle' });

  const styles = await page.evaluate(() => {
    const root = document.getElementById('root');
    const shell = document.querySelector('[data-testid="app-shell"]');
    const toolbar = document.querySelector('[data-testid="app-toolbar"]');
    const inputPanel = document.querySelector('[data-testid="input-panel"]');

    if (!root || !shell || !toolbar || !inputPanel) {
      throw new Error('Expected shell test hooks were not found.');
    }

    const shellRect = shell.getBoundingClientRect();
    const toolbarRect = toolbar.getBoundingClientRect();

    return {
      htmlBg: getComputedStyle(document.documentElement).backgroundColor,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      rootBg: getComputedStyle(root).backgroundColor,
      rootColorScheme: getComputedStyle(document.documentElement).colorScheme,
      shellBg: getComputedStyle(shell).backgroundColor,
      shellBorder: getComputedStyle(shell).borderTopColor,
      toolbarBg: getComputedStyle(toolbar).backgroundColor,
      inputPanelBg: getComputedStyle(inputPanel).backgroundColor,
      shellWidth: shellRect.width,
      toolbarHeight: toolbarRect.height,
    };
  });

  expect(styles.htmlBg).toBe('rgb(43, 43, 43)');
  expect(styles.bodyBg).toBe('rgb(43, 43, 43)');
  expect(styles.rootBg).toBe('rgb(43, 43, 43)');
  expect(styles.rootColorScheme).toContain('dark');
  expect(styles.shellBg).toBe('rgb(60, 60, 60)');
  expect(styles.shellBorder).toBe('rgb(26, 26, 26)');
  expect(styles.toolbarBg).toBe('rgb(34, 34, 34)');
  expect(styles.inputPanelBg).toBe('rgb(68, 68, 68)');
  expect(styles.shellWidth).toBeGreaterThan(1000);
  expect(styles.toolbarHeight).toBeGreaterThanOrEqual(39);
  expect(styles.toolbarHeight).toBeLessThanOrEqual(41);
});
