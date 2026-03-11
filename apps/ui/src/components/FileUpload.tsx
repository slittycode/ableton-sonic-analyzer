import React, { useCallback, useEffect, useRef, useState } from 'react';
import { UploadCloud, FileAudio, X, AlertTriangle } from 'lucide-react';

import { isSupportedAudioFile } from '../services/audioFile';

interface FileUploadProps {
  onFileSelect: (file: File) => void;
  onFileClear: () => void;
  isLoading: boolean;
}

const FILE_SIZE_WARNING_BYTES = 100 * 1024 * 1024; // 100 MB

export function FileUpload({ onFileSelect, onFileClear, isLoading }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileSizeWarning, setFileSizeWarning] = useState<string | null>(null);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    return () => {
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    };
  }, []);

  const showFileError = useCallback((msg: string) => {
    setFileError(msg);
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    dismissTimerRef.current = setTimeout(() => setFileError(null), 4000);
  }, []);

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
      if (isLoading) return;

      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        const file = files[0];
        if (isSupportedAudioFile(file)) {
          setFileError(null);
          setFileSizeWarning(
            file.size > FILE_SIZE_WARNING_BYTES
              ? `Large file (${(file.size / (1024 * 1024)).toFixed(0)} MB). Analysis may take significantly longer.`
              : null,
          );
          setSelectedFile(file);
          onFileSelect(file);
        } else {
          showFileError('File type not supported. Please upload MP3, WAV, FLAC, or AIFF.');
        }
      }
    },
    [onFileSelect, isLoading, showFileError]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (isLoading) return;
      const files = e.target.files;
      if (files && files.length > 0) {
        const file = files[0];
        if (!isSupportedAudioFile(file)) {
          showFileError('File type not supported. Please upload MP3, WAV, FLAC, or AIFF.');
          return;
        }
        setFileError(null);
        setFileSizeWarning(
          file.size > FILE_SIZE_WARNING_BYTES
            ? `Large file (${(file.size / (1024 * 1024)).toFixed(0)} MB). Analysis may take significantly longer.`
            : null,
        );
        setSelectedFile(file);
        onFileSelect(file);
      }
    },
    [onFileSelect, isLoading, showFileError]
  );

  const clearFile = () => {
    if (isLoading) return;
    setSelectedFile(null);
    setFileSizeWarning(null);
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
          } ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
          onClick={() => !isLoading && document.getElementById('audio-upload')?.click()}
        >
          <input
            type="file"
            id="audio-upload"
            accept="audio/*"
            className="hidden"
            onChange={handleFileInput}
            disabled={isLoading}
          />
          <div className="w-12 h-12 rounded-sm bg-bg-panel border border-border flex items-center justify-center mb-4 group-hover:border-accent/50 transition-colors">
            <UploadCloud className="w-6 h-6 text-text-secondary group-hover:text-accent transition-colors" />
          </div>
          <p className="text-sm font-bold mb-1 tracking-wide text-text-primary">Drop Audio Here</p>
          <p className="text-[10px] text-text-secondary font-mono uppercase tracking-wider">or click to browse</p>
          <div className="mt-4 flex gap-2">
             {['MP3', 'WAV', 'FLAC', 'AIFF'].map(fmt => (
               <span key={fmt} className="text-[9px] font-mono text-text-secondary border border-border px-1.5 py-0.5 rounded-sm bg-bg-panel opacity-60">
                 {fmt}
               </span>
             ))}
          </div>
          {fileError && (
            <div className="mt-3 flex items-center gap-2 text-error text-[10px] font-mono uppercase tracking-wider" role="alert">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              {fileError}
            </div>
          )}
        </div>
      ) : (
        <div className="bg-bg-card border border-border rounded-sm p-4 flex items-center justify-between relative overflow-hidden group">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-accent"></div>
          <div className="flex items-center space-x-4 pl-2">
            <div className="bg-bg-panel p-2 rounded-sm border border-border">
              <FileAudio className="w-6 h-6 text-accent" />
            </div>
            <div>
              <p className="font-bold text-sm tracking-tight truncate max-w-[200px] md:max-w-xs">{selectedFile.name}</p>
              <p className="text-[10px] text-text-secondary font-mono uppercase tracking-wider flex items-center mt-1">
                <span className="w-1.5 h-1.5 rounded-full bg-success mr-2"></span>
                Ready • {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
              </p>
              {fileSizeWarning && (
                <p className="text-[10px] text-warning font-mono uppercase tracking-wider flex items-center mt-1">
                  <AlertTriangle className="w-3 h-3 shrink-0 mr-1.5" />
                  {fileSizeWarning}
                </p>
              )}
            </div>
          </div>
          {!isLoading && (
            <button
              onClick={clearFile}
              className="p-1.5 hover:bg-bg-panel rounded-sm border border-transparent hover:border-border transition-all group/btn"
              title="Remove File"
            >
              <X className="w-4 h-4 text-text-secondary group-hover/btn:text-error" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
