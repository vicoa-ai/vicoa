'use client';

import { useMemo, useState, type ReactNode } from 'react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type Modifier,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  CalendarClock,
  Circle,
  CircleAlert,
  CircleCheck,
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
import { matchesScheduleFilter, type ScheduleFilter } from '../lib/schedule-filter';
import {
  sortAutomations,
  type AutomationSortDirection,
  type AutomationSortField,
} from '../lib/sort';
import { automationState, isCompleted, summarizeCompleted } from '../lib/state';

export type AutomationFilter = 'all' | 'active' | 'paused' | 'completed';

// Rows only move up and down, and stay inside their group's list (dnd-kit's
// container rect is the dragged row's parent): a row's group is its project,
// which a drag can't change, so it shouldn't look like it can leave.
const restrictToGroup: Modifier = ({ transform, draggingNodeRect, containerNodeRect }) => ({
  ...transform,
  x: 0,
  y:
    draggingNodeRect && containerNodeRect
      ? Math.min(
          Math.max(transform.y, containerNodeRect.top - draggingNodeRect.top),
          containerNodeRect.bottom - draggingNodeRect.bottom,
        )
      : transform.y,
});

// A row's own controls must not start a drag: a press that wobbles past the
// activation distance would drag the row instead of toggling or opening the menu.
const stopDragStart = (e: React.PointerEvent) => e.stopPropagation();

function matches(
  a: AutomationResponse,
  filter: AutomationFilter,
  schedule: ScheduleFilter,
  q: string,
): boolean {
  if (filter !== 'all' && automationState(a) !== filter) return false;
  if (!matchesScheduleFilter(a, schedule)) return false;
  if (q && !a.title.toLowerCase().includes(q)) return false;
  return true;
}

/** The row's second line: when it fires, or how its one run went. */
const summary = (a: AutomationResponse): string =>
  isCompleted(a) ? summarizeCompleted(a) : summarizeSchedule(a);

export function AutomationList({
  automations,
  groupProjects = null,
  emptyLabel = 'No automations yet.',
  filter,
  scheduleFilter,
  sortBy,
  sortDirection,
  selectedId,
  onSelect,
  onRunNow,
  onTogglePause,
  onDelete,
  onReorder,
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
  scheduleFilter: ScheduleFilter;
  /** Anything but `position` (Manual) replaces the viewer's drag order, so rows
   *  can't be dragged. Completed one-time automations sink to the bottom of a
   *  group either way, and are never draggable. */
  sortBy: AutomationSortField;
  sortDirection: AutomationSortDirection;
  selectedId: string | null;
  onSelect: (a: AutomationResponse) => void;
  onRunNow: (a: AutomationResponse) => void;
  onTogglePause: (a: AutomationResponse) => void;
  onDelete: (a: AutomationResponse) => void;
  /** Rows were dragged: the ids one group shows, in their new order. Yours and
   *  collaborators' alike, since the order is the viewer's own view. */
  onReorder: (rendered: string[]) => void;
  busyId: string | null;
}) {
  const [query, setQuery] = useState('');

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sortAutomations(
      automations.filter((a) => matches(a, filter, scheduleFilter, q)),
      sortBy,
      sortDirection,
    );
  }, [automations, filter, scheduleFilter, query, sortBy, sortDirection]);

  const groups = useMemo(
    () => (groupProjects ? groupByProject(visible, groupProjects) : null),
    [visible, groupProjects],
  );

  const dragEnabled = sortBy === 'position';

  const renderRow = (a: AutomationResponse, sortable: boolean) =>
    a.owner ? (
      <SharedRow
        key={a.id}
        automation={a}
        sortable={sortable}
        selected={selectedId === a.id}
        onSelect={onSelect}
      />
    ) : (
      <OwnRow
        key={a.id}
        automation={a}
        sortable={sortable}
        selected={selectedId === a.id}
        busy={busyId === a.id}
        onSelect={onSelect}
        onRunNow={onRunNow}
        onTogglePause={onTogglePause}
        onDelete={onDelete}
      />
    );

  // One group's rows: the live ones, draggable among themselves in manual
  // order, then the completed ones, which are done and stay put. `rows` is
  // already sorted, so live rows all come before completed ones.
  const renderRows = (rows: AutomationResponse[]) => {
    const live = rows.filter((a) => !isCompleted(a));
    const completed = rows.filter(isCompleted);
    return (
      <>
        {live.length > 0 && (
          <SortableRows rows={live} enabled={dragEnabled} onReorder={onReorder}>
            {live.map((a) => renderRow(a, dragEnabled))}
          </SortableRows>
        )}
        {completed.length > 0 && <ul>{completed.map((a) => renderRow(a, false))}</ul>}
      </>
    );
  };

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
          ) : groups ? (
            <ul>
              {groups.map((group) => (
                <li key={group.key}>
                  <div className="flex items-center gap-1.5 px-3 pb-1 pt-3 text-[0.8rem] font-normal text-muted-foreground">
                    {/* A project the viewer can't see is still a project. */}
                    <ProjectIcon
                      project={
                        group.project ??
                        (group.key === NO_PROJECT ? null : { name: 'Other project' })
                      }
                    />
                    <span className="truncate">
                      {group.project?.name ??
                        (group.key === NO_PROJECT ? 'No project' : 'Other project')}
                    </span>
                  </div>
                  {renderRows(group.rows)}
                </li>
              ))}
            </ul>
          ) : (
            renderRows(visible)
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}

/**
 * One group's rows, draggable among themselves only: a row's group is its
 * project, which comes from its folder, so a drag can't move it to another.
 */
