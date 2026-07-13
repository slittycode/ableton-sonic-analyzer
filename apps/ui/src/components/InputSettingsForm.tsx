// Analysis settings controls (ANALYSIS MODE + the pitch/note, MT3, and AI
// interpretation toggles), extracted verbatim from App.tsx (App.tsx cleanup).
// Stateless: every value + change handler is owned by App and passed in, so the
// native form controls the Playwright smoke suite drives (getByLabel + check/
// uncheck) keep their exact aria-labels and behavior.

interface InputSettingsFormProps {
  isAnalyzing: boolean;
  analysisMode: 'full' | 'standard';
  onAnalysisModeChange: (mode: 'full' | 'standard') => void;
  pitchNoteTranslationRequested: boolean;
  onPitchNoteTranslationRequestedChange: (checked: boolean) => void;
  mt3ConfigEnabled: boolean;
  mt3Requested: boolean;
  onMt3RequestedChange: (checked: boolean) => void;
  interpretationRequested: boolean;
  phase2ConfigEnabled: boolean;
  onInterpretationRequestedChange: (checked: boolean) => void;
  phase2StatusBadge: string | null;
  phase2HelperCopy: string;
}

export function InputSettingsForm({
  isAnalyzing,
  analysisMode,
  onAnalysisModeChange,
  pitchNoteTranslationRequested,
  onPitchNoteTranslationRequestedChange,
  mt3ConfigEnabled,
  mt3Requested,
  onMt3RequestedChange,
  interpretationRequested,
  phase2ConfigEnabled,
  onInterpretationRequestedChange,
  phase2StatusBadge,
  phase2HelperCopy,
}: InputSettingsFormProps) {
  return (
    <>
      <div className="mt-4 rounded-sm border border-border bg-bg-panel px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="space-y-1">
            <p className="text-meta font-mono uppercase tracking-wider text-text-secondary">ANALYSIS MODE</p>
            {/* Audit revised #4: helper paragraphs in the
                Input Source panel were all-caps mono walls.
                Switched to sans-serif sentence case (eyebrow
                above stays mono-uppercase for label scan). */}
            <p className="text-xs leading-snug text-text-secondary/80">
              Full keeps every measurement. Standard is faster and skips advanced detail.
            </p>
          </div>
          <select
            aria-label="ANALYSIS MODE"
            value={analysisMode}
            onChange={(e) => onAnalysisModeChange(e.target.value as 'full' | 'standard')}
            disabled={isAnalyzing}
            className="appearance-none bg-bg-card border border-border text-text-primary text-meta font-mono py-1.5 pl-2 pr-6 rounded-sm focus:outline-none focus:border-accent cursor-pointer disabled:opacity-50"
          >
            <option value="full">Full</option>
            <option value="standard">Standard</option>
          </select>
        </div>
      </div>
      <label
        className={`mt-4 rounded-sm border px-3 py-3 transition-colors cursor-pointer ${
          pitchNoteTranslationRequested
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border bg-bg-panel text-text-secondary'
        } ${isAnalyzing ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <div className="flex items-start gap-3">
          {/* Native input kept here rather than the Radix
              Checkbox primitive because Playwright smoke tests
              depend on getByLabel + .toBeChecked() + .uncheck()
              against this control (tests/smoke/upload-estimate-
              phase1.spec.ts:242). Those locators work reliably
              for native form controls; the Radix
              <button role="checkbox"> equivalent is less
              consistently supported. The Checkbox primitive
              still exists in components/ui/ for surfaces that
              aren't load-bearing for smoke selectors. */}
          <input
            type="checkbox"
            checked={pitchNoteTranslationRequested}
            onChange={(e) => onPitchNoteTranslationRequestedChange(e.target.checked)}
            disabled={isAnalyzing}
            aria-label="PITCH/NOTE TRANSLATION"
            className="mt-0.5 h-4 w-4 accent-accent"
          />
          <div className="space-y-1">
            <p className="text-meta font-mono uppercase tracking-wider">STEM PITCH/NOTE TRANSLATION</p>
            {/* Audit revised #4: see ANALYSIS MODE helper above. */}
            <p className="text-xs leading-snug opacity-80">
              Optional. Slower and heavier. Turns on the stem-aware note draft (Demucs + torchcrepe on bass and lead). When off, the measurement-layer melody contour and Gemini stem listening notes can still appear when those stages run.
            </p>
          </div>
        </div>
      </label>
      {mt3ConfigEnabled && (
        <label
          className={`mt-3 rounded-sm border px-3 py-3 transition-colors cursor-pointer ${
            mt3Requested
              ? 'border-accent bg-accent/10 text-accent'
              : 'border-border bg-bg-panel text-text-secondary'
          } ${isAnalyzing ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <div className="flex items-start gap-3">
            {/* Native input (not the Radix Checkbox) so the
                Playwright smoke test drives it via
                getByLabel().check() — same rationale as the
                PITCH/NOTE toggle above. */}
            <input
              type="checkbox"
              checked={mt3Requested}
              onChange={(e) => onMt3RequestedChange(e.target.checked)}
              disabled={isAnalyzing}
              aria-label="MT3 POLYPHONIC TRANSCRIPTION"
              className="mt-0.5 h-4 w-4 accent-accent"
            />
            <div className="space-y-1">
              <p className="text-meta font-mono uppercase tracking-wider">MT3 POLYPHONIC TRANSCRIPTION</p>
              <p className="text-xs leading-snug opacity-80">
                Experimental and heavy (separate model + weights). Extracts per-instrument MIDI via MT3 — additive only, never overrides Phase 1 measurements. Best with PITCH/NOTE TRANSLATION on; without Demucs stems it falls back to a lower-quality full-mix pass.
              </p>
            </div>
          </div>
        </label>
      )}
      <label
        className={`mt-3 rounded-sm border px-3 py-3 transition-colors cursor-pointer ${
          interpretationRequested && phase2ConfigEnabled
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border bg-bg-panel text-text-secondary'
        } ${isAnalyzing || !phase2ConfigEnabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <div className="flex items-start gap-3">
          {/* See PITCH/NOTE toggle above for the rationale. */}
          <input
            type="checkbox"
            checked={interpretationRequested}
            onChange={(e) => onInterpretationRequestedChange(e.target.checked)}
            disabled={isAnalyzing || !phase2ConfigEnabled}
            aria-label="AI INTERPRETATION"
            className="mt-0.5 h-4 w-4 accent-accent"
          />
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-meta font-mono uppercase tracking-wider">AI INTERPRETATION</p>
              {phase2StatusBadge && (
                <span
                  data-testid="phase2-status-inline"
                  className="text-meta font-mono uppercase tracking-wider opacity-80"
                >
                  {phase2StatusBadge}
                </span>
              )}
            </div>
            {/* Audit revised #4: see ANALYSIS MODE helper above. */}
            <p className="text-xs leading-snug opacity-80">
              {phase2HelperCopy}
            </p>
          </div>
        </div>
      </label>
    </>
  );
}
