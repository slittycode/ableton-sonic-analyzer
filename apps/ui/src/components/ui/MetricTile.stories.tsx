import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { Music, AudioWaveform } from 'lucide-react';

import { MetricTile } from './MetricTile';
import { Pill } from './Pill';

const meta: Meta<typeof MetricTile> = {
  title: 'UI/MetricTile',
  component: MetricTile,
  args: {
    label: 'TEMPO',
    value: '126',
    unit: 'BPM',
    size: 'lg',
    accent: 'accent',
  },
  argTypes: {
    accent: {
      control: 'radio',
      options: ['none', 'accent', 'success', 'warning', 'error', 'neutral'],
    },
    size: { control: 'radio', options: ['sm', 'md', 'lg', 'xl'] },
    status: {
      control: 'radio',
      options: [undefined, 'idle', 'active', 'success', 'warning', 'error'],
    },
  },
};

export default meta;
type Story = StoryObj<typeof MetricTile>;

export const Default: Story = {};

export const MeasurementSummary: Story = {
  render: () => (
    <div className="grid grid-cols-4 gap-2 w-[640px]">
      <MetricTile label="TEMPO" value="126" unit="BPM" size="lg" accent="accent" />
      <MetricTile label="KEY SIG" value="A min" size="lg" accent="success" />
      <MetricTile label="METER" value="4/4" size="lg" />
      <MetricTile label="CHARACTER" value="DARK" size="lg" accent="neutral" />
    </div>
  ),
};

export const SizeMatrix: Story = {
  render: () => (
    <div className="grid grid-cols-4 gap-2 w-[640px]">
      {(['sm', 'md', 'lg', 'xl'] as const).map((size) => (
        <MetricTile key={size} label={`SIZE ${size}`} value="126" unit="BPM" size={size} accent="accent" />
      ))}
    </div>
  ),
};

export const WithHeaderRight: Story = {
  render: () => (
    <div className="w-[240px]">
      <MetricTile
        label="LUFS"
        value="-14.2"
        unit="dB"
        size="lg"
        accent="accent"
        status="success"
        headerRight={<Pill tone="success" size="xs">MEASURED</Pill>}
      />
    </div>
  ),
};

export const WithIconAndFooter: Story = {
  render: () => (
    <div className="w-[240px]">
      <MetricTile
        label="KEY"
        value="A min"
        size="lg"
        icon={<Music className="w-3 h-3" />}
        accent="success"
        footer={
          <span className="font-mono text-[9px] text-text-secondary">
            High confidence · 0.92
          </span>
        }
      />
    </div>
  ),
};

export const Stack: Story = {
  render: () => (
    <div className="space-y-2 w-[280px]">
      <MetricTile
        size="md"
        label="Sub bass"
        value="-12.4"
        unit="dB"
        icon={<AudioWaveform className="w-3 h-3" />}
        accent="accent"
      />
      <MetricTile
        size="md"
        label="Low mids"
        value="-9.1"
        unit="dB"
        icon={<AudioWaveform className="w-3 h-3" />}
        accent="success"
      />
      <MetricTile
        size="md"
        label="Highs"
        value="-15.7"
        unit="dB"
        icon={<AudioWaveform className="w-3 h-3" />}
        accent="warning"
      />
    </div>
  ),
};
