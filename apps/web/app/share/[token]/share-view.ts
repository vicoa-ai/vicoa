// The pure half of a shared project's page: which view the URL asks for, and
// how a shared automation reads in words. Kept out of the components so the
// rules (what opens by default, what a schedule says) are testable without
// mounting React.

import type { AutomationRunStatus, ShareScope } from '@/lib/backend-api';
import type { SessionConfig } from '@/lib/agent-catalog';
import type { PublicAutomation } from '@/lib/public-share-api';
import { summarizeFrequency } from '@/app/dashboard/automation/lib/frequency';

/** What the main pane of a project link shows. */
export type ProjectShareView = 'tasks' | 'sessions' | 'automations';

/**
 * The view a project link's URL asks for, given what the link carries.
 *
 * An explicit `?view=` wins, then a deep-linked `?automation=` / `?session=`.
 * With nothing asked for, the page opens on something rather than on a "pick
 * one" pane: the tasks when the link carries them (the project's overview),
 * else the sessions (the newest one), else the automations. A parameter for a
 * part the link does not carry is ignored.
 */
export function resolveProjectView(
  scopes: readonly ShareScope[],
  params: { view: string | null; session: string | null; automation: string | null },
): ProjectShareView {
  const tasks = scopes.includes('tasks');
  const sessions = scopes.includes('sessions');
  const automations = scopes.includes('automations');
  if (automations && (params.view === 'automations' || params.automation)) return 'automations';
  if (tasks && params.view === 'tasks') return 'tasks';
  if (sessions && params.session) return 'sessions';
  if (tasks) return 'tasks';
  if (sessions) return 'sessions';
  return automations ? 'automations' : 'sessions';
}

/** A timestamp in the visitor's own clock: "Oct 4, 9:00 AM". */
export function formatShareTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/**
 * One line for when an automation runs: the dashboard's own words for a
 * recurring schedule (in the automation's time zone), or the one moment a
 * one-off runs, in the visitor's clock.
 */
export function publicScheduleSummary(
  a: Pick<PublicAutomation, 'schedule_kind' | 'frequency' | 'next_run_at'>,
): string {
  if (a.schedule_kind === 'once') {
    return a.next_run_at ? `Once, ${formatShareTime(a.next_run_at)}` : 'Once';
  }
  return a.frequency ? summarizeFrequency(a.frequency) : 'Recurring';
}

export const RUN_STATUS_LABEL: Record<AutomationRunStatus, string> = {
  fired: 'Ran',
  missed_offline: 'Missed (machine offline)',
  failed: 'Failed',
  skipped: 'Skipped',
};

/** "Ran, Oct 4, 9:00 AM" / "Never run". */
export function lastRunSummary(
  a: Pick<PublicAutomation, 'last_run_at' | 'last_run_status'>,
  format: (iso: string) => string = formatShareTime,
): string {
  if (!a.last_run_status && !a.last_run_at) return 'Never run';
  const label = a.last_run_status ? RUN_STATUS_LABEL[a.last_run_status] : 'Ran';
  return a.last_run_at ? `${label}, ${format(a.last_run_at)}` : label;
}

/**
 * The display keys of a public `session_config` as a `SessionConfig`, or null
 * when it names no agent. The server sends only display keys, but as an
 * untyped object, so each one is checked rather than cast.
 */
export function publicSessionConfig(raw: Record<string, unknown> | null): SessionConfig | null {
  if (!raw) return null;
  const str = (key: string): string | undefined => {
    const value = raw[key];
    return typeof value === 'string' && value ? value : undefined;
  };
  const agent = str('agent');
  if (!agent) return null;
  return {
    agent,
    model: str('model'),
    thinking_effort: str('thinking_effort'),
    reasoning_effort: str('reasoning_effort'),
    permission_mode: str('permission_mode'),
    opencode_mode: str('opencode_mode'),
  };
}
