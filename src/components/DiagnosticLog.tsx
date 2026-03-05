import React from 'react';
import { DiagnosticLogEntry } from '../types';
import { Terminal } from 'lucide-react';

interface DiagnosticLogProps {
  logs: DiagnosticLogEntry[];
}

export function DiagnosticLog({ logs }: DiagnosticLogProps) {
  if (logs.length === 0) return null;

  return (
    <div className="mt-12 space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-wider text-text-secondary flex items-center">
        <span className="w-2 h-2 bg-accent rounded-full mr-2"></span>
        System Diagnostics
      </h2>
      <div className="bg-[#1a1a1a] border border-border rounded-sm p-4 font-mono text-xs overflow-x-auto relative shadow-inner">
        <div className="space-y-4 relative z-10">
          {logs.map((log, idx) => (
            <div key={idx} className="space-y-1 border-l-2 border-border pl-3 ml-1 hover:border-accent/50 transition-colors group">
              <div className="flex items-center text-accent/80 group-hover:text-accent">
                <span className="mr-3 opacity-50">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                <span className="font-bold tracking-wide uppercase"> &gt;&gt; {log.phase}</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-8 gap-y-1 text-text-secondary/70 pl-2">
                <div className="flex justify-between gap-4">
                  <span className="opacity-50">MODEL:</span>
                  <span className="text-text-primary">{log.model}</span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="opacity-50">EXEC_TIME:</span>
                  <span className="text-text-primary">{log.durationMs}ms</span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="opacity-50">TOKENS_IN:</span>
                  <span className="text-text-primary">{log.promptLength}</span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="opacity-50">TOKENS_OUT:</span>
                  <span className="text-text-primary">{log.responseLength}</span>
                </div>
                {idx === 0 && (
                  <>
                    <div className="flex justify-between gap-4 col-span-1 md:col-span-2">
                      <span className="opacity-50">FILE:</span>
                      <span className="text-text-primary truncate">{log.audioMetadata.name}</span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="opacity-50">SIZE:</span>
                      <span className="text-text-primary">{(log.audioMetadata.size / 1024).toFixed(1)} KB</span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="opacity-50">TYPE:</span>
                      <span className="text-text-primary">{log.audioMetadata.type}</span>
                    </div>
                  </>
                )}
              </div>
            </div>
          ))}
          <div className="animate-pulse text-accent/50 pl-1">_</div>
        </div>
      </div>
    </div>
  );
}
