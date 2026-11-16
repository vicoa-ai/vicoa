'use client';

// What an agent is doing with a task right now, from the task's latest dispatch
// (plans/todos/task-assignment-agents.md): "Queued", "Starting", "<agent>
// working", or a red "Failed" with the reason. Nothing once the agent's turn is
// over or the request was cancelled: then the assignee and the timeline say the
// rest. With a session behind it, the chip opens that session.

import { useRouter } from 'next/navigation';
import { AlertCircle, Clock, Loader2 } from 'lucide-react';

import type { TaskDispatchSummary } from '@/lib/backend-api';
import { useAgentProfiles } from '@/lib/use-agent-profiles';
import { cn } from '@/lib/utils';

export type DispatchTone = 'waiting' | 'working' | 'failed';

export interface DispatchChipState {
  label: string;
  tone: DispatchTone;
  /** Longer words for the tooltip: the server's reason, when it gave one. */
  tooltip: string;
}

/** The chip a dispatch shows, or null when there is nothing to say. */
export function dispatchChipState(
  dispatch: TaskDispatchSummary | null | undefined,
  agentName: string,
): DispatchChipState | null {
  if (!dispatch) return null;
  switch (dispatch.state) {
    case 'queued':
      return {
        label: 'Queued',
        tone: 'waiting',
        tooltip: dispatch.detail ?? `${agentName} will start on this shortly`,
      };
    case 'dispatching':
      return { label: 'Starting', tone: 'waiting', tooltip: `Starting ${agentName}` };
    case 'started':
      // Spawned; until the session registers there is no status to read.
      if (dispatch.session_status === null || dispatch.session_status === 'ACTIVE') {
        return {
          label: dispatch.session_status === 'ACTIVE' ? `${agentName} working` : 'Starting',
          tone: dispatch.session_status === 'ACTIVE' ? 'working' : 'waiting',
          tooltip: `${agentName} is working on this`,
        };
      }
      return null;
    case 'delivered':
    case 'resumed':
      return dispatch.session_status === 'ACTIVE'
        ? { label: `${agentName} working`, tone: 'working', tooltip: `${agentName} is working on this` }
        : null;
    case 'failed':
      return {
        label: 'Failed',
        tone: 'failed',
        tooltip: dispatch.detail ? `${agentName} couldn't start: ${dispatch.detail}` : `${agentName} couldn't start`,
      };
    case 'cancelled':
    default:
      return null;
  }
}

export function TaskDispatchChip({
  dispatch,
  onOpenSession,
  className,
}: {
  dispatch: TaskDispatchSummary | null | undefined;
  /** Open the session in place; without it the chip navigates to the session page. */
  onOpenSession?: (sessionId: string) => void;
  className?: string;
}) {
  const router = useRouter();
  const { byId } = useAgentProfiles();
  const agentName = dispatch ? byId.get(dispatch.agent_profile_id)?.name ?? 'Agent' : 'Agent';
  const state = dispatchChipState(dispatch, agentName);
  if (!state || !dispatch) return null;
  const sessionId = dispatch.agent_instance_id;
  const Icon = state.tone === 'failed' ? AlertCircle : state.tone === 'working' ? Loader2 : Clock;
  const chip = (
    <>
      <Icon className={cn('size-3 shrink-0', state.tone === 'working' && 'animate-spin')} />
      <span className="truncate">{state.label}</span>
    </>
  );
  const classes = cn(
    'inline-flex h-5 min-w-0 max-w-full items-center gap-1 rounded-full px-1.5 text-[11px] leading-none',
    state.tone === 'failed' && 'bg-destructive/10 text-destructive',
    state.tone === 'working' && 'bg-primary/10 text-primary',
    state.tone === 'waiting' && 'bg-muted text-muted-foreground',
    className,
  );
  if (!sessionId) {
    return (
      <span className={classes} title={state.tooltip}>
        {chip}
      </span>
    );
  }
  return (
    <button
      type="button"
      title={`${state.tooltip}. Open the session`}
      className={cn(classes, 'cursor-pointer hover:opacity-80')}
      // The chip sits on a clickable card or row: opening the session must not
      // also open the task.
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
        if (onOpenSession) onOpenSession(sessionId);
        else router.push(`/dashboard/sessions/${sessionId}`);
      }}
    >
      {chip}
    </button>
  );
}
