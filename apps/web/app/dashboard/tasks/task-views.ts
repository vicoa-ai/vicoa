'use client';

// Local (per-device) saved views for the tasks page. Each view is a named
// preset holding its own display mode + filters + collapsed sections; the
// tabs strip (task-views-bar.tsx) lets the user create/switch/rename them.
//
// Persisted through lib/desktop-prefs.ts, so on the desktop app they live in
// the hand-editable settings.json and on web they fall back to localStorage.
// There is no backend model — views don't sync across devices (matching the
// tasks surface, which is web/desktop-only today). The `+` on the tab strip
// is also the future home for "Connect Linear / GitLab" integrations.

import { getPref, setPref } from '@/lib/desktop-prefs';
import type { TaskPriority, TaskResponse, TaskStatus } from '@/lib/backend-api';

export type TaskViewMode = 'list' | 'board';

/**
 * How tasks are ordered within each status group (multica's "Display →
 * ordering"). 'position' is the manual drag order; the rest map to a
 * `TaskResponse` field. 'status' is intentionally absent — the list/board are
 * always grouped by status (sections / columns), so sorting by it is a no-op.
 */
export type TaskSortField =
  | 'position'
  | 'priority'
  | 'start_date'
  | 'due_date'
  | 'created_at'
  | 'updated_at'
  | 'title';

export type TaskSortDirection = 'asc' | 'desc';

export const DEFAULT_TASK_SORT: TaskSortField = 'position';
export const DEFAULT_TASK_SORT_DIRECTION: TaskSortDirection = 'asc';

/** Ordered entries for the Display popover's "Ordering" dropdown. */
export const TASK_SORT_OPTIONS: { key: TaskSortField; label: string }[] = [
  { key: 'position', label: 'Manual' },
  { key: 'priority', label: 'Priority' },
  { key: 'start_date', label: 'Start date' },
  { key: 'due_date', label: 'Due date' },
  { key: 'created_at', label: 'Created date' },
  { key: 'updated_at', label: 'Updated date' },
  { key: 'title', label: 'Title' },
];

// Highest priority first (urgent → none), matching PRIORITY_ORDER in task-ui.
const PRIORITY_RANK: Record<TaskPriority, number> = {
  urgent: 0,
  high: 1,
  medium: 2,
  low: 3,
  none: 4,
};

/**
 * Comparator for the chosen ordering (mirrors multica's compareIssuesForSort).
 * Manual ('position') ignores direction; every other field honours asc/desc.
 * Missing start/due dates always sort last — an empty due date isn't "early".
 * Ties break on created_at then id so the order is stable across renders.
 * `created_at`/`updated_at`/dates are ISO-8601, so a string compare is
 * chronological (no Date parsing needed).
 */
export function compareTasks(
  a: TaskResponse,
  b: TaskResponse,
  sortBy: TaskSortField,
  direction: TaskSortDirection,
): number {
  const dir = sortBy !== 'position' && direction === 'desc' ? -1 : 1;
  const tieBreak = () =>
    a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id);
  const byDate = (av: string | null, bv: string | null) => {
    if (!av && !bv) return tieBreak();
    if (!av) return 1;
    if (!bv) return -1;
    return dir * av.localeCompare(bv) || tieBreak();
  };
  switch (sortBy) {
    case 'priority':
      return dir * (PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority]) || tieBreak();
    case 'title':
      return dir * a.title.localeCompare(b.title) || tieBreak();
    case 'created_at':
      return dir * a.created_at.localeCompare(b.created_at) || tieBreak();
    case 'updated_at':
      return dir * a.updated_at.localeCompare(b.updated_at) || tieBreak();
    case 'start_date':
      return byDate(a.start_date, b.start_date);
    case 'due_date':
      return byDate(a.due_date, b.due_date);
    case 'position':
    default:
      return a.position - b.position || tieBreak();
  }
}

/**
 * Which properties render on a task's list row / board card (multica's
 * "Display → card properties"). Priority/title always show; these are the
 * optional ones the user can hide per view.
 */
export interface TaskViewProperties {
  priority: boolean;
  labels: boolean;
  project: boolean;
  startDate: boolean;
  dueDate: boolean;
  childProgress: boolean;
  parent: boolean;
}

