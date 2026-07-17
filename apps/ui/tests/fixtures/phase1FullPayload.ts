import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const contractFixturePath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../backend/tests/fixtures/contracts/phase1.v2.json',
);

export const phase1EnvelopeFixture = JSON.parse(
  readFileSync(contractFixturePath, 'utf8'),
) as Record<string, unknown>;

export const validBackendAnalyzeResponse = {
  requestId: 'req_123',
  phase1: phase1EnvelopeFixture,
  diagnostics: {
    backendDurationMs: 1420,
    engineVersion: '0.4.0',
    timings: {
      totalMs: 1560,
      analysisMs: 1420,
      serverOverheadMs: 140,
      flagsUsed: ['--transcribe'],
      fileSizeBytes: 543210,
      fileDurationSeconds: 184.2,
      msPerSecondOfAudio: 7.71,
    },
  },
};
