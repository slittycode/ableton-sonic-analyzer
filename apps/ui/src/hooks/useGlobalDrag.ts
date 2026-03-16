import { useEffect, useRef, useState } from 'react';

interface UseGlobalDragOptions {
  disabled?: boolean;
  onFilesDrop?: (files: File[]) => void;
}

function eventHasFiles(event: DragEvent): boolean {
  const types = event.dataTransfer?.types;
  const items = event.dataTransfer?.items;

  if (types && Array.from(types).includes('Files')) {
    return true;
  }

  return Array.from(items ?? []).some((item) => item.kind === 'file');
}

export function useGlobalDrag({
  disabled = false,
  onFilesDrop,
}: UseGlobalDragOptions): { isDraggingFile: boolean } {
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const dragDepthRef = useRef(0);

  useEffect(() => {
    const resetDragState = () => {
      dragDepthRef.current = 0;
      setIsDraggingFile(false);
    };

    const handleDragEnter = (event: DragEvent) => {
      if (!eventHasFiles(event)) return;
      event.preventDefault();

      dragDepthRef.current += 1;
      if (!disabled) {
        setIsDraggingFile(true);
      }
    };

    const handleDragOver = (event: DragEvent) => {
      if (!eventHasFiles(event)) return;
      event.preventDefault();
      if (!disabled) {
        setIsDraggingFile(true);
      }
    };

    const handleDragLeave = (event: DragEvent) => {
      if (!eventHasFiles(event)) return;
      event.preventDefault();

      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
      if (dragDepthRef.current === 0) {
        setIsDraggingFile(false);
      }
    };

    const handleDrop = (event: DragEvent) => {
      if (!eventHasFiles(event)) return;
      event.preventDefault();

      const files = Array.from(event.dataTransfer?.files ?? []);
      resetDragState();

      if (!disabled && files.length > 0) {
        onFilesDrop?.(files);
      }
    };

    const handleWindowBlur = () => {
      resetDragState();
    };

    document.addEventListener('dragenter', handleDragEnter);
    document.addEventListener('dragover', handleDragOver);
    document.addEventListener('dragleave', handleDragLeave);
    document.addEventListener('drop', handleDrop);
    window.addEventListener('blur', handleWindowBlur);

    return () => {
      document.removeEventListener('dragenter', handleDragEnter);
      document.removeEventListener('dragover', handleDragOver);
      document.removeEventListener('dragleave', handleDragLeave);
      document.removeEventListener('drop', handleDrop);
      window.removeEventListener('blur', handleWindowBlur);
    };
  }, [disabled, onFilesDrop]);

  return { isDraggingFile };
}
