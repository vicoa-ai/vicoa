'use client';

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * A titled group card (e.g. "Details", "Frequency") wrapping flattened rows.
 * Rows are separated by hairlines, no per-chip borders — the ChatGPT
 * scheduled-tasks look.
 */
export function FieldGroup({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      {title && (
        <div className="px-1 text-sm font-normal text-muted-foreground">{title}</div>
      )}
      <div className="divide-y divide-border/60 overflow-hidden rounded-xl border border-border/60 bg-card/40">
        {children}
      </div>
    </div>
  );
}

/**
 * One flattened row: a left label and a right-aligned control. `align="start"`
 * top-aligns the control for tall editors (e.g. weekday chips that wrap).
 */
export function FieldRow({
  label,
  children,
  align = 'center',
}: {
  label: string;
  children: ReactNode;
  align?: 'center' | 'start';
}) {
  return (
    <div
      className={cn(
        'flex min-h-[44px] gap-3 px-3.5 py-2',
        align === 'center' ? 'items-center' : 'items-start',
      )}
    >
      <div
        className={cn(
          'shrink-0 text-sm text-foreground/80',
          align === 'start' && 'pt-1.5',
        )}
      >
        {label}
      </div>
      <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-1.5">
        {children}
      </div>
    </div>
  );
}
