import React from 'react';
import { Phase1Result, Phase2Result } from '../types';
import { Music, Activity, Clock, Disc, Sliders, Settings2, CheckCircle2, XCircle, Layers, Info, BarChart3, Sparkles, Download, FileJson, FileText } from 'lucide-react';
import { motion } from 'motion/react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip } from 'recharts';
import { Tooltip } from './Tooltip';
import { downloadFile, generateMarkdown } from '../utils/exportUtils';

function FrequencyRangeBar({ range }: { range: string }) {
  const r = range.toLowerCase();
  
  let activeIndices = new Set<number>();
  
  if (r.includes('full') || r.includes('all') || r.includes('wide')) {
    [0,1,2,3,4,5,6].forEach(i => activeIndices.add(i));
  } else {
    if (r.includes('sub')) activeIndices.add(0);
    if (r.includes('low') || r.includes('bass') || r.includes('bottom')) {
      activeIndices.add(0);
      activeIndices.add(1);
      if (r.includes('mid')) activeIndices.add(2);
    }
    if (r.includes('mid')) {
      if (r.includes('low')) activeIndices.add(2);
      else if (r.includes('high') || r.includes('upper')) activeIndices.add(4);
      else {
        activeIndices.add(2);
        activeIndices.add(3);
        activeIndices.add(4);
      }
    }
    if (r.includes('high') || r.includes('treble') || r.includes('top')) {
      activeIndices.add(5);
      activeIndices.add(6);
      if (r.includes('mid')) activeIndices.add(4);
    }
    if (r.includes('air') || r.includes('presence') || r.includes('brilliance')) {
      activeIndices.add(6);
    }
  }
  
  // Fallback if nothing matched (e.g. they just gave numbers)
  if (activeIndices.size === 0) {
    if (r.includes('hz')) {
      if (r.includes('20') || r.includes('30') || r.includes('40') || r.includes('50') || r.includes('60')) activeIndices.add(0);
      if (r.includes('100') || r.includes('200')) activeIndices.add(1);
      if (r.includes('300') || r.includes('400') || r.includes('500')) activeIndices.add(2);
      if (r.includes('1k') || r.includes('2k') || r.includes('1000') || r.includes('2000')) activeIndices.add(3);
      if (r.includes('3k') || r.includes('4k') || r.includes('5k')) activeIndices.add(4);
      if (r.includes('6k') || r.includes('8k') || r.includes('10k')) activeIndices.add(5);
      if (r.includes('12k') || r.includes('15k') || r.includes('20k')) activeIndices.add(6);
    }
  }

  // If still empty, just light up the middle as a fallback
  if (activeIndices.size === 0) {
    activeIndices.add(3);
  }

  const colors = [
    'bg-[#FF4B4B]', // Sub
    'bg-[#FF8A27]', // Low
    'bg-[#E3C938]', // L-Mid
    'bg-[#89D966]', // Mid
    'bg-[#44C5D2]', // H-Mid
    'bg-[#4A8CFF]', // High
    'bg-[#B266FF]', // Air
  ];

  return (
    <div className="flex flex-col items-end">
      <div className="flex space-x-[2px] h-2 w-24 bg-bg-app border border-border p-[2px] rounded-sm mb-1" title={range}>
        {colors.map((color, i) => (
          <div key={i} className={`flex-1 h-full rounded-[1px] ${activeIndices.has(i) ? color : 'bg-border/30'}`} />
        ))}
      </div>
      <span className="text-[9px] font-mono text-text-secondary uppercase tracking-wider">{range}</span>
    </div>
  );
}

interface AnalysisResultsProps {
  phase1: Phase1Result | null;
  phase2: Phase2Result | null;
}

