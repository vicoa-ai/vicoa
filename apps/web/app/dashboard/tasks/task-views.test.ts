import { describe, expect, it } from 'vitest';

import {
  NO_PROJECT_FILTER,
  activeLabelFilter,
  capColumnIds,
  compareTasks,
  createProjectDefault,
  labelFilterOptions,
  taskMatchesLabels,
} from './task-views';
import type { TaskLabelResponse, TaskResponse, TaskStatus } from '@/lib/backend-api';

const label = (id: string, name: string): TaskLabelResponse => ({
  id,
  name,
  color: '#3b82f6',
  team_id: null,
});

const task = (id: string, labels: TaskLabelResponse[]): TaskResponse => ({
  id,
  project_id: null,
  number: null,
  identifier: null,
  title: id,
  description: null,
  status: 'todo',
  priority: 'none',
  position: 0,
  parent_task_id: null,
  parent_title: null,
  assignee_type: null,
  assignee_id: null,
  assignee: null,
  labels,
  start_date: null,
  due_date: null,
  created_in_instance_id: null,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
});

const bug = label('l-bug', 'bug');
const docs = label('l-docs', 'docs');
const ui = label('l-ui', 'UI');

describe('labelFilterOptions', () => {
  it('adds labels that only appear on tasks, deduped and sorted by name', () => {
    // `docs` is on a task in a board someone else shared, so it is not in the
    // caller's own vocabulary.
    const options = labelFilterOptions([ui, bug], [task('t1', [bug, docs]), task('t2', [docs])]);
    expect(options.map((l) => l.id)).toEqual(['l-bug', 'l-docs', 'l-ui']);
  });

  it('prefers the vocabulary copy of a label also found on a task', () => {
    const renamed = { ...bug, name: 'bug (stale)' };
    const options = labelFilterOptions([bug], [task('t1', [renamed])]);
    expect(options).toEqual([bug]);
  });
});

describe('activeLabelFilter', () => {
  it('drops ids whose label no longer exists', () => {
    const active = activeLabelFilter(['l-bug', 'l-gone'], [bug, docs]);
    expect([...active]).toEqual(['l-bug']);
  });
});

describe('taskMatchesLabels', () => {
  it('passes every task when no label is active', () => {
    expect(taskMatchesLabels(task('t1', []), new Set())).toBe(true);
  });

  it('passes a task carrying any of the active labels', () => {
    const active = new Set(['l-bug', 'l-docs']);
    expect(taskMatchesLabels(task('t1', [docs]), active)).toBe(true);
    expect(taskMatchesLabels(task('t2', [ui]), active)).toBe(false);
    expect(taskMatchesLabels(task('t3', []), active)).toBe(false);
  });
});

describe('createProjectDefault', () => {
  const writable = [{ id: 'alpha' }, { id: 'beta' }];

  it('starts a new task in the project the view is filtered to', () => {
    expect(createProjectDefault('alpha', writable)).toBe('alpha');
    expect(createProjectDefault('beta', writable)).toBe('beta');
  });

  it('starts unfiled under "All" and "No project"', () => {
    expect(createProjectDefault('all', writable)).toBeUndefined();
    expect(createProjectDefault(NO_PROJECT_FILTER, writable)).toBeUndefined();
  });

  it('ignores a project the caller cannot file into', () => {
    // A stale saved view, or a board shared read-only: not offered by the dialog.
    expect(createProjectDefault('gamma', writable)).toBeUndefined();
    expect(createProjectDefault('alpha', [])).toBeUndefined();
  });
});

// A row with the fields the comparator reads; `updatedDay` is a day in October.
const row = (
  id: string,
  status: TaskStatus,
  position: number,
  updatedDay: number,
  priority: TaskResponse['priority'] = 'none',
): TaskResponse => ({
  ...task(id, []),
  status,
  position,
  priority,
  updated_at: `2026-10-${String(updatedDay).padStart(2, '0')}T00:00:00Z`,
});

const order = (tasks: TaskResponse[], sortBy: Parameters<typeof compareTasks>[2]) =>
  [...tasks].sort((a, b) => compareTasks(a, b, sortBy, 'asc')).map((t) => t.id);

describe('compareTasks', () => {
  it('lists a closed column newest first under Manual, whatever the positions', () => {
    // d-new was finished last but kept the high position it had in Todo.
    const tasks = [row('d-old', 'done', 1, 2), row('d-new', 'done', 9, 20), row('d-mid', 'done', 5, 10)];
    expect(order(tasks, 'position')).toEqual(['d-new', 'd-mid', 'd-old']);
  });

  it('keeps open columns in manual position order', () => {
    const tasks = [row('t-b', 'todo', 2, 20), row('t-a', 'todo', 1, 2)];
    expect(order(tasks, 'position')).toEqual(['t-a', 't-b']);
  });

  it('applies an explicit ordering to closed columns too', () => {
    const tasks = [row('d-low', 'done', 1, 20, 'low'), row('d-urgent', 'done', 2, 2, 'urgent')];
    expect(order(tasks, 'priority')).toEqual(['d-urgent', 'd-low']);
  });

  it('is a total order over mixed statuses (each column comes out the same)', () => {
    // Without grouping by status first, open-vs-closed pairs compared by
    // position and closed pairs by recency would form a cycle.
    const tasks = [row('d1', 'done', 3, 20), row('d2', 'done', 1, 2), row('t1', 'todo', 2, 10)];
    for (const shuffled of [tasks, [...tasks].reverse(), [tasks[2], tasks[0], tasks[1]]]) {
      const ids = order(shuffled, 'position');
      expect(ids.filter((id) => id.startsWith('d'))).toEqual(['d1', 'd2']);
    }
  });
});

describe('capColumnIds', () => {
  const ids = ['a', 'b', 'c', 'd'];

  it('keeps a column at or under the cap whole', () => {
    expect(capColumnIds(ids, 4, null)).toBe(ids);
  });

  it('cuts a longer column to the cap', () => {
    expect(capColumnIds(ids, 2, null)).toEqual(['a', 'b']);
  });

  it('keeps the card being dragged even past the cap', () => {
    expect(capColumnIds(ids, 2, 'c')).toEqual(['a', 'b', 'c']);
  });
});
