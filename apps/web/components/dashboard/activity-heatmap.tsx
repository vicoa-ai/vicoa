'use client';

import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { activityTooltip, buildHeatmapColumns } from './activity-heatmap-grid';
import { cn } from '@/lib/utils';

/**
 * GitHub-style daily activity heatmap. Pure/presentational: give it a
 * `YYYY-MM-DD → count` map and it renders the trailing `weeks` weeks as a
 * 7-row grid (Sunday at top) with month labels along the bottom. Session
 * counts drive a four-step blue intensity ramp; days after `endDate` are
 * hidden so the grid ends cleanly at today. Grid math lives in
 * activity-heatmap-grid.ts.
 *
 * Hovering a cell shows a floating tooltip ("X messages on July 3") — a custom
 * element rather than the native `title`, which is slow/unreliable in Electron.
 */

// Empty first, then four increasingly saturated blues.
const LEVEL_CLASSES = [
  'bg-foreground/[0.06]',
  'bg-blue-500/30',
  'bg-blue-500/50',
  'bg-blue-500/70',
  'bg-blue-500/90',
];

interface HoverTip {
  text: string;
  /** Viewport coords of the hovered cell (top-center). */
  left: number;
  top: number;
}

export interface ActivityHeatmapProps {
  /** Local `YYYY-MM-DD` → sessions started that day. */
  counts: Map<string, number>;
  /** Right edge of the range; defaults to today. */
  endDate?: Date;
  /** Number of week columns to show (default 53 ≈ one year). */
  weeks?: number;
  className?: string;
}

export function ActivityHeatmap({
  counts,
  endDate,
  weeks = 53,
  className,
}: ActivityHeatmapProps) {
  const columns = useMemo(
    () => buildHeatmapColumns(counts, endDate ?? new Date(), weeks),
    [counts, endDate, weeks],
  );
  const currentYear = (endDate ?? new Date()).getFullYear();
  const [tip, setTip] = useState<HoverTip | null>(null);

  const showTip = (event: React.MouseEvent<HTMLDivElement>, text: string) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setTip({ text, left: rect.left + rect.width / 2, top: rect.top });
  };

  return (
    <div className={cn('overflow-x-auto', className)}>
      <div className="inline-flex min-w-full flex-col gap-1.5">
        {/* Cell grid */}
        <div className="flex gap-[3px]">
          {columns.map((column) => (
            <div key={column.index} className="flex flex-col gap-[3px]">
              {column.days.map((day) => (
                <div
                  key={day.key}
                  onMouseEnter={
                    day.isFuture
                      ? undefined
                      : (e) => showTip(e, activityTooltip(day.count, day.key, currentYear))
                  }
                  onMouseLeave={day.isFuture ? undefined : () => setTip(null)}
                  className={cn(
                    'h-2.5 w-2.5 rounded-[2px]',
                    day.isFuture ? 'invisible' : LEVEL_CLASSES[day.level],
                  )}
                />
              ))}
            </div>
          ))}
        </div>
        {/* Month labels — each starts at its column's left edge and overflows right. */}
        <div className="flex gap-[3px]">
          {columns.map((column) => (
            <div key={column.index} className="relative h-3 w-2.5">
              {column.label && (
                <span className="absolute left-0 top-0 whitespace-nowrap text-[10px] leading-none text-muted-foreground">
                  {column.label}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Floating tooltip (portaled to body so overflow/transforms never clip it). */}
      {tip &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            className="pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-md border border-border/60 bg-popover px-2 py-1 font-mono text-xs text-popover-foreground shadow-md"
            style={{ left: tip.left, top: tip.top - 6 }}
          >
            {tip.text}
          </div>,
          document.body,
        )}
    </div>
  );
}
