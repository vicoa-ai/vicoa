'use client';

import { useMemo, useState } from 'react';
import {
  Circle,
  CirclePause,
  CirclePlay,
  Loader2,
  MoreHorizontal,
  Play,
  Search,
  Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { AutomationResponse } from '@/lib/backend-api';
import { summarizeSchedule } from '../lib/frequency';

export type AutomationFilter = 'all' | 'active' | 'paused';

export function AutomationList({
  automations,
  filter,
  selectedId,
  onSelect,
  onRunNow,
  onTogglePause,
  onDelete,
  busyId,
}: {
  automations: AutomationResponse[];
  filter: AutomationFilter;
  selectedId: string | null;
  onSelect: (a: AutomationResponse) => void;
  onRunNow: (a: AutomationResponse) => void;
  onTogglePause: (a: AutomationResponse) => void;
  onDelete: (a: AutomationResponse) => void;
  busyId: string | null;
}) {
  const [query, setQuery] = useState('');

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return automations.filter((a) => {
      if (filter === 'active' && !a.enabled) return false;
      if (filter === 'paused' && a.enabled) return false;
      if (q && !a.title.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [automations, filter, query]);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex h-full flex-col">
        {/* Search */}
        <div className="border-b border-border p-2">
          <div className="flex items-center gap-2 rounded-lg bg-muted/40 px-2.5">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              value={query}
              placeholder="Search automations"
              onChange={(e) => setQuery(e.target.value)}
              className="h-8 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground/60"
            />
          </div>
        </div>

        {/* List */}
        <div className="custom-scrollbar flex-1 overflow-y-auto">
          {visible.length === 0 ? (
            <div className="px-4 py-10 text-center text-xs text-muted-foreground">
              {automations.length === 0 ? 'No automations yet.' : 'No matches.'}
            </div>
          ) : (
            <ul>
              {visible.map((a) => (
                <li
                  key={a.id}
                  onClick={() => onSelect(a)}
                  className={cn(
                    'group flex cursor-pointer items-center gap-2.5 border-b border-border/50 px-3 py-2.5',
                    selectedId === a.id
                      ? 'bg-foreground/[0.07]'
                      : 'hover:bg-foreground/[0.04]',
                  )}
                >
                  {/* Active/paused toggle: empty circle when active (hover →
                      circle-pause), circle-play when paused. */}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onTogglePause(a);
                        }}
                        className="group/status flex-shrink-0 text-muted-foreground hover:text-foreground"
                      >
                        {a.enabled ? (
                          <>
                            <Circle className="h-4 w-4 group-hover/status:hidden" />
                            <CirclePause className="hidden h-4 w-4 group-hover/status:block" />
                          </>
                        ) : (
                          <CirclePlay className="h-4 w-4" />
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>{a.enabled ? 'Pause' : 'Resume'}</TooltipContent>
                  </Tooltip>

                  <div className="min-w-0 flex-1">
                    <div
                      className={cn(
                        'truncate text-sm',
                        !a.enabled && 'text-muted-foreground',
                      )}
                    >
                      {a.title}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {summarizeSchedule(a)}
                    </div>
                  </div>

                  {busyId === a.id ? (
                    <Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-muted-foreground" />
                  ) : (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          onClick={(e) => e.stopPropagation()}
                          className="flex-shrink-0 rounded-md p-1 text-muted-foreground opacity-0 hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground group-hover:opacity-100 data-[state=open]:opacity-100"
                          title="Actions"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent
                        align="end"
                        className="rounded-xl"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <DropdownMenuItem onClick={() => onRunNow(a)}>
                          <Play className="mr-2 h-4 w-4" />
                          Run now
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => onTogglePause(a)}>
                          {a.enabled ? (
                            <>
                              <CirclePause className="mr-2 h-4 w-4" />
                              Pause
                            </>
                          ) : (
                            <>
                              <CirclePlay className="mr-2 h-4 w-4" />
                              Resume
                            </>
                          )}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => onDelete(a)}>
                          <Trash2 className="mr-2 h-4 w-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}
