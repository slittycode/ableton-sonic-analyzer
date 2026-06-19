import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { LaneContainer, LaneRow, StatsBar, TimeRuler } from './Lane';

const meta: Meta<typeof LaneContainer> = {
  title: 'UI/Lane',
  component: LaneContainer,
};

export default meta;
type Story = StoryObj<typeof LaneContainer>;

export const ArrangementLanes: Story = {
  render: () => (
    <LaneContainer>
      <StatsBar
        items={[
          { label: 'Key', value: 'A min' },
          { label: 'Strength', value: '82%', color: 'var(--color-accent)' },
          { label: 'Chords', value: '4' },
        ]}
      />
      <TimeRuler durationSeconds={180} label="Structure" />
      <LaneRow label="Progr.">
        <div className="flex h-full">
          {['Am', 'F', 'C', 'G'].map((c) => (
            <div
              key={c}
              className="flex-1 flex items-center justify-center border-r border-border-light last:border-r-0 text-eyebrow font-mono font-semibold text-text-primary"
            >
              {c}
            </div>
          ))}
        </div>
      </LaneRow>
      <LaneRow label="Pitch" height="h-7">
        <div className="flex items-center gap-4 px-3 h-full text-micro font-mono text-text-secondary">
          <span>bass · 110 Hz</span>
          <span>lead · 440 Hz</span>
        </div>
      </LaneRow>
    </LaneContainer>
  ),
};
