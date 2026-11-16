'use client';

// Assignee filter for the tasks page header: Me, the user's own agents, and
// Unassigned, any number of them (a task shows when its assignee is any one).
// Lives on the active view (task-views.ts `assigneeFilter`) like the label and
// project filters beside it, so "Assigned to me" is a view a user saves for
// themselves rather than something every account gets.

import { useState } from 'react';
import { UserRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { PickerItem } from '@/components/dashboard/task-ui';
import type { AgentProfile } from '@/lib/backend-api';
import { agentPrincipal } from '@/lib/use-agent-profiles';
import { ASSIGNEE_ME, ASSIGNEE_NONE } from './task-views';

export function TaskAssigneeFilter({
  agents,
  selected,
  onChange,
}: {
  /** The user's own unarchived agent profiles. */
  agents: AgentProfile[];
  /** Active values (task-views.ts `activeAssigneeFilter`). */
  selected: Set<string>;
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);

  const nameOf = (value: string): string => {
    if (value === ASSIGNEE_ME) return 'Me';
    if (value === ASSIGNEE_NONE) return 'Unassigned';
    return agents.find((agent) => agent.id === value)?.name ?? 'Agent';
  };
  const picked = [...selected];

  // Writes back from `selected`, so an agent that was deleted drops out of the
  // saved view on the next toggle.
  const toggle = (value: string) => {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange([...next]);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs" title="Filter by assignee">
          <UserRound className="size-3.5 text-muted-foreground" />
          <span className="hidden max-w-28 truncate md:inline">
            {picked.length === 0
              ? 'Assignee'
              : picked.length === 1
                ? nameOf(picked[0])
                : `${picked.length} assignees`}
          </span>
        </Button>
      </PopoverTrigger>
      {/* bg-menu to match the neighbouring header dropdowns. */}
      <PopoverContent align="end" className="w-56 bg-menu p-1">
        <PickerItem selected={selected.has(ASSIGNEE_ME)} onClick={() => toggle(ASSIGNEE_ME)}>
          <UserRound className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="truncate">Me</span>
        </PickerItem>
        {agents.map((agent) => (
          <PickerItem
            key={agent.id}
            selected={selected.has(agent.id)}
            onClick={() => toggle(agent.id)}
          >
            <PrincipalAvatar principal={agentPrincipal(agent)} size="xs" />
            <span className="truncate">{agent.name}</span>
          </PickerItem>
        ))}
        <PickerItem selected={selected.has(ASSIGNEE_NONE)} onClick={() => toggle(ASSIGNEE_NONE)}>
          <UserRound className="h-3.5 w-3.5 text-muted-foreground/50" />
          <span className="truncate text-muted-foreground">Unassigned</span>
        </PickerItem>
        {picked.length > 0 && (
          <div className="mt-1 border-t pt-1">
            <button
              type="button"
              onClick={() => onChange([])}
              className="flex w-full cursor-pointer items-center rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              Clear filter
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
