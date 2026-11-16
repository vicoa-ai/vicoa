import { describe, expect, it } from 'vitest';

import type { TaskDispatchSummary } from '@/lib/backend-api';
import { changedStatuses, dispatchSettling, nextDelay } from './use-task-live-refresh';

function dispatch(over: Partial<TaskDispatchSummary>): TaskDispatchSummary {
  return {
    id: 'd1',
    agent_profile_id: 'p1',
    mode: 'ownership',
    trigger: 'assigned',
    state: 'queued',
    detail: null,
    agent_instance_id: null,
    session_status: null,
    created_at: '2026-11-16T08:00:00Z',
    updated_at: '2026-11-16T08:00:00Z',
    ...over,
  };
}

describe('dispatchSettling', () => {
  it('follows a dispatch until its session has registered', () => {
    expect(dispatchSettling(dispatch({ state: 'queued' }))).toBe(true);
    expect(dispatchSettling(dispatch({ state: 'dispatching' }))).toBe(true);
    expect(dispatchSettling(dispatch({ state: 'started', session_status: null }))).toBe(true);
  });

  it('stops once there is a session to watch, or nothing left to happen', () => {
    expect(dispatchSettling(dispatch({ state: 'started', session_status: 'ACTIVE' }))).toBe(false);
    expect(dispatchSettling(dispatch({ state: 'delivered', session_status: 'ACTIVE' }))).toBe(false);
    expect(dispatchSettling(dispatch({ state: 'failed' }))).toBe(false);
    expect(dispatchSettling(dispatch({ state: 'cancelled' }))).toBe(false);
    expect(dispatchSettling(null)).toBe(false);
    expect(dispatchSettling(undefined)).toBe(false);
  });
});

describe('nextDelay', () => {
  it('backs off from 2s to the normal 30s poll', () => {
    const delays = [2_000];
    while (delays.length < 12) delays.push(nextDelay(delays[delays.length - 1]));
    expect(delays.slice(0, 3)).toEqual([2_000, 3_000, 4_500]);
    expect(Math.max(...delays)).toBe(30_000);
  });
});

describe('changedStatuses', () => {
  it('reloads when a known session changes status', () => {
    const seen = new Map([['s1', 'ACTIVE']]);
    expect(changedStatuses(seen, new Map([['s1', 'REVIEWED']]))).toBe(true);
    expect(changedStatuses(seen, new Map([['s1', 'ACTIVE']]))).toBe(false);
  });

  it('a session appearing for the first time is not a change', () => {
    expect(changedStatuses(new Map(), new Map([['s2', 'ACTIVE']]))).toBe(false);
  });
});
