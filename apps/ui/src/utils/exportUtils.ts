import { Phase1Result, Phase2Result } from '../types';
import {
  formatContractRange,
  formatContractValue,
} from '../services/recommendationsContract';

export function downloadFile(content: string, fileName: string, contentType: string) {
  const a = document.createElement('a');
  const file = new Blob([content], { type: contentType });
  a.href = URL.createObjectURL(file);
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** Track identity carried into exports so re-runs of different rips can't mislead. */
export interface ExportSourceMeta {
  filename?: string | null;
  contentSha256?: string | null;
  sizeBytes?: number | null;
  durationSeconds?: number | null;
  analyzedAt?: string | null;
  phase1Version?: string | null;
}

function sanitizeBasename(filename: string | null | undefined): string {
  const raw = (filename ?? 'track').trim() || 'track';
  const withoutExt = raw.replace(/\.[^/.]+$/, '');
  const cleaned = withoutExt
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  return cleaned || 'track';
}

function exportDateStamp(iso: string | null | undefined): string {
  const parsed = iso ? new Date(iso) : new Date();
  if (Number.isNaN(parsed.getTime())) {
    return new Date().toISOString().slice(0, 10);
  }
  return parsed.toISOString().slice(0, 10);
}

/** `track-analysis-<basename>-<YYYY-MM-DD>.{md,json,pdf,png}` */
export function buildExportFileName(
  extension: 'md' | 'json' | 'pdf' | 'png',
  source: ExportSourceMeta | null | undefined = null,
): string {
  const base = sanitizeBasename(source?.filename);
  const day = exportDateStamp(source?.analyzedAt);
  const suffix = extension === 'pdf' || extension === 'png' ? `-ui` : '';
  return `track-analysis-${base}-${day}${suffix}.${extension}`;
}

function formatMarkdownNumber(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, '');
}

function formatShaShort(sha: string | null | undefined): string | null {
  if (!sha || typeof sha !== 'string') return null;
  const trimmed = sha.trim();
  if (!trimmed) return null;
  return trimmed.length > 12 ? trimmed.slice(0, 12) : trimmed;
}

