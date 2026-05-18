import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { AlertTriangle, FileQuestion, Music2 } from 'lucide-react';

import { EmptyState } from './EmptyState';
import { Button } from './Button';

const meta: Meta<typeof EmptyState> = {
  title: 'UI/EmptyState',
  component: EmptyState,
  args: {
    tone: 'neutral',
    padding: 'md',
    title: 'No data yet',
    description: 'Run an analysis to populate this panel.',
  },
  argTypes: {
    tone: { control: 'radio', options: ['neutral', 'warning', 'error'] },
    padding: { control: 'radio', options: ['sm', 'md', 'lg'] },
  },
};

export default meta;
type Story = StoryObj<typeof EmptyState>;

export const Default: Story = {
  render: (args) => (
    <div className="w-[420px]">
      <EmptyState {...args} icon={<FileQuestion className="w-5 h-5" />} />
    </div>
  ),
};

export const Tones: Story = {
  render: () => (
    <div className="grid grid-cols-3 gap-3 w-[720px]">
      <EmptyState
        tone="neutral"
        icon={<FileQuestion className="w-5 h-5" />}
        title="No data yet"
        description="Run an analysis to populate this panel."
      />
      <EmptyState
        tone="warning"
        icon={<AlertTriangle className="w-5 h-5" />}
        title="Low confidence"
        description="Pitch estimate could not be locked. Treat as approximate."
      />
      <EmptyState
        tone="error"
        icon={<AlertTriangle className="w-5 h-5" />}
        title="Analysis failed"
        description="The pipeline returned an error. Retry or upload a different file."
      />
    </div>
  ),
};

export const WithAction: Story = {
  render: () => (
    <div className="w-[420px]">
      <EmptyState
        icon={<Music2 className="w-5 h-5" />}
        title="Session Musician off"
        description="Enable pitch/note translation to populate this panel."
        action={
          <Button variant="secondary" size="sm">
            Re-analyze with pitch/note
          </Button>
        }
      />
    </div>
  ),
};
