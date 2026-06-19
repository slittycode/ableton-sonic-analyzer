#!/usr/bin/env node
/**
 * check-style-discipline.mjs — design-token enforcement guard.
 *
 * Fails when source under an enforced directory uses:
 *   1. Arbitrary Tailwind font sizes  →  text-[13px] / text-[0.8rem]
 *      Use the --text-* scale tokens from src/index.css instead:
 *        text-nano · text-micro · text-meta · text-eyebrow · text-body-sm
 *        text-body · text-value · text-value-lg · text-value-xl
 *   2. Raw color hex literals          →  #ff8800 / #1a1a1a
 *      Use the semantic color tokens / Tailwind color utilities instead.
 *
 * Why this exists: a 2026-05-13 pass removed hardcoded hex, but it silently
 * returned because nothing enforced the rule. This guard is that enforcement.
 * ENFORCED_DIRS is widened directory-by-directory as the UI overhaul clears
 * each area, so the guard can never regress what it has already cleaned.
 *
 * Out of scope (allowlisted):
 *   - *.stories.tsx — dev-only Storybook artifacts, not shipped UI.
 *   - Canvas / color-math modules that compute colors CSS classes can't express.
 *   - src/utils/colorScales.ts — the sanctioned home for centralized palettes.
 *   - DenseDawConcept.tsx — the off-system ?view=daw demo (excluded from overhaul).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, basename, relative, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const uiRoot = join(here, '..');
const srcRoot = join(uiRoot, 'src');

// Directories currently held to the discipline. Widen as overhaul phases land.
const ENFORCED_DIRS = [join(srcRoot, 'components', 'ui')];

// Basenames exempt anywhere within enforced dirs.
const ALLOWLIST = new Set([
  'colorScales.ts',
  'DenseDawConcept.tsx',
  'RetroVisualizer.tsx',
  'SpectrogramViewer.tsx',
  'ChromaHeatmap.tsx',
  'SpectralEvolutionChart.tsx',
  'Sparkline.tsx',
  'TranscriptionPianoroll.tsx',
  'WaveformPlayer.tsx',
  'PianoRollCanvas.tsx',
]);

const RULES = [
  {
    id: 'arbitrary-text-size',
    re: /text-\[[0-9.]+(?:px|rem|em)\]/g,
    hint: 'use a --text-* scale token (e.g. text-meta, text-eyebrow, text-body-sm)',
  },
  {
    id: 'raw-hex-color',
    re: /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/g,
    hint: 'use a semantic color token (var(--color-*) or a Tailwind color utility)',
  },
];

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...walk(full));
    } else if (
      /\.(ts|tsx)$/.test(entry) &&
      !/\.stories\.tsx$/.test(entry) &&
      !/\.test\.tsx?$/.test(entry)
    ) {
      out.push(full);
    }
  }
  return out;
}

const violations = [];
for (const dir of ENFORCED_DIRS) {
  for (const file of walk(dir)) {
    if (ALLOWLIST.has(basename(file))) continue;
    const lines = readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, i) => {
      for (const rule of RULES) {
        rule.re.lastIndex = 0;
        let m;
        while ((m = rule.re.exec(line)) !== null) {
          violations.push({
            file: relative(uiRoot, file),
            line: i + 1,
            match: m[0],
            rule: rule.id,
            hint: rule.hint,
          });
        }
      }
    });
  }
}

if (violations.length > 0) {
  console.error(`\n✗ style-discipline: ${violations.length} violation(s)\n`);
  for (const v of violations) {
    console.error(`  ${v.file}:${v.line}  ${v.match}  [${v.rule}]`);
    console.error(`      → ${v.hint}`);
  }
  console.error('');
  process.exit(1);
}

console.log(
  '✓ style-discipline: no arbitrary text sizes or raw hex in enforced dirs',
);
