import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { DiagnosticLog } from '../../src/components/DiagnosticLog';
import { DiagnosticLogEntry } from '../../src/types';

const baseLog: DiagnosticLogEntry = {
  model: 'local-dsp-engine',
  phase: 'Phase 1: Local DSP analysis',
  promptLength: 0,
  responseLength: 0,
  durationMs: 42000,
  audioMetadata: {
    name: 'track.mp3',
    size: 1024,
    type: 'audio/mpeg',
  },
  timestamp: '2026-03-06T02:00:00.000Z',
  source: 'backend',
  status: 'error',
  message: 'Local DSP analysis timed out before completion.',
  errorCode: 'ANALYZER_TIMEOUT',
};

describe('DiagnosticLog rendering', () => {
  it('renders error status, message, and error code', () => {
    const html = renderToStaticMarkup(React.createElement(DiagnosticLog, { logs: [baseLog] }));

    expect(html).toContain('ERROR');
    expect(html).toContain('ANALYZER_TIMEOUT');
    expect(html).toContain('Local DSP analysis timed out before completion.');
  });

  it('renders a timings summary row below the metadata grid', () => {
    const html = renderToStaticMarkup(
      React.createElement(DiagnosticLog, {
        logs: [
          {
            ...baseLog,
            timings: {
              totalMs: 1560,
              analysisMs: 1420,
              serverOverheadMs: 140,
              flagsUsed: ['--transcribe', '--separate'],
              fileSizeBytes: 543210,
              fileDurationSeconds: 184.2,
              msPerSecondOfAudio: 7.71,
            },
          },
        ],
      }),
    );

    expect(html).toContain('TIMINGS:');
    expect(html).toContain('TOTAL: 1560ms');
    expect(html).toContain('ANALYSIS: 1420ms');
    expect(html).toContain('OVERHEAD: 140ms');
    expect(html).toContain('FLAGS: --transcribe --separate');
    expect(html).toContain('7.71 ms/s of audio');
    expect(html.indexOf('TYPE:')).toBeLessThan(html.indexOf('TIMINGS:'));
  });

  it('renders fallback timing copy when flags and ms/s are unavailable', () => {
    const html = renderToStaticMarkup(
      React.createElement(DiagnosticLog, {
        logs: [
          {
            ...baseLog,
            timings: {
              totalMs: 820,
              analysisMs: 800,
              serverOverheadMs: 20,
              flagsUsed: [],
              fileSizeBytes: 543210,
              fileDurationSeconds: null,
              msPerSecondOfAudio: null,
            },
          },
        ],
      }),
    );

    expect(html).toContain('FLAGS: none');
    expect(html).toContain('N/A ms/s of audio');
  });

  it('omits the timings row when backend timings are absent', () => {
    const html = renderToStaticMarkup(React.createElement(DiagnosticLog, { logs: [baseLog] }));

    expect(html).not.toContain('TIMINGS:');
  });

  it('renders skipped entries without the running cursor', () => {
    const html = renderToStaticMarkup(
      React.createElement(DiagnosticLog, {
        logs: [
          {
            ...baseLog,
            phase: 'Phase 2: Advisory skipped',
            model: 'disabled',
            source: 'system',
            status: 'skipped',
            message: 'Phase 2 advisory is disabled.',
            errorCode: undefined,
          },
        ],
      }),
    );

    expect(html).toContain('SKIPPED');
    expect(html).toContain('Phase 2 advisory is disabled.');
    expect(html).not.toContain('animate-pulse');
  });

  it('renders client timeout entries without pretending the backend timed out', () => {
    const html = renderToStaticMarkup(
      React.createElement(DiagnosticLog, {
        logs: [
          {
            ...baseLog,
            message: 'The UI timed out waiting for the local DSP backend response.',
            errorCode: 'CLIENT_TIMEOUT',
          },
        ],
      }),
    );

    expect(html).toContain('CLIENT_TIMEOUT');
    expect(html).toContain('The UI timed out waiting for the local DSP backend response.');
    expect(html).not.toContain('ANALYZER_TIMEOUT');
  });
});
