/**
 * Type definitions for the Phase 3 audition-sample manifest.
 *
 * Mirrors the JSON written by `apps/backend/sample_generation.py` and
 * decorated by `apps/backend/server_samples.py`. Do not rename fields without
 * updating both sides — the canonical shape lives in the backend.
 */

export type SampleCategory = 'tonal' | 'drums' | 'melody';
export type SampleConfidence = 'HIGH' | 'MED' | 'LOW';
export type SampleSynthesisBackend = 'fluidsynth' | 'sine_fallback';
export type SampleTheoryBackend = 'pytheory' | 'fallback';

export interface SampleCitations {
  phase1Fields: string[];
  phase2Recommendations: string[];
  rationale: string;
}

export interface SampleRecord {
  id: string;
  label: string;
  category: SampleCategory;
  filename: string;
  mimeType: 'audio/wav' | string;
  durationSeconds: number;
  confidence: SampleConfidence;
  lowConfidence: boolean;
  cites: SampleCitations;
  midiFilename?: string;
  /** Populated by the backend route layer; absent in the raw manifest file. */
  artifactId?: string;
  midiArtifactId?: string;
}

export interface SamplesManifest {
  schemaVersion: 'samples.v1';
  runId: string;
  generatedAt: string;
  synthesisBackend: SampleSynthesisBackend;
  soundfont: string | null;
  framing: string;
  theoryBackend: SampleTheoryBackend;
  samples: SampleRecord[];
  manifestArtifactId?: string;
}
