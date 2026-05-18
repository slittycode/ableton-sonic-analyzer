import React from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';

import { DataTable } from './DataTable';
import { Pill } from './Pill';

const meta: Meta<typeof DataTable> = {
  title: 'UI/DataTable',
  component: DataTable as React.ComponentType<unknown>,
};

export default meta;
type Story = StoryObj<typeof DataTable>;

interface Row {
  band: string;
  energy: string;
  target: string;
  delta: string;
  status: 'success' | 'warning' | 'error';
}

const rows: Row[] = [
  { band: 'Sub bass', energy: '-14.2 dB', target: '-12.0', delta: '-2.2', status: 'warning' },
  { band: 'Low mids', energy: '-9.1 dB', target: '-10.0', delta: '+0.9', status: 'success' },
  { band: 'Mids', energy: '-8.4 dB', target: '-8.0', delta: '-0.4', status: 'success' },
  { band: 'High mids', energy: '-11.3 dB', target: '-9.0', delta: '-2.3', status: 'warning' },
  { band: 'Highs', energy: '-15.7 dB', target: '-13.0', delta: '-2.7', status: 'error' },
];

export const Default: Story = {
  render: () => (
    <div className="w-[680px]">
      <DataTable<Row>
        data={rows}
        columns={[
          { key: 'band', label: 'Band', textRole: 'item-title' },
          { key: 'energy', label: 'Energy', align: 'right', monospace: true, textRole: 'value' },
          { key: 'target', label: 'Target', align: 'right', monospace: true, textRole: 'meta' },
          { key: 'delta', label: 'Δ', align: 'right', monospace: true, textRole: 'value' },
          {
            key: 'status',
            label: 'Status',
            align: 'right',
            render: (row) => (
              <Pill
                tone={row.status === 'error' ? 'error' : row.status === 'warning' ? 'warning' : 'success'}
                size="xs"
              >
                {row.status}
              </Pill>
            ),
          },
        ]}
      />
    </div>
  ),
};
