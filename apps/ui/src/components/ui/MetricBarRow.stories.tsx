import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { MetricBarRow } from './MetricBarRow';

const meta: Meta<typeof MetricBarRow> = {
  title: 'UI/MetricBarRow',
  component: MetricBarRow,
  args: {
    label: 'Integrated loudness',
    valueLabel: '-14.2 LUFS',
    value: -14.2,
    min: -23,
    max: -6,
  },
};

export default meta;
type Story = StoryObj<typeof MetricBarRow>;

export const Default: Story = {
  render: (args) => (
    <div className="w-[420px]">
      <MetricBarRow {...args} />
    </div>
  ),
};

export const Stack: Story = {
  render: () => (
    <div className="w-[420px] space-y-3">
      <MetricBarRow label="LUFS integrated" valueLabel="-14.2" value={-14.2} min={-23} max={-6} />
      <MetricBarRow
        label="LUFS short-term"
        valueLabel="-12.5"
        value={-12.5}
        min={-23}
        max={-6}
        color="var(--color-success)"
      />
      <MetricBarRow
        label="True peak"
        valueLabel="-1.0 dBTP"
        value={-1.0}
        min={-6}
        max={0}
        color="var(--color-warning)"
      />
    </div>
  ),
};
