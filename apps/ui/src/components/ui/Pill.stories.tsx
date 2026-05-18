import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { Pill } from './Pill';

const meta: Meta<typeof Pill> = {
  title: 'UI/Pill',
  component: Pill,
  args: { children: 'Pill', tone: 'neutral', variant: 'solid', size: 'sm' },
  argTypes: {
    tone: { control: 'radio', options: ['accent', 'success', 'warning', 'error', 'neutral'] },
    variant: { control: 'radio', options: ['solid', 'outline', 'ghost'] },
    size: { control: 'radio', options: ['xs', 'sm'] },
  },
};

export default meta;
type Story = StoryObj<typeof Pill>;

export const Default: Story = {};

export const TonesMatrix: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      {(['solid', 'outline', 'ghost'] as const).map((variant) => (
        <div key={variant} className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-[10px] uppercase tracking-wider text-text-secondary w-16">
            {variant}
          </span>
          {(['accent', 'success', 'warning', 'error', 'neutral'] as const).map((tone) => (
            <Pill key={tone} tone={tone} variant={variant}>
              {tone}
            </Pill>
          ))}
        </div>
      ))}
    </div>
  ),
};

export const WithLeadingDot: Story = {
  render: () => (
    <div className="flex gap-2 flex-wrap">
      <Pill tone="success" leadingDot>Measured</Pill>
      <Pill tone="warning" leadingDot>Low confidence</Pill>
      <Pill tone="error" leadingDot>Failed</Pill>
      <Pill tone="accent" leadingDot>Active</Pill>
    </div>
  ),
};

export const ConfidenceBadges: Story = {
  render: () => (
    <div className="flex gap-2 flex-wrap">
      <Pill tone="success">HIGH confidence</Pill>
      <Pill tone="neutral">MED confidence</Pill>
      <Pill tone="warning">Low confidence</Pill>
    </div>
  ),
};
