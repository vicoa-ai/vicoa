'use client';

// The tasks page's one Filter menu. Each dimension (Assignee, Relation to me,
// Labels) is a row that opens its own submenu beside the menu, where values
// are ticked in place: the menu stays open, so several can be picked in one
// go. A dimension in use shows how many values it has ticked at the end of its
// row (the submenu names them), and the button says how many dimensions
// filter ("2 filters"), so nothing else on the page has to repeat it.
//
// Values within a dimension are OR ("Assigned to me" or "Waiting on me" is
// everything that needs me); dimensions are AND. All state lives on the active
// view (task-views.ts), like the project filter beside it.

import { useState, type ReactNode } from 'react';
import { CircleUserRound, Hourglass, ListFilter, Tag, UserRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import type { AgentProfile, TaskLabelResponse } from '@/lib/backend-api';
import { agentPrincipal } from '@/lib/use-agent-profiles';
import { cn } from '@/lib/utils';
import { ASSIGNEE_NONE, TASK_RELATION_OPTIONS, type TaskRelation } from './task-views';

/** The filters a view holds, already narrowed to values that still exist. */
export interface TaskFilterState {
  /** The user's own unarchived agent profiles: what Assignee offers. */
  agents: AgentProfile[];
  /** Every label Labels can offer (task-views.ts `labelFilterOptions`). */
  labels: TaskLabelResponse[];
  assignee: Set<string>;
  relation: Set<TaskRelation>;
  label: Set<string>;
  onAssigneeChange: (values: string[]) => void;
  onRelationChange: (values: TaskRelation[]) => void;
  onLabelChange: (labelIds: string[]) => void;
}

/** How many dimensions filter: what the button counts. */
export function activeFilterCount(state: TaskFilterState): number {
  return [state.assignee.size, state.relation.size, state.label.size].filter((n) => n > 0)
    .length;
}

/** Whether the view filters by anything the menu controls. */
export function hasActiveFilters(state: TaskFilterState): boolean {
  return activeFilterCount(state) > 0;
}

function toggled<T>(selected: Set<T>, value: T): Set<T> {
  const next = new Set(selected);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

// A tick keeps the menu open: picking several values is one visit, not three.
const keepOpen = (event: Event) => event.preventDefault();

const ITEM_CLASS = 'cursor-pointer text-xs';

/** A dimension's row: icon, name, and how many values it has ticked. */
function DimensionTrigger({
  icon,
  label,
  count,
}: {
  icon: ReactNode;
  label: string;
  count: number;
}) {
  return (
    <DropdownMenuSubTrigger className="cursor-pointer gap-2 text-xs">
      {icon}
      <span className="truncate">{label}</span>
      {count > 0 && (
        <span className="ml-auto pl-3 font-medium tabular-nums text-primary">{count}</span>
      )}
    </DropdownMenuSubTrigger>
  );
}

function AssigneeSubmenu({ state }: { state: TaskFilterState }) {
  // Writes back from the narrowed set, so an agent that was deleted drops out
  // of the saved view on the next tick.
  const toggle = (value: string) => state.onAssigneeChange([...toggled(state.assignee, value)]);
  return (
    <DropdownMenuSub>
      <DimensionTrigger
        icon={<UserRound className="size-3.5 text-muted-foreground" />}
        label="Assignee"
        count={state.assignee.size}
      />
      <DropdownMenuSubContent className="custom-scrollbar max-h-72 w-52 overflow-y-auto">
        {state.agents.map((agent) => (
          <DropdownMenuCheckboxItem
            key={agent.id}
            checked={state.assignee.has(agent.id)}
            onCheckedChange={() => toggle(agent.id)}
            onSelect={keepOpen}
            className={ITEM_CLASS}
          >
            <PrincipalAvatar principal={agentPrincipal(agent)} size="xs" />
            <span className="truncate">{agent.name}</span>
          </DropdownMenuCheckboxItem>
        ))}
        <DropdownMenuCheckboxItem
          checked={state.assignee.has(ASSIGNEE_NONE)}
          onCheckedChange={() => toggle(ASSIGNEE_NONE)}
          onSelect={keepOpen}
          className={ITEM_CLASS}
        >
          <UserRound className="size-3.5 text-muted-foreground/50" />
          <span className="truncate text-muted-foreground">Unassigned</span>
        </DropdownMenuCheckboxItem>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

function RelationSubmenu({ state }: { state: TaskFilterState }) {
  // In menu order, so the row reads the same whichever was ticked first.
  const toggle = (value: TaskRelation) => {
    const next = toggled(state.relation, value);
    state.onRelationChange(TASK_RELATION_OPTIONS.map((o) => o.key).filter((k) => next.has(k)));
  };
  return (
    <DropdownMenuSub>
      <DimensionTrigger
        icon={<CircleUserRound className="size-3.5 text-muted-foreground" />}
        label="Relation to me"
        count={state.relation.size}
      />
      <DropdownMenuSubContent className="w-48">
        {TASK_RELATION_OPTIONS.map((option) => (
          <DropdownMenuCheckboxItem
            key={option.key}
            checked={state.relation.has(option.key)}
            onCheckedChange={() => toggle(option.key)}
            onSelect={keepOpen}
            className={ITEM_CLASS}
          >
            {option.key === 'assigned' ? (
              <UserRound className="size-3.5 text-muted-foreground" />
            ) : (
              <Hourglass className="size-3.5 text-muted-foreground" />
            )}
            <span className="truncate">{option.label}</span>
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

function LabelsSubmenu({ state }: { state: TaskFilterState }) {
  const [query, setQuery] = useState('');
  const needle = query.trim().toLowerCase();
  const visible = needle
    ? state.labels.filter((label) => label.name.toLowerCase().includes(needle))
    : state.labels;
  const toggle = (id: string) => state.onLabelChange([...toggled(state.label, id)]);
  return (
    <DropdownMenuSub onOpenChange={(open) => !open && setQuery('')}>
      <DimensionTrigger
        icon={<Tag className="size-3.5 text-muted-foreground" />}
        label="Labels"
        count={state.label.size}
      />
      <DropdownMenuSubContent className="w-56 p-0">
        <div className="border-b px-2.5 py-1.5">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            // The menu reads letters as type-ahead and arrows as navigation;
            // in the search field they are text. Escape still closes.
            onKeyDown={(e) => {
              if (e.key !== 'Escape') e.stopPropagation();
            }}
            placeholder="Search labels"
            aria-label="Search labels"
            className="w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground"
            autoFocus
          />
        </div>
        <div className="custom-scrollbar max-h-64 overflow-y-auto p-1">
          {visible.map((label) => (
            <DropdownMenuCheckboxItem
              key={label.id}
              checked={state.label.has(label.id)}
              onCheckedChange={() => toggle(label.id)}
              onSelect={keepOpen}
              className={ITEM_CLASS}
            >
              <span
                className="size-2 shrink-0 rounded-full"
                style={{ backgroundColor: label.color }}
              />
              <span className="truncate">{label.name}</span>
            </DropdownMenuCheckboxItem>
          ))}
          {visible.length === 0 && (
            <p className="px-2 py-3 text-center text-xs text-muted-foreground">
              {state.labels.length === 0 ? 'No labels yet' : 'No matching labels'}
            </p>
          )}
        </div>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

/** The header's Filter button and its menu. */
export function TaskFilterMenu({
  state,
  onClear,
}: {
  state: TaskFilterState;
  onClear: () => void;
}) {
  const count = activeFilterCount(state);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            'h-7 gap-1.5 text-xs',
            count > 0 && 'border-primary/40 bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary',
          )}
          title="Filter tasks"
        >
          <ListFilter className={cn('size-3.5', count === 0 && 'text-muted-foreground')} />
          <span className="hidden md:inline">
            {count === 0 ? 'Filter' : count === 1 ? '1 filter' : `${count} filters`}
          </span>
          {count > 0 && <span className="tabular-nums md:hidden">{count}</span>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60 text-xs">
        <AssigneeSubmenu state={state} />
        <RelationSubmenu state={state} />
        <LabelsSubmenu state={state} />
        {count > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onClear} className="cursor-pointer text-xs text-muted-foreground">
              Clear filters
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
