'use client';

// A task's Sessions list: every session its record names (filed under it,
// created it, changed it, commented on it, referenced it), one line each, most
// recently active first. A row is only a way into the session; resuming it is
// the session page's own business.
//
// Drawn in the page's rail (240px wide) and above the peek panel's timeline,
// so a row is one line: the agent mark, the title, and the strongest relation.
// The rest (every relation, when it was last active) is the row's tooltip.

import { useState } from 'react';
import Link from 'next/link';

import { SessionAgentIcon } from '@/components/dashboard/agent-type-icon';
import { formatSidebarTime, getSessionTitle } from '@/components/dashboard/session-display';
import type { TaskSessionRelation, TaskSessionResponse } from '@/lib/backend-api';
import { sessionLinkClick } from './task-timeline';

/** Rows shown before "Show all": the recent few are the ones you resume. */
const COLLAPSED_ROWS = 5;

export const TASK_SESSION_RELATION_LABEL: Record<TaskSessionRelation, string> = {
  linked: 'Linked',
  created: 'Created',
  updated: 'Updated',
  commented: 'Commented',
  referenced: 'Referenced',
};

const RELATION_DESCRIPTION: Record<TaskSessionRelation, string> = {
  linked: 'Started from or linked to this task',
  created: 'Created this task',
  updated: 'Changed this task',
  commented: 'Commented on this task',
  referenced: 'Referenced this task',
};

function rowTooltip(session: TaskSessionResponse): string {
  return [
    getSessionTitle(session),
    session.task_relations.map((relation) => RELATION_DESCRIPTION[relation]).join(' · '),
    `Last active ${formatSidebarTime(session)}`,
  ]
    .filter(Boolean)
    .join('\n');
}

function TaskSessionRow({
  session,
  onOpenSession,
}: {
  session: TaskSessionResponse;
  onOpenSession?: (sessionId: string) => void;
}) {
  const relation = session.task_relations[0];
  return (
    <Link
      href={`/dashboard/sessions/${session.id}`}
      onClick={sessionLinkClick(session.id, onOpenSession)}
      title={rowTooltip(session)}
      className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent/60"
    >
      <SessionAgentIcon
        agentTypeName={session.agent_type_name}
        status={session.status}
        size={14}
      />
      <span className="min-w-0 flex-1 truncate">{getSessionTitle(session)}</span>
      {relation && (
        <span className="shrink-0 text-xs text-muted-foreground">
          {TASK_SESSION_RELATION_LABEL[relation]}
        </span>
      )}
    </Link>
  );
}

export function TaskSessionList({
  sessions,
  onOpenSession,
}: {
  sessions: TaskSessionResponse[];
  /** Open the session in place (the peek panel); without it rows are plain links. */
  onOpenSession?: (sessionId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? sessions : sessions.slice(0, COLLAPSED_ROWS);
  return (
    <div className="space-y-0.5">
      {shown.map((session) => (
        <TaskSessionRow key={session.id} session={session} onOpenSession={onOpenSession} />
      ))}
      {sessions.length > COLLAPSED_ROWS && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="w-full cursor-pointer rounded-md px-2 py-1 text-left text-xs text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
        >
          {expanded ? 'Show fewer' : `Show all (${sessions.length})`}
        </button>
      )}
    </div>
  );
}
