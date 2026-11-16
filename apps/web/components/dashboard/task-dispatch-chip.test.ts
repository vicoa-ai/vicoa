import { describe, expect, it } from 'vitest';

import type { TaskDispatchSummary } from '@/lib/backend-api';
import { dispatchChipState } from './task-dispatch-chip';

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
    created_at: '2026-11-15T00:00:00Z',
    updated_at: '2026-11-15T00:00:00Z',
    ...over,
  };
}

describe('dispatchChipState', () => {
  it('queued shows the server reason in the tooltip', () => {
    const state = dispatchChipState(dispatch({ detail: 'queued: 2 of 2 sessions busy' }), 'Claude');
    expect(state?.label).toBe('Queued');
    expect(state?.tooltip).toBe('queued: 2 of 2 sessions busy');
  });

  it('a delivered turn that is running reads as working', () => {
    const state = dispatchChipState(dispatch({ state: 'delivered', session_status: 'ACTIVE' }), 'Claude');
    expect(state).toMatchObject({ label: 'Claude working', tone: 'working' });
  });

  it('says nothing once the turn is over or it was cancelled', () => {
    expect(dispatchChipState(dispatch({ state: 'delivered', session_status: 'AWAITING_INPUT' }), 'C')).toBeNull();
    expect(dispatchChipState(dispatch({ state: 'cancelled' }), 'C')).toBeNull();
    expect(dispatchChipState(null, 'C')).toBeNull();
  });

  it('a spawn not yet registered reads as starting', () => {
    expect(dispatchChipState(dispatch({ state: 'started' }), 'C')?.label).toBe('Starting');
  });

  it('a failure is red with its reason', () => {
    const state = dispatchChipState(dispatch({ state: 'failed', detail: 'this agent is archived' }), 'Claude');
    expect(state).toMatchObject({ label: 'Failed', tone: 'failed' });
    expect(state?.tooltip).toContain('this agent is archived');
  });
});
