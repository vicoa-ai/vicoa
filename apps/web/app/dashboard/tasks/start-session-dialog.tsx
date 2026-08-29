'use client';

// Shown from the Tasks page when you "Start session" on a task that has
// sub-tasks: pick which sub-tasks to pull into the session. The checked ones
// seed the session's first prompt and move to in_progress alongside the parent
// (handled on the New Session page). Backlog + todo children are pre-checked;
// done/cancelled are shown greyed for context but left unchecked.

import { useEffect, useMemo, useState } from 'react';
import { Check, ChevronRight, Play, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { TaskResponse, TaskStatus } from '@/lib/backend-api';
import { StatusIcon } from '@/components/dashboard/task-ui';
import { cn } from '@/lib/utils';

// Statuses that come pre-selected: work that hasn't been started yet.
const DEFAULT_CHECKED: ReadonlySet<TaskStatus> = new Set<TaskStatus>(['backlog', 'todo']);

export function StartSessionDialog({
  open,
  parentTask,
  subtasks,
  onClose,
  onConfirm,
}: {
  open: boolean;
  parentTask: TaskResponse | null;
  /** Direct children of `parentTask` (any status). */
  subtasks: TaskResponse[];
  onClose: () => void;
  /** Chosen sub-task ids, in list order; empty = start the parent alone. */
  onConfirm: (selectedIds: string[]) => void;
}) {
  const ordered = useMemo(
    () =>
      [...subtasks].sort(
        (a, b) => a.position - b.position || a.created_at.localeCompare(b.created_at),
      ),
    [subtasks],
  );

  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Re-seed the default selection every time the dialog opens for a task.
  useEffect(() => {
    if (!open) return;
    setSelected(new Set(ordered.filter((t) => DEFAULT_CHECKED.has(t.status)).map((t) => t.id)));
  }, [open, parentTask?.id, ordered]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allSelected = ordered.length > 0 && ordered.every((t) => selected.has(t.id));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(ordered.map((t) => t.id)));

  if (!open || !parentTask) return null;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="flex max-h-[80vh] max-w-lg flex-col gap-0 overflow-hidden p-0 sm:rounded-xl">
        <DialogTitle className="sr-only">Start session</DialogTitle>

        {/* Header: breadcrumb + close */}
        <div className="flex shrink-0 items-center justify-between px-5 pb-2 pt-3">
          <div className="flex min-w-0 items-center gap-1.5 text-xs">
            <span className="text-muted-foreground">Tasks</span>
            <ChevronRight className="size-3 shrink-0 text-muted-foreground/50" />
            <span className="truncate font-medium">{parentTask.title}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="cursor-pointer rounded-sm p-1.5 opacity-70 transition-all hover:bg-accent/60 hover:opacity-100"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Intro + select-all */}
        <div className="flex shrink-0 items-center justify-between px-5 pb-1">
          <p className="text-sm text-muted-foreground">Include sub-tasks in this session</p>
          {ordered.length > 0 && (
            <button
              type="button"
              onClick={toggleAll}
              className="cursor-pointer text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              {allSelected ? 'Clear all' : 'Select all'}
            </button>
          )}
        </div>

        {/* Sub-task checklist */}
        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-3 py-2">
          {ordered.map((sub) => {
            const isChecked = selected.has(sub.id);
            const isClosed = sub.status === 'done' || sub.status === 'cancelled';
            return (
              <button
                key={sub.id}
                type="button"
                onClick={() => toggle(sub.id)}
                className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent/50"
              >
                <span
                  className={cn(
                    'flex size-4 shrink-0 items-center justify-center rounded border transition-colors',
                    isChecked ? 'border-primary bg-primary text-primary-foreground' : 'border-input',
                  )}
                >
                  {isChecked && <Check className="size-3" />}
                </span>
                <StatusIcon status={sub.status} className="size-3.5" />
                <span
                  className={cn(
                    'min-w-0 flex-1 truncate',
                    isClosed && 'text-muted-foreground line-through',
                  )}
                >
                  {sub.title}
                </span>
              </button>
            );
          })}
        </div>

        {/* Footer: count + primary action */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-t px-4 py-3">
          <span className="text-xs text-muted-foreground">
            {selected.size} of {ordered.length} selected
          </span>
          <Button
            size="sm"
            className="gap-1.5"
            onClick={() => onConfirm(ordered.filter((t) => selected.has(t.id)).map((t) => t.id))}
          >
            <Play className="size-3.5" />
            Start session
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
