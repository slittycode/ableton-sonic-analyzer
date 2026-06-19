import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { TokenBadgeList } from './TokenBadgeList';

const meta: Meta<typeof TokenBadgeList> = {
  title: 'UI/TokenBadgeList',
  component: TokenBadgeList,
  args: {
    items: [
      { label: 'house', tone: 'accent' },
      { label: 'techno', tone: 'neutral' },
    ],
  },
};

export default meta;
type Story = StoryObj<typeof TokenBadgeList>;

export const Default: Story = {};

export const Tones: Story = {
  render: () => (
    <TokenBadgeList
      items={[
        { label: 'accent', tone: 'accent' },
        { label: 'success', tone: 'success' },
        { label: 'warning', tone: 'warning' },
        { label: 'error', tone: 'error' },
        { label: 'neutral', tone: 'neutral' },
      ]}
    />
  ),
};
