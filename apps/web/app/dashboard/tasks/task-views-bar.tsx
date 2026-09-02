'use client';

// Tab strip for the tasks page's local saved views (task-views.ts). Each tab
// is a view; the active one is highlighted. The trailing `+` creates a new
// view and is the placeholder home for future Linear / GitLab integrations.
// Per-tab `⋯` menu renames / duplicates / deletes.

import { useEffect, useRef, useState } from 'react';
import { Copy, MoreHorizontal, Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import type { TaskView } from './task-views';

export function TaskViewsBar({
  views,
  activeViewId,
  onSelect,
  onCreate,
  onRename,
  onDuplicate,
  onDelete,
}: {
  views: TaskView[];
  activeViewId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRename: (id: string, name: string) => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingId) inputRef.current?.select();
  }, [editingId]);

  const startRename = (view: TaskView) => {
    setEditingId(view.id);
    setDraft(view.name);
  };

  const commitRename = () => {
    if (editingId) {
      const name = draft.trim();
      if (name) onRename(editingId, name);
    }
    setEditingId(null);
  };

  return (
    <div className="flex items-center gap-1 overflow-x-auto">
      {views.map((view) => {
        const active = view.id === activeViewId;
        if (editingId === view.id) {
          return (
            <input
              key={view.id}
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitRename();
                if (e.key === 'Escape') setEditingId(null);
              }}
              className="h-7 w-28 rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          );
        }
        return (
          <div
            key={view.id}
            className={cn(
              'group/tab flex h-7 shrink-0 items-center rounded-md text-xs transition-colors',
              active
                ? 'bg-accent text-accent-foreground'
                : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
            )}
          >
            <button
              type="button"
              onClick={() => onSelect(view.id)}
              onDoubleClick={() => startRename(view)}
              className="cursor-pointer whitespace-nowrap px-2.5 py-1 outline-none"
            >
              {view.name}
            </button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label="View options"
                  className={cn(
                    'mr-0.5 flex size-5 items-center justify-center rounded-sm opacity-0 transition-opacity hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 group-hover/tab:opacity-100 data-[state=open]:opacity-100',
                    active && 'opacity-70',
                  )}
                  onClick={(e) => e.stopPropagation()}
                >
                  <MoreHorizontal className="size-3.5" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-40 text-xs">
                <DropdownMenuItem onSelect={() => startRename(view)}>
                  <Pencil className="mr-2 size-3.5" />
                  Rename
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => onDuplicate(view.id)}>
                  <Copy className="mr-2 size-3.5" />
                  Duplicate
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  disabled={views.length <= 1}
                  className="text-red-600 focus:text-red-600 dark:text-red-400 dark:focus:text-red-400"
                  onSelect={() => onDelete(view.id)}
                >
                  <Trash2 className="mr-2 size-3.5" />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        );
      })}

      {/* New view / future integrations */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 shrink-0 rounded-md p-0 text-muted-foreground"
            title="Add view"
          >
            <Plus className="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-48 text-xs">
          <DropdownMenuItem onSelect={onCreate}>
            <Plus className="mr-2 size-3.5" />
            New view
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled className="justify-between">
            Connect Linear
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Soon</span>
          </DropdownMenuItem>
          <DropdownMenuItem disabled className="justify-between">
            Connect GitLab
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Soon</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
