'use client';

// The one control at the end of a capped (closed) status column / list
// section: "Show N more" while capped, "Show less" once expanded, never both.
// One click reveals every hidden card (they are all loaded already). Board: a
// dashed ghost card the width of the cards. List: a row aligned with the task
// rows, the chevron in the priority slot.

import { ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CLOSED_COLUMN_LIMIT } from './task-views';

export function ColumnShowMore({
  total,
  visible,
  expanded,
  onToggle,
  variant,
}: {
  /** Cards in the column, hidden ones included. */
  total: number;
  /** Cards the column renders right now. */
  visible: number;
  /** The column is expanded past the cap. */
  expanded: boolean;
  onToggle: () => void;
  variant: 'board' | 'list';
}) {
  const hidden = Math.max(0, total - visible);
  const showLess = expanded && total > CLOSED_COLUMN_LIMIT;
  if (!showLess && (expanded || hidden === 0)) return null;

  const Icon = showLess ? ChevronUp : ChevronDown;
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        'flex w-full cursor-pointer items-center text-xs text-muted-foreground transition-colors hover:text-foreground',
        variant === 'board'
          ? 'justify-center gap-1.5 rounded-lg border border-dashed border-border py-2 hover:bg-accent/30'
          : 'h-9 gap-2 rounded-md px-3 hover:bg-accent/50',
      )}
    >
      <Icon className="size-3.5 shrink-0" />
      {showLess ? 'Show less' : `Show ${hidden} more`}
    </button>
  );
}
