import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { TimeReadout } from './TimeReadout';

const meta: Meta<typeof TimeReadout> = {
  title: 'UI/TimeReadout',
  component: TimeReadout,
  args: { elapsedMs: 42_000, estimateMs: 120_000 },
};

export default meta;
type Story = StoryObj<typeof TimeReadout>;

export const Default: Story = {};

export const Pending: Story = {
  args: { pending: true, estimateRangeMs: [60_000, 90_000] },
};

export const WithRange: Story = {
  args: { elapsedMs: 132_000, estimateRangeMs: [120_000, 180_000] },
};

export const NoEstimate: Story = {
  args: { elapsedMs: 9_500, estimateMs: undefined, estimateRangeMs: undefined },
};
