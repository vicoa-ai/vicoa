import { describe, expect, it } from 'vitest';
import type { AutomationResponse } from '@/lib/backend-api';
import { groupByProject } from './group-by-project';
import { reorderRows } from './order';

function row(id: string, project_id: string | null = null): AutomationResponse {
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
    created_at: '',
    updated_at: '',
    project_id,
  };
}

const ids = (rows: AutomationResponse[]) => rows.map((r) => r.id);

describe('reorderRows', () => {
  it('applies a drag in an unfiltered list', () => {
    const rows = [row('a'), row('b'), row('c'), row('d')];
    // a dropped below c
    expect(ids(reorderRows(rows, ['b', 'c', 'a', 'd']))).toEqual(['b', 'c', 'a', 'd']);
  });

  it('keeps other groups in their slots', () => {
    // Projects interleave in the full list; a drag inside p1 only swaps p1 rows.
    const rows = [row('a', 'p1'), row('x', 'p2'), row('b', 'p1'), row('y', 'p2'), row('c', 'p1')];
    expect(ids(reorderRows(rows, ['c', 'a', 'b']))).toEqual(['c', 'x', 'a', 'y', 'b']);
  });

  it('keeps rows hidden by a filter or a search in their slots', () => {
    const rows = [row('a'), row('b'), row('c'), row('d')];
    // b and c hidden; d dragged above a.
    expect(ids(reorderRows(rows, ['d', 'a']))).toEqual(['d', 'b', 'c', 'a']);
  });

  it('ignores ids that are not in the list', () => {
    const rows = [row('a'), row('b')];
    expect(ids(reorderRows(rows, ['b', 'gone', 'a']))).toEqual(['b', 'a']);
  });

  it('shows the dragged order inside the group once regrouped', () => {
    const rows = [row('a', 'p1'), row('x', 'p2'), row('b', 'p1'), row('c', 'p1')];
    const next = reorderRows(rows, ['b', 'c', 'a']);
    const p1 = groupByProject(next, []).find((g) => g.key === 'p1')!;
    expect(ids(p1.rows)).toEqual(['b', 'c', 'a']);
  });
});
