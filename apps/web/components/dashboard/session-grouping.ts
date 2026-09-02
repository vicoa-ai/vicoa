import type { AgentInstanceResponse, ProjectResponse } from '@/lib/backend-api';
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
/** Desktop-only (see the divergence note above): sub-group projects by worktree. */
export const DISPLAY_WORKTREE_STORAGE_KEY = 'sidebar-display-worktree';

/** Group-key for sessions with no project at all. */
export const NO_PROJECT_KEY = '__no_project__';

/**
 * Stable identity of the project a session belongs to, for top-level grouping.
 *
 * Prefers the formal `project_id` (server-matched from the session's machine +
 * working dir, and — for a worktree — its repo root/remote), so two checkouts
 * of one repo collapse into a single group even when their folder names differ,
 * and two unrelated repos that happen to share a basename stay apart. Falls back
 * to the path basename when no project is linked (unchanged legacy behavior, and
 * a UUID never collides with a basename), and to `NO_PROJECT_KEY` for sessions
 * with no project path. Keep in sync with `projectDisplayName`.
 */
export function projectGroupKey(instance: AgentInstanceResponse): string {
  if (instance.project_id) return instance.project_id;
  return instance.project ? getLastPathPart(instance.project) : NO_PROJECT_KEY;
}

/**
 * Human label for a project group. Prefers the DB project's `name` when the
 * group is a linked project (identity-unification §5a) so the sidebar and Tasks
 * board show the same identity; falls back to the path basename for sessions
 * with no linked project. Never the raw id.
 */
function projectDisplayName(
  instances: AgentInstanceResponse[],
  projectsById?: Map<string, ProjectResponse>,
): string {
  const key = projectGroupKey(instances[0]);
  const dbName = projectsById?.get(key)?.name;
  if (dbName) return dbName;
  const first = instances.find((i) => i.project);
  return first?.project ? getLastPathPart(first.project) : key;
}

/** Distinct project groups present in the list, as `{ key, label }` pairs. */
export function distinctProjects(
  instances: AgentInstanceResponse[],
): { key: string; label: string }[] {
  const byKey = new Map<string, string>();
  for (const instance of instances) {
    const key = projectGroupKey(instance);
    if (key === NO_PROJECT_KEY) continue;
    if (!byKey.has(key)) {
      byKey.set(key, instance.project ? getLastPathPart(instance.project) : key);
    }
  }
  return Array.from(byKey, ([key, label]) => ({ key, label })).sort((a, b) =>
    a.label.localeCompare(b.label),
  );
}

/** A project the Settings page can open a per-project pane for: its stable
 *  group key + label, plus the machine and repo dir needed to route the
 *  committed-config file RPC (see WorktreeSetupSection). */
export interface ProjectSettingsTarget {
  key: string;
  label: string;
  machineId: string;
  dir: string;
}

/**
 * Per-project settings targets, one per project group present in the list.
 *
 * `dir` is the repo's *main* checkout (a session with no `worktree_name`),
 * falling back to any session's cwd — the same directory the sidebar's project
 * "+" and "Project settings" action use, so the config resolves to the repo
 * root rather than a worktree. Groups with no reachable machine or no directory
 * (nothing to route a file RPC to) are dropped.
 */
