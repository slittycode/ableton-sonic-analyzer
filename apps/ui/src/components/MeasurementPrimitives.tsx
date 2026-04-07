import React from 'react';

import {
  formatDisplayText,
  getTextRoleClassName,
  type DisplayTextCase,
  type TextRole,
} from '../utils/displayText';

type PrimitiveTone =
  | 'accent'
  | 'success'
  | 'warning'
  | 'error'
  | 'muted'
  | 'info'
  | 'violet'
  | 'blue'
  | 'teal';

const BADGE_TONE_CLASSES: Record<PrimitiveTone, string> = {
  accent: 'border-accent/40 bg-accent/10 text-accent',
  success: 'border-success/30 bg-success/10 text-success',
  warning: 'border-warning/30 bg-warning/10 text-warning',
  error: 'border-error/30 bg-error/10 text-error',
  muted: 'border-border-light bg-bg-card/20 text-text-secondary',
  info: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  violet: 'border-violet-500/30 bg-violet-500/10 text-violet-300',
  blue: 'border-blue-500/30 bg-blue-500/10 text-blue-300',
  teal: 'border-teal-500/30 bg-teal-500/10 text-teal-300',
};

const ACCENT_CARD_CLASSES: Record<NonNullable<AccentMetricCardProps['accent']>, string> = {
  accent: 'border-l-2 border-accent',
  success: 'border-l-2 border-success',
  warning: 'border-l-2 border-warning',
  error: 'border-l-2 border-error',
  violet: 'border-l-2 border-violet-400',
  blue: 'border-l-2 border-blue-400',
  teal: 'border-l-2 border-teal-400',
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function resolvePercent({
  value,
  min = 0,
  max = 1,
  percent,
}: {
  value: number | null | undefined;
  min?: number;
  max?: number;
  percent?: number;
}): number {
  if (typeof percent === 'number' && Number.isFinite(percent)) {
    return clamp(percent, 0, 100);
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  if (max === min) return 0;
  return clamp(((value - min) / (max - min)) * 100, 0, 100);
}

function formatSignedNumber(value: number, decimals: number, showSign: boolean): string {
  const abs = Math.abs(value).toFixed(decimals);
  if (!showSign) return value.toFixed(decimals);
  return `${value >= 0 ? '+' : '-'}${abs}`;
}

export interface StatusBadgeProps {
  label: React.ReactNode;
  tone: PrimitiveTone;
  compact?: boolean;
  className?: string;
}

export function StatusBadge({
  label,
  tone,
  compact = false,
  className = '',
}: StatusBadgeProps) {
  return (
    <span
      className={[
        'inline-flex items-center rounded-sm border font-mono uppercase tracking-[0.18em]',
        compact ? 'px-1.5 py-0.5 text-[9px]' : 'px-2 py-1 text-[10px]',
        BADGE_TONE_CLASSES[tone],
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {label}
    </span>
  );
}

export interface DeltaBadgeProps {
  value: number | null | undefined;
  unit?: string;
  decimals?: number;
  okThreshold: number;
  warnThreshold: number;
  invert?: boolean;
  showSign?: boolean;
  className?: string;
}

export function DeltaBadge({
  value,
  unit,
  decimals = 1,
  okThreshold,
  warnThreshold,
  invert = false,
  showSign = true,
  className,
}: DeltaBadgeProps) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return <StatusBadge label="n/a" tone="muted" compact className={className} />;
  }

  const magnitude = Math.abs(value);
  const tone =
    magnitude <= okThreshold
      ? invert
        ? 'error'
        : 'success'
      : magnitude <= warnThreshold
        ? 'warning'
        : invert
          ? 'success'
          : 'error';
  const label = `${formatSignedNumber(value, decimals, showSign)}${unit ? ` ${unit}` : ''}`;

  return <StatusBadge label={label} tone={tone} compact className={className} />;
}

export interface MetricBarProps {
  value: number | null | undefined;
  min?: number;
  max?: number;
  percent?: number;
  color?: string;
  glow?: boolean;
  leftLabel?: string;
  rightLabel?: string;
  heightClassName?: string;
  className?: string;
}

export function MetricBar({
  value,
  min = 0,
  max = 1,
  percent,
  color = 'var(--color-accent)',
  glow = false,
  leftLabel,
  rightLabel,
  heightClassName = 'h-2',
  className = '',
}: MetricBarProps) {
  const width = resolvePercent({ value, min, max, percent });

  return (
    <div className={['space-y-1', className].filter(Boolean).join(' ')}>
      <div className={[heightClassName, 'rounded-full border border-border/30 bg-bg-app/80 overflow-hidden'].join(' ')}>
        <div
          className={[heightClassName, 'rounded-full transition-[width] duration-300 ease-out'].join(' ')}
          style={{
            width: `${width}%`,
            background: `linear-gradient(90deg, ${color}99, ${color})`,
            boxShadow: glow ? `0 0 14px ${color}44` : undefined,
          }}
        />
      </div>
      {(leftLabel || rightLabel) && (
        <div className="flex items-center justify-between text-[8px] font-mono text-text-secondary/50">
          <span>{leftLabel ?? ''}</span>
          <span>{rightLabel ?? ''}</span>
        </div>
      )}
    </div>
  );
}

export interface MetricBarRowProps {
  label: string;
  valueLabel: React.ReactNode;
  value: number | null | undefined;
  min?: number;
  max?: number;
  percent?: number;
  color?: string;
  sparkline?: React.ReactNode;
  leftLabel?: string;
  rightLabel?: string;
  monospaceValue?: boolean;
  className?: string;
}

export function MetricBarRow({
  label,
  valueLabel,
  value,
  min,
  max,
  percent,
  color,
  sparkline,
  leftLabel,
  rightLabel,
  monospaceValue = true,
  className = '',
}: MetricBarRowProps) {
  return (
    <div className={['space-y-1.5', className].filter(Boolean).join(' ')}>
      <div className="flex items-center justify-between gap-3">
        <span
          data-text-role="eyebrow"
          className={getTextRoleClassName('eyebrow')}
        >
          {formatDisplayText(label, 'eyebrow')}
        </span>
        <div className="flex items-center gap-2">
          {sparkline && <span className="shrink-0">{sparkline}</span>}
          <span
            data-text-role="value"
            className={[
              getTextRoleClassName('value'),
              monospaceValue ? 'tabular-nums' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            {valueLabel}
          </span>
        </div>
      </div>
      <MetricBar
        value={value}
        min={min}
        max={max}
        percent={percent}
        color={color}
        glow
        leftLabel={leftLabel}
        rightLabel={rightLabel}
      />
    </div>
  );
}

export interface AccentMetricCardProps {
  label: React.ReactNode;
  value: React.ReactNode;
  unit?: React.ReactNode;
  accent?: 'accent' | 'success' | 'warning' | 'error' | 'violet' | 'blue' | 'teal';
  headerRight?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export function AccentMetricCard({
  label,
  value,
  unit,
  accent = 'accent',
  headerRight,
  footer,
  className = '',
}: AccentMetricCardProps) {
  return (
    <div
      className={[
        'bg-bg-surface-dark border border-border-light rounded-sm p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]',
        ACCENT_CARD_CLASSES[accent],
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="flex items-start justify-between gap-3">
        <span
          data-text-role="eyebrow"
          className={getTextRoleClassName('eyebrow')}
        >
          {label}
        </span>
        {headerRight}
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span
          data-text-role="value"
          className={[getTextRoleClassName('value'), 'text-3xl'].join(' ')}
        >
          {value}
        </span>
        {unit && (
          <span
            data-text-role="meta"
            className={getTextRoleClassName('meta')}
          >
            {unit}
          </span>
        )}
      </div>
      {footer && <div className="mt-4">{footer}</div>}
    </div>
  );
}

export interface TokenBadgeListProps {
  items: Array<{ label: string; tone?: 'accent' | 'success' | 'warning' | 'error' | 'muted' | 'violet' | 'blue' }>;
  className?: string;
}

export function TokenBadgeList({ items, className = '' }: TokenBadgeListProps) {
  return (
    <div className={['flex flex-wrap gap-1.5', className].filter(Boolean).join(' ')}>
      {items.map((item, index) => (
        <span
          key={`${item.label}-${index}`}
          className={[
            'inline-flex items-center rounded-sm border px-2 py-1 text-[10px] font-mono tracking-wide',
            BADGE_TONE_CLASSES[item.tone ?? 'muted'],
          ].join(' ')}
        >
          {item.label}
        </span>
      ))}
    </div>
  );
}

export interface StyledDataTableColumn<T> {
  key: string;
  label: string;
  align?: 'left' | 'right';
  monospace?: boolean;
  displayCase?: DisplayTextCase;
  textRole?: TextRole;
  render?: (row: T) => React.ReactNode;
}

export interface StyledDataTableProps<T> {
  data: T[];
  columns: StyledDataTableColumn<T>[];
  rowClassName?: (row: T, index: number) => string;
  className?: string;
}

export function StyledDataTable<T>({
  data,
  columns,
  rowClassName,
  className = '',
}: StyledDataTableProps<T>) {
  const renderTextValue = (
    value: string | number,
    textRole: TextRole,
    displayCase: DisplayTextCase,
    monospace = false,
  ) => (
    <span
      data-text-role={textRole}
      className={[
        getTextRoleClassName(textRole),
        monospace ? 'tabular-nums' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {typeof value === 'string' ? formatDisplayText(value, displayCase) : value}
    </span>
  );

  return (
    <div className={['overflow-x-auto rounded-sm border border-border-light', className].filter(Boolean).join(' ')}>
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-card/75">
            {columns.map((column) => (
              <th
                key={column.key}
                className={[
                  'px-3 py-2 font-normal',
                  getTextRoleClassName('eyebrow'),
                  column.align === 'right' ? 'text-right' : 'text-left',
                ].join(' ')}
                data-text-role="eyebrow"
              >
                {formatDisplayText(column.label, 'eyebrow')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className={[
                rowIndex % 2 === 0 ? 'bg-bg-surface-dark/95' : 'bg-bg-panel/70',
                'border-t border-border-light/60',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {columns.map((column) => {
                const value = column.render
                  ? column.render(row)
                  : String((row as Record<string, unknown>)[column.key] ?? '—');
                return (
                  <td
                    key={`${rowIndex}-${column.key}`}
                    className={[
                      'px-3 py-2 align-top',
                      column.align === 'right' ? 'text-right' : 'text-left',
                      rowClassName?.(row, rowIndex) ?? '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                  >
                    {typeof value === 'string' || typeof value === 'number'
                      ? renderTextValue(
                          value,
                          column.textRole ?? (column.monospace ? 'value' : 'body'),
                          column.displayCase ?? 'none',
                          column.monospace,
                        )
                      : value}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export interface OutlinePillButtonProps {
  label: string;
  active?: boolean;
  done?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  tone?: 'accent' | 'success' | 'muted';
  className?: string;
}

export function OutlinePillButton({
  label,
  active = false,
  done = false,
  disabled = false,
  onClick,
  tone = 'muted',
  className = '',
}: OutlinePillButtonProps) {
  const resolvedTone = done ? 'success' : active ? tone : 'muted';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={[
        'rounded-sm border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
        BADGE_TONE_CLASSES[resolvedTone],
        !active && !done ? 'hover:border-accent/30 hover:text-text-primary' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {label}
    </button>
  );
}

/* ── DAW Lane Primitives ─────────────────────────────────────────────── */

export function LaneContainer({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-[#1a1a1a] border border-border rounded-sm overflow-hidden">
      {children}
    </div>
  );
}

export interface LaneRowProps {
  label: string;
  height?: string;
  children: React.ReactNode;
}

export function LaneRow({ label, height = 'h-8', children }: LaneRowProps) {
  return (
    <div className={`flex ${height} border-b border-[#2a2a2a] last:border-b-0`}>
      <div className="w-[72px] min-w-[72px] bg-[#252525] flex items-center px-2 border-r border-[#333]">
        <span className="text-[8px] font-mono text-[#777] uppercase tracking-[0.5px] truncate">
          {label}
        </span>
      </div>
      <div className="flex-1 relative bg-[#1e1e1e]">{children}</div>
    </div>
  );
}

export function TimeRuler({
  durationSeconds,
  label = 'Structure',
}: {
  durationSeconds: number;
  label?: string;
}) {
  const markerCount = Math.min(Math.max(Math.floor(durationSeconds / 30) + 1, 3), 10);
  const step = durationSeconds / (markerCount - 1);
  const markers = Array.from({ length: markerCount }, (_, i) => {
    const secs = Math.round(i * step);
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  });

  return (
    <div className="flex items-center h-6 bg-[#222] border-b border-[#333] px-2 gap-3">
      <span className="text-[9px] font-mono text-accent uppercase tracking-[1px]">{label}</span>
      <div className="flex-1 flex justify-between text-[8px] font-mono text-[#555]">
        {markers.map((m, i) => (
          <span key={i}>{m}</span>
        ))}
      </div>
    </div>
  );
}

export interface StatsBarItem {
  label: string;
  value: React.ReactNode;
  color?: string;
}

export function StatsBar({ items }: { items: StatsBarItem[] }) {
  return (
    <div className="flex h-7 bg-[#222] border-t border-[#333] px-2 items-center gap-4">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="text-[8px] font-mono text-[#555] uppercase">{item.label}</span>
          <span
            className="text-[10px] font-mono tabular-nums"
            style={{ color: item.color || '#e6e6e6' }}
          >
            {item.value}
          </span>
        </div>
      ))}
    </div>
  );
}
