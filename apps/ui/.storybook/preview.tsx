import React from 'react';
import type { Preview } from '@storybook/react-vite';

import '../src/index.css';
import { TooltipProvider } from '../src/components/ui/Tooltip';

const preview: Preview = {
  parameters: {
    backgrounds: {
      default: 'app',
      values: [
        { name: 'app', value: '#2b2b2b' },
        { name: 'panel', value: '#3c3c3c' },
        { name: 'card', value: '#444444' },
        { name: 'surface-dark', value: '#222222' },
      ],
    },
    layout: 'centered',
    controls: { expanded: true },
  },
  decorators: [
    (Story) => (
      <TooltipProvider>
        <div className="font-sans text-text-primary p-6 min-w-[320px]">
          <Story />
        </div>
      </TooltipProvider>
    ),
  ],
};

export default preview;
