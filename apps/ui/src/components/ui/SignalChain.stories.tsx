import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { RotateCcw } from 'lucide-react';

import { SignalChain, type SignalStageStatus } from './SignalChain';
import { Pill } from './Pill';
import { Button } from './Button';
import { TimeReadout } from './TimeReadout';

const meta: Meta<typeof SignalChain> = {
  title: 'UI/SignalChain',
  component: SignalChain,
};

export default meta;
type Story = StoryObj<typeof SignalChain>;

const baseStages = (
  measure: SignalStageStatus,
  pitch: SignalStageStatus,
  interpret: SignalStageStatus,
) => [
  {
    key: 'measure',
    name: 'MEASURE',
    status: measure,
    parameter:
      measure === 'success' ? (
        <TimeReadout elapsedMs={134_000} />
      ) : measure === 'active' ? (
        <TimeReadout elapsedMs={42_000} estimateRangeMs={[60_000, 90_000]} />
      ) : null,
    statusLabel:
      measure === 'success'
        ? 'DONE'
        : measure === 'active'
          ? 'RUNNING'
          : measure === 'error'
            ? 'FAILED'
            : measure === 'queued'
              ? 'QUEUED'
              : 'WAITING',
  },
  {
    key: 'pitch',
    name: 'PITCH/NOTE',
    status: pitch,
    parameter:
      pitch === 'active' ? (
        <Pill tone="accent">62%</Pill>
      ) : pitch === 'success' ? (
        <Pill tone="success">4 stems</Pill>
      ) : null,
    statusLabel:
      pitch === 'success'
        ? 'DONE'
        : pitch === 'active'
          ? 'RUNNING'
          : pitch === 'error'
            ? 'FAILED'
            : pitch === 'queued'
              ? 'QUEUED'
              : 'WAITING',
    action:
      pitch === 'error' ? (
        <Button variant="ghost" size="sm" leadingIcon={<RotateCcw className="w-3 h-3" />}>
          Retry
        </Button>
      ) : undefined,
  },
  {
    key: 'interpret',
    name: 'INTERPRET',
    status: interpret,
    parameter:
      interpret === 'success' ? (
        <Pill tone="success">Gemini 2.5</Pill>
      ) : null,
    statusLabel:
      interpret === 'success'
        ? 'DONE'
        : interpret === 'active'
          ? 'RUNNING'
          : interpret === 'error'
            ? 'FAILED'
            : interpret === 'queued'
              ? 'QUEUED'
              : 'WAITING',
  },
];

export const AllIdle: Story = {
  render: () => (
    <div className="w-[840px]">
      <SignalChain stages={baseStages('idle', 'idle', 'idle')} />
    </div>
  ),
};

export const Measuring: Story = {
  render: () => (
    <div className="w-[840px]">
      <SignalChain animated stages={baseStages('active', 'queued', 'queued')} />
    </div>
  ),
};

export const PitchActive: Story = {
  render: () => (
    <div className="w-[840px]">
      <SignalChain animated stages={baseStages('success', 'active', 'queued')} />
    </div>
  ),
};

export const InterpretActive: Story = {
  render: () => (
    <div className="w-[840px]">
      <SignalChain animated stages={baseStages('success', 'success', 'active')} />
    </div>
  ),
};

export const AllComplete: Story = {
  render: () => (
    <div className="w-[840px]">
      <SignalChain stages={baseStages('success', 'success', 'success')} />
    </div>
  ),
};

export const PitchFailed: Story = {
  render: () => (
    <div className="w-[840px]">
      <SignalChain stages={baseStages('success', 'error', 'idle')} />
    </div>
  ),
};

export const Vertical: Story = {
  render: () => (
    <div className="w-[320px]">
      <SignalChain orientation="vertical" animated stages={baseStages('success', 'active', 'queued')} />
    </div>
  ),
};
