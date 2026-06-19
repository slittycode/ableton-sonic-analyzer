import React, { useCallback, useEffect, useRef, useState } from 'react';
import { UploadCloud, FileAudio, X, AlertTriangle } from 'lucide-react';

import { isSupportedAudioFile } from '../services/audioFile';
import { Button, Panel, Pill } from './ui';

interface FileUploadProps {
  onFileSelect: (file: File) => void;
  onFileClear: () => void;
  onLoadDemoTrack: () => Promise<void> | void;
  isLoading: boolean;
  isDemoLoading?: boolean;
  selectedFile: File | null;
}

const FILE_SIZE_WARNING_BYTES = 100 * 1024 * 1024; // 100 MB

export function FileUpload({
  onFileSelect,
  onFileClear,
  onLoadDemoTrack,
  isLoading,
  isDemoLoading = false,
  selectedFile,
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileSizeWarning, setFileSizeWarning] = useState<string | null>(null);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!selectedFile) {
      setFileSizeWarning(null);
      return;
    }

    setFileSizeWarning(
      selectedFile.size > FILE_SIZE_WARNING_BYTES
        ? `Large file (${(selectedFile.size / (1024 * 1024)).toFixed(0)} MB). Analysis may take significantly longer.`
        : null,
    );
  }, [selectedFile]);

  const showFileError = useCallback((msg: string) => {
    setFileError(msg);
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    dismissTimerRef.current = setTimeout(() => setFileError(null), 4000);
  }, []);

  const handleAcceptedFile = useCallback(
    (file: File) => {
      setFileError(null);
      onFileSelect(file);
    },
    [onFileSelect],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (isLoading || isDemoLoading) return;

      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        const file = files[0];
        if (isSupportedAudioFile(file)) {
          handleAcceptedFile(file);
        } else {
          showFileError('File type not supported. Please upload MP3, WAV, FLAC, or AIFF.');
        }
      }
    },
    [handleAcceptedFile, isDemoLoading, isLoading, showFileError],
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (isLoading || isDemoLoading) return;
      const files = e.target.files;
      if (files && files.length > 0) {
        const file = files[0];
        if (!isSupportedAudioFile(file)) {
          showFileError('File type not supported. Please upload MP3, WAV, FLAC, or AIFF.');
          return;
        }
        handleAcceptedFile(file);
      }
    },
    [handleAcceptedFile, isDemoLoading, isLoading, showFileError],
  );

  const clearFile = () => {
    if (isLoading) return;
    onFileClear();
  };

  return (
    <div className="w-full h-full">
      {!selectedFile ? (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`h-full border border-dashed rounded-sm p-8 flex flex-col items-center justify-center transition-all cursor-pointer relative overflow-hidden group ${
            fileError
              ? 'border-error/50 bg-error/5'
              : isDragging
                ? 'border-accent bg-accent/5'
                : 'border-border bg-bg-card hover:border-text-secondary/50 hover:bg-bg-card-hover'
          } ${isLoading || isDemoLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
          onClick={() => !isLoading && !isDemoLoading && document.getElementById('audio-upload')?.click()}
        >
          <input
            type="file"
            id="audio-upload"
            accept="audio/*"
            className="hidden"
            onChange={handleFileInput}
            disabled={isLoading || isDemoLoading}
          />
          <div className="w-12 h-12 rounded-sm bg-bg-panel border border-border flex items-center justify-center mb-4 group-hover:border-accent/50 transition-colors">
            <UploadCloud className="w-6 h-6 text-text-secondary group-hover:text-accent transition-colors" />
          </div>
          <p className="text-sm font-bold mb-1 tracking-wide text-text-primary">Drop Audio Here</p>
          <p className="text-meta text-text-secondary font-mono uppercase tracking-wider">or click to browse</p>
          <div className="mt-4 flex gap-1.5">
            {['MP3', 'WAV', 'FLAC', 'AIFF'].map((fmt) => (
              <Pill key={fmt} tone="neutral" variant="outline" size="xs">
                {fmt}
              </Pill>
            ))}
          </div>
          <div className="mt-4">
            <Button
              variant="secondary"
              size="md"
              onClick={(event) => {
                event.stopPropagation();
                void onLoadDemoTrack();
              }}
              disabled={isLoading || isDemoLoading}
            >
              {isDemoLoading ? 'Loading Demo...' : 'Load Demo Track'}
            </Button>
          </div>
          {fileError && (
            <div className="mt-3 flex items-center gap-2 text-error text-meta font-mono uppercase tracking-wider" role="alert">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              {fileError}
            </div>
          )}
        </div>
      ) : (
        <Panel variant="surface" padding="md" className="relative overflow-hidden group">
          {/* Accent stripe down the left edge — the same Live device-on
              affordance used elsewhere. */}
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-accent" aria-hidden />
          <div className="flex items-center justify-between gap-3 pl-2">
            <div className="flex items-center gap-3 min-w-0">
              <div className="bg-bg-panel p-2 rounded-sm border border-border shrink-0">
                <FileAudio className="w-6 h-6 text-accent" />
              </div>
              <div className="min-w-0">
                <p className="font-bold text-sm tracking-tight truncate max-w-[200px] md:max-w-xs">
                  {selectedFile.name}
                </p>
                <p className="text-meta text-text-secondary font-mono uppercase tracking-wider flex items-center mt-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-success mr-2" aria-hidden />
                  Ready • {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                </p>
                {fileSizeWarning && (
                  <p className="text-meta text-warning font-mono uppercase tracking-wider flex items-center mt-1">
                    <AlertTriangle className="w-3 h-3 shrink-0 mr-1.5" />
                    {fileSizeWarning}
                  </p>
                )}
              </div>
            </div>
            {!isLoading && (
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                onClick={clearFile}
                title="Remove File"
                aria-label="Remove File"
              >
                <X className="w-4 h-4" />
              </Button>
            )}
          </div>
        </Panel>
      )}
    </div>
  );
}
