import type { AutomationResponse } from '@/lib/backend-api';
import { isCompleted } from './state';

/**
 * How the list is ordered, as on the Tasks page's Ordering: `position` is the
 * viewer's own drag order (the backend returns the list in it); every other
 * field replaces it, and rows then can't be dragged since a drag would change
 * nothing.
 */
export type AutomationSortField = 'position' | 'next_run_at' | 'created_at';

export type AutomationSortDirection = 'asc' | 'desc';

export const DEFAULT_SORT: AutomationSortField = 'position';
export const DEFAULT_SORT_DIRECTION: AutomationSortDirection = 'asc';

/** Ordered entries for the Sort menu. */
export const SORT_OPTIONS: { key: AutomationSortField; label: string }[] = [
  { key: 'position', label: 'Manual' },
  { key: 'next_run_at', label: 'Next run' },
  { key: 'created_at', label: 'Created date' },
];

export interface AutomationSort {
  sortBy: AutomationSortField;
  sortDirection: AutomationSortDirection;
}

export const SORT_STORAGE_KEY = 'automation:sort';

/** The saved ordering, or null when there is none worth keeping. */
export function parseSort(raw: string | null): AutomationSort | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<AutomationSort> | null;
    const sortBy = SORT_OPTIONS.find((o) => o.key === v?.sortBy)?.key;
    if (!sortBy) return null;
    return {
      sortBy,
      sortDirection: v?.sortDirection === 'desc' ? 'desc' : DEFAULT_SORT_DIRECTION,
    };
  } catch {
    return null;
  }
}

function ms(iso: string | null | undefined): number {
  const t = iso ? Date.parse(iso) : NaN;
  return Number.isNaN(t) ? 0 : t;
}

/** Newest first: how ties, and rows with nothing to compare, fall. */
const newestFirst = (a: AutomationResponse, b: AutomationResponse): number =>
  ms(b.created_at) - ms(a.created_at);

/** The next fire time of a row that will actually fire; null otherwise. */
function nextFire(a: AutomationResponse): number | null {
  return a.enabled && a.next_run_at ? ms(a.next_run_at) : null;
}

/**
 * The rows ordered by `sortBy`, with completed one-time automations after
 * everything else whatever the order: they are done, so they sink, most
 * recently run first (in `position` the incoming order stays). A row with no
 * next run (paused) sorts after those that have one in both directions, like a
 * missing date on the Tasks page: an empty next run isn't "soon".
 */
export function sortAutomations(
  rows: AutomationResponse[],
  sortBy: AutomationSortField,
  direction: AutomationSortDirection,
): AutomationResponse[] {
  const live = rows.filter((a) => !isCompleted(a));
  const done = rows.filter(isCompleted);
  const dir = direction === 'desc' ? -1 : 1;
  if (sortBy === 'next_run_at') {
    live.sort((a, b) => {
      const an = nextFire(a);
      const bn = nextFire(b);
      if (an === null || bn === null) {
        return an === bn ? newestFirst(a, b) : an === null ? 1 : -1;
      }
      return dir * (an - bn) || newestFirst(a, b);
    });
  } else if (sortBy === 'created_at') {
    live.sort((a, b) => dir * (ms(a.created_at) - ms(b.created_at)));
  }
  if (sortBy !== 'position') {
    done.sort((a, b) => ms(b.last_run_at) - ms(a.last_run_at) || newestFirst(a, b));
  }
  return [...live, ...done];
}