export function AnalysisResults({ phase1, phase2 }: AnalysisResultsProps) {
  if (!phase1) return null;

  const handleExportJSON = () => {
    const data = {
      phase1,
      phase2,
      exportedAt: new Date().toISOString(),
    };
    downloadFile(JSON.stringify(data, null, 2), 'track-analysis.json', 'application/json');
  };

  const handleExportMD = () => {
    const markdown = generateMarkdown(phase1, phase2);
    downloadFile(markdown, 'track-analysis.md', 'text/markdown');
  };

  let finalBpm = phase1.bpm;
  let hasBpmCorrection = false;
  if (phase2 && phase2.bpmCorrection !== undefined && phase2.bpmCorrection !== null && phase2.bpmCorrection !== 0 && phase2.bpmCorrection !== phase1.bpm) {
    finalBpm = phase2.bpmCorrection;
    hasBpmCorrection = true;
  }

  let finalKey = phase1.key;

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-12"
    >
      {/* Header & Export Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-border relative">
        <div>
          <h1 className="text-2xl font-display font-bold tracking-tight text-text-primary uppercase flex items-center">
            <Activity className="w-6 h-6 mr-3 text-accent" />
            Analysis Results
          </h1>
          <p className="text-text-secondary font-mono text-xs mt-1 tracking-wider uppercase opacity-70">
            SESSION ID: {new Date().getTime().toString(36).toUpperCase()} // PHASE COMPLETE
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExportJSON}
            className="flex items-center gap-2 px-4 py-2 bg-bg-panel border border-border rounded text-xs font-mono uppercase tracking-wider hover:bg-bg-card-hover hover:border-accent/50 transition-all group"
          >
            <FileJson className="w-3 h-3 text-text-secondary group-hover:text-accent" />
            <span>JSON_DATA</span>
          </button>
          <button
            onClick={handleExportMD}
            className="flex items-center gap-2 px-4 py-2 bg-accent/10 border border-accent/50 text-accent rounded text-xs font-mono uppercase tracking-wider hover:bg-accent/20 transition-all shadow-[0_0_10px_rgba(255,85,0,0.1)]"
          >
            <FileText className="w-3 h-3" />
            <span>REPORT_MD</span>
          </button>
        </div>
      </div>
      
      {/* Metadata Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-bg-panel border border-border rounded-sm p-1 relative group overflow-hidden">
          <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="bg-bg-card h-full p-4 rounded-sm flex flex-col items-center justify-center text-center border border-border/50 relative z-10">
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Activity className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase">TEMPO</span>
            </div>
            <div className="flex items-baseline space-x-1">
              <p className="text-3xl font-display font-bold text-text-primary">
                {finalBpm}
              </p>
              <span className="text-xs font-mono text-text-secondary">BPM</span>
            </div>
            {hasBpmCorrection && <span className="text-[10px] font-mono text-green-500 mt-1 uppercase tracking-wider">[CORRECTED]</span>}
            
            <div className="w-full bg-bg-app h-1 mt-3 overflow-hidden border border-border/30">
              <motion.div 
                initial={{ width: 0 }}
                animate={{ width: `${phase1.bpmConfidence * 100}%` }}
                className="h-full bg-accent shadow-[0_0_5px_#ff9500]"
              />
            </div>
            <p className="text-[10px] font-mono text-text-secondary mt-1 opacity-70">CONF: {(phase1.bpmConfidence * 100).toFixed(0)}%</p>
          </div>
        </div>
        
        <div className="bg-bg-panel border border-border rounded-sm p-1 relative group overflow-hidden">
          <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="bg-bg-card h-full p-4 rounded flex flex-col items-center justify-center text-center border border-border/50 relative z-10">
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Music className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase">KEY SIG</span>
            </div>
            <div className="flex items-baseline space-x-1">
              <p className="text-3xl font-display font-bold text-text-primary">
                {finalKey}
              </p>
            </div>
            
            <div className="w-full bg-bg-app h-1 mt-3 overflow-hidden border border-border/30">
              <motion.div 
                initial={{ width: 0 }}
                animate={{ width: `${phase1.keyConfidence * 100}%` }}
                className="h-full bg-accent shadow-[0_0_5px_#ff9500]"
              />
            </div>
            <p className="text-[10px] font-mono text-text-secondary mt-1 opacity-70">CONF: {(phase1.keyConfidence * 100).toFixed(0)}%</p>
          </div>
        </div>

        <div className="bg-bg-panel border border-border rounded-sm p-1 relative group overflow-hidden">
          <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="bg-bg-card h-full p-4 rounded flex flex-col items-center justify-center text-center border border-border/50 relative z-10">
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Clock className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase">METER</span>
            </div>
            <p className="text-3xl font-display font-bold text-text-primary mt-1">{phase1.timeSignature}</p>
            <p className="text-[10px] font-mono text-text-secondary mt-auto opacity-70">DETECTED</p>
          </div>
        </div>

        <div className="bg-bg-panel border border-border rounded-sm p-1 relative group overflow-hidden col-span-1 md:col-span-1">
          <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="bg-bg-card h-full p-4 rounded-sm flex flex-col items-center justify-center text-center border border-border/50 relative z-10">
            <div className="w-full flex justify-between items-start mb-2 opacity-50">
              <Disc className="w-4 h-4 text-accent" />
              <span className="text-[10px] font-mono uppercase">CHARACTER</span>
            </div>
            <p className="text-xs font-mono text-text-primary mt-1 line-clamp-3 w-full px-1 text-left">
              {phase2?.trackCharacter || "SCANNING..."}
            </p>
            <p className="text-[10px] font-mono text-text-secondary mt-auto opacity-70 pt-2">OVERVIEW</p>
          </div>
        </div>
      </div>

      {/* Detected Characteristics */}
      {phase2?.detectedCharacteristics && phase2.detectedCharacteristics.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Detected Characteristics
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">PHASE 2</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {phase2.detectedCharacteristics.map((char, idx) => (
              <div key={idx} className={`bg-bg-card border rounded-sm p-4 flex flex-col transition-all hover:border-accent/40 group relative overflow-hidden border-accent/30`}>
                <div className="absolute top-0 left-0 w-1 h-full bg-accent"></div>
                <div className="flex items-center justify-between mb-3 pl-2">
                  <h3 className="font-bold tracking-wide text-sm">{char.name}</h3>
                  <span className={`flex items-center text-[10px] font-mono font-bold px-2 py-1 rounded-sm border ${
                    char.confidence === 'HIGH' ? 'text-green-500 bg-green-500/10 border-green-500/20' :
                    char.confidence === 'MED' ? 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20' :
                    'text-red-500 bg-red-500/10 border-red-500/20'
                  }`}>
                    {char.confidence} CONFIDENCE
                  </span>
                </div>
                <div className="mt-auto space-y-2 pl-2">
                  <p className="text-xs text-text-secondary leading-relaxed font-mono opacity-80 border-t border-border/50 pt-2 mt-2">
                    {char.explanation}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Arrangement Section */}
      {phase2?.arrangementOverview && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Arrangement Overview
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">PHASE 2</span>
          </div>
          
          <div className="bg-bg-card border border-border rounded-sm p-6 relative overflow-hidden">
            <p className="text-sm text-text-secondary font-mono leading-relaxed opacity-80">
              {phase2.arrangementOverview}
            </p>
          </div>
        </div>
      )}

      {/* Phase 2: Sonic Elements */}
      {phase2?.sonicElements && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Sonic Elements & Reconstruction
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">PHASE 2</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(phase2.sonicElements).map(([key, value], idx) => (
              <div key={idx} className="bg-bg-card border border-border rounded-sm p-0 overflow-hidden group hover:border-accent/40 transition-all">
                {/* Module Header */}
                <div className="bg-bg-panel border-b border-border p-3 flex justify-between items-center">
                  <h3 className="text-sm font-bold uppercase tracking-wide text-text-primary flex items-center">
                    <div className="w-1.5 h-1.5 bg-accent rounded-full mr-2"></div>
                    {key.replace(/([A-Z])/g, ' $1').trim()}
                  </h3>
                </div>
                
                <div className="p-4 space-y-4 relative">
                  <div>
                    <p className="text-sm leading-relaxed font-mono text-text-primary/90 border-l-2 border-accent/20 pl-2">{value}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Mix and Master Chain */}
      {phase2?.mixAndMasterChain && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Mix and Master Chain
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">PHASE 2</span>
          </div>
          
          <div className="bg-bg-card border border-border rounded-sm p-6 relative overflow-hidden">
            <p className="text-sm text-text-secondary font-mono leading-relaxed opacity-80">
              {phase2.mixAndMasterChain}
            </p>
          </div>
        </div>
      )}

      {/* Confidence Notes */}
      {phase2?.confidenceNotes && phase2.confidenceNotes.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
              <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
              Confidence Notes
            </h2>
            <span className="text-[10px] font-mono bg-accent text-bg-app px-2 py-1 rounded font-bold">PHASE 2</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {phase2.confidenceNotes.map((note, idx) => (
              <div key={idx} className={`bg-bg-card border rounded-sm p-4 flex flex-col transition-all hover:border-orange-500/40 group relative overflow-hidden border-orange-500/30`}>
                <div className="absolute top-0 left-0 w-1 h-full bg-orange-500"></div>
                <div className="flex items-center justify-between mb-3 pl-2">
                  <h3 className="font-bold tracking-wide text-sm">{note.field}</h3>
                  <span className="text-[10px] font-mono text-orange-500 bg-orange-500/10 px-2 py-1 rounded border border-orange-500/20">
                    {note.value}
                  </span>
                </div>
                <div className="mt-auto space-y-2 pl-2">
                  <p className="text-xs text-text-secondary leading-relaxed font-mono opacity-80 border-t border-border/50 pt-2 mt-2">
                    {note.reason}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Phase 3: Mix Critique & Recommendations */}
      {phase2 && (
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="space-y-12"
        >
          {/* Secret Sauce Callout */}
          {phase2.secretSauce && (
            <div className="relative overflow-hidden bg-bg-card border border-accent/30 rounded-sm p-0 group">
              <div className="bg-accent/10 p-4 border-b border-accent/20 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="bg-accent text-bg-app p-1.5 rounded-sm">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <h2 className="text-sm font-bold tracking-wide uppercase text-accent">Secret Sauce Protocol</h2>
                </div>
                <span className="text-[10px] font-mono bg-accent/20 text-accent px-2 py-1 rounded-sm border border-accent/30">
                  CONFIDENTIAL
                </span>
              </div>
              
              <div className="p-6 relative">
                <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none">
                  <Sparkles className="w-32 h-32 text-accent" />
                </div>
                
                <div className="relative z-10 space-y-6">
                  <div className="space-y-2">
                    <h3 className="text-lg font-bold text-text-primary">{phase2.secretSauce.title}</h3>
                    <p className="text-sm font-mono text-text-secondary leading-relaxed max-w-3xl border-l-2 border-accent/30 pl-4">
                      {phase2.secretSauce.explanation}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-border/50">
                    {phase2.secretSauce.implementationSteps.map((step, idx) => (
                      <div key={idx} className="flex space-x-4 group/step">
                        <span className="flex-shrink-0 w-6 h-6 rounded-sm bg-bg-panel border border-border flex items-center justify-center text-accent font-mono text-xs group-hover/step:border-accent/50 transition-colors">
                          {idx + 1}
                        </span>
                        <p className="text-xs text-text-secondary leading-relaxed font-mono pt-1">
                          {step}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Ableton Recommendations */}
          {phase2.abletonRecommendations && phase2.abletonRecommendations.length > 0 && (
            <div className="space-y-6">
              <div className="flex items-center justify-between border-b border-border pb-2">
                <h2 className="text-sm font-mono uppercase tracking-wider flex items-center text-text-secondary">
                  <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
                  Live 12 Patch Framework
                </h2>
                <Sliders className="w-4 h-4 text-accent opacity-50" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {phase2.abletonRecommendations.map((rec, idx) => (
                  <div key={idx} className="bg-bg-card border border-border rounded-sm overflow-hidden group hover:border-accent/40 transition-colors flex flex-col">
                    <div className="bg-bg-panel border-b border-border p-3 flex justify-between items-start">
                      <div className="flex items-center">
                        <Settings2 className="w-4 h-4 mr-2 text-accent opacity-70" />
                        <h3 className="text-sm font-bold text-text-primary tracking-wide">{rec.device}</h3>
                      </div>
                      {rec.category && (
                        <span className="text-[9px] font-mono text-text-secondary uppercase bg-bg-app px-2 py-1 rounded border border-border/50">
                          {rec.category}
                        </span>
                      )}
                    </div>
                    <div className="p-4 flex-grow flex flex-col">
                      <div className="flex justify-between items-start mb-3 gap-4">
                        <div className="flex-1">
                          <p className="text-[10px] text-text-secondary font-mono uppercase tracking-wider mb-1">Parameter</p>
                          <div className="inline-block bg-bg-panel px-2 py-1 rounded border border-border/50 text-text-primary text-xs font-mono">
                            {rec.parameter}
                          </div>
                        </div>
                        <div className="flex-1 text-right">
                          <p className="text-[10px] text-text-secondary font-mono uppercase tracking-wider mb-1">Target Value</p>
                          <span className="text-accent font-bold text-sm font-mono">
                            {rec.value}
                          </span>
                        </div>
                      </div>
                      
                      <div className="mt-2 text-xs text-text-secondary/90 leading-relaxed font-mono border-l-2 border-border/50 pl-3">
                        {rec.reason}
                      </div>

                      {rec.advancedTip && (
                        <div className="mt-auto pt-4">
                          <div className="bg-accent/5 border border-accent/20 rounded-sm p-3">
                            <p className="text-[9px] text-accent font-mono uppercase tracking-wider mb-1 flex items-center">
                              <Sparkles className="w-3 h-3 mr-1" />
                              Pro Tip
                            </p>
                            <p className="text-xs text-text-primary/80 font-mono leading-relaxed">
                              {rec.advancedTip}
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}


