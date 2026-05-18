import React, { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { Checkbox } from './Checkbox';

const meta: Meta<typeof Checkbox> = {
  title: 'UI/Checkbox',
  component: Checkbox,
  args: { label: 'Pitch & note translation', defaultChecked: true, size: 'md' },
  argTypes: {
    size: { control: 'radio', options: ['sm', 'md', 'lg'] },
  },
};

export default meta;
type Story = StoryObj<typeof Checkbox>;

export const Default: Story = {};

export const WithDescription: Story = {
  args: {
    label: 'Pitch & note translation',
    description: 'Adds ~30s. Runs torchcrepe on separated stems.',
    defaultChecked: true,
  },
};

export const Controlled: Story = {
  render: () => {
    const [checked, setChecked] = useState<boolean | 'indeterminate'>(false);
    return (
      <Checkbox
        label="Include interpretation (Phase 2)"
        description="Runs the Gemini-backed Phase 2 advisor."
        checked={checked}
        onCheckedChange={setChecked}
      />
    );
  },
};

export const Sizes: Story = {
  render: () => (
    <div className="flex flex-col gap-3">
      <Checkbox size="sm" label="Small checkbox" defaultChecked />
      <Checkbox size="md" label="Medium checkbox" defaultChecked />
      <Checkbox size="lg" label="Large checkbox" defaultChecked />
    </div>
  ),
};

export const Disabled: Story = {
  args: { disabled: true, label: 'Disabled', defaultChecked: true },
};
