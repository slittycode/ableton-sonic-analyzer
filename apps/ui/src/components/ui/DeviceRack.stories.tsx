import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { X, RotateCcw } from 'lucide-react';

import { DeviceRack } from './DeviceRack';
import { Button } from './Button';
import { MetricTile } from './MetricTile';
import { Pill } from './Pill';
import { SignalChain } from './SignalChain';

const meta: Meta<typeof DeviceRack> = {
  title: 'UI/DeviceRack',
  component: DeviceRack,
  args: {
    name: 'MEASUREMENT',
    subtitle: '· 4–5 min',
    status: 'idle',
  },
  argTypes: {
    status: {
      control: 'radio',
      options: ['idle', 'active', 'success', 'warning', 'error'],
    },
    density: { control: 'radio', options: ['normal', 'dense'] },
  },
};

export default meta;
type Story = StoryObj<typeof DeviceRack>;

// === 01 — Live 12 Vocabulary anchor: empty shell ===
export const EmptyShell: Story = {
  name: '01 · Empty Shell',
  render: () => (
    <div className="w-[420px]">
      <DeviceRack name="EMPTY RACK" status="idle">
        <p className="font-mono text-[11px] text-text-secondary">
          The bare Live 12 device chrome: title strip + LED + body.
        </p>
      </DeviceRack>
    </div>
  ),
};

// === 02 — Live 12 Vocabulary anchor: with parameter grid ===
export const WithParameterGrid: Story = {
  name: '02 · With Parameter Grid',
  render: () => (
    <div className="w-[640px]">
      <DeviceRack name="MEASUREMENT SUMMARY" status="success" density="dense">
        <div className="grid grid-cols-4 gap-2">
          <MetricTile label="TEMPO" value="126" unit="BPM" size="lg" accent="accent" />
          <MetricTile label="KEY SIG" value="A min" size="lg" accent="success" />
          <MetricTile label="METER" value="4/4" size="lg" />
          <MetricTile label="CHARACTER" value="DARK" size="lg" accent="neutral" />
        </div>
      </DeviceRack>
    </div>
  ),
};

// === 03 — Live 12 Vocabulary anchor: in a signal chain ===
export const InChain: Story = {
  name: '03 · In Chain',
  render: () => (
    <div className="w-[820px]">
      <SignalChain
        animated
        stages={[
          {
            key: 'measure',
            name: 'MEASURE',
            status: 'success',
            statusLabel: 'DONE',
            parameter: <Pill tone="success">2:14</Pill>,
          },
          {
            key: 'pitch',
            name: 'PITCH/NOTE',
            status: 'active',
            statusLabel: 'RUNNING',
            parameter: <Pill tone="accent">62%</Pill>,
          },
          {
            key: 'interpret',
            name: 'INTERPRET',
            status: 'queued',
            statusLabel: 'WAITING',
          },
        ]}
      />
    </div>
  ),
};

// === 04 — Live 12 Vocabulary anchor: active state progression ===
export const ActiveStateProgression: Story = {
  name: '04 · Active State Progression',
  render: () => (
    <div className="grid grid-cols-2 gap-4 w-[840px]">
      {(['idle', 'active', 'success', 'error'] as const).map((status) => (
        <DeviceRack
          key={status}
          name={`STATUS: ${status.toUpperCase()}`}
          status={status}
          density="dense"
        >
          <p className="font-mono text-[10px] text-text-secondary">
            box-shadow + LED reflect the status state.
          </p>
        </DeviceRack>
      ))}
    </div>
  ),
};

export const WithAction: Story = {
  render: () => (
    <div className="w-[480px]">
      <DeviceRack
        name="ANALYSIS RUN"
        subtitle="· a4f9c2b8"
        status="active"
        action={
          <Button variant="danger" size="sm" leadingIcon={<X className="w-3 h-3" />}>
            Stop
          </Button>
        }
      >
        <p className="font-mono text-[11px] text-text-secondary">
          Title-strip action slot. Button stays on the strip; body remains scrollable.
        </p>
      </DeviceRack>
    </div>
  ),
};

export const WithSignalRail: Story = {
  render: () => (
    <div className="w-[480px]">
      <DeviceRack
        name="PITCH/NOTE"
        status="active"
        signalIn="success"
        signalOut="idle"
        railContent={<span className="tabular-mono text-accent">62%</span>}
      >
        <div className="flex items-center justify-between">
          <span className="font-mono text-[11px] text-text-secondary">
            Stem analysis in progress
          </span>
          <Button variant="ghost" size="sm" leadingIcon={<RotateCcw className="w-3 h-3" />}>
            Retry
          </Button>
        </div>
      </DeviceRack>
    </div>
  ),
};