function formatBytes(sizeBytes: number | null | undefined): string | null {
  if (typeof sizeBytes !== 'number' || !Number.isFinite(sizeBytes) || sizeBytes < 0) {
    return null;
  }
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KiB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(2)} MiB`;
}

function formatSourceMarkdown(source: ExportSourceMeta | null | undefined): string {
  if (!source) return '';
  const lines: string[] = ['## Source'];
  if (source.filename) lines.push(`- **Filename**: ${source.filename}`);
  const shaShort = formatShaShort(source.contentSha256);
  if (shaShort) {
    const full = source.contentSha256?.trim() ?? shaShort;
    lines.push(`- **SHA-256**: \`${shaShort}\`${full.length > 12 ? ` (\`${full}\`)` : ''}`);
  }
  const sizeLabel = formatBytes(source.sizeBytes ?? null);
  if (sizeLabel) lines.push(`- **Size**: ${sizeLabel}`);
  if (typeof source.durationSeconds === 'number' && Number.isFinite(source.durationSeconds)) {
    lines.push(`- **Duration**: ${formatMarkdownNumber(source.durationSeconds)}s`);
  }
  if (source.analyzedAt) lines.push(`- **Analyzed at**: ${source.analyzedAt}`);
  if (source.phase1Version) lines.push(`- **Phase 1 version**: ${source.phase1Version}`);
  if (lines.length === 1) return '';
  return `${lines.join('\n')}\n\n`;
}

function formatArrangementOverviewMarkdown(arrangementOverview: Phase2Result['arrangementOverview']): string {
  let md = `${arrangementOverview.summary}\n`;

  if (arrangementOverview.segments.length > 0) {
    md += '\nSegments:\n';
    arrangementOverview.segments.forEach((segment) => {
      const timeRange = `${formatMarkdownNumber(segment.startTime)}s-${formatMarkdownNumber(segment.endTime)}s`;
      const lufsLabel = typeof segment.lufs === 'number' ? `, ${formatMarkdownNumber(segment.lufs)} LUFS` : '';
      const spectralNote = segment.spectralNote ? ` Spectral note: ${segment.spectralNote}` : '';
      md += `- Segment ${segment.index} (${timeRange}${lufsLabel}): ${segment.description}${spectralNote}\n`;
    });
  }

  if (arrangementOverview.noveltyNotes) {
    md += `\nNovelty Notes: ${arrangementOverview.noveltyNotes}\n`;
  }

  return md;
}

function formatMixAndMasterChainMarkdown(mixAndMasterChain: Phase2Result['mixAndMasterChain']): string {
  return mixAndMasterChain
    .map((item) => `${item.order}. ${item.device} — ${item.parameter}: ${item.value}. ${item.reason}`)
    .join('\n');
}

export function generateMarkdown(
  phase1: Phase1Result,
  phase2: Phase2Result | null,
  phase2StatusMessage: string | null = null,
  source: ExportSourceMeta | null = null,
): string {
  let md = '# Track Analysis Report\n\n';
  md += formatSourceMarkdown(source);

  md += '## Phase 1 Metadata\n';
  md += `- **BPM**: ${phase1.bpm}\n`;
  md += `- **BPM Confidence**: ${(phase1.bpmConfidence * 100).toFixed(1)}%\n`;
  md += `- **Key**: ${phase1.key ?? 'Unknown'}\n`;
  md += `- **Key Confidence**: ${(phase1.keyConfidence * 100).toFixed(1)}%\n`;
  md += `- **Time Signature**: ${phase1.timeSignature}\n`;
  md += `- **Duration (s)**: ${phase1.durationSeconds}\n`;
  md += `- **Integrated LUFS**: ${phase1.lufsIntegrated}\n`;
  md += `- **True Peak**: ${phase1.truePeak === null ? '—' : `${phase1.truePeak} dBTP`}\n`;
  md += `- **Stereo Width**: ${phase1.stereoWidth}\n`;
  md += `- **Stereo Correlation**: ${phase1.stereoCorrelation}\n\n`;

  md += '### Spectral Balance\n';
  md += `- **Sub Bass**: ${phase1.spectralBalance.subBass}\n`;
  md += `- **Low Bass**: ${phase1.spectralBalance.lowBass}\n`;
  md += `- **Mids**: ${phase1.spectralBalance.mids}\n`;
  md += `- **Upper Mids**: ${phase1.spectralBalance.upperMids}\n`;
  md += `- **Highs**: ${phase1.spectralBalance.highs}\n`;
  md += `- **Brilliance**: ${phase1.spectralBalance.brilliance}\n\n`;

  if (!phase2) {
    md += '## Phase 2\n';
    md += `${phase2StatusMessage ?? 'Phase 2 (Gemini reconstruction advice) was skipped or unavailable.'}\n`;
    return md;
  }

  md += '## Phase 2 Reconstruction\n';
  md += `### Track Character\n${phase2.trackCharacter}\n\n`;

  if (phase2.detectedCharacteristics.length > 0) {
    md += '### Detected Characteristics\n';
    phase2.detectedCharacteristics.forEach((item) => {
      md += `- **${item.name}** (${item.confidence}): ${item.explanation}\n`;
    });
    md += '\n';
  }

  md += `### Arrangement Overview\n${formatArrangementOverviewMarkdown(phase2.arrangementOverview)}\n`;

  md += '### Sonic Elements\n';
  md += `- **Kick**: ${phase2.sonicElements.kick}\n`;
  md += `- **Bass**: ${phase2.sonicElements.bass}\n`;
  md += `- **Melodic Arp**: ${phase2.sonicElements.melodicArp}\n`;
  md += `- **Groove and Timing**: ${phase2.sonicElements.grooveAndTiming}\n`;
  md += `- **Effects and Texture**: ${phase2.sonicElements.effectsAndTexture}\n`;
  if (phase2.sonicElements.widthAndStereo) {
    md += `- **Width and Stereo**: ${phase2.sonicElements.widthAndStereo}\n`;
  }
  if (phase2.sonicElements.harmonicContent) {
    md += `- **Harmonic Content**: ${phase2.sonicElements.harmonicContent}\n`;
  }
  md += '\n';

  md += `### Mix and Master Chain\n${formatMixAndMasterChainMarkdown(phase2.mixAndMasterChain)}\n\n`;

  md += `### Secret Sauce: ${phase2.secretSauce.title}\n`;
  md += `${phase2.secretSauce.explanation}\n\n`;
  md += 'Implementation Steps:\n';
  phase2.secretSauce.implementationSteps.forEach((step, index) => {
    md += `${index + 1}. ${step}\n`;
  });
  md += '\n';

  if (phase2.confidenceNotes.length > 0) {
    md += '### Confidence Notes\n';
    phase2.confidenceNotes.forEach((note) => {
      md += `- **${note.field} (${note.value})**: ${note.reason}\n`;
    });
    md += '\n';
  }

  if (phase2.abletonRecommendations && phase2.abletonRecommendations.length > 0) {
    md += '### Ableton Recommendations\n';
    md += '| Device | Category | Parameter | Value | Reason |\n';
    md += '| :--- | :--- | :--- | :--- | :--- |\n';
    phase2.abletonRecommendations.forEach((rec) => {
      md += `| ${rec.device} | ${rec.category} | ${rec.parameter} | ${rec.value} | ${rec.reason} |\n`;
    });
    md += '\n';
  }

  // recommendations.v1 (ADR 0003): the schema-validated, citation-gated
  // projection the backend attaches to the interpretation. Every entry here
  // cites the Phase 1 measurement(s) that justify it — the machine-checkable
  // half of the report, alongside the raw cards above.
  if (phase2.recommendations && phase2.recommendations.recommendations.length > 0) {
    md += `### Validated Recommendations (${phase2.recommendations.version})\n`;
    md += 'Schema-validated projection of the device cards above. Entries are admitted only when they cite at least one Phase 1 measurement.\n';
    md += '| Device | Parameter | Value | Working Range | Cited Measurements |\n';
    md += '| :--- | :--- | :--- | :--- | :--- |\n';
    phase2.recommendations.recommendations.forEach((entry) => {
      const range = formatContractRange(entry) ?? '—';
      md += `| ${entry.device} | ${entry.parameter} | ${formatContractValue(entry)} | ${range} | ${entry.cited_measurements.join(', ')} |\n`;
    });
  }

  return md;
}

export function buildExportPayload(
  phase1: Phase1Result,
  phase2: Phase2Result | null,
  source: ExportSourceMeta | null = null,
): Record<string, unknown> {
  const analyzedAt = source?.analyzedAt ?? new Date().toISOString();
  return {
    phase1,
    phase2,
    exportedAt: analyzedAt,
    source: {
      filename: source?.filename ?? null,
      contentSha256: source?.contentSha256 ?? null,
      sizeBytes: source?.sizeBytes ?? null,
      durationSeconds:
        source?.durationSeconds ??
        (typeof phase1.durationSeconds === 'number' ? phase1.durationSeconds : null),
      analyzedAt,
      phase1Version: source?.phase1Version ?? phase1.phase1Version ?? null,
    },
  };
}
