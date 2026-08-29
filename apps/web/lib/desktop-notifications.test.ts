import { describe, it, expect } from 'vitest';
import { diffSessionStatuses } from '@/lib/desktop-notifications';

const row = (id: string, status: string, name: string | null = null) => ({ id, status, name });

describe('diffSessionStatuses', () => {
  it('seeds the baseline without transitions on the first snapshot', () => {
    const diff = diffSessionStatuses(null, [
      row('a', 'AWAITING_INPUT'),
      row('b', 'ACTIVE'),
    ]);
    expect(diff.transitions).toEqual([]);
    expect(diff.statuses.get('a')).toBe('AWAITING_INPUT');
    expect(diff.awaitingCount).toBe(1);
  });

  it('emits a transition when a session flips into AWAITING_INPUT', () => {
    const prev = new Map([['a', 'ACTIVE']]);
    const diff = diffSessionStatuses(prev, [row('a', 'AWAITING_INPUT', 'Fix the tests')]);
    expect(diff.transitions).toEqual([
      { instanceId: 'a', title: 'Fix the tests', body: 'Needs your input' },
    ]);
  });

  it('emits transitions for COMPLETED and FAILED', () => {
    const prev = new Map([
      ['a', 'ACTIVE'],
      ['b', 'ACTIVE'],
    ]);
    const diff = diffSessionStatuses(prev, [
      row('a', 'COMPLETED'),
      row('b', 'FAILED'),
    ]);
    expect(diff.transitions.map((t) => t.body)).toEqual([
      'Session completed',
      'Session failed',
    ]);
  });

  it('stays silent on unchanged statuses and non-notify transitions', () => {
    const prev = new Map([
      ['a', 'AWAITING_INPUT'],
      ['b', 'AWAITING_INPUT'],
      ['c', 'ACTIVE'],
    ]);
    const diff = diffSessionStatuses(prev, [
      row('a', 'AWAITING_INPUT'), // unchanged
      row('b', 'REVIEWED'), // user opened it — no banner
      row('c', 'PAUSED'), // not a notify status
    ]);
    expect(diff.transitions).toEqual([]);
  });

  it('skips ids that were not in the previous snapshot', () => {
    const prev = new Map([['a', 'ACTIVE']]);
    const diff = diffSessionStatuses(prev, [
      row('a', 'ACTIVE'),
      row('new', 'AWAITING_INPUT'),
    ]);
    expect(diff.transitions).toEqual([]);
    // ...but the new id is tracked, so its next change diffs normally.
    const next = diffSessionStatuses(diff.statuses, [
      row('a', 'ACTIVE'),
      row('new', 'COMPLETED'),
    ]);
    expect(next.transitions.map((t) => t.instanceId)).toEqual(['new']);
  });

  it('falls back to a generic title for unnamed sessions', () => {
    const prev = new Map([['a', 'ACTIVE']]);
    const diff = diffSessionStatuses(prev, [row('a', 'AWAITING_INPUT', '  ')]);
    expect(diff.transitions[0]?.title).toBe('Vicoa session');
  });

  it('counts every session currently awaiting input', () => {
    const diff = diffSessionStatuses(new Map(), [
      row('a', 'AWAITING_INPUT'),
      row('b', 'AWAITING_INPUT'),
      row('c', 'COMPLETED'),
    ]);
    expect(diff.awaitingCount).toBe(2);
  });
});
