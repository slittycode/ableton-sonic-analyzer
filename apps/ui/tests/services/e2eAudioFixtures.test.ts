import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import {
  INLINE_SIZE_LIMIT,
  writeMusicalReferenceWav,
  writeOversizedMusicalWav,
} from '../e2e/support/audioFixtures';

const tempDirs: string[] = [];

async function createTempFile(name: string): Promise<string> {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'sonic-e2e-fixtures-'));
  tempDirs.push(tempDir);
  return path.join(tempDir, name);
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => fs.rm(dir, { recursive: true, force: true })));
});

describe('e2e audio fixtures', () => {
  it('writes a compact musical reference wav for inline Gemini coverage', async () => {
    const filePath = await createTempFile('reference.wav');
    const fixture = await writeMusicalReferenceWav(filePath);
    const buffer = await fs.readFile(filePath);

    expect(fixture.filePath).toBe(filePath);
    expect(fixture.sampleRate).toBeGreaterThanOrEqual(44_100);
    expect(fixture.durationSeconds).toBeGreaterThan(8);
    expect(fixture.byteLength).toBe(buffer.byteLength);
    expect(fixture.byteLength).toBeLessThan(INLINE_SIZE_LIMIT);
    expect(buffer.subarray(0, 4).toString('ascii')).toBe('RIFF');
    expect(buffer.subarray(8, 12).toString('ascii')).toBe('WAVE');
    expect(buffer.subarray(36, 40).toString('ascii')).toBe('data');
  });

  it('writes an oversized wav that forces the Gemini Files API path', async () => {
    const filePath = await createTempFile('oversized.wav');
    const fixture = await writeOversizedMusicalWav(filePath);
    const stats = await fs.stat(filePath);

    expect(fixture.filePath).toBe(filePath);
    expect(fixture.byteLength).toBe(stats.size);
    expect(fixture.byteLength).toBeGreaterThan(INLINE_SIZE_LIMIT);
    expect(fixture.durationSeconds).toBeGreaterThan(20);
  }, 60_000);
});
