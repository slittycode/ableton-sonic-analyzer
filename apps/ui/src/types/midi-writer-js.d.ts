declare module 'midi-writer-js' {
  export class Track {
    addEvent(event: unknown, mapFunction?: (event: unknown, index: number) => unknown): Track;
    setTempo(bpm: number, tick?: number): Track;
  }

  export class ProgramChangeEvent {
    constructor(opts: { instrument: number; channel?: number });
  }

  export class NoteEvent {
    constructor(opts: {
      pitch: string | string[];
      duration: string | number | string[];
      velocity?: number;
      startTick?: number;
      channel?: number;
      wait?: string | number;
    });
  }

  export class Writer {
    constructor(tracks: Track[]);
    buildFile(): Uint8Array;
    dataUri(): string;
  }

  const MidiWriter: {
    Track: typeof Track;
    ProgramChangeEvent: typeof ProgramChangeEvent;
    NoteEvent: typeof NoteEvent;
    Writer: typeof Writer;
  };

  export default MidiWriter;
}
