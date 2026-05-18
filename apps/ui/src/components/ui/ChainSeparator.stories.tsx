import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { ChainSeparator } from './ChainSeparator';

const meta: Meta<typeof ChainSeparator> = {
  title: 'UI/ChainSeparator',
  component: ChainSeparator,
  args: { tone: 'active', animated: true, orientation: 'horizontal' },
  argTypes: {
    tone: { control: 'radio', options: ['idle', 'active', 'success'] },
    orientation: { control: 'radio', options: ['horizontal', 'vertical'] },
  },
};

export default meta;
type Story = StoryObj<typeof ChainSeparator>;

export const Horizontal: Story = {
  render: (args) => (
    <div className="flex items-center w-[320px] h-12 bg-bg-panel rounded-sm border border-border px-3">
      <ChainSeparator {...args} />
    </div>
  ),
};

export const Vertical: Story = {
  render: () => (
    <div className="flex flex-col items-center w-32 py-4 bg-bg-panel rounded-sm border border-border">
      <span className="font-mono text-[10px] text-text-secondary">UP</span>
      <ChainSeparator tone="active" animated orientation="vertical" />
      <span className="font-mono text-[10px] text-text-secondary">DOWN</span>
    </div>
  ),
};

export const Tones: Story = {
  render: () => (
    <div className="space-y-3 w-[320px]">
      {(['idle', 'active', 'success'] as const).map((tone) => (
        <div
          key={tone}
          className="flex items-center h-10 bg-bg-panel rounded-sm border border-border px-3 gap-3"
        >
          <span className="font-mono text-[10px] uppercase text-text-secondary w-12">
            {tone}
          </span>
          <ChainSeparator tone={tone} animated={tone === 'active'} />
        </div>
      ))}
    </div>
  ),
};
