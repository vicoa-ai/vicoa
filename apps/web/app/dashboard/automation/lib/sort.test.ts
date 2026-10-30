import { describe, expect, it } from 'vitest';
import type { AutomationResponse } from '@/lib/backend-api';
import { DEFAULT_SORT_DIRECTION, parseSort, sortAutomations } from './sort';
import { automationState, summarizeCompleted } from './state';

function row(id: string, over: Partial<AutomationResponse> = {}): AutomationResponse {
  return {
    id,
    title: id,
    prompt: 'p',
    machine_id: 'm',
    directory: '/d',
    worktree: null,
    session_config: {},
    schedule_kind: 'recurring',
    frequency: { kind: 'daily', time: '09:00' },
    timezone: 'UTC',
    next_run_at: null,
    enabled: true,
    last_run_at: null,
    last_run_status: null,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '',
    ...over,
  };
}

const ids = (rows: AutomationResponse[]) => rows.map((r) => r.id);

const done = (id: string, over: Partial<AutomationResponse> = {}) =>
  row(id, {
    schedule_kind: 'once',
    frequency: null,
    enabled: false,
    next_run_at: null,
    last_run_at: '2026-10-10T00:00:00Z',
    last_run_status: 'fired',
    ...over,
  });

describe('automationState', () => {
  it('is completed for a one-time automation with no fire time left', () => {
    expect(automationState(done('a'))).toBe('completed');
  });

  it('still calls a resumed, time-less one-time automation completed', () => {
    expect(automationState(done('a', { enabled: true }))).toBe('completed');
  });

  it('keeps a pending one-time automation active or paused', () => {
    const pending = { schedule_kind: 'once' as const, next_run_at: '2026-11-01T00:00:00Z' };
    expect(automationState({ ...pending, enabled: true })).toBe('active');
    expect(automationState({ ...pending, enabled: false })).toBe('paused');
  });

  it('never calls a recurring automation completed', () => {
    expect(automationState(row('a', { enabled: false }))).toBe('paused');
    expect(automationState(row('a'))).toBe('active');
  });
});

describe('summarizeCompleted', () => {
  it('says how the single run went', () => {
    expect(summarizeCompleted({ last_run_at: null, last_run_status: 'fired' })).toBe(
      'Once · completed',
    );
    expect(summarizeCompleted({ last_run_at: null, last_run_status: 'failed' })).toBe(
      'Once · failed',
    );
    expect(
      summarizeCompleted({ last_run_at: '2026-10-10T00:00:00Z', last_run_status: 'fired' }),
    ).toMatch(/^Once · ran /);
    expect(
      summarizeCompleted({ last_run_at: '2026-10-10T00:00:00Z', last_run_status: 'missed_offline' }),
    ).toMatch(/^Once · missed, machine offline /);
  });
});

describe('sortAutomations', () => {
  const rows = [
    row('late', { next_run_at: '2026-11-05T00:00:00Z', created_at: '2026-10-02T00:00:00Z' }),
    row('paused', {
      enabled: false,
      next_run_at: '2026-11-01T00:00:00Z',
      created_at: '2026-10-06T00:00:00Z',
    }),
    row('soon', { next_run_at: '2026-11-02T00:00:00Z', created_at: '2026-10-03T00:00:00Z' }),
    done('old-done', { last_run_at: '2026-10-05T00:00:00Z', created_at: '2026-10-09T00:00:00Z' }),
    done('new-done', { last_run_at: '2026-10-12T00:00:00Z', created_at: '2026-10-01T00:00:00Z' }),
  ];

  it('position keeps the incoming order, completed rows last, whatever the direction', () => {
    const expected = ['late', 'paused', 'soon', 'old-done', 'new-done'];
    expect(ids(sortAutomations(rows, 'position', 'asc'))).toEqual(expected);
    expect(ids(sortAutomations(rows, 'position', 'desc'))).toEqual(expected);
  });

  it('next run ascending puts the soonest firing first', () => {
    expect(ids(sortAutomations(rows, 'next_run_at', 'asc'))).toEqual([
      'soon',
      'late',
      'paused',
      'new-done',
      'old-done',
    ]);
  });

  it('next run descending flips the rows that will fire, but a paused one stays after them', () => {
    expect(ids(sortAutomations(rows, 'next_run_at', 'desc'))).toEqual([
      'late',
      'soon',
      'paused',
      'new-done',
      'old-done',
    ]);
  });

  it('next run breaks ties newest first', () => {
    const tied = [
      row('a', { next_run_at: '2026-11-01T00:00:00Z', created_at: '2026-10-01T00:00:00Z' }),
      row('b', { next_run_at: '2026-11-01T00:00:00Z', created_at: '2026-10-03T00:00:00Z' }),
    ];
    expect(ids(sortAutomations(tied, 'next_run_at', 'asc'))).toEqual(['b', 'a']);
  });

  it('created date goes oldest first ascending, newest first descending', () => {
    expect(ids(sortAutomations(rows, 'created_at', 'asc'))).toEqual([
      'late',
      'soon',
      'paused',
      'new-done',
      'old-done',
    ]);
    expect(ids(sortAutomations(rows, 'created_at', 'desc'))).toEqual([
      'paused',
      'soon',
      'late',
      'new-done',
      'old-done',
    ]);
  });

  it('does not mutate its input', () => {
    const before = ids(rows);
    sortAutomations(rows, 'next_run_at', 'desc');
    expect(ids(rows)).toEqual(before);
  });
});

describe('parseSort', () => {
  it('reads what was saved', () => {
    expect(parseSort('{"sortBy":"next_run_at","sortDirection":"desc"}')).toEqual({
      sortBy: 'next_run_at',
      sortDirection: 'desc',
    });
  });

  it('falls back to the default direction when it is missing or unknown', () => {
    expect(parseSort('{"sortBy":"created_at"}')?.sortDirection).toBe(DEFAULT_SORT_DIRECTION);
    expect(parseSort('{"sortBy":"created_at","sortDirection":"up"}')?.sortDirection).toBe(
      DEFAULT_SORT_DIRECTION,
    );
  });

  it('ignores nothing, junk, and a field that no longer exists', () => {
    expect(parseSort(null)).toBeNull();
    expect(parseSort('')).toBeNull();
    expect(parseSort('not json')).toBeNull();
    expect(parseSort('null')).toBeNull();
    expect(parseSort('{"sortBy":"title"}')).toBeNull();
  });
});
