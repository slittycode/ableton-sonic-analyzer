import { Phase1Result, Phase2Result } from '../types';

export function downloadFile(content: string, fileName: string, contentType: string) {
  const a = document.createElement('a');
  const file = new Blob([content], { type: contentType });
  a.href = URL.createObjectURL(file);
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function generateMarkdown(phase1: Phase1Result, phase2: Phase2Result | null): string {
  let finalBpm = phase1.bpm;
  let hasBpmCorrection = false;
  if (phase2 && phase2.bpmCorrection !== undefined && phase2.bpmCorrection !== null && phase2.bpmCorrection !== 0 && phase2.bpmCorrection !== phase1.bpm) {
    finalBpm = phase2.bpmCorrection;
    hasBpmCorrection = true;
  }

  let finalKey = phase1.key;
  let hasKeyCorrection = false;
  if (phase2 && phase2.keyCorrection && phase2.keyCorrection !== "null" && phase2.keyCorrection.toLowerCase() !== "null" && phase2.keyCorrection !== phase1.key) {
    finalKey = phase2.keyCorrection;
    hasKeyCorrection = true;
  }

  let md = `# Track Analysis Report\n\n`;
  
  md += `## Metadata Overview\n`;
  md += `- **BPM**: ${finalBpm}${hasBpmCorrection ? ' (corrected)' : ''}\n`;
  md += `- **Key**: ${finalKey}${hasKeyCorrection ? ' (corrected)' : ''}\n`;
  md += `- **Time Signature**: ${phase1.timeSignature}\n`;
  md += `- **Genre**: ${phase2?.genre || "Analyzing..."}\n`;
  if (phase2?.genreAlternatives && phase2.genreAlternatives.length > 0) {
    md += `- **Genre Alternatives**:\n`;
    phase2.genreAlternatives.forEach(alt => {
      if (typeof alt === 'object') {
        md += `  - ${alt.genre}: ${alt.reasoning}\n`;
      } else {
        md += `  - ${alt}\n`;
      }
    });
  }
  md += `\n`;

  if (phase2?.characteristics && phase2.characteristics.length > 0) {
    md += `## Detected Characteristics\n`;
    phase2.characteristics.forEach(char => {
      md += `### ${char.trait} (${char.detected ? 'Detected' : 'Absent'})\n`;
      if (char.detected) {
        if (char.keyValue) md += `- **Key Value**: ${char.keyValue}\n`;
        if (char.description) md += `- ${char.description}\n`;
      }
      md += `\n`;
    });
  }

  if (phase2?.arrangement && phase2.arrangement.length > 0) {
    md += `## Arrangement\n`;
    md += `| Time | Segment | Description |\n`;
    md += `| :--- | :--- | :--- |\n`;
    phase2.arrangement.forEach(seg => {
      md += `| ${seg.startTime} - ${seg.endTime} | ${seg.segmentName} | ${seg.description} |\n`;
    });
    md += `\n`;
  }

  if (phase2?.elements && phase2.elements.length > 0) {
    md += `## Sonic Elements\n`;
    phase2.elements.forEach(el => {
      md += `### ${el.name}\n`;
      md += `- **Character**: ${el.character}\n`;
      md += `- **Role**: ${el.role}\n`;
      if (el.perceivedLoudness) md += `- **Perceived Loudness**: ${el.perceivedLoudness}\n`;
      md += `- **Frequency Range**: ${el.frequencyRange}\n`;
      if (el.recreationAdvice) md += `- **Ableton Recreation**: ${el.recreationAdvice}\n`;
      if (el.deviceChain && el.deviceChain.length > 0) md += `- **Device Chain**: ${el.deviceChain.join(' -> ')}\n`;
      if (el.reconstructionDifficulty) md += `- **Difficulty**: ${el.reconstructionDifficulty} (${el.difficultyReasoning})\n`;
      md += `\n`;
    });
  }

  if (phase2 && phase2.secretSauce) {
    md += `## Secret Sauce\n`;
    md += `### ${phase2.secretSauce.title}\n`;
    md += `${phase2.secretSauce.explanation}\n\n`;
    md += `**Implementation Steps:**\n`;
    phase2.secretSauce.implementationSteps.forEach((step, i) => {
      md += `${i + 1}. ${step}\n`;
    });
    md += `\n`;
  }

  if (phase2 && phase2.mixCritique) {
    const { mixCritique } = phase2;
    md += `## Mix Critique\n`;
    md += `- **Overall Balance**: ${mixCritique.overallBalance}\n`;
    md += `- **Low End (${mixCritique.lowEndScore || 0}/10)**: ${mixCritique.lowEnd}\n`;
    md += `- **Mid Range (${mixCritique.midRangeScore || 0}/10)**: ${mixCritique.midRange}\n`;
    md += `- **High End (${mixCritique.highEndScore || 0}/10)**: ${mixCritique.highEnd}\n`;
    md += `- **Stereo Image (${mixCritique.stereoImageScore || 0}/10)**: ${mixCritique.stereoImage}\n`;
    md += `- **Dynamics (${mixCritique.dynamicsScore || 0}/10)**: ${mixCritique.dynamics}\n\n`;
  }

  if (phase2 && phase2.effectsChain && phase2.effectsChain.length > 0) {
    md += `## Master & Return Effects Chain\n`;
    phase2.effectsChain.forEach(chain => {
      md += `### ${chain.name}\n`;
      md += `*${chain.description}*\n\n`;
      chain.devices.forEach(dev => {
        md += `- **${dev.device}**: ${dev.parameters}\n`;
      });
      md += `\n`;
    });
  }

  if (phase2 && phase2.abletonRecommendations && phase2.abletonRecommendations.length > 0) {
    md += `## Ableton Live 12 Recommendations\n`;
    md += `| Device | Parameter | Value | Reason |\n`;
    md += `| :--- | :--- | :--- | :--- |\n`;
    phase2.abletonRecommendations.forEach(rec => {
      md += `| ${rec.device} | ${rec.parameter} | ${rec.value} | ${rec.reason} |\n`;
    });
  }

  return md;
}
