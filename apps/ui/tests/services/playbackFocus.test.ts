import { describe, expect, it, vi } from 'vitest';

import { claimPlaybackFocus, onPlaybackFocusClaimed } from '../../src/services/playbackFocus';

describe('playbackFocus', () => {
  it('tells every subscribed player who started playing', () => {
    const waveform = vi.fn();
    const beatCheck = vi.fn();
    const stopWaveform = onPlaybackFocusClaimed(waveform);
    const stopBeatCheck = onPlaybackFocusClaimed(beatCheck);

    claimPlaybackFocus('beat-check');
    expect(waveform).toHaveBeenCalledWith('beat-check');
    expect(beatCheck).toHaveBeenCalledWith('beat-check');

    stopWaveform();
    stopBeatCheck();
  });

  it('stops notifying after unsubscribe, including from inside a callback', () => {
    const later = vi.fn();
    let unsubscribeSelf = () => {};
    const self = vi.fn(() => unsubscribeSelf());
    unsubscribeSelf = onPlaybackFocusClaimed(self);
    const stopLater = onPlaybackFocusClaimed(later);

    claimPlaybackFocus('waveform');
    claimPlaybackFocus('waveform');
    expect(self).toHaveBeenCalledTimes(1);
    expect(later).toHaveBeenCalledTimes(2);

    stopLater();
    claimPlaybackFocus('beat-check');
    expect(later).toHaveBeenCalledTimes(2);
  });
});
