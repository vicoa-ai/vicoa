import type { AgentInstanceResponse } from '@/lib/backend-api';
import { isManagedWorktreePath } from '@/lib/worktree-selection';

/**
 * Shared session filter + group-by logic for the sidebars.
 *
 * The web dashboard sidebar (dashboard-layout.tsx) and the desktop sidebar
 * (desktop-sidebar.tsx) both drive their lists from `groupSessions` and share
 * localStorage keys, so a session lands in the same group in either one. Their
 * *controls* have diverged, though: only desktop exposes the Agent, Project and
 * Display rows, and the two disagree on status-filter labels. Every dimension
 * past `groupBy` is therefore an optional argument that defaults to "off", so
 * the web sidebar's three-argument call keeps its current behavior.
 */

export type StatusFilter =
  | 'all'
  | 'not_closed'
  | 'in_progress'
  | 'in_review'
  | 'done'
  | 'closed';

export type GroupBy = 'project' | 'status' | 'time';

/** localStorage keys shared by both sidebars. */
export const STATUS_FILTER_STORAGE_KEY = 'sidebar-status-filter';
export const GROUP_BY_STORAGE_KEY = 'sidebar-group-by';
export const AGENT_FILTER_STORAGE_KEY = 'sidebar-agent-filter';
export const PROJECT_ORDER_STORAGE_KEY = 'sidebar-project-order';
export const HIDDEN_PROJECTS_STORAGE_KEY = 'sidebar-hidden-projects';
/** Desktop-only (see the divergence note above): sub-group projects by worktree. */
export const DISPLAY_WORKTREE_STORAGE_KEY = 'sidebar-display-worktree';

/** Distinct project display names (last path part) present in the list. */
export function distinctProjectNames(instances: AgentInstanceResponse[]): string[] {
  const names = new Set<string>();
  for (const instance of instances) {
    if (instance.project) names.add(getLastPathPart(instance.project));
  }
  return Array.from(names).sort((a, b) => a.localeCompare(b));
}

/** Distinct agent type names present in the list (for the Agent filter menu). */
export function distinctAgentNames(instances: AgentInstanceResponse[]): string[] {
  const names = new Set<string>();
  for (const instance of instances) {
    if (instance.agent_type_name) names.add(instance.agent_type_name);
  }
  return Array.from(names).sort((a, b) => a.localeCompare(b));
}

/** Statuses that count as "closed" (terminal). */
export const CLOSED_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'KILLED',
  'DELETED',
  'DISCONNECTED',
]);

/** Filter option set (value + human label), shared by both dropdowns.
    "Active" (formerly "Not closed") leads and is the default; "Archived"
    keeps the legacy 'closed' storage value. */
export const STATUS_FILTER_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'not_closed', label: 'Active' },
  { value: 'all', label: 'All' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'in_review', label: 'In Review' },
  { value: 'done', label: 'Done' },
  { value: 'closed', label: 'Archived' },
];

export const DEFAULT_STATUS_FILTER: StatusFilter = 'not_closed';

/**
 * Whether a given filter should restrict the backing fetch to active sessions
 * (mirrors the web sidebar's `setActiveOnly` call). Non-terminal filters only
 * need active sessions loaded.
 */
export const filterWantsActiveOnly = (filter: StatusFilter): boolean =>
  filter !== 'all' && filter !== 'done' && filter !== 'closed';

/** Last path segment of a project path (its display name). */
export function getLastPathPart(path: string): string {
  const cleanPath = path.replace(/\/+$/, '');
  const parts = cleanPath.split('/');
  return parts[parts.length - 1] || path;
}

export interface SessionGroup {
  key: string;
  label: string | null;
  instances: AgentInstanceResponse[];
}

/** One worktree of a project, with the sessions running in it (possibly none). */
export interface WorktreeSessionGroup {
  branch: string;
  path: string;
  /** Daemon-managed (under ~/vicoa/workspaces) → removable from the sidebar. */
  managed: boolean;
  instances: AgentInstanceResponse[];
}

export interface ProjectWorktreeSplit {
  /** Main-checkout sessions plus any whose worktree no longer exists (orphans). */
  mainInstances: AgentInstanceResponse[];
  worktrees: WorktreeSessionGroup[];
}

