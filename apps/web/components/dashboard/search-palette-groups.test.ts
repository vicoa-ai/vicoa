import { describe, expect, test } from 'vitest';
import {
  GROUP_PREVIEW_COUNT,
  buildSearchGroups,
  searchGroupForPath,
  searchWords,
  type SearchGroupKey,
} from './search-palette-groups';
import type {
  SearchAutomationResult,
  SearchSessionResult,
  SearchTaskResult,
} from '@/lib/backend-api';

function session(
  name: string,
  match_source: SearchSessionResult['match_source'] = 'name',
): SearchSessionResult {
  return {
    id: name,
    name,
    agent_type_name: 'claude',
    status: 'ACTIVE' as SearchSessionResult['status'],
    project: null,
    started_at: '2026-11-05T10:00:00',
    latest_message: null,
    latest_message_at: null,
    match_source,
    snippet: null,
  };
}

function task(
  title: string,
  over: Partial<SearchTaskResult> = {},
): SearchTaskResult {
  return {
    id: title,
    identifier: null,
    title,
    status: 'todo',
    priority: 'none',
    project_id: null,
    updated_at: '2026-11-05T10:00:00',
    match_source: 'title',
    snippet: null,
    ...over,
  };
}

function automation(title: string): SearchAutomationResult {
  return {
    id: title,
    title,
    enabled: true,
    schedule_kind: 'once',
    next_run_at: null,
    match_source: 'title',
    snippet: null,
  };
}

const NONE: ReadonlySet<SearchGroupKey> = new Set();

function build(over: Partial<Parameters<typeof buildSearchGroups>[0]>) {
  return buildSearchGroups({
    sessions: [],
    tasks: [],
    automations: [],
    query: 'fix',
    currentGroup: null,
    expanded: NONE,
    ...over,
  });
}

const keys = (groups: ReturnType<typeof build>) => groups.map((group) => group.key);

describe('buildSearchGroups', () => {
  test('leaves empty groups out', () => {
    expect(keys(build({ tasks: [task('fix it')] }))).toEqual(['tasks']);
    expect(build({})).toEqual([]);
  });

  test('keeps the usual order when groups match equally well', () => {
    const groups = build({
      sessions: [session('a fix')],
      tasks: [task('a fix')],
      automations: [automation('a fix')],
    });
    expect(keys(groups)).toEqual(['sessions', 'tasks', 'automations']);
  });

  test('puts the group with the best top match first', () => {
    const groups = build({
      sessions: [session('a fix for later')],
      tasks: [task('fix')],
      automations: [automation('fix the nightly run')],
    });
    expect(keys(groups)).toEqual(['tasks', 'automations', 'sessions']);
  });

  test('a full identifier counts as an exact match', () => {
    const groups = build({
      query: 'vic-42',
      sessions: [session('vic-42 follow up')],
      tasks: [task('Unrelated title', { identifier: 'VIC-42', match_source: 'identifier' })],
    });
    expect(keys(groups)).toEqual(['tasks', 'sessions']);
  });

  test('a session that only matched in a message goes to a last group', () => {
    const groups = build({
      sessions: [session('mentions it', 'message'), session('a fix')],
      tasks: [task('needs a fix')],
    });
    expect(keys(groups)).toEqual(['sessions', 'tasks', 'messages']);
    expect(groups[0].rows.map((row) => row.id)).toEqual(['a fix']);
    expect(groups[2].rows.map((row) => row.id)).toEqual(['mentions it']);
  });

  test('the current page leads even over a better match', () => {
    const groups = build({
      sessions: [session('fix')],
      tasks: [task('needs a fix')],
      currentGroup: 'tasks',
    });
    expect(keys(groups)).toEqual(['tasks', 'sessions']);
  });

  test('the current page never moves message hits up', () => {
    const groups = build({
      sessions: [session('mentions it', 'message')],
      tasks: [task('needs a fix')],
      currentGroup: 'sessions',
    });
    expect(keys(groups)).toEqual(['tasks', 'messages']);
  });

  test('caps a group and reports what is left', () => {
    const tasks = Array.from({ length: GROUP_PREVIEW_COUNT + 3 }, (_, i) => task(`fix ${i}`));
    const [group] = build({ tasks });
    expect(group.rows).toHaveLength(GROUP_PREVIEW_COUNT);
    expect(group.hidden).toBe(3);
  });

  test('expanding shows the whole group and leaves the others capped', () => {
    const tasks = Array.from({ length: 8 }, (_, i) => task(`fix ${i}`));
    const automations = Array.from({ length: 8 }, (_, i) => automation(`fix ${i}`));
    const groups = build({ tasks, automations, expanded: new Set(['tasks']) });
    expect(groups.map((group) => [group.key, group.rows.length, group.hidden])).toEqual([
      ['tasks', 8, 0],
      ['automations', GROUP_PREVIEW_COUNT, 3],
    ]);
  });

  test('does not cap the recent sessions shown with no query', () => {
    const sessions = Array.from({ length: 7 }, (_, i) => session(`recent ${i}`));
    const [group] = build({ query: '', sessions });
    expect(group.rows).toHaveLength(7);
    expect(group.hidden).toBe(0);
  });
});

describe('searchGroupForPath', () => {
  test.each([
    ['/dashboard/tasks', 'tasks'],
    ['/dashboard/tasks/abc', 'tasks'],
    ['/dashboard/automation', 'automations'],
    ['/dashboard/sessions/abc', 'sessions'],
    ['/dashboard/kanban', 'sessions'],
    ['/dashboard/settings', null],
    ['/dashboard', null],
  ])('%s', (pathname, expected) => {
    expect(searchGroupForPath(pathname)).toBe(expected);
  });
});

describe('searchWords', () => {
  test('splits on any whitespace, including a full-width space', () => {
    expect(searchWords('  Search\u3000BAR  tasks ')).toEqual(['search', 'bar', 'tasks']);
    expect(searchWords('   ')).toEqual([]);
  });
});
