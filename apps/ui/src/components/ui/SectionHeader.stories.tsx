import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { Download } from 'lucide-react';

import { SectionHeader } from './SectionHeader';
import { Button } from './Button';

const meta: Meta<typeof SectionHeader> = {
  title: 'UI/SectionHeader',
  component: SectionHeader,
  args: {
    title: 'Mix Chain',
    variant: 'underline',
    size: 'md',
    ledTone: 'accent',
  },
  argTypes: {
    variant: { control: 'radio', options: ['inline', 'underline'] },
    size: { control: 'radio', options: ['sm', 'md', 'lg'] },
    ledTone: {
      control: 'radio',
      options: ['accent', 'success', 'warning', 'error', 'neutral'],
    },
    titleRole: {
      control: 'select',
      options: [
        undefined,
        'page-title',
        'section-title',
        'subsection-title',
        'item-title',
        'eyebrow',
        'body',
        'meta',
        'value',
      ],
    },
  },
};

export default meta;
type Story = StoryObj<typeof SectionHeader>;

export const Default: Story = {};

export const WithEyebrow: Story = {
  args: {
    eyebrow: 'ASA Results',
    title: 'Analysis Results',
    titleRole: 'page-title',
    size: 'lg',
  },
};

export const WithAction: Story = {
  args: {
    eyebrow: 'ASA Results',
    title: 'Analysis Results',
    titleRole: 'page-title',
    size: 'lg',
    action: (
      <>
        <Button variant="secondary" size="sm" leadingIcon={<Download className="w-3 h-3" />}>
          Download data
        </Button>
        <Button variant="primary" size="sm" leadingIcon={<Download className="w-3 h-3" />}>
          Download report
        </Button>
      </>
    ),
  },
};

export const AllSizes: Story = {
  render: () => (
    <div className="flex flex-col gap-6 min-w-[480px]">
      {(['sm', 'md', 'lg'] as const).map((size) => (
        <SectionHeader
          key={size}
          size={size}
          variant="underline"
          eyebrow={`size · ${size}`}
          title={`Section header (${size})`}
        />
      ))}
    </div>
  ),
};
