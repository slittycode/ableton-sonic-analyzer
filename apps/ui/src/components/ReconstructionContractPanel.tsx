/**
 * Reconstruction Contract — the verbatim recommendations.v1 envelope (ADR 0003).
 *
 * The rich Mix Chain / Patch cards are the producer-facing surface; this panel
 * is the honest machine view of the frozen, schema-validated, citation-gated
 * projection that actually flows to the export and the asa-ableton .als
 * generator. Flat, domain-agnostic, citation-required — every row carries ≥1
 * cited measurement by construction. Renders nothing when the envelope is
 * absent (older runs, stem_summary) or empty.
 */
import React, { useState } from 'react';
import { ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react';

import type { Phase1Result } from '../types';
import type { RecommendationsContract } from '../types/interpretation';
import {
  projectContractRows,
  type ContractRow,
} from '../services/recommendationsContract';
import { DataTable, type DataTableColumn, Panel, SectionHeader } from './ui';

interface ReconstructionContractPanelProps {
  phase1: Phase1Result;
  contract?: RecommendationsContract;
}

const COLUMNS: DataTableColumn<ContractRow>[] = [
  { key: 'device', label: 'Device' },
  { key: 'parameter', label: 'Parameter' },
  {
    key: 'value',
    label: 'Value',
    render: (row) => (
      <span className="font-mono tabular-nums text-text-primary">{row.value}</span>
    ),
  },
  {
    key: 'citations',
    label: 'Cited measurements',
    render: (row) => (
      <div className="flex flex-col gap-0.5">
        {row.citations.map((citation, index) => (
          <span key={index} className="font-mono text-[10px] text-text-secondary">
            {citation}
          </span>
        ))}
      </div>
    ),
  },
];

export function ReconstructionContractPanel({
  phase1,
  contract,
}: ReconstructionContractPanelProps) {
  const [open, setOpen] = useState(false);
  const rows = projectContractRows(contract, phase1);
  if (rows.length === 0) {
    return null;
  }

  return (
    <Panel variant="surface" padding="none" className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-full text-left px-4 py-3 hover:bg-bg-panel transition-colors"
        aria-expanded={open}
      >
        <SectionHeader
          ledTone="success"
          title={
            <span className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-success" />
              Reconstruction Contract
            </span>
          }
          eyebrow={`${rows.length} citation-gated, schema-validated recommendation${
            rows.length === 1 ? '' : 's'
          } — the exact set exported to the .als generator`}
          action={
            open ? (
              <ChevronDown className="w-4 h-4 text-text-secondary" />
            ) : (
              <ChevronRight className="w-4 h-4 text-text-secondary" />
            )
          }
        />
      </button>
      {open && (
        <div className="px-4 pb-4">
          <DataTable data={rows} columns={COLUMNS} />
        </div>
      )}
    </Panel>
  );
}
