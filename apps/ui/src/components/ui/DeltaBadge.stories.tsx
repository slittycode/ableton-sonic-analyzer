import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { DeltaBadge } from './DeltaBadge';

const meta: Meta<typeof DeltaBadge> = {
  title: 'UI/DeltaBadge',
  component: DeltaBadge,
  args: { value: -1.8, unit: 'dB', okThreshold: 0.5, warnThreshold: 1.5 },
};

export default meta;
type Story = StoryObj<typeof DeltaBadge>;

export const Default: Story = {};

export const ThresholdLadder: Story = {
  render: () => (
    <div className="flex gap-2 flex-wrap">
      <DeltaBadge value={0.3} unit="dB" okThreshold={0.5} warnThreshold={1.5} />
      <DeltaBadge value={1.1} unit="dB" okThreshold={0.5} warnThreshold={1.5} />
      <DeltaBadge value={4.2} unit="dB" okThreshold={0.5} warnThreshold={1.5} />
      <DeltaBadge value={null} unit="dB" okThreshold={0.5} warnThreshold={1.5} />
    </div>
  ),
};
