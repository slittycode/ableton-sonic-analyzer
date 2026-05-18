import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { Tooltip } from './Tooltip';
import { Button } from './Button';

const meta: Meta<typeof Tooltip> = {
  title: 'UI/Tooltip',
  component: Tooltip,
  args: {
    text: 'Integrated loudness measured at 1-second resolution.',
    side: 'top',
    align: 'center',
  },
  argTypes: {
    side: { control: 'radio', options: ['top', 'right', 'bottom', 'left'] },
    align: { control: 'radio', options: ['start', 'center', 'end'] },
  },
};

export default meta;
type Story = StoryObj<typeof Tooltip>;

export const Default: Story = {
  render: (args) => (
    <Tooltip {...args}>
      <Button variant="secondary" size="sm">
        Hover me
      </Button>
    </Tooltip>
  ),
};

export const Sides: Story = {
  render: () => (
    <div className="grid grid-cols-2 gap-12 p-12">
      {(['top', 'right', 'bottom', 'left'] as const).map((side) => (
        <div key={side} className="flex justify-center">
          <Tooltip text={`Side: ${side}`} side={side}>
            <Button variant="ghost" size="sm">
              {side}
            </Button>
          </Tooltip>
        </div>
      ))}
    </div>
  ),
};
