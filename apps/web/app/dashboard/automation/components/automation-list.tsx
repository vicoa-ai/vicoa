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
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import type { AutomationResponse, ProjectResponse } from '@/lib/backend-api';
import { principalDisplayName, principalFromResponse } from '@/lib/principals';
import { summarizeSchedule } from '../lib/frequency';
import { groupByProject, NO_PROJECT } from '../lib/group-by-project';

export type AutomationFilter = 'all' | 'active' | 'paused';

function matches(a: AutomationResponse, filter: AutomationFilter, q: string): boolean {
  if (filter === 'active' && !a.enabled) return false;
  if (filter === 'paused' && a.enabled) return false;
  if (q && !a.title.toLowerCase().includes(q)) return false;
  return true;
}

export function AutomationList({
  automations,
  groupProjects = null,
  emptyLabel = 'No automations yet.',
  filter,
  selectedId,
  onSelect,
  onRunNow,
  onTogglePause,
  onDelete,
  busyId,
}: {
  /** Yours and collaborators' mixed: a row with `owner` set is a
   *  collaborator's, drawn read-only (no pause toggle, no actions). */
  automations: AutomationResponse[];
  /** Set: rows are grouped under the project each is filed in, in this
   *  order, with "No project" last. Null: one flat list. */
  groupProjects?: ProjectResponse[] | null;
  emptyLabel?: string;
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
    return automations.filter((a) => matches(a, filter, q));
  }, [automations, filter, query]);

  const groups = useMemo(
    () => (groupProjects ? groupByProject(visible, groupProjects) : null),
    [visible, groupProjects],
  );

  const renderRow = (a: AutomationResponse) =>
    a.owner ? (
      <SharedRow key={a.id} automation={a} selected={selectedId === a.id} onSelect={onSelect} />
    ) : (
      <OwnRow
        key={a.id}
        automation={a}
        selected={selectedId === a.id}
        busy={busyId === a.id}
        onSelect={onSelect}
        onRunNow={onRunNow}
        onTogglePause={onTogglePause}
        onDelete={onDelete}
      />
    );

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
              {automations.length === 0 ? emptyLabel : 'No matches.'}
            </div>
          ) : (
            <ul>
              {groups
                ? groups.map((group) => (
                    <li key={group.key}>
                      <div className="flex items-center gap-1.5 px-3 pb-1 pt-3 text-[0.8rem] font-normal text-muted-foreground">
                        <ProjectIcon project={group.project} />
                        <span className="truncate">
                          {group.project?.name ??
                            (group.key === NO_PROJECT ? 'No project' : 'Other project')}
                        </span>
                      </div>
                      <ul>{group.rows.map(renderRow)}</ul>
                    </li>
                  ))
                : visible.map(renderRow)}
            </ul>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}

/** One of your own automations: pause toggle on the left, actions on hover. */
function OwnRow({
  automation: a,
  selected,
  busy,
  onSelect,
  onRunNow,
  onTogglePause,
  onDelete,
}: {
  automation: AutomationResponse;
  selected: boolean;
  busy: boolean;
  onSelect: (a: AutomationResponse) => void;
  onRunNow: (a: AutomationResponse) => void;
  onTogglePause: (a: AutomationResponse) => void;
  onDelete: (a: AutomationResponse) => void;
}) {
  return (
    <li
      onClick={() => onSelect(a)}
      className={cn(
        'group flex cursor-pointer items-center gap-2.5 border-b border-border/50 px-3 py-2.5',
        selected
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

      {busy ? (
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
  );
}

/**
 * A collaborator's automation, in a project shared with the viewer. No pause
 * toggle and no actions menu: only its author can change or run it, so the
 * row just opens the read-only panel. The author's face sits where the menu
 * would be.
 */
function SharedRow({
  automation: a,
  selected,
  onSelect,
}: {
  automation: AutomationResponse;
  selected: boolean;
  onSelect: (a: AutomationResponse) => void;
}) {
  return (
    <li
      onClick={() => onSelect(a)}
      className={cn(
        'flex cursor-pointer items-center gap-2.5 border-b border-border/50 px-3 py-2.5',
        selected ? 'bg-foreground/[0.07]' : 'hover:bg-foreground/[0.04]',
      )}
    >
      <span
        className="flex-shrink-0 text-muted-foreground"
        title={a.enabled ? 'Active' : 'Paused'}
      >
        {a.enabled ? <Circle className="h-4 w-4" /> : <CirclePause className="h-4 w-4" />}
      </span>
      <div className="min-w-0 flex-1">
        <div className={cn('truncate text-sm', !a.enabled && 'text-muted-foreground')}>
          {a.title}
        </div>
        <div className="truncate text-xs text-muted-foreground">{summarizeSchedule(a)}</div>
      </div>
      <AuthorAvatar automation={a} />
    </li>
  );
}

function AuthorAvatar({ automation }: { automation: AutomationResponse }) {
  const author = principalFromResponse(automation.owner);
  if (!author) return null;
  return (
    <PrincipalAvatar
      principal={author}
      size="sm"
      className="flex-shrink-0"
      title={principalDisplayName(author)}
    />
  );
}