function SortableRows({
  rows,
  enabled,
  onReorder,
  children,
}: {
  rows: AutomationResponse[];
  /** Off when the list is sorted by something other than the drag order: the
   *  rows are then plain (their `sortable` is off too). */
  enabled: boolean;
  onReorder: (rendered: string[]) => void;
  children: ReactNode;
}) {
  // A small activation distance keeps a plain click opening the row. A focused
  // row also moves with space, then the arrow keys.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ids = rows.map((a) => a.id);

  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over) return;
    const from = ids.indexOf(String(active.id));
    const to = ids.indexOf(String(over.id));
    if (from < 0 || to < 0 || from === to) return;
    onReorder(arrayMove(ids, from, to));
  };

  if (!enabled) return <ul>{children}</ul>;

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      modifiers={[restrictToGroup]}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <ul>{children}</ul>
      </SortableContext>
    </DndContext>
  );
}

/**
 * A row's `<li>`. Sortable ones join their group's `SortableRows`; the rest
 * (completed rows, or any row while the list isn't in drag order) are plain, so
 * they take no part in a drag and never show as a drop target.
 */
function RowItem({
  id,
  sortable,
  className,
  onClick,
  children,
}: {
  id: string;
  sortable: boolean;
  className: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return sortable ? (
    <SortableItem id={id} className={className} onClick={onClick}>
      {children}
    </SortableItem>
  ) : (
    <li onClick={onClick} className={className}>
      {children}
    </li>
  );
}

function SortableItem({
  id,
  className,
  onClick,
  children,
}: {
  id: string;
  className: string;
  onClick: () => void;
  children: ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={cn(className, isDragging && 'relative z-10 bg-background shadow-md')}
    >
      {children}
    </li>
  );
}

/**
 * A completed one-time automation's mark: a check, or an alert when its one
 * run didn't go through (the scheduler gives such a row no second try).
 */
function CompletedIcon({ automation: a }: { automation: AutomationResponse }) {
  const failed = a.last_run_status === 'failed' || a.last_run_status === 'missed_offline';
  const Icon = failed ? CircleAlert : CircleCheck;
  return (
    <span
      className="flex-shrink-0 text-muted-foreground"
      title={failed ? 'Did not run' : 'Completed'}
    >
      <Icon className="h-4 w-4" />
    </span>
  );
}

/**
 * One of your own automations: pause toggle on the left, actions on hover.
 * A completed one-time automation has nothing to pause or resume (it has no
 * next run): a check stands in for the toggle and the menu offers Reschedule.
 */
function OwnRow({
  automation: a,
  sortable,
  selected,
  busy,
  onSelect,
  onRunNow,
  onTogglePause,
  onDelete,
}: {
  automation: AutomationResponse;
  sortable: boolean;
  selected: boolean;
  busy: boolean;
  onSelect: (a: AutomationResponse) => void;
  onRunNow: (a: AutomationResponse) => void;
  onTogglePause: (a: AutomationResponse) => void;
  onDelete: (a: AutomationResponse) => void;
}) {
  const completed = isCompleted(a);
  const dim = completed || !a.enabled;
  return (
    <RowItem
      id={a.id}
      sortable={sortable}
      onClick={() => onSelect(a)}
      className={cn(
        'group flex cursor-pointer items-center gap-2.5 border-b border-border/50 px-3 py-2.5',
        selected
          ? 'bg-foreground/[0.07]'
          : 'hover:bg-foreground/[0.04]',
      )}
    >
      {completed ? (
        <CompletedIcon automation={a} />
      ) : (
        /* Active/paused toggle: empty circle when active (hover →
           circle-pause), circle-play when paused. */
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onPointerDown={stopDragStart}
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
      )}

      <div className="min-w-0 flex-1">
        <div className={cn('truncate text-sm', dim && 'text-muted-foreground')}>
          {a.title}
        </div>
        <div className="truncate text-xs text-muted-foreground">{summary(a)}</div>
      </div>

      {busy ? (
        <Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-muted-foreground" />
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              onPointerDown={stopDragStart}
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
            {completed ? (
              // Opens the panel, whose time field is empty: saving a new time
              // is what brings it back.
              <DropdownMenuItem onClick={() => onSelect(a)}>
                <CalendarClock className="mr-2 h-4 w-4" />
                Reschedule
              </DropdownMenuItem>
            ) : (
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
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => onDelete(a)}>
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </RowItem>
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
  sortable,
  selected,
  onSelect,
}: {
  automation: AutomationResponse;
  sortable: boolean;
  selected: boolean;
  onSelect: (a: AutomationResponse) => void;
}) {
  const completed = isCompleted(a);
  return (
    <RowItem
      id={a.id}
      sortable={sortable}
      onClick={() => onSelect(a)}
      className={cn(
        'flex cursor-pointer items-center gap-2.5 border-b border-border/50 px-3 py-2.5',
        selected ? 'bg-foreground/[0.07]' : 'hover:bg-foreground/[0.04]',
      )}
    >
      {completed ? (
        <CompletedIcon automation={a} />
      ) : (
        <span
          className="flex-shrink-0 text-muted-foreground"
          title={a.enabled ? 'Active' : 'Paused'}
        >
          {a.enabled ? <Circle className="h-4 w-4" /> : <CirclePause className="h-4 w-4" />}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <div
          className={cn('truncate text-sm', (completed || !a.enabled) && 'text-muted-foreground')}
        >
          {a.title}
        </div>
        <div className="truncate text-xs text-muted-foreground">{summary(a)}</div>
      </div>
      <AuthorAvatar automation={a} />
    </RowItem>
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
