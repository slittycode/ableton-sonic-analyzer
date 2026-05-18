import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { Play, Square, Download, RotateCcw, X } from 'lucide-react';

import { Button } from './Button';

const meta: Meta<typeof Button> = {
  title: 'UI/Button',
  component: Button,
  args: {
    children: 'Run Analysis',
    variant: 'secondary',
    size: 'md',
  },
  argTypes: {
    variant: {
      control: 'radio',
      options: ['primary', 'secondary', 'ghost', 'danger', 'link'],
    },
    size: { control: 'radio', options: ['sm', 'md', 'lg'] },
  },
};

export default meta;
type Story = StoryObj<typeof Button>;

export const Default: Story = {};

export const Primary: Story = {
  args: { variant: 'primary', children: 'Run Analysis', ledIndicator: true },
};

export const VariantMatrix: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      {(['primary', 'secondary', 'ghost', 'danger', 'link'] as const).map((variant) => (
        <div key={variant} className="flex items-center gap-3">
          <span className="font-mono text-[10px] uppercase tracking-wider text-text-secondary w-20">
            {variant}
          </span>
          {(['sm', 'md', 'lg'] as const).map((size) => (
            <Button key={size} variant={variant} size={size}>
              {variant} · {size}
            </Button>
          ))}
        </div>
      ))}
    </div>
  ),
};

export const WithIcons: Story = {
  render: () => (
    <div className="flex flex-wrap gap-3">
      <Button variant="primary" leadingIcon={<Play className="w-3 h-3 fill-current" />}>
        Play
      </Button>
      <Button variant="secondary" leadingIcon={<Download className="w-3 h-3" />}>
        Download Report
      </Button>
      <Button variant="ghost" leadingIcon={<RotateCcw className="w-3 h-3" />}>
        Retry
      </Button>
      <Button variant="danger" leadingIcon={<Square className="w-3 h-3 fill-current" />}>
        Stop
      </Button>
    </div>
  ),
};

export const IconOnly: Story = {
  render: () => (
    <div className="flex gap-3">
      <Button variant="ghost" iconOnly size="sm" aria-label="Close">
        <X className="w-3 h-3" />
      </Button>
      <Button variant="secondary" iconOnly size="md" aria-label="Play">
        <Play className="w-3.5 h-3.5 fill-current" />
      </Button>
      <Button variant="primary" iconOnly size="lg" aria-label="Play">
        <Play className="w-4 h-4 fill-current" />
      </Button>
    </div>
  ),
};

export const Disabled: Story = {
  args: { disabled: true, children: 'Disabled' },
};

export const WithLedIndicator: Story = {
  args: { variant: 'primary', size: 'lg', ledIndicator: true, children: 'Run Analysis' },
};
