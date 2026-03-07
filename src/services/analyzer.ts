import { appConfig, isGeminiPhase2Available } from "../config";
import { analyzePhase1WithBackend, mapBackendError } from "./backendPhase1Client";
import { PHASE1_LABEL, PHASE2_SKIPPED_LABEL } from "./phaseLabels";
import { DiagnosticLogEntry, Phase1Result, Phase2Result } from "../types";

interface AnalyzeAudioOptions {
  transcribe?: boolean;
  separate?: boolean;
}

export function isPhase2GeminiEnabled(): boolean {
  return isGeminiPhase2Available();
}

export async function analyzeAudio(
  file: File,
  modelName: string,
  dspJson: string | null,
  onPhase1Complete: (result: Phase1Result, log: DiagnosticLogEntry) => void,
  onPhase2Complete: (result: Phase2Result | null, log: DiagnosticLogEntry) => void,
  onError: (error: Error) => void,
  analysisOptions?: AnalyzeAudioOptions,
) {
  let phase1Completed = false;
  const audioMetadata: DiagnosticLogEntry["audioMetadata"] = {
    name: file.name,
    size: file.size,
    type: file.type || "audio/mp3",
  };

  try {
    const phase1Start = Date.now();
    const backendResult = await analyzePhase1WithBackend(file, dspJson, {
      apiBaseUrl: appConfig.apiBaseUrl,
      transcribe: analysisOptions?.transcribe ?? false,
      separate: analysisOptions?.separate ?? false,
    });
    const phase1End = Date.now();

    const phase1Log: DiagnosticLogEntry = {
      model: "local-dsp-engine",
      phase: PHASE1_LABEL,
      promptLength: dspJson?.length ?? 0,
      responseLength: JSON.stringify(backendResult.phase1).length,
      durationMs: phase1End - phase1Start,
      audioMetadata,
      timestamp: new Date().toISOString(),
      requestId: backendResult.requestId,
      source: "backend",
      status: "success",
      message: "Local DSP analysis complete.",
      estimateLowMs: backendResult.diagnostics?.estimatedLowMs,
      estimateHighMs: backendResult.diagnostics?.estimatedHighMs,
    };

    onPhase1Complete(backendResult.phase1, phase1Log);
    phase1Completed = true;

    if (!isGeminiPhase2Available()) {
      const phase2SkippedLog: DiagnosticLogEntry = {
        model: "disabled",
        phase: PHASE2_SKIPPED_LABEL,
        promptLength: 0,
        responseLength: 0,
        durationMs: 0,
        audioMetadata,
        timestamp: new Date().toISOString(),
        requestId: backendResult.requestId,
        source: "system",
        status: "skipped",
        message: "Phase 2 advisory is disabled or missing an API key.",
      };
      onPhase2Complete(null, phase2SkippedLog);
      return;
    }

    const { analyzePhase2WithGemini } = await import("./geminiPhase2Client");
    const phase2 = await analyzePhase2WithGemini({
      file,
      modelName,
      phase1Result: backendResult.phase1,
      audioMetadata,
    });

    onPhase2Complete(phase2.result, {
      ...phase2.log,
      requestId: backendResult.requestId,
    });
  } catch (error) {
    if (!phase1Completed) {
      onError(mapBackendError(error));
      return;
    }
    onError(error instanceof Error ? error : new Error(String(error)));
  }
}
