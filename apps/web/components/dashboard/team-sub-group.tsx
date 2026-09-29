'use client';

// The Team row at the end of a project group: other people's open sessions in
// that project, collapsed by default (see team-sessions.ts). Styled as a
// sibling of the worktree sub-group rows — same indent, type and chevron — so
// a project reads as "my branches, then the team", one level deep either way.
//
// Collapsed it names no one: a label, a count, and a spinner while any of the
// sessions is working. Expanded it lists them most recently active first, as
// the same rows as your own; a row shows faces only when several people are in
// that session, like everywhere else in the list.

import { useState, type ReactNode } from 'react';
import { ChevronRight, Users } from 'lucide-react';

import { SnakeLoader } from '@/components/dashboard/snake-loader';
import { TEAM_ROWS_SHOWN } from '@/components/dashboard/team-sessions';
import type { AgentInstanceResponse } from '@/lib/backend-api';
import { cn } from '@/lib/utils';

export function TeamSubGroup({
  label,
  sessions,
  expanded,
  onToggle,
  working,
  renderSession,
}: {
  label: string;
  sessions: AgentInstanceResponse[];
  expanded: boolean;
  onToggle: () => void;
  /** Some session here is running right now. */
  working: boolean;
  renderSession: (instance: AgentInstanceResponse) => ReactNode;
}) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? sessions : sessions.slice(0, TEAM_ROWS_SHOWN);
  const more = sessions.length - shown.length;

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="group/label flex w-full cursor-pointer select-none items-center gap-1 py-0.5 pl-3 pr-2 text-left"
      >
        <Users className="h-3 w-3 shrink-0 text-muted-foreground/60" />
        <span className="truncate text-[11px] font-light text-muted-foreground/60">{label}</span>
        <span className="shrink-0 text-[11px] font-light text-muted-foreground/40">· {sessions.length}</span>
        <ChevronRight
          className={cn(
            'h-3 w-3 shrink-0 text-muted-foreground/50 transition-transform group-hover/label:text-muted-foreground',
            expanded && 'rotate-90',
          )}
        />
        {!expanded && working && (
          <span className="ml-auto flex shrink-0 items-center" aria-label="Working" title="Working">
            <SnakeLoader size={11} />
          </span>
        )}
      </button>
      {expanded && (
        <div className="space-y-0.5 pl-2">
          {shown.map(renderSession)}
          {more > 0 && (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="w-full cursor-pointer py-0.5 pl-3 text-left text-[11px] font-light text-muted-foreground/60 hover:text-muted-foreground"
            >
              Show {more} more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
