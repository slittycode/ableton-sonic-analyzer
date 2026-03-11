export interface MidiDisplayNote {
  midi: number;
  name: string;
  startTime: number;
  duration: number;
  velocity: number;
  confidence: number;
}

export type QuantizeGrid = 'off' | '1/4' | '1/8' | '1/16' | '1/32';

export interface QuantizeOptions {
  grid: QuantizeGrid;
  swing: number;
}
