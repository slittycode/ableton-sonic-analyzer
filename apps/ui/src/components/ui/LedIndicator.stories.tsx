import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { LedIndicator } from './LedIndicator';

const meta: Meta<typeof LedIndicator> = {
  title: 'UI/LedIndicator',
  component: LedIndicator,
  args: { status: 'idle', size: 'sm' },
  argTypes: {
    status: {
      control: 'radio',
      options: ['idle', 'active', 'success', 'warning', 'error', 'pulsing'],
    },
    size: { control: 'radio', options: ['sm', 'md'] },
  },
};

export default meta;
type Story = StoryObj<typeof LedIndicator>;

export const Default: Story = {};

export const AllStates: Story = {
  render: () => (
    <div className="flex flex-col gap-3">
      {(['idle', 'active', 'success', 'warning', 'error', 'pulsing'] as const).map((status) => (
        <div key={status} className="flex items-center gap-3">
          <span className="font-mono text-[10px] uppercase tracking-wider text-text-secondary w-20">
            {status}
          </span>
          <LedIndicator status={status} />
          <LedIndicator status={status} size="md" />
          <LedIndicator status={status} label={status} />
        </div>
      ))}
    </div>
  ),
};