/** Order worktrees by their most-recent session (empty ones last, then by name). */
function sortWorktrees(worktrees: WorktreeSessionGroup[]): WorktreeSessionGroup[] {
  const recency = (g: WorktreeSessionGroup): number => {
    const first = g.instances[0];
    return first ? new Date(first.latest_message_at || first.started_at).getTime() : -Infinity;
  };
  return [...worktrees].sort((a, b) => {
    const ra = recency(a);
    const rb = recency(b);
    if (ra !== rb) return rb - ra;
    return a.branch.localeCompare(b.branch);
  });
}

/**
 * Split one project's sessions into its main checkout plus a group per worktree.
 *
 * `gitWorktrees` is the live `git worktree list` for the repo — the source of
 * truth for which worktrees exist:
 *   - Every worktree shows, even with no sessions (#4).
 *   - A session whose branch matches no live worktree is orphaned (its worktree
 *     was removed) and folds back into the main checkout (#3).
 * Pass `null` before that list has loaded (or when git is unavailable): sessions
 * are then grouped by their own `worktree_name` as a baseline, so worktrees
 * stay visible immediately instead of flashing flat, and nothing is treated as
 * orphaned until git actually says so.
 *
 * `instances` is expected newest-first (as `groupSessions` returns), so each
 * worktree's most recent session leads and drives the group ordering.
 */
export function splitProjectByWorktree(
  instances: AgentInstanceResponse[],
  gitWorktrees: ReadonlyArray<{ path: string; branch: string; managed: boolean }> | null,
): ProjectWorktreeSplit {
  const mainInstances: AgentInstanceResponse[] = [];
  const byBranch = new Map<string, AgentInstanceResponse[]>();
  const push = (branch: string, inst: AgentInstanceResponse) => {
    const arr = byBranch.get(branch);
    if (arr) arr.push(inst);
    else byBranch.set(branch, [inst]);
  };

  if (gitWorktrees === null) {
    for (const inst of instances) {
      if (inst.worktree_name) push(inst.worktree_name, inst);
      else mainInstances.push(inst);
    }
    const worktrees = Array.from(byBranch.entries()).map(([branch, group]) => ({
      branch,
      path: group[0]?.project ?? '',
      managed: isManagedWorktreePath(group[0]?.project ?? ''),
      instances: group,
    }));
    return { mainInstances, worktrees: sortWorktrees(worktrees) };
  }

  const live = new Set(gitWorktrees.map((w) => w.branch));
  for (const inst of instances) {
    if (inst.worktree_name && live.has(inst.worktree_name)) push(inst.worktree_name, inst);
    else mainInstances.push(inst); // main checkout, or an orphaned worktree
  }
  const worktrees = gitWorktrees.map((w) => ({
    branch: w.branch,
    path: w.path,
    managed: w.managed,
    instances: byBranch.get(w.branch) ?? [],
  }));
  return { mainInstances, worktrees: sortWorktrees(worktrees) };
}

/**
 * Sort (newest first, pinned pulled to the top), filter by status and agent,
 * then group by the chosen dimension. Pinned sessions always form the first
 * "Pinned" group, are excluded from the other groups, and (like the status
 * filter) are exempt from the agent filter.
 */