export const DEFAULT_TASK_PROPERTIES: TaskViewProperties = {
  priority: true,
  labels: true,
  project: true,
  startDate: true,
  dueDate: true,
  childProgress: true,
  parent: true,
};

/** Ordered labels for the Display popover. */
export const TASK_PROPERTY_OPTIONS: { key: keyof TaskViewProperties; label: string }[] = [
  { key: 'priority', label: 'Priority' },
  { key: 'project', label: 'Project' },
  { key: 'labels', label: 'Labels' },
  { key: 'startDate', label: 'Start date' },
  { key: 'dueDate', label: 'Due date' },
  { key: 'childProgress', label: 'Sub-task progress' },
  { key: 'parent', label: 'Parent' },
];

export interface TaskView {
  id: string;
  name: string;
  mode: TaskViewMode;
  /** 'all' or a project id. */
  projectFilter: string;
  /** When false, sub-tasks (tasks with a parent) are hidden — parents only. */
  showSubTasks: boolean;
  /** Which optional properties render on rows/cards. */
  properties: TaskViewProperties;
  /** Field tasks are ordered by within each status group. */
  sortBy: TaskSortField;
  /** Sort direction; ignored when `sortBy` is 'position' (manual). */
  sortDirection: TaskSortDirection;
  /** Statuses collapsed in list view. */
  collapsed: TaskStatus[];
}

const VIEWS_KEY = 'tasks:views';
const ACTIVE_VIEW_KEY = 'tasks:activeView';

let idCounter = 0;

/** A stable-enough id without pulling in a uuid dep. */
function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  idCounter += 1;
  return `view-${idCounter}-${idCounter * 2654435761}`;
}

export function defaultView(): TaskView {
  return {
    id: newId(),
    name: 'All tasks',
    mode: 'list',
    projectFilter: 'all',
    showSubTasks: true,
    properties: { ...DEFAULT_TASK_PROPERTIES },
    sortBy: DEFAULT_TASK_SORT,
    sortDirection: DEFAULT_TASK_SORT_DIRECTION,
    collapsed: [],
  };
}

/** Fill in any missing fields so a view saved by an older build stays usable. */
function normalizeView(raw: Partial<TaskView> | null | undefined): TaskView | null {
  if (!raw || typeof raw !== 'object') return null;
  const base = defaultView();
  return {
    id: typeof raw.id === 'string' && raw.id ? raw.id : base.id,
    name: typeof raw.name === 'string' && raw.name.trim() ? raw.name : base.name,
    mode: raw.mode === 'board' ? 'board' : 'list',
    projectFilter: typeof raw.projectFilter === 'string' ? raw.projectFilter : 'all',
    showSubTasks: raw.showSubTasks !== false,
    // Merge over defaults so a property added in a newer build inherits `true`
    // for views saved before it existed.
    properties: { ...DEFAULT_TASK_PROPERTIES, ...(raw.properties ?? {}) },
    sortBy: TASK_SORT_OPTIONS.some((o) => o.key === raw.sortBy)
      ? (raw.sortBy as TaskSortField)
      : base.sortBy,
    sortDirection: raw.sortDirection === 'desc' ? 'desc' : 'asc',
    collapsed: Array.isArray(raw.collapsed) ? (raw.collapsed as TaskStatus[]) : [],
  };
}

/** Load persisted views, always returning at least the default view. */
export function loadViews(): TaskView[] {
  const raw = getPref<unknown>(VIEWS_KEY);
  const list = Array.isArray(raw)
    ? raw.map((v) => normalizeView(v as Partial<TaskView>)).filter((v): v is TaskView => v !== null)
    : [];
  return list.length > 0 ? list : [defaultView()];
}

export function saveViews(views: TaskView[]): void {
  setPref(VIEWS_KEY, views);
}

export function loadActiveViewId(): string | null {
  return getPref<string>(ACTIVE_VIEW_KEY);
}

export function saveActiveViewId(id: string): void {
  setPref(ACTIVE_VIEW_KEY, id);
}

/** A fresh view seeded from an existing one (used by "New view" / Duplicate). */
export function cloneView(source: TaskView, name: string): TaskView {
  return {
    ...source,
    id: newId(),
    name,
    properties: { ...source.properties },
    collapsed: [...source.collapsed],
  };
}
