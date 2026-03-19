import type { GenreProfile, MixDoctorReport } from '../types';

interface MixDoctorPanelProps {
  report: MixDoctorReport | null;
  profiles: GenreProfile[];
  activeProfileId: string | null;
  autoProfileId: string | null;
  autoGenreId: string | null;
  onProfileChange: (id: string | null) => void;
}

function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-400';
  if (score >= 50) return 'text-yellow-400';
  return 'text-red-400';
}

function scoreBg(score: number): string {
  if (score >= 80) return 'bg-green-400/20 border-green-400/40';
  if (score >= 50) return 'bg-yellow-400/20 border-yellow-400/40';
  return 'bg-red-400/20 border-red-400/40';
}

function issueColor(issue: string): string {
  if (issue === 'optimal') return 'bg-green-400/60';
  if (issue === 'too-loud') return 'bg-red-400/60';
  return 'bg-amber-400/60';
}

function issueBarColor(issue: string): string {
  if (issue === 'optimal') return 'bg-green-400/40';
  if (issue === 'too-loud') return 'bg-red-400/40';
  return 'bg-amber-400/40';
}

export function MixDoctorPanel({ report, profiles, activeProfileId, autoProfileId, autoGenreId, onProfileChange }: MixDoctorPanelProps) {
  const header = (
    <div className="flex items-center justify-between border-b border-border pb-2">
      <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
        <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
        Mix Doctor
      </h2>
      {report && (
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono bg-bg-panel border border-border px-2 py-1 rounded font-bold text-text-secondary">
            PHASE 1
          </span>
          <div className={`text-sm font-mono font-bold px-2 py-1 rounded border ${scoreBg(report.overallScore)}`}>
            <span className={scoreColor(report.overallScore)}>{report.overallScore}</span>
            <span className="text-text-secondary text-[10px] ml-1">/100</span>
          </div>
        </div>
      )}
    </div>
  );

  const selector = (
    <div className="flex items-center gap-3">
      <label className="text-xs font-mono text-text-secondary shrink-0">Profile:</label>
      <select
        value={activeProfileId ?? ''}
        onChange={e => onProfileChange(e.target.value || null)}
        className="flex-1 text-xs font-mono bg-bg-panel border border-border rounded px-2 py-1.5 text-text-primary"
      >
        {!activeProfileId && (
          <option value="">Select a genre profile...</option>
        )}
        {profiles.map(p => (
          <option key={p.id} value={p.id}>
            {p.name}{p.id === autoProfileId ? ' (auto-detected)' : ''}
          </option>
        ))}
      </select>
      {autoProfileId && (
        <span className="text-[10px] font-mono text-text-secondary">
          {autoGenreId ? 'Genre-matched' : 'Family fallback'}
        </span>
      )}
    </div>
  );

  if (!report || !activeProfileId) {
    return (
      <div className="space-y-4">
        {header}
        {selector}
        <p className="text-xs font-mono text-text-secondary text-center py-4">
          Select a genre profile above to see mix analysis
        </p>
      </div>
    );
  }

  const maxAbsDiff = Math.max(...report.advice.map(a => Math.abs(a.diffDb)), 1);

  return (
    <div className="space-y-4">
      {header}
      {selector}

      {/* Spectral comparison */}
      <div className="bg-bg-card border border-border rounded-sm p-4 space-y-2">
        <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-3">Spectral Balance vs {report.genreName}</p>
        {report.advice.map(a => {
          const pct = (Math.abs(a.diffDb) / maxAbsDiff) * 100;
          const isRight = a.diffDb >= 0;
          return (
            <div key={a.band} className="flex items-center gap-2">
              <span className="text-xs font-mono text-text-secondary w-20 text-right shrink-0">{a.band}</span>
              <div className="flex-1 h-3 bg-bg-panel rounded-sm overflow-hidden relative">
                <div className="absolute inset-0 flex">
                  <div className="w-1/2 flex justify-end">
                    {!isRight && (
                      <div
                        className={`h-full ${issueBarColor(a.issue)} rounded-l-sm`}
                        style={{ width: `${pct}%` }}
                      />
                    )}
                  </div>
                  <div className="w-px bg-text-secondary/30 shrink-0" />
                  <div className="w-1/2">
                    {isRight && (
                      <div
                        className={`h-full ${issueBarColor(a.issue)} rounded-r-sm`}
                        style={{ width: `${pct}%` }}
                      />
                    )}
                  </div>
                </div>
              </div>
              <span className="text-xs font-mono w-14 text-right shrink-0">
                <span className={a.issue === 'optimal' ? 'text-green-400' : a.issue === 'too-loud' ? 'text-red-400' : 'text-amber-400'}>
                  {a.diffDb > 0 ? '+' : ''}{a.diffDb.toFixed(1)}
                </span>
              </span>
              <span className={`w-2 h-2 rounded-full shrink-0 ${issueColor(a.issue)}`} />
            </div>
          );
        })}
      </div>

      {/* Diagnostic cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {/* Dynamics */}
        <div className="bg-bg-card border border-border rounded-sm p-3">
          <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-1">Dynamics</p>
          <p className={`text-sm font-mono font-bold ${
            report.dynamicsAdvice.issue === 'optimal' ? 'text-green-400' :
            report.dynamicsAdvice.issue === 'too-compressed' ? 'text-red-400' : 'text-amber-400'
          }`}>
            {report.dynamicsAdvice.issue === 'optimal' ? 'ON TARGET' :
             report.dynamicsAdvice.issue === 'too-compressed' ? 'OVER-COMPRESSED' : 'TOO DYNAMIC'}
          </p>
          <p className="text-xs font-mono text-text-secondary mt-1">
            Crest: {report.dynamicsAdvice.actualCrest} dB
          </p>
        </div>

        {/* PLR */}
        {report.plrAdvice && (
          <div className="bg-bg-card border border-border rounded-sm p-3">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-1">PLR</p>
            <p className={`text-sm font-mono font-bold ${
              report.plrAdvice.issue === 'optimal' ? 'text-green-400' :
              report.plrAdvice.issue === 'too-crushed' ? 'text-red-400' : 'text-amber-400'
            }`}>
              {report.plrAdvice.issue === 'optimal' ? 'ON TARGET' :
               report.plrAdvice.issue === 'too-crushed' ? 'CRUSHED' : 'VERY OPEN'}
            </p>
            <p className="text-xs font-mono text-text-secondary mt-1">
              PLR: {report.plrAdvice.actualPlr} dB
            </p>
          </div>
        )}

        {/* Loudness */}
        {report.loudnessAdvice && (
          <div className="bg-bg-card border border-border rounded-sm p-3">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-1">Loudness</p>
            <p className={`text-sm font-mono font-bold ${
              report.loudnessAdvice.issue === 'optimal' ? 'text-green-400' :
              report.loudnessAdvice.issue === 'too-loud' ? 'text-red-400' : 'text-amber-400'
            }`}>
              {report.loudnessAdvice.issue === 'optimal' ? 'ON TARGET' :
               report.loudnessAdvice.issue === 'too-loud' ? 'TOO LOUD' : 'TOO QUIET'}
            </p>
            <p className="text-xs font-mono text-text-secondary mt-1">
              {report.loudnessAdvice.actualLufs} LUFS / {report.loudnessAdvice.truePeak} dBTP
            </p>
          </div>
        )}

        {/* Stereo */}
        {report.stereoAdvice && (
          <div className="bg-bg-card border border-border rounded-sm p-3">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-1">Stereo Field</p>
            <p className={`text-sm font-mono font-bold ${
              report.stereoAdvice.monoCompatible ? 'text-green-400' : 'text-red-400'
            }`}>
              {report.stereoAdvice.monoCompatible ? 'MONO SAFE' : 'PHASE RISK'}
            </p>
            <p className="text-xs font-mono text-text-secondary mt-1">
              Corr: {report.stereoAdvice.correlation.toFixed(2)} / Width: {Math.round(report.stereoAdvice.width * 100)}%
            </p>
          </div>
        )}
      </div>

      {/* Non-optimal band advice */}
      {(() => {
        const issues = report.advice.filter(a => a.issue !== 'optimal');
        if (issues.length === 0) return null;
        return (
          <div className="bg-bg-card border border-border rounded-sm p-4 space-y-2">
            <p className="text-[10px] font-mono uppercase tracking-wide text-text-secondary mb-2">Band Issues</p>
            {issues.map(a => (
              <div key={a.band} className="flex items-start gap-2">
                <span className={`w-2 h-2 rounded-full mt-1 shrink-0 ${issueColor(a.issue)}`} />
                <div>
                  <span className="text-xs font-mono font-bold text-text-primary">{a.band}:</span>
                  <span className="text-xs font-mono text-text-secondary ml-1">{a.message}</span>
                </div>
              </div>
            ))}
          </div>
        );
      })()}
    </div>
  );
}
