/**
 * How the ⌘K palette groups, orders and caps its results. Pure, so it can be
 * tested without a DOM; `search-palette.tsx` draws what this returns.
 */

import type {
  SearchAutomationResult,
  SearchSessionResult,
  SearchTaskResult,
} from '@/lib/backend-api';

/** Rows a group shows before its "Show N more" row. */
export const GROUP_PREVIEW_COUNT = 5;

export type SearchGroupKey = 'sessions' | 'tasks' | 'automations' | 'messages';

export type SearchGroup =
  | { key: 'sessions' | 'messages'; rows: SearchSessionResult[]; hidden: number }
  | { key: 'tasks'; rows: SearchTaskResult[]; hidden: number }
  | { key: 'automations'; rows: SearchAutomationResult[]; hidden: number };

// The order groups that match equally well keep.
const TIE_ORDER: SearchGroupKey[] = ['sessions', 'tasks', 'automations'];

export function searchWords(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

/** The group a dashboard page is about, which then leads the results there. */
export function searchGroupForPath(pathname: string): SearchGroupKey | null {
  if (pathname.startsWith('/dashboard/tasks')) return 'tasks';
  if (pathname.startsWith('/dashboard/automation')) return 'automations';
  if (
    pathname.startsWith('/dashboard/sessions') ||
    pathname.startsWith('/dashboard/kanban')
  ) {
    return 'sessions';
  }
  return null;
}

/** How well a title answers the query; lower is better. Mirrors the tiers the
 * backend ranks each group by, which only compare rows inside one group. */
function titleTier(title: string | null, query: string): number {
  const lowered = (title ?? '').toLowerCase();
  const wanted = query.toLowerCase();
  if (lowered === wanted) return 0;
  if (lowered.startsWith(wanted)) return 1;
  if (lowered.includes(wanted)) return 2;
  if (searchWords(query).every((word) => lowered.includes(word))) return 3;
  return 4;
}

function taskTier(task: SearchTaskResult, query: string): number {
  if (task.identifier?.toLowerCase() === query.toLowerCase()) return 0;
  if (task.match_source === 'identifier') return 1;
  return titleTier(task.title, query);
}

function cap<Row>(rows: Row[], limit: number): { rows: Row[]; hidden: number } {
  return { rows: rows.slice(0, limit), hidden: Math.max(0, rows.length - limit) };
}

interface BuildSearchGroupsInput {
  sessions: SearchSessionResult[];
  tasks: SearchTaskResult[];
  automations: SearchAutomationResult[];
  query: string;
  /** The group the current page is about; it leads whatever the matches. */
  currentGroup: SearchGroupKey | null;
  expanded: ReadonlySet<SearchGroupKey>;
}

/**
 * The non-empty groups, best first. Sessions that only matched in a message
 * become their own group, always last: they are the weakest kind of hit, and
 * mixing them in is what used to bury an exact task title. With no query this
 * is just the short recent-sessions list, which is not capped.
 */
export function buildSearchGroups({
  sessions,
  tasks,
  automations,
  query,
  currentGroup,
  expanded,
}: BuildSearchGroupsInput): SearchGroup[] {
  const limitFor = (key: SearchGroupKey) =>
    !query || expanded.has(key) ? Infinity : GROUP_PREVIEW_COUNT;

  const named = sessions.filter((session) => session.match_source !== 'message');
  const inMessages = sessions.filter((session) => session.match_source === 'message');

  const ranked: { group: SearchGroup; tier: number }[] = [];
  if (named.length > 0) {
    ranked.push({
      group: { key: 'sessions', ...cap(named, limitFor('sessions')) },
      tier: titleTier(named[0].name, query),
    });
  }
  if (tasks.length > 0) {
    ranked.push({
      group: { key: 'tasks', ...cap(tasks, limitFor('tasks')) },
      tier: taskTier(tasks[0], query),
    });
  }
  if (automations.length > 0) {
    ranked.push({
      group: { key: 'automations', ...cap(automations, limitFor('automations')) },
      tier: titleTier(automations[0].title, query),
    });
  }

  const position = ({ group, tier }: { group: SearchGroup; tier: number }) =>
    group.key === currentGroup ? -1 : tier;
  const ordered = ranked
    .sort(
      (a, b) =>
        position(a) - position(b) ||
        TIE_ORDER.indexOf(a.group.key) - TIE_ORDER.indexOf(b.group.key),
    )
    .map(({ group }) => group);

  return inMessages.length > 0
    ? [...ordered, { key: 'messages', ...cap(inMessages, limitFor('messages')) }]
    : ordered;
}
