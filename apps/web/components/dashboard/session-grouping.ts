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

/**
 * Fold a reordering of the project groups on screen back into the full
 * project order.
 *
 * `full` ranks every project the user has — including ones with no session in
 * the current list (filtered out, archived-only, or simply idle) — and is what
 * gets synced to the backend; `rendered` is the on-screen subset in its new
 * order. The rendered keys are dealt back into the slots rendered keys held
 * before, so an off-screen project keeps its place instead of being dropped
 * from the order (and silently reset to recency) every time the user drags
 * with a status filter on. Keys not in `full` yet (a group whose project has
 * not loaded, or a basename group with no project) are appended first, so a
 * drag onto them still lands where it was dropped.
 */
export function mergeRenderedOrder(full: string[], rendered: string[]): string[] {
  const known = new Set(full);
  const base = [...full, ...rendered.filter((key) => !known.has(key))];
  const onScreen = new Set(rendered);
  const queue = [...rendered];
  return base.map((key) => (onScreen.has(key) ? queue.shift()! : key));
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
  /** The worktree's folder — its identity. A session's registered `project`
   *  (home-collapsed `~/…`) when it has sessions, else git's path. */
  path: string;
  /** Display label: the live branch when git reported one, else the branch
   *  the sessions were started on. Empty for a detached HEAD. */
  branch: string;
  /** Daemon-managed (under ~/vicoa/workspaces) → removable from the sidebar. */
  managed: boolean;
  /** Git no longer has a checkout at this folder (removed outside the app, or
   *  only a prunable registration is left). Always false without a git list. */
  missing: boolean;
  instances: AgentInstanceResponse[];
}

export interface ProjectWorktreeSplit {
  /** Sessions started in the repo's main checkout (no `worktree_name`). */
  mainInstances: AgentInstanceResponse[];
  worktrees: WorktreeSessionGroup[];
}

/** One entry of the daemon's `git-worktree-list`, as the split consumes it.
 *  `display_path` (home-collapsed like a session's `project`) and `prunable`
 *  are absent from an older daemon; both degrade to "unknown". */
export interface LiveWorktree {
  path: string;
  display_path?: string;
  branch: string;
  managed: boolean;
  prunable?: boolean;
}

/** Folder-path identity: trailing slashes never make two paths differ. */
export function normalizeWorktreePath(path: string): string {
  const trimmed = path.replace(/\/+$/, '');
  return trimmed || path;
}

/**
 * The distinct worktree folders a project's sessions run in (sorted, in the
 * same normalized form `splitProjectByWorktree` keys on). The sidebar fetches
 * a fresh `git worktree list` whenever this set changes, and records it as the
 * set the fetch can vouch for — see the `judgeable` argument below.
 */
export function worktreeSessionPaths(instances: AgentInstanceResponse[]): string[] {
  const paths = new Set<string>();
  for (const inst of instances) {
    if (inst.worktree_name) paths.add(normalizeWorktreePath(inst.project ?? ''));
  }
  return Array.from(paths).sort();
}

/** Claude Code's own scratch worktrees (`EnterWorktree`) — agent-internal, so
 *  one with no Vicoa session in it is noise in a sidebar, not a workspace. */
function isAgentScratchWorktree(path: string): boolean {
  return path.includes('/.claude/worktrees/');
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
 * A worktree's identity is its FOLDER (the session's registered `project`,
 * immutable), never its branch — the same model orca uses (`repoId::path`).
 * Switching branches inside a worktree therefore keeps every session in the
 * same group and only changes the label; the old branch-keyed split turned
 * one folder into two groups as soon as a session was started after a
 * `git checkout -b`. Sessions with no `worktree_name` are the main checkout.
 * A session always keeps its own node: a removed worktree never folds its
 * sessions into main, it is shown as `missing` instead.
 *
 * `gitWorktrees` (the live `git worktree list`) is an ENRICHMENT, not the
 * source of membership: it supplies the current branch for the label, the
 * authoritative managed flag, the `missing` verdict, and surfaces worktrees
 * that currently have no session (#4). Pass `null` on web / before it resolves
 * — grouping then runs purely off the sessions' stored fields (label =
 * `worktree_name`, the branch at session start), so the same folders render
 * with or without git.
 *
 * `judgeable` is the set of session folders that existed when `gitWorktrees`
 * was fetched. Only those can be called `missing`: a session that appeared
 * after the fetch (a just-started "new worktree" session) is not in it, and a
 * list older than the session has no standing to say its folder is gone — it
 * was simply fetched before the folder was created. Omit it to judge every
 * folder (the list is known to be current).
 *
 * `instances` is expected newest-first (as `groupSessions` returns), so each
 * worktree's most recent session leads and drives the group ordering.
 */
export function splitProjectByWorktree(
  instances: AgentInstanceResponse[],
  gitWorktrees: ReadonlyArray<LiveWorktree> | null,
  judgeable?: ReadonlySet<string>,
): ProjectWorktreeSplit {
  const mainInstances: AgentInstanceResponse[] = [];
  const byPath = new Map<string, AgentInstanceResponse[]>();
  for (const inst of instances) {
    if (inst.worktree_name) {
      const key = normalizeWorktreePath(inst.project ?? '');
      const arr = byPath.get(key);
      if (arr) arr.push(inst);
      else byPath.set(key, [inst]);
    } else {
      mainInstances.push(inst); // main checkout
    }
  }

  // Index live worktrees under both spellings of their folder: git's absolute
  // path, and the daemon's home-collapsed `display_path` — which is how a
  // session registers its `project`, so the two match by plain equality.
  const live = new Map<string, LiveWorktree>();
  for (const w of gitWorktrees ?? []) {
    live.set(normalizeWorktreePath(w.path), w);
    if (w.display_path) live.set(normalizeWorktreePath(w.display_path), w);
  }
  const claimed = new Set<LiveWorktree>();

  const worktrees: WorktreeSessionGroup[] = [];
  for (const [path, group] of byPath) {
    const liveInfo = live.get(path);
    if (liveInfo) claimed.add(liveInfo);
    const present = liveInfo !== undefined && !liveInfo.prunable;
    worktrees.push({
      path,
      // Live branch wins (it may have changed since the session started); the
      // stored name is the label when git is unavailable or the folder is gone.
      branch: present ? liveInfo.branch : group[0]?.worktree_name ?? '',
      managed: liveInfo ? liveInfo.managed : isManagedWorktreePath(path),
      missing:
        gitWorktrees !== null && !present && (judgeable === undefined || judgeable.has(path)),
      instances: group,
    });
  }
  if (gitWorktrees) {
    for (const w of gitWorktrees) {
      if (claimed.has(w) || w.prunable || isAgentScratchWorktree(w.path)) continue;
      worktrees.push({
        path: normalizeWorktreePath(w.display_path ?? w.path),
        branch: w.branch,
        managed: w.managed,
        missing: false,
        instances: [],
      });
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
    // `projectOrder` first (indices in it) — the sidebar feeds it the backend's
    // project list, which is the user's synced drag order and then recency, so
    // a never-dragged project still lands by recency rather than by the
    // arbitrary id order below — then keys it doesn't know (a basename group
    // with no project, or before the list loads) sorted by key, no-project
    // always last. `key` is the project_id (or basename fallback); the display
    // label is derived separately so a linked project never shows its raw id.
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
