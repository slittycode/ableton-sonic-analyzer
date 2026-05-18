import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { Panel } from './Panel';

const meta: Meta<typeof Panel> = {
  title: 'UI/Panel',
  component: Panel,
  args: { variant: 'surface', padding: 'md', tone: 'neutral' },
  argTypes: {
    variant: { control: 'radio', options: ['rack', 'surface', 'ghost', 'inset'] },
    padding: { control: 'radio', options: ['none', 'sm', 'md', 'lg'] },
    tone: {
      control: 'radio',
      options: ['neutral', 'active', 'success', 'warning', 'error'],
    },
  },
};

export default meta;
type Story = StoryObj<typeof Panel>;

export const Default: Story = {
  args: { children: 'A surface panel for sub-content inside a device.' },
};

export const VariantMatrix: Story = {
  render: () => (
    <div className="grid grid-cols-2 gap-4 min-w-[480px]">
      {(['rack', 'surface', 'ghost', 'inset'] as const).map((variant) => (
        <Panel key={variant} variant={variant} padding="md">
          <p className="font-mono text-[11px] uppercase tracking-wider text-text-secondary">
            variant: {variant}
          </p>
          <p className="font-mono text-xs text-text-primary mt-1">Sample body content.</p>
        </Panel>
      ))}
    </div>
  ),
};

export const ToneMatrix: Story = {
  render: () => (
    <div className="grid grid-cols-2 gap-4 min-w-[480px]">
      {(['neutral', 'active', 'success', 'warning', 'error'] as const).map((tone) => (
        <Panel key={tone} variant="rack" tone={tone} padding="md">
          <p className="font-mono text-[11px] uppercase tracking-wider text-text-secondary">
            rack tone: {tone}
          </p>
        </Panel>
      ))}
    </div>
  ),
};
