'use client';

// "Waiting on Nick": an agent asked someone a question on this task and it is
// still open (lib/task-questions). Drawn on a board card, a list row and the
// question's own comment header. It says whose turn it is, so for the viewer
// it reads "Waiting on you" and takes the primary tone; for anyone else it is
// muted, like the dispatch chip's waiting state beside it. Pure: the caller
// passes the viewer, since the thread also renders on a public share page,
// outside the dashboard.

import { Hourglass } from 'lucide-react';

import type { PrincipalResponse } from '@/lib/backend-api';
import { waitingOnLabel } from '@/lib/task-questions';
import { cn } from '@/lib/utils';

export function WaitingOnPill({
  people,
  viewerId,
  className,
}: {
  /** Whom it waits on (lib/task-questions `waitingOnPeople`). Empty: nothing. */
  people: PrincipalResponse[];
  /** The signed-in user, or null while unknown. */
  viewerId: string | null;
  className?: string;
}) {
  const label = waitingOnLabel(people, viewerId);
  if (!label) return null;
  const mine = !!viewerId && people.some((p) => p.id === viewerId);
  const names = people.map((p) => p.name?.trim() || 'someone').join(', ');
  return (
    <span
      className={cn(
        'inline-flex h-5 min-w-0 max-w-full items-center gap-1 rounded-full px-1.5 text-[11px] leading-none',
        mine ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground',
        className,
      )}
      title={
        mine
          ? 'An agent asked you a question. Comment on the task to answer it.'
          : `An agent asked ${names} a question.`
      }
    >
      <Hourglass className="size-3 shrink-0" />
      <span className="truncate">{label}</span>
    </span>
  );
}
