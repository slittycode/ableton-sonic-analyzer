/**
 * playbackFocus — keeps the page's full-track players from playing over each
 * other.
 *
 * Two things can play the reference track: the Signal Monitor's waveform
 * player (an <audio> element on the media clock) and Beat Check (a decoded
 * buffer on the audio engine's clock). Running both at once gives two
 * unsynchronised copies of the track — exactly the flamming Beat Check asks
 * the producer to listen for. Each track player claims focus when it starts
 * and stops itself when another one claims it.
 *
 * Deliberately not claimed by Key Check or Session Musician previews: those
 * are meant to sound *over* the track.
 *
 * A plain module (no audio, no React) so both the eagerly-loaded waveform
 * player and the lazily-loaded audio engine island can use it.
 */

export type PlaybackOwner = 'waveform' | 'beat-check';

type Listener = (owner: PlaybackOwner) => void;

const listeners = new Set<Listener>();

/** Announce that `owner` has started playing the track. */
export function claimPlaybackFocus(owner: PlaybackOwner): void {
  for (const listener of [...listeners]) listener(owner);
}

/** Called whenever any track player claims focus (including the caller's own claims). */
export function onPlaybackFocusClaimed(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
