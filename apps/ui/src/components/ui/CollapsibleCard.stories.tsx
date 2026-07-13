import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { CollapsibleCard } from './CollapsibleCard';
import { Pill } from './Pill';
import { Button } from './Button';

const meta: Meta<typeof CollapsibleCard> = {
  title: 'UI/CollapsibleCard',
  component: CollapsibleCard,
  args: {
    title: 'Sonic Elements',
    eyebrow: 'Reconstruction',
    tone: 'neutral',
    variant: 'surface',
  },
  argTypes: {
    tone: {
      control: 'radio',
      options: ['neutral', 'accent', 'success', 'warning', 'error'],
    },
    variant: {
      control: 'radio',
      options: ['surface', 'ghost', 'inset', 'rack'],
    },
    open: { control: 'boolean' },
  },
};

export default meta;
type Story = StoryObj<typeof CollapsibleCard>;

const sampleBody = (
  <div className="space-y-2 text-text-secondary text-body-sm">
    <p>Kick · sub-weighted, ~55 Hz fundamental, short decay.</p>
    <p>Bass · saw-driven, mono below 120 Hz, light glide.</p>
    <p>Lead · detuned supersaw, wide stereo, bright top end.</p>
  </div>
);

/** Interactive wrapper — CollapsibleCard is controlled, so stories own the open state. */
function Interactive(args: React.ComponentProps<typeof CollapsibleCard>) {
  const [open, setOpen] = React.useState(args.open ?? true);
  return (
    <div className="min-w-[420px]">
      <CollapsibleCard {...args} open={open} onToggle={() => setOpen((v) => !v)} />
    </div>
  );
}

export const Default: Story = {
  render: (args) => <Interactive {...args} />,
  args: { open: true, children: sampleBody },
};

export const Collapsed: Story = {
  render: (args) => <Interactive {...args} />,
  args: { open: false, children: sampleBody },
};

export const PrimaryAccent: Story = {
  render: (args) => <Interactive {...args} />,
  args: {
    open: true,
    tone: 'accent',
    title: 'Mix & Master Chain',
    eyebrow: 'Primary',
    children: sampleBody,
  },
};

export const WithActions: Story = {
  render: (args) => <Interactive {...args} />,
  args: {
    open: true,
    title: 'Patch Framework',
    eyebrow: 'Synthesis',
    action: (
      <>
        <Pill tone="success">verified</Pill>
        <Button variant="secondary" size="sm">
          Apply
        </Button>
      </>
    ),
    children: sampleBody,
  },
};

export const AllTones: Story = {
  render: () => (
    <div className="flex flex-col gap-4 min-w-[420px]">
      {(['neutral', 'accent', 'success', 'warning', 'error'] as const).map((tone) => (
        <CollapsibleCard
          key={tone}
          tone={tone}
          title={`Tone · ${tone}`}
          eyebrow="example"
          open
          onToggle={() => {}}
        >
          {sampleBody}
        </CollapsibleCard>
      ))}
    </div>
  ),
};
