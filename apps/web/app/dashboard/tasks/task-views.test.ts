import { describe, expect, it } from 'vitest';

import { activeLabelFilter, labelFilterOptions, taskMatchesLabels } from './task-views';
import type { TaskLabelResponse, TaskResponse } from '@/lib/backend-api';

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