export function groupSessions(
  instances: AgentInstanceResponse[],
  statusFilter: StatusFilter,
  groupBy: GroupBy,
  agentFilter: string = 'all',
  projectOrder: string[] = [],
  hiddenProjects: string[] = [],
): SessionGroup[] {
  const sortedInstances = [...instances].sort((a, b) => {
    const aTime = new Date(a.latest_message_at || a.started_at).getTime();
    const bTime = new Date(b.latest_message_at || b.started_at).getTime();
    return bTime - aTime;
  });

  const pinnedInstances = sortedInstances.filter((i) => i.pinned_at);
  const pinnedIds = new Set(pinnedInstances.map((i) => i.id));
  const unpinnedSorted = sortedInstances.filter((i) => !pinnedIds.has(i.id));

  const statusVisible = (() => {
    switch (statusFilter) {
      case 'all':         return unpinnedSorted;
      case 'not_closed':  return unpinnedSorted.filter((i) => !CLOSED_STATUSES.has(i.status));
      case 'in_progress': return unpinnedSorted.filter((i) => ['ACTIVE', 'STALE'].includes(i.status));
      case 'in_review':   return unpinnedSorted.filter((i) => i.status === 'AWAITING_INPUT');
      case 'done':        return unpinnedSorted.filter((i) => i.status === 'REVIEWED');
      case 'closed':      return unpinnedSorted.filter((i) => CLOSED_STATUSES.has(i.status));
      default:            return unpinnedSorted;
    }
  })();

  const agentVisible =
    agentFilter === 'all'
      ? statusVisible
      : statusVisible.filter((i) => i.agent_type_name === agentFilter);

  // Deselected projects are hidden; sessions without a project always show.
  const hidden = new Set(hiddenProjects);
  const visibleInstances =
    hidden.size === 0
      ? agentVisible
      : agentVisible.filter((i) => !i.project || !hidden.has(getLastPathPart(i.project)));

  let groups: SessionGroup[];
  if (groupBy === 'project') {
    const projectMap = new Map<string, AgentInstanceResponse[]>();
    for (const instance of visibleInstances) {
      const key = instance.project ? getLastPathPart(instance.project) : '__no_project__';
      if (!projectMap.has(key)) projectMap.set(key, []);
      projectMap.get(key)!.push(instance);
    }
    // User-dragged order first (indices in projectOrder), then unranked
    // projects alphabetically, no-project always last.
    groups = Array.from(projectMap.entries())
      .sort(([a], [b]) => {
        if (a === '__no_project__') return 1;
        if (b === '__no_project__') return -1;
        const rankA = projectOrder.indexOf(a);
        const rankB = projectOrder.indexOf(b);
        if (rankA !== -1 && rankB !== -1) return rankA - rankB;
        if (rankA !== -1) return -1;
        if (rankB !== -1) return 1;
        return a.localeCompare(b);
      })
      .map(([key, groupInstances]) => ({
        key,
        label: key !== '__no_project__' ? key : null,
        instances: groupInstances,
      }));
  } else if (groupBy === 'time') {
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startOfYesterday = startOfToday - 86400000;
    const startOf7Days = startOfToday - 6 * 86400000;
    const startOf30Days = startOfToday - 29 * 86400000;
    const getInstanceTime = (i: AgentInstanceResponse) =>
      new Date(i.latest_message_at || i.started_at).getTime();
    groups = [
      { key: 'TODAY',     label: 'Today',        instances: visibleInstances.filter((i) => getInstanceTime(i) >= startOfToday) },
      { key: 'YESTERDAY', label: 'Yesterday',    instances: visibleInstances.filter((i) => getInstanceTime(i) >= startOfYesterday && getInstanceTime(i) < startOfToday) },
      { key: 'LAST7',     label: 'Last 7 days',  instances: visibleInstances.filter((i) => getInstanceTime(i) >= startOf7Days && getInstanceTime(i) < startOfYesterday) },
      { key: 'LAST30',    label: 'Last 30 days', instances: visibleInstances.filter((i) => getInstanceTime(i) >= startOf30Days && getInstanceTime(i) < startOf7Days) },
      { key: 'OLDER',     label: 'Older',        instances: visibleInstances.filter((i) => getInstanceTime(i) < startOf30Days) },
    ];
  } else {
    groups = [
      { key: 'IN_PROGRESS', label: 'In Progress', instances: visibleInstances.filter((i) => ['ACTIVE', 'STALE'].includes(i.status)) },
      { key: 'IN_REVIEW',   label: 'In Review',   instances: visibleInstances.filter((i) => i.status === 'AWAITING_INPUT') },
      { key: 'DONE',        label: 'Done',        instances: visibleInstances.filter((i) => i.status === 'REVIEWED') },
      ...(statusFilter === 'all' || statusFilter === 'closed'
        ? [{ key: 'CLOSED', label: 'Archived', instances: visibleInstances.filter((i) => CLOSED_STATUSES.has(i.status)) }]
        : []),
    ];
  }

  if (pinnedInstances.length > 0) {
    groups = [{ key: 'PINNED', label: 'Pinned', instances: pinnedInstances }, ...groups];
  }

  return groups;
}
