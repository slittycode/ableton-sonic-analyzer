import React from 'react';

import {
  formatDisplayText,
  getTextRoleClassName,
  type DisplayTextCase,
  type TextRole,
} from '../../utils/displayText';
import { cn } from './cn';

export interface DataTableColumn<T> {
  key: string;
  label: string;
  align?: 'left' | 'right';
  monospace?: boolean;
  displayCase?: DisplayTextCase;
  textRole?: TextRole;
  render?: (row: T) => React.ReactNode;
}

export interface DataTableProps<T> {
  data: T[];
  columns: DataTableColumn<T>[];
  rowClassName?: (row: T, index: number) => string;
  className?: string;
}

export function DataTable<T>({
  data,
  columns,
  rowClassName,
  className,
}: DataTableProps<T>) {
  return (
    <div
      className={cn(
        'overflow-x-auto rounded-sm border border-border-light',
        className,
      )}
    >
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-bg-card/75">
            {columns.map((column) => (
              <th
                key={column.key}
                data-text-role="eyebrow"
                className={cn(
                  'px-3 py-2 font-normal',
                  getTextRoleClassName('eyebrow'),
                  column.align === 'right' ? 'text-right' : 'text-left',
                )}
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
              className={cn(
                rowIndex % 2 === 0 ? 'bg-bg-surface-dark/95' : 'bg-bg-panel/70',
                'border-t border-border-light/60',
                rowClassName?.(row, rowIndex),
              )}
            >
              {columns.map((column) => {
                const rendered = column.render
                  ? column.render(row)
                  : ((row as Record<string, unknown>)[column.key] as React.ReactNode);
                const textRole = column.textRole ?? 'body';
                const isPrimitive =
                  typeof rendered === 'string' || typeof rendered === 'number';
                return (
                  <td
                    key={column.key}
                    className={cn(
                      'px-3 py-2 align-middle',
                      column.align === 'right' ? 'text-right' : 'text-left',
                    )}
                  >
                    {isPrimitive ? (
                      <span
                        data-text-role={textRole}
                        className={cn(
                          getTextRoleClassName(textRole),
                          column.monospace && 'tabular-nums',
                        )}
                      >
                        {typeof rendered === 'string'
                          ? formatDisplayText(rendered, column.displayCase ?? 'none')
                          : rendered}
                      </span>
                    ) : (
                      rendered
                    )}
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
