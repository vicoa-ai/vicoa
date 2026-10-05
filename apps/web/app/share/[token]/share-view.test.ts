import { describe, expect, it } from 'vitest';

import type { ShareScope } from '@/lib/backend-api';
import type { PublicAutomation } from '@/lib/public-share-api';
import {
  RUN_STATUS_LABEL,
  lastRunSummary,
  publicScheduleSummary,
  publicSessionConfig,
  resolveProjectView,
} from './share-view';

const none = { view: null, session: null, automation: null };

describe('resolveProjectView', () => {
  const all: ShareScope[] = ['tasks', 'sessions', 'automations'];

  it('opens on the tasks, else the sessions, else the automations', () => {
    expect(resolveProjectView(all, none)).toBe('tasks');
    expect(resolveProjectView(['sessions', 'automations'], none)).toBe('sessions');
    expect(resolveProjectView(['automations'], none)).toBe('automations');
  });

  it('keeps how a tasks and sessions link has always opened', () => {
    const both: ShareScope[] = ['tasks', 'sessions'];
    expect(resolveProjectView(both, none)).toBe('tasks');
    expect(resolveProjectView(both, { ...none, session: 's-1' })).toBe('sessions');
    expect(resolveProjectView(both, { ...none, view: 'tasks', session: 's-1' })).toBe('tasks');
    expect(resolveProjectView(['tasks'], { ...none, session: 's-1' })).toBe('tasks');
  });

  it('follows a deep link into the automations', () => {
    expect(resolveProjectView(all, { ...none, view: 'automations' })).toBe('automations');
    expect(resolveProjectView(all, { ...none, automation: 'a-1' })).toBe('automations');
    expect(resolveProjectView(['sessions', 'automations'], { ...none, view: 'automations', session: 's-1' })).toBe(
      'automations',
    );
  });

  it('ignores a view the link does not carry', () => {
    expect(resolveProjectView(['tasks', 'sessions'], { ...none, view: 'automations' })).toBe('tasks');
    expect(resolveProjectView(['sessions'], { ...none, automation: 'a-1' })).toBe('sessions');
    expect(resolveProjectView(['automations'], { ...none, view: 'tasks' })).toBe('automations');
  });
});

function automation(over: Partial<PublicAutomation> = {}): PublicAutomation {
  return {
    id: 'a-1',
    title: 'Nightly review',
    prompt: 'Review yesterday\'s PRs.\n\nList anything risky.',
    session_config: { agent: 'claude', model: 'opus' },
    schedule_kind: 'recurring',
    frequency: { kind: 'daily', time: '09:00' },
    timezone: 'Asia/Singapore',
    next_run_at: '2026-10-06T01:00:00Z',
    enabled: true,
    last_run_at: null,
    last_run_status: null,
    ...over,
  };
}

describe('publicScheduleSummary', () => {
  it('speaks the dashboard words for a recurring schedule', () => {
    expect(publicScheduleSummary(automation())).toBe('Daily at 9:00 AM');
    expect(publicScheduleSummary(automation({ frequency: { kind: 'weekly', weekdays: [5, 1], time: '14:30' } }))).toBe(
      'Weekly on Mon, Fri at 2:30 PM',
    );
    expect(publicScheduleSummary(automation({ frequency: null }))).toBe('Recurring');
  });

  it('names the moment a one-off runs', () => {
    expect(publicScheduleSummary(automation({ schedule_kind: 'once', frequency: null }))).toMatch(/^Once, /);
    expect(publicScheduleSummary(automation({ schedule_kind: 'once', frequency: null, next_run_at: null }))).toBe(
      'Once',
    );
  });
});

describe('lastRunSummary', () => {
  const at = (iso: string) => `at ${iso}`;

  it('says when it has never run', () => {
    expect(lastRunSummary(automation(), at)).toBe('Never run');
  });

  it('names the outcome and the time', () => {
    expect(lastRunSummary(automation({ last_run_status: 'fired', last_run_at: 'T' }), at)).toBe('Ran, at T');
    expect(lastRunSummary(automation({ last_run_status: 'missed_offline', last_run_at: 'T' }), at)).toBe(
      'Missed (machine offline), at T',
    );
    expect(lastRunSummary(automation({ last_run_status: 'failed', last_run_at: null }), at)).toBe('Failed');
  });

  it('has no em or en dashes in its labels', () => {
    for (const label of Object.values(RUN_STATUS_LABEL)) expect(label).not.toMatch(/[—–]/);
  });
});

describe('publicSessionConfig', () => {
  it('keeps the display keys that are strings', () => {
    expect(
      publicSessionConfig({ agent: 'codex', model: 'gpt-5', reasoning_effort: 'high', permission_mode: 7 }),
    ).toEqual({
      agent: 'codex',
      model: 'gpt-5',
      thinking_effort: undefined,
      reasoning_effort: 'high',
      permission_mode: undefined,
      opencode_mode: undefined,
    });
  });

  it('is null without an agent', () => {
    expect(publicSessionConfig(null)).toBeNull();
    expect(publicSessionConfig({ model: 'opus' })).toBeNull();
    expect(publicSessionConfig({ agent: '' })).toBeNull();
  });
});
