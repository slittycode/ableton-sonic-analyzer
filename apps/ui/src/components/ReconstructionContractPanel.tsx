/**
 * Reconstruction Contract — the verbatim recommendations.v1 envelope (ADR 0003).
 *
 * The recommendation cards pair each device with its contract entry inline
 * (ContractValidatedBadge / ContractEntriesBlock). This panel is the
 * complementary single machine-view: the flat, schema-validated, citation-gated
 * set exactly as it is exported to the asa-ableton .als generator and the
 * phase2-export envelope. Every row carries ≥1 cited measurement by
 * construction. Renders nothing when the envelope is absent (older runs,
 * stem_summary) or empty.
 */
import React, { useState } from 'react';

import type { RecommendationsContract, RecommendationContractEntry } from '../types';
import { formatContractValue, formatContractRange } from '../services/recommendationsContract';
import { CollapsibleCard, DataTable, type DataTableColumn } from './ui';

interface ReconstructionContractPanelProps {
  contract?: RecommendationsContract | null;
  className?: string;
}

const COLUMNS: DataTableColumn<RecommendationContractEntry>[] = [
  { key: 'device', label: 'Device' },
  { key: 'parameter', label: 'Parameter' },
  {
    key: 'value',
    label: 'Value',
    render: (entry) => (
      <span className="font-mono tabular-nums text-text-primary">
        {formatContractValue(entry)}
      </span>
    ),
  },
  {
    key: 'range',
    label: 'Working range',
    render: (entry) => {
      const range = formatContractRange(entry);
      return (
        <span className="font-mono tabular-nums text-text-secondary">{range ?? '—'}</span>
      );
    },
  },
  {
    key: 'cited_measurements',
    label: 'Cited measurements',
    render: (entry) => (
      <div className="flex flex-col gap-0.5">
        {entry.cited_measurements.map((path, index) => (
          <span key={index} className="font-mono text-micro text-text-secondary">
            {path}
          </span>
        ))}
      </div>
    ),
  },
];

export function ReconstructionContractPanel({
  contract,
  className,
}: ReconstructionContractPanelProps) {
  const [open, setOpen] = useState(false);
  const entries = contract?.recommendations ?? [];
  if (entries.length === 0) {
    return null;
  }

  return (
    <CollapsibleCard
      open={open}
      onToggle={() => setOpen((prev) => !prev)}
      tone="success"
      className={className}
      eyebrow="recommendations.v1 · exported to .als"
      title={`Reconstruction Contract · ${entries.length} validated recommendation${
        entries.length === 1 ? '' : 's'
      }`}
    >
      <DataTable data={entries} columns={COLUMNS} />
    </CollapsibleCard>
  );
}
