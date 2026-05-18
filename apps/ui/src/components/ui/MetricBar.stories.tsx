import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { MetricBar } from './MetricBar';

const meta: Meta<typeof MetricBar> = {
  title: 'UI/MetricBar',
  component: MetricBar,
  args: { value: 0.6, min: 0, max: 1, glow: true },
};

export default meta;
type Story = StoryObj<typeof MetricBar>;

export const Default: Story = {
  render: (args) => (
    <div className="w-[320px]">
      <MetricBar {...args} />
    </div>
  ),
};

export const Tones: Story = {
  render: () => (
    <div className="w-[320px] space-y-3">
      <MetricBar value={0.85} glow color="var(--color-accent)" leftLabel="0" rightLabel="100%" />
      <MetricBar value={0.7} glow color="var(--color-success)" leftLabel="0" rightLabel="100%" />
      <MetricBar value={0.5} glow color="var(--color-warning)" leftLabel="0" rightLabel="100%" />
      <MetricBar value={0.3} glow color="var(--color-error)" leftLabel="0" rightLabel="100%" />
    </div>
  ),
};

export const WithLabels: Story = {
  render: () => (
    <div className="w-[320px]">
      <MetricBar value={-14.2} min={-23} max={-6} glow leftLabel="-23 LUFS" rightLabel="-6 LUFS" />
    </div>
  ),
};
