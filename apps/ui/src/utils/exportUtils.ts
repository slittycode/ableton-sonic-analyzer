import { Phase1Result, Phase2Result, type GenreProfile } from '../types';
import { generateMixReport, type MixDoctorReport } from '../services/mixDoctor';
import genreProfilesData from '../data/genreProfiles.json';

export function downloadFile(content: string, fileName: string, contentType: string) {
  const a = document.createElement('a');
  const file = new Blob([content], { type: contentType });
  a.href = URL.createObjectURL(file);
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(a.href);
}

function formatMarkdownNumber(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, '');
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

function formatMixDoctorMarkdown(report: MixDoctorReport): string {
  let md = `## Mix Doctor (${report.genreName})\n`;
  md += `**Overall Score: ${report.overallScore}/100**\n\n`;

  md += '### Spectral Balance\n';
  for (const a of report.advice) {
    const sign = a.diffDb > 0 ? '+' : '';
    const status = a.issue === 'optimal' ? '✓' : a.issue === 'too-loud' ? '▲' : '▼';
    md += `- ${status} **${a.band}**: ${sign}${a.diffDb.toFixed(1)} dB — ${a.message}\n`;
  }
  md += '\n';

  md += `### Dynamics\n- ${report.dynamicsAdvice.message}\n`;
  md += `- Crest Factor: ${report.dynamicsAdvice.actualCrest} dB\n\n`;

  if (report.loudnessAdvice) {
    md += `### Loudness\n- ${report.loudnessAdvice.message}\n`;
    md += `- LUFS: ${report.loudnessAdvice.actualLufs} / True Peak: ${report.loudnessAdvice.truePeak} dBTP\n\n`;
  }

  if (report.stereoAdvice) {
    md += `### Stereo Field\n- ${report.stereoAdvice.message}\n`;
    md += `- Correlation: ${report.stereoAdvice.correlation.toFixed(2)} / Width: ${Math.round(report.stereoAdvice.width * 100)}%\n\n`;
  }

  return md;
}

export function generateMarkdown(
  phase1: Phase1Result,
  phase2: Phase2Result | null,
  phase2StatusMessage: string | null = null,
): string {
  let md = '# Track Analysis Report\n\n';

  md += '## Phase 1 Metadata\n';
  md += `- **BPM**: ${phase1.bpm}\n`;
  md += `- **BPM Confidence**: ${(phase1.bpmConfidence * 100).toFixed(1)}%\n`;
  md += `- **Key**: ${phase1.key ?? 'Unknown'}\n`;
  md += `- **Key Confidence**: ${(phase1.keyConfidence * 100).toFixed(1)}%\n`;
  md += `- **Time Signature**: ${phase1.timeSignature}\n`;
  md += `- **Duration (s)**: ${phase1.durationSeconds}\n`;
  md += `- **Integrated LUFS**: ${phase1.lufsIntegrated}\n`;
  md += `- **True Peak**: ${phase1.truePeak}\n`;
  md += `- **Stereo Width**: ${phase1.stereoWidth}\n`;
  md += `- **Stereo Correlation**: ${phase1.stereoCorrelation}\n\n`;

  md += '### Spectral Balance\n';
  md += `- **Sub Bass**: ${phase1.spectralBalance.subBass}\n`;
  md += `- **Low Bass**: ${phase1.spectralBalance.lowBass}\n`;
  md += `- **Mids**: ${phase1.spectralBalance.mids}\n`;
  md += `- **Upper Mids**: ${phase1.spectralBalance.upperMids}\n`;
  md += `- **Highs**: ${phase1.spectralBalance.highs}\n`;
  md += `- **Brilliance**: ${phase1.spectralBalance.brilliance}\n\n`;

  // Mix Doctor section (derived analysis, not measurement)
  const profiles = genreProfilesData as GenreProfile[];
  const gd = phase1.genreDetail;
  const autoId = gd && gd.confidence >= 0.6 ? gd.genre : null;
  const familyId = gd ? gd.genreFamily : null;
  const profileId = autoId ?? familyId ?? profiles[0]?.id;
  const profile = profiles.find(p => p.id === profileId);
  if (profile) {
    const report = generateMixReport(phase1, profile);
    md += formatMixDoctorMarkdown(report);
  }

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
  }

  return md;
}
