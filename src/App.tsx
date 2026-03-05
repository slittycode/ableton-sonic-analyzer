import React, { useState } from 'react';
import { FileUpload } from './components/FileUpload';
import { AnalysisResults } from './components/AnalysisResults';
import { DiagnosticLog } from './components/DiagnosticLog';
import { WaveformPlayer } from './components/WaveformPlayer';
import { EQSpinner } from './components/EQSpinner';
import { analyzeAudio, isPhase2GeminiEnabled } from './services/analyzer';
import { Phase1Result, Phase2Result, DiagnosticLogEntry } from './types';
import { AudioWaveform, Sparkles, Activity } from 'lucide-react';

const MODELS = [
  { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro Preview (Recommended)' },
  { id: 'gemini-3.1-flash-preview', name: 'Gemini 3.1 Flash Preview' },
  { id: 'gemini-3-pro-preview', name: 'Gemini 3.0 Pro Preview' },
  { id: 'gemini-3-flash-preview', name: 'Gemini 3.0 Flash Preview' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
];

export default function App() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState(MODELS[0].id);
  const phase2Enabled = isPhase2GeminiEnabled();
  
  const [phase1Result, setPhase1Result] = useState<Phase1Result | null>(null);
  const [phase2Result, setPhase2Result] = useState<Phase2Result | null>(null);
  const [logs, setLogs] = useState<DiagnosticLogEntry[]>([]);
  
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  
  const [dspJsonInput, setDspJsonInput] = useState("");
  const [dspJsonError, setDspJsonError] = useState<string | null>(null);

  const handleJsonChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setDspJsonInput(val);
    if (val.trim()) {
      try {
        JSON.parse(val);
        setDspJsonError(null);
      } catch (err) {
        setDspJsonError("Invalid JSON format. Will proceed with audio-only analysis if started.");
      }
    } else {
      setDspJsonError(null);
    }
  };

  const handleFileSelect = (file: File) => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioFile(file);
    setAudioUrl(URL.createObjectURL(file));
    // Reset previous analysis
    setPhase1Result(null);
    setPhase2Result(null);
    setLogs([]);
    setError(null);
    setCurrentPhase(0);
  };

  const handleFileClear = () => {
    setAudioFile(null);
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(null);
    setPhase1Result(null);
    setPhase2Result(null);
    setLogs([]);
    setError(null);
    setCurrentPhase(0);
  };

  const handleStartAnalysis = async () => {
    if (!audioFile) return;
    
    let validJson: string | null = null;
    if (dspJsonInput.trim()) {
      try {
        JSON.parse(dspJsonInput);
        validJson = dspJsonInput;
      } catch (err) {
        // Validation already warns user, we proceed with null
      }
    }
    
    setIsAnalyzing(true);
    setCurrentPhase(1);
    setError(null);

    try {
      await analyzeAudio(
        audioFile,
        selectedModel,
        validJson,
        (result, log) => {
          setPhase1Result(result);
          setLogs(prev => [...prev, log]);
          setCurrentPhase(2);
        },
        (result, log) => {
          setPhase2Result(result);
          setLogs(prev => [...prev, log]);
          setCurrentPhase(0);
          setIsAnalyzing(false);
        },
        (err) => {
          setError(err.message);
          setIsAnalyzing(false);
          setCurrentPhase(0);
        }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setIsAnalyzing(false);
      setCurrentPhase(0);
    }
  };

  return (
    <div className="min-h-screen p-4 md:p-8 font-sans flex items-center justify-center bg-bg-app">
      <div className="w-full max-w-6xl bg-bg-panel border border-border rounded-sm shadow-md overflow-hidden flex flex-col">
        
        {/* Top Toolbar (Ableton style) */}
        <div className="h-10 bg-[#222] border-b border-border flex items-center justify-between px-4">
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <AudioWaveform className="w-4 h-4 text-accent" />
              <span className="text-xs font-bold text-text-primary tracking-wide">SonicAnalyzer</span>
            </div>
            <div className="h-4 w-px bg-border"></div>
            <span className="text-[10px] font-mono text-text-secondary uppercase">Live 12 Integration</span>
          </div>
          
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <label className="text-[10px] font-mono text-text-secondary uppercase">Model</label>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={isAnalyzing || !phase2Enabled}
                className="appearance-none bg-bg-card border border-border text-text-primary text-[10px] font-mono py-1 pl-2 pr-6 rounded-sm focus:outline-none focus:border-accent cursor-pointer disabled:opacity-50"
              >
                {MODELS.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name}
                  </option>
                ))}
              </select>
            </div>
            {!phase2Enabled && (
              <span className="text-[10px] font-mono text-text-secondary uppercase">PHASE 2 OFF</span>
            )}
            <div className="h-4 w-px bg-border"></div>
            <div className="flex items-center space-x-1">
              <span className="text-[10px] font-mono text-text-secondary uppercase">CPU</span>
              <div className="w-16 h-3 bg-bg-card border border-border rounded-sm overflow-hidden flex items-end p-[1px]">
                <div className={`w-full bg-accent transition-all duration-300 ${isAnalyzing ? 'h-[80%] animate-pulse' : 'h-[10%]'}`}></div>
              </div>
            </div>
          </div>
        </div>

        {/* Main Interface Area */}
        <div className="p-4 md:p-6 space-y-6 flex-grow">
          
          {/* Main Content */}
          <main className="space-y-6">
            
            {/* Upload & Preview Section */}
            <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-4 flex flex-col gap-4">
                <div className="flex flex-col">
                  <div className="bg-[#222] border border-border border-b-0 rounded-t-sm px-3 py-1.5 flex items-center">
                    <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
                    <h3 className="text-[10px] font-mono text-text-secondary uppercase tracking-wider">Input Source</h3>
                  </div>
                  <div className="bg-bg-card border border-border rounded-b-sm p-4 flex flex-col min-h-[220px]">
                    <FileUpload onFileSelect={handleFileSelect} onFileClear={handleFileClear} isLoading={isAnalyzing} />
                  </div>
                </div>

                <div className="flex flex-col flex-grow">
                  <div className="bg-[#222] border border-border border-b-0 rounded-t-sm px-3 py-1.5 flex items-center">
                    <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
                    <h3 className="text-[10px] font-mono text-text-secondary uppercase tracking-wider">DSP JSON (Optional)</h3>
                  </div>
                  <div className="flex-grow bg-bg-card border border-border rounded-b-sm p-4 flex flex-col min-h-[150px]">
                    <textarea
                      value={dspJsonInput}
                      onChange={handleJsonChange}
                      disabled={isAnalyzing}
                      placeholder="Paste DSP analysis JSON here..."
                      className="flex-grow w-full bg-bg-panel border border-border rounded-sm p-2 text-xs font-mono text-text-primary focus:border-accent focus:outline-none resize-none disabled:opacity-50 min-h-[100px]"
                    />
                    {dspJsonError && (
                      <p className="text-[10px] text-red-400 font-mono mt-2">{dspJsonError}</p>
                    )}
                  </div>
                </div>
              </div>

              <div className="lg:col-span-8 flex flex-col h-full">
                <div className="bg-[#222] border border-border border-b-0 rounded-t-sm px-3 py-1.5 flex items-center justify-between">
                  <div className="flex items-center">
                    <span className={`w-2 h-2 rounded-full mr-2 ${audioUrl ? 'bg-green-500' : 'bg-border'}`}></span>
                    <h3 className="text-[10px] font-mono text-text-secondary uppercase tracking-wider">Signal Monitor</h3>
                  </div>
                </div>
                
                <div className="flex-grow bg-bg-card border border-border rounded-b-sm p-4 relative flex flex-col">
                  {audioUrl && audioFile ? (
                    <div className="h-full flex flex-col justify-between relative z-10">
                      <WaveformPlayer audioUrl={audioUrl} audioFile={audioFile} />
                      
                      {!isAnalyzing && currentPhase === 0 && !phase1Result && (
                        <div className="mt-4 flex justify-end">
                          <button
                            onClick={handleStartAnalysis}
                            className="bg-accent hover:bg-[#ff9933] text-bg-app font-bold py-2 px-6 rounded-sm flex items-center transition-colors uppercase tracking-wider font-mono text-xs"
                          >
                            <Sparkles className="w-3 h-3 mr-2" />
                            Initiate Analysis
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center text-text-secondary opacity-50 font-mono text-xs border border-dashed border-border rounded-sm m-2 min-h-[150px] bg-bg-app">
                      <Activity className="w-8 h-8 mb-2" />
                      NO SIGNAL DETECTED
                    </div>
                  )}
                </div>
              </div>
            </section>

            {/* Status Display */}
            {error && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-sm text-red-400 text-xs font-mono flex items-center">
                <div className="w-2 h-2 bg-red-500 rounded-full mr-2"></div>
                ERROR: {error}
              </div>
            )}

            {isAnalyzing && (
              <div className="flex flex-col items-center justify-center p-8 border border-border bg-bg-card rounded-sm relative overflow-hidden">
                <EQSpinner audioUrl={audioUrl} />
                <p className="text-sm font-bold tracking-wide uppercase">
                  {currentPhase === 1 ? 'Phase 1: Metadata Extraction' : 'Phase 2: Sonic Deconstruction'}
                </p>
                <p className="text-[10px] font-mono text-text-secondary mt-1">PROCESSING AUDIO STREAM...</p>
              </div>
            )}

            {/* Results Section */}
            <AnalysisResults phase1={phase1Result} phase2={phase2Result} sourceFileName={audioFile?.name ?? null} />

            {/* Diagnostic Log */}
            <DiagnosticLog logs={logs} />
            
          </main>
        </div>
      </div>
    </div>
  );
}