export function projectSettingsTargets(
  instances: AgentInstanceResponse[],
): ProjectSettingsTarget[] {
  const byKey = new Map<string, AgentInstanceResponse[]>();
  for (const instance of instances) {
    const key = projectGroupKey(instance);
    if (key === NO_PROJECT_KEY) continue;
    const list = byKey.get(key);
    if (list) list.push(instance);
    else byKey.set(key, [instance]);
  }
  const targets: ProjectSettingsTarget[] = [];
  for (const [key, list] of byKey) {
    const machineId = list[0]?.machine_id ?? null;
    const dir = list.find((i) => !i.worktree_name)?.project ?? list[0]?.project ?? null;
    if (!machineId || !dir) continue;
    targets.push({ key, label: projectDisplayName(list), machineId, dir });
  }
  return targets.sort((a, b) => a.label.localeCompare(b.label));
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
 * Membership is keyed on each session's OWN stored worktree (`worktree_name`,
 * captured once at registration and immutable), NOT on a live `git worktree
 * list`. This is deliberate: a session started in a worktree stays under that
 * worktree even if the worktree's branch is later switched or the worktree is
 * removed — it never silently "jumps" into the main checkout (the old
 * live-branch cross-check did exactly that). Sessions with no `worktree_name`
 * are the main checkout.
 *
 * `gitWorktrees` (the live `git worktree list`, desktop-only) is an ENRICHMENT,
 * not the source of membership: it supplies the authoritative path/managed flag
 * for a worktree and surfaces worktrees that currently have no session (#4).
 * Pass `null` on web / before it resolves — grouping then runs purely off the
 * sessions' stored fields, so the same split renders with or without git.
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
  for (const inst of instances) {
    if (inst.worktree_name) {
      const arr = byBranch.get(inst.worktree_name);
      if (arr) arr.push(inst);
      else byBranch.set(inst.worktree_name, [inst]);
    } else {
      mainInstances.push(inst); // main checkout
    }
  }

  // Each session's own worktree node always exists (derived from the session,
  // so a removed/renamed worktree never drops it into main). Live git only
  // overrides the node's path/managed and adds worktrees that have no session.
  const live = new Map((gitWorktrees ?? []).map((w) => [w.branch, w] as const));
  const worktrees: WorktreeSessionGroup[] = [];
  for (const [branch, group] of byBranch) {
    const liveInfo = live.get(branch);
    const path = liveInfo?.path ?? group[0]?.project ?? '';
    worktrees.push({
      branch,
      path,
      managed: liveInfo ? liveInfo.managed : isManagedWorktreePath(path),
      instances: group,
    });
  }
  if (gitWorktrees) {
    for (const w of gitWorktrees) {
      if (!byBranch.has(w.branch)) {
        worktrees.push({ branch: w.branch, path: w.path, managed: w.managed, instances: [] });
      }
    }
  }
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
  projectsById?: Map<string, ProjectResponse>,
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

  // Archived projects drop out of the sidebar (cross-device declutter, §5b —
  // replaces the old per-device localStorage hide). Sessions with no project, or
  // whose project isn't loaded yet, always show.
  const visibleInstances =
    !projectsById || projectsById.size === 0
      ? agentVisible
      : agentVisible.filter((i) => {
          const project = i.project_id ? projectsById.get(i.project_id) : undefined;
          return !project?.is_archived;
        });

  let groups: SessionGroup[];
  if (groupBy === 'project') {
    const projectMap = new Map<string, AgentInstanceResponse[]>();
    for (const instance of visibleInstances) {
      const key = projectGroupKey(instance);
      if (!projectMap.has(key)) projectMap.set(key, []);
      projectMap.get(key)!.push(instance);
    }
    // User-dragged order first (indices in projectOrder), then unranked
    // projects alphabetically, no-project always last. `key` is the project_id
    // (or basename fallback); the display label is derived separately so a
    // linked project never shows its raw id.
    groups = Array.from(projectMap.entries())
      .sort(([a], [b]) => {
        if (a === NO_PROJECT_KEY) return 1;
        if (b === NO_PROJECT_KEY) return -1;
        const rankA = projectOrder.indexOf(a);
        const rankB = projectOrder.indexOf(b);
        if (rankA !== -1 && rankB !== -1) return rankA - rankB;
        if (rankA !== -1) return -1;
        if (rankB !== -1) return 1;
        return a.localeCompare(b);
      })
      .map(([key, groupInstances]) => ({
        key,
        label:
          key !== NO_PROJECT_KEY
            ? projectDisplayName(groupInstances, projectsById)
            : null,
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
