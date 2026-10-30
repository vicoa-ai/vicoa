import type { AutomationResponse } from '@/lib/backend-api';

export type AutomationState = 'active' | 'paused' | 'completed';

/**
 * Where an automation is in its life. A one-time automation that has fired
 * keeps no fire time (the scheduler clears `next_run_at` and disables it), so
 * "completed" is derived rather than stored. Resuming one by flipping
 * `enabled` alone would only leave a row that looks active and never fires, so
 * a row in this state is rescheduled (a new time) instead of resumed. The
 * `enabled` flag is ignored here on purpose: such a row that was resumed
 * before this state existed is completed too.
 */
export function automationState(
  a: Pick<AutomationResponse, 'schedule_kind' | 'next_run_at' | 'enabled'>,
): AutomationState {
  if (a.schedule_kind === 'once' && !a.next_run_at) return 'completed';
  return a.enabled ? 'active' : 'paused';
}

export function isCompleted(
  a: Pick<AutomationResponse, 'schedule_kind' | 'next_run_at' | 'enabled'>,
): boolean {
  return automationState(a) === 'completed';
}

/** How a completed one-time automation's single run turned out, for its row. */
export function summarizeCompleted(
  a: Pick<AutomationResponse, 'last_run_at' | 'last_run_status'>,
): string {
  const outcome =
    a.last_run_status === 'failed'
      ? 'failed'
      : a.last_run_status === 'missed_offline'
        ? 'missed, machine offline'
        : a.last_run_status === 'skipped'
          ? 'skipped'
          : 'ran';
  return a.last_run_at
    ? `Once · ${outcome} ${new Date(a.last_run_at).toLocaleString()}`
    : `Once · ${outcome === 'ran' ? 'completed' : outcome}`;
}
