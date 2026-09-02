'use client';

import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  Loader2,
  ListFilter,
  Check,
  Archive,
  ChevronRight,
  Kanban,
  MoreHorizontal,
  Settings,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { cn } from '@/lib/utils';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { useSessionOperations, useCopyToClipboard } from '@/lib/hooks/use-session-operations';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { SnakeLoader } from '@/components/dashboard/snake-loader';
import {
  SessionActionsMenu,
  SessionActionItemContent,
  buildSessionActions,
  type SessionActionsConfig,
} from '@/components/dashboard/session-actions-menu';
import { NewSessionButton } from '@/components/dashboard/new-session-button';
import { WorktreeSubGroupHeader } from '@/components/dashboard/worktree-sub-group-header';
import type { AgentInstanceResponse, ProjectResponse } from '@/lib/backend-api';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import {
  formatSidebarTime,
  getSessionTitle,
} from '@/components/dashboard/session-display';
import {
  AGENT_FILTER_STORAGE_KEY,
  CLOSED_STATUSES,
  DEFAULT_STATUS_FILTER,
  DISPLAY_WORKTREE_STORAGE_KEY,
  distinctAgentNames,
  filterWantsActiveOnly,
  groupSessions,
  splitProjectByWorktree,
  GROUP_BY_STORAGE_KEY,
  PROJECT_ORDER_STORAGE_KEY,
  STATUS_FILTER_OPTIONS,
  STATUS_FILTER_STORAGE_KEY,
  type GroupBy,
  type StatusFilter,
} from '@/components/dashboard/session-grouping';
import { isReachable, liveStateHint, liveStateLabel, resolveLiveState } from '@/lib/session-liveness';
import {
  canResumeSession,
  isWithinResumeGrace,
  resumeBlockedMessage,
  resumeBlockedReason,
  resumeBlockedShortLabel,
  resumeSession,
} from '@/lib/session-resume';
import { useNow } from '@/lib/hooks/use-session-liveness';
import { isMacPlatform, matchesShortcut } from '@/lib/desktop-shortcuts';
import { getPref, setPref } from '@/lib/desktop-prefs';
import {
  RenameSessionDialog,
  DeleteSessionDialog,
  WorktreeDeleteDialog,
} from '@/components/dashboard/session-dialogs';
import {
  rpcGitStatus,
  rpcGitWorktreeList,
  rpcGitWorktreeRemove,
  type WorktreeInfo,
} from '@/components/files-git-panel/rpc';

// Selected-row highlight, shared between session rows and the view-options menu.
const ITEM_SELECTED = 'bg-foreground/[0.08] dark:bg-foreground/10 text-foreground';

// Group-by options. Order + labels mirror the web sidebar.
const GROUP_BY_OPTIONS: { value: GroupBy; label: string }[] = [
  { value: 'project', label: 'Project' },
  { value: 'status', label: 'Status' },
  { value: 'time', label: 'Time' },
];

/** Per-project git view backing worktree display: the live worktree list plus
    the main checkout's current branch (the "main folder" header). */
interface ProjectGitView {
  branch: string | null;
  worktrees: WorktreeInfo[];
}

/** One rendered row-group under a project: the main folder or a worktree. */
interface RenderedSubGroup {
  key: string;
  label: string;
  instances: AgentInstanceResponse[];
  /** Target of this group's "+", or null to hide it. */
  directory: string | null;
  /** Preselect this worktree on the new-session page; absent for main. */
  worktreeBranch?: string;
  /** Right-click delete target, or null when not removable (main / unmanaged). */
  remove: { machineId: string; path: string; branch: string } | null;
}

/**
 * Fetch, per project, its `git worktree list` and its main-checkout branch.
 * Keyed by the caller's group key. `listPath` is any session's cwd (git lists a
 * repo's worktrees from any of them); `mainPath` is a main-checkout session's
 * cwd, needed because git-status on a worktree path would return that worktree's
 * branch, not the repo's.
 *
 * Refetched on window focus since worktrees can be created/removed and branches
 * switched outside the app. Failures resolve to an empty view rather than an
 * error — the sidebar falls back to its session-derived baseline.
 */
function useProjectWorktrees(
  targets: ReadonlyArray<{
    key: string;
    machineId: string | null;
    listPath: string;
    mainPath: string | null;
  }>,
  refreshNonce: number,
): Map<string, ProjectGitView> {
  const [views, setViews] = useState<Map<string, ProjectGitView>>(new Map());
  // Primitive dep: only re-run when the target set changes, not every render.
  const signature = JSON.stringify(
    targets.map((t) => [t.key, t.machineId ?? '', t.listPath, t.mainPath ?? '']),
  );

  useEffect(() => {
    let cancelled = false;
    const fetchAll = async () => {
      const entries = await Promise.all(
        targets.map(async (t): Promise<readonly [string, ProjectGitView] | null> => {
          if (!t.machineId || !t.listPath) return null;
          const machineId = t.machineId;
          const [worktrees, branch] = await Promise.all([
            rpcGitWorktreeList(machineId, t.listPath).catch(() => [] as WorktreeInfo[]),
            t.mainPath
              ? rpcGitStatus(machineId, t.mainPath)
                  .then((s) => s.branch)
                  .catch(() => null)
              : Promise.resolve<string | null>(null),
          ]);
          return [t.key, { branch, worktrees }] as const;
        }),
      );
      if (cancelled) return;
      setViews(
        new Map(entries.filter((e): e is readonly [string, ProjectGitView] => e !== null)),
      );
    };
    void fetchAll();
    const onFocus = () => void fetchAll();
    window.addEventListener('focus', onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener('focus', onFocus);
    };
    // `signature` captures the meaningful contents of `targets`; `refreshNonce`
    // forces a refetch after a removal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, refreshNonce]);

  return views;
}

export interface SidebarSessionsProps {
  /** The currently open session id — drives row highlight and clears the
      per-row navigation spinner once the route lands on it. */
  selectedInstanceId: string | null;
  /** Platform-specific side effects when a row is opened (mark reviewed /
      auto-review). The shared component already handles navigation + spinner +
      scroll persistence, so this is *only* the post-open bookkeeping. */
  onSessionOpened?: (instance: AgentInstanceResponse) => void;
  /** Called after a session is archived or deleted, so the caller can tear its
      terminals + persisted layout down (web). Desktop omits it. */
  onAfterCloseSession?: (instanceId: string) => void;
  /** Worktree sub-grouping + git RPCs. Desktop-local only; off on web where
      there is no reachable local daemon. */
  enableWorktrees?: boolean;
  /** ⌘1–⌘9 / ⌘] / ⌘[ / ⌘N session-switching shortcuts (desktop). */
  enableKeyboardShortcuts?: boolean;
  /** Page in more sessions as the list nears the bottom. On both web and
      desktop the backing store only returns the first page up front (50 rows),
      so without this a user with more sessions is capped at that first page. */
  enableInfiniteScroll?: boolean;
}

/**
 * The shared central region of both sidebars: the "Workspaces" header row
 * (filter + Kanban), the grouped/collapsible session list, per-row hover actions
 * (archive + a three-dot menu) plus the right-click context menu, and the
 * rename/delete/worktree confirmation dialogs.
 *
 * The desktop and web sidebars wrap this with their own header + account areas.
 * Everything platform-specific rides in through the props above; the data itself
 * comes from `useAgentDashboard()`, which degrades gracefully in desktop-local
 * mode (local daemon server + local WS stream).
 */
export function SidebarSessions({
  selectedInstanceId,
  onSessionOpened,
  onAfterCloseSession,
  enableWorktrees = false,
  enableKeyboardShortcuts = false,
  enableInfiniteScroll = false,
}: SidebarSessionsProps) {
  const router = useRouter();
  const pathname = usePathname();
  // One shared clock for the whole list: liveness decays with elapsed time, so
  // rows must re-derive periodically rather than only on data changes.
  const livenessNow = useNow();
  const {
    recentInstances,
    isLoading,
    isLoadingMoreInstances,
    hasMoreInstances,
    setActiveOnly,
    refreshData,
    loadMoreInstances,
    api,
    updateInstanceStatus,
  } = useAgentDashboard();

  // Row hover actions reuse the shared session-operations hook. Passing the
  // selected id lets a delete of the currently-open session navigate to a
  // neighbor. `togglePin` doesn't refetch on its own, so we drive `refreshData`.
  const { togglePin, markAsComplete, renameSession, deleteSession } = useSessionOperations(
    selectedInstanceId ?? undefined,
  );
  const { copied: copiedSessionId, copy: copySessionId } = useCopyToClipboard();

  // Rename/delete confirmations reuse the shared dialogs, held locally.
  const [renameDialog, setRenameDialog] = useState({ open: false, sessionId: '', currentName: '' });
  const [deleteDialog, setDeleteDialog] = useState({ open: false, sessionId: '', sessionName: '' });
  const [resumingId, setResumingId] = useState<string | null>(null);

  const handleTogglePin = useCallback(async (instance: AgentInstanceResponse) => {
    await togglePin(instance.id, !instance.pinned_at);
    await refreshData();
  }, [togglePin, refreshData]);

  // Relaunch a stopped session from the sidebar, so a dead session doesn't have
  // to be opened to be revived.
  const handleResumeInstance = useCallback(async (instance: AgentInstanceResponse) => {
    if (resumingId) return;
    setResumingId(instance.id);
    try {
      await resumeSession(instance);
      await refreshData();
    } catch (error) {
      console.error('Failed to resume session:', error);
    } finally {
      setResumingId(null);
    }
  }, [resumingId, refreshData]);

  const handleArchive = useCallback(async (instance: AgentInstanceResponse) => {
    await markAsComplete(instance.id);
    // Archiving closes the session's workspace: let the caller tear down its
    // terminals + persisted layout (both web and desktop wire this).
    onAfterCloseSession?.(instance.id);
  }, [markAsComplete, onAfterCloseSession]);

  const handleDelete = useCallback(async (instanceId: string) => {
    await deleteSession(instanceId, true);
    onAfterCloseSession?.(instanceId);
  }, [deleteSession, onAfterCloseSession]);

  // Marks a reviewed session unread again (back to awaiting-input), restoring
  // the blue dot. Optimistic flip first, then the API call; WS reconciles.
  const handleUnread = useCallback(async (instance: AgentInstanceResponse) => {
    if (!api) return;
    updateInstanceStatus(instance.id, 'AWAITING_INPUT');
    try {
      await api.updateAgentStatus(instance.id, { status: 'AWAITING_INPUT' });
      await refreshData();
    } catch (error) {
      console.error(`Failed to mark ${instance.id} as unread:`, error);
    }
  }, [api, updateInstanceStatus, refreshData]);

  // Filters + group-by, persisted to the same localStorage keys as before so
  // the two sidebars stay in sync. Read post-mount to keep SSR stable.
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(DEFAULT_STATUS_FILTER);
  const [agentFilter, setAgentFilter] = useState<string>('all');
  const [groupBy, setGroupBy] = useState<GroupBy>('time');
  // Split each project group by worktree (desktop-local only). Off by default so
  // the flat project list stays the baseline view.
  const [displayWorktrees, setDisplayWorktrees] = useState(false);
  const worktreesOn = enableWorktrees && displayWorktrees;

  useEffect(() => {
    const savedGroupBy = getPref<GroupBy>(GROUP_BY_STORAGE_KEY);
    if (savedGroupBy) setGroupBy(savedGroupBy);
    const savedAgent = getPref<string>(AGENT_FILTER_STORAGE_KEY);
    if (savedAgent) setAgentFilter(savedAgent);
    const savedOrder = getPref<string[]>(PROJECT_ORDER_STORAGE_KEY);
    if (Array.isArray(savedOrder) && savedOrder.every((k) => typeof k === 'string')) {
      setProjectOrder(savedOrder);
    }
    const savedWorktrees = getPref<boolean>(DISPLAY_WORKTREE_STORAGE_KEY);
    if (typeof savedWorktrees === 'boolean') setDisplayWorktrees(savedWorktrees);
    const filter = getPref<StatusFilter>(STATUS_FILTER_STORAGE_KEY) ?? DEFAULT_STATUS_FILTER;
    setStatusFilter(filter);
    setActiveOnly(filterWantsActiveOnly(filter));
  }, [setActiveOnly]);

  const handleSetGroupBy = useCallback((value: GroupBy) => {
    setGroupBy(value);
    setPref(GROUP_BY_STORAGE_KEY, value);
  }, []);

  const handleSetStatusFilter = useCallback((value: StatusFilter) => {
    setStatusFilter(value);
    setPref(STATUS_FILTER_STORAGE_KEY, value);
    setActiveOnly(filterWantsActiveOnly(value));
  }, [setActiveOnly]);

  const handleSetAgentFilter = useCallback((value: string) => {
    setAgentFilter(value);
    setPref(AGENT_FILTER_STORAGE_KEY, value);
  }, []);

  const handleSetDisplayWorktrees = useCallback((value: boolean) => {
    setDisplayWorktrees(value);
    setPref(DISPLAY_WORKTREE_STORAGE_KEY, value);
  }, []);

  // Agent names present in the loaded list (submenu options).
  const agentNames = useMemo(() => distinctAgentNames(recentInstances), [recentInstances]);

  // The DB projects, by id — the source of truth for a group's name, icon, and
  // archived state (identity-unification §5a/§5b). Refetched when the set of
  // linked project ids changes so an auto-created project's name/icon appears
  // and a just-archived one drops out. Empty until it loads → grouping falls
  // back to the path basename (unchanged legacy behavior).
  const [projectsById, setProjectsById] = useState<Map<string, ProjectResponse>>(
    () => new Map(),
  );
  const linkedProjectIds = useMemo(() => {
    const ids = new Set<string>();
    for (const instance of recentInstances) {
      if (instance.project_id) ids.add(instance.project_id);
    }
    return Array.from(ids).sort().join(',');
  }, [recentInstances]);
  const refreshProjects = useCallback(() => {
    if (!api) return;
    // include_archived so the map carries the archived flag (grouping needs it
    // to drop archived groups); an unknown/loading id defaults to visible.
    api
      .listProjects(true)
      .then((list) => setProjectsById(new Map(list.map((p) => [p.id, p]))))
      .catch(() => {
        /* best-effort: grouping falls back to basenames until it loads */
      });
  }, [api]);
  useEffect(() => {
    refreshProjects();
    // Re-run when a session's project link appears/changes (linkedProjectIds)
    // and when navigating back to a dashboard route (pathname) — so an icon/name
    // edited in /dashboard/settings shows up without a hard refresh. The image
    // <img src> is cache-busted by the project's updated_at, so a refetched row
    // reloads the picture.
  }, [refreshProjects, linkedProjectIds, pathname]);

  // Also refresh when the window/tab regains focus (edited in another tab/window).
  useEffect(() => {
    const onFocus = () => refreshProjects();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [refreshProjects]);

  // Archive a project → it (and its sessions) leave every device's sidebar
  // (§5b). Optimistically drop it locally, then reconcile from the server.
  const handleArchiveProject = useCallback(
    async (projectId: string) => {
      if (!api) return;
      setProjectsById((prev) => {
        const next = new Map(prev);
        const project = next.get(projectId);
        if (project) next.set(projectId, { ...project, is_archived: true });
        return next;
      });
      try {
        await api.updateProject(projectId, { is_archived: true });
      } catch (err) {
        console.error('Failed to archive project:', err);
      } finally {
        refreshProjects();
      }
    },
    [api, refreshProjects],
  );

  // Custom project order (drag-and-drop when grouped by project). Reordered
  // live during dragover, persisted on drag end.
  const [projectOrder, setProjectOrder] = useState<string[]>([]);
  const [draggingProject, setDraggingProject] = useState<string | null>(null);

  // Worktree display is applied in a second pass (renderLayout) with live git
  // data, so grouping itself stays a pure function of the sessions.
  const sidebarGroups = useMemo(
    () => groupSessions(recentInstances, statusFilter, groupBy, agentFilter, projectOrder, projectsById),
    [recentInstances, statusFilter, groupBy, agentFilter, projectOrder, projectsById],
  );

  // Bumped after a worktree is removed so the per-project git views refetch
  // immediately instead of waiting for the next window focus.
  const [gitViewNonce, setGitViewNonce] = useState(0);

  // Per-project git worktree lists + main branch, fetched only when worktree
  // display is on. Empty targets = no RPCs (so web, with worktrees off, never
  // reaches for a daemon it can't talk to).
  const worktreeTargets = useMemo(
    () =>
      // Runs on web too: `git worktree list` goes over the RPC relay to the
      // session's machine (the same path the new-session worktree picker uses),
      // so a worktree with no sessions yet still surfaces. A failed/offline
      // fetch degrades to the session-derived split (the hook catches errors),
      // so this never blocks the sidebar.
      !worktreesOn || groupBy !== 'project'
        ? []
        : sidebarGroups
            .filter((g) => g.key !== 'PINNED' && g.label !== null && g.instances.length > 0)
            .map((g) => ({
              key: g.key,
              machineId: g.instances[0]?.machine_id ?? null,
              listPath: g.instances[0]?.project ?? '',
              mainPath: g.instances.find((i) => !i.worktree_name)?.project ?? null,
            })),
    [sidebarGroups, worktreesOn, groupBy],
  );
  const projectGitViews = useProjectWorktrees(worktreeTargets, gitViewNonce);

  // Right-click "Delete worktree" confirmation. Held null until a deletion needs
  // confirming (a live session or uncommitted changes); a clean, session-free
  // worktree is removed immediately without this dialog.
  const [worktreeDelete, setWorktreeDelete] = useState<{
    machineId: string;
    path: string;
    branch: string;
    sessionIds: string[];
    hasSession: boolean;
    isDirty: boolean;
    busy: boolean;
    error: string | null;
  } | null>(null);

  // The daemon keeps the branch on remove, so commits survive; only the checkout
  // is deleted. Bump the git-view nonce so the removed worktree drops off the
  // list right away.
  const performWorktreeRemove = useCallback(
    async (machineId: string, path: string, force: boolean) => {
      await rpcGitWorktreeRemove(machineId, path, path, force);
      await refreshData();
      setGitViewNonce((n) => n + 1);
    },
    [refreshData],
  );

  const requestWorktreeDelete = useCallback(
    async (target: {
      machineId: string;
      path: string;
      branch: string;
      instances: AgentInstanceResponse[];
    }) => {
      const { machineId, path, branch, instances } = target;
      const sessionIds = instances
        .filter((i) => !CLOSED_STATUSES.has(i.status))
        .map((i) => i.id);
      const hasSession = sessionIds.length > 0;
      let isDirty = false;
      let statusKnown = false;
      try {
        const status = await rpcGitStatus(machineId, path);
        isDirty =
          status.staged.length + status.unstaged.length + status.untracked.length > 0;
        statusKnown = true;
      } catch {
        statusKnown = false;
      }
      if (!hasSession && statusKnown && !isDirty) {
        try {
          await performWorktreeRemove(machineId, path, false);
          return;
        } catch {
          // A race (turned dirty) or a submodule refusal — fall through to the
          // confirm dialog, which surfaces the error rather than failing silently.
        }
      }
      setWorktreeDelete({
        machineId,
        path,
        branch,
        sessionIds,
        hasSession,
        isDirty,
        busy: false,
        error: null,
      });
    },
    [performWorktreeRemove],
  );

  const confirmWorktreeDelete = useCallback(async () => {
    if (!worktreeDelete) return;
    const { machineId, path, sessionIds } = worktreeDelete;
    setWorktreeDelete((prev) => (prev ? { ...prev, busy: true, error: null } : prev));
    try {
      for (const id of sessionIds) {
        await markAsComplete(id);
      }
      await performWorktreeRemove(machineId, path, true);
      setWorktreeDelete(null);
    } catch (e) {
      const error = e instanceof Error ? e.message : 'Failed to delete worktree';
      setWorktreeDelete((prev) => (prev ? { ...prev, busy: false, error } : prev));
    }
  }, [worktreeDelete, performWorktreeRemove, markAsComplete]);

  // Move the dragged project group so it lands at the hovered group's slot.
  const handleProjectDragOver = useCallback((overKey: string) => {
    if (draggingProject === null || draggingProject === overKey) return;
    setProjectOrder((prev) => {
      const rendered = sidebarGroups
        .filter((g) => g.key !== 'PINNED' && g.label !== null)
        .map((g) => g.key);
      const withoutDragged = rendered.filter((k) => k !== draggingProject);
      const overIndex = withoutDragged.indexOf(overKey);
      if (overIndex === -1) return prev;
      const fromIndex = rendered.indexOf(draggingProject);
      const toIndex = rendered.indexOf(overKey);
      const insertAt = fromIndex < toIndex ? overIndex + 1 : overIndex;
      const next = [...withoutDragged];
      next.splice(insertAt, 0, draggingProject);
      return next;
    });
  }, [draggingProject, sidebarGroups]);

  const handleProjectDragEnd = useCallback(() => {
    setDraggingProject(null);
    setProjectOrder((current) => {
      setPref(PROJECT_ORDER_STORAGE_KEY, current);
      return current;
    });
  }, []);

  // Collapsible groups: clicking a group label hides/shows its sessions.
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const toggleGroupCollapsed = useCallback((key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  // Scroll persistence across session navigations (restored after data loads).
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [navigatingId, setNavigatingId] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const openSession = useCallback((instance: AgentInstanceResponse) => {
    if (navigatingId) return;
    if (scrollContainerRef.current) {
      try {
        sessionStorage.setItem('sidebarScrollTop', String(scrollContainerRef.current.scrollTop));
      } catch {
        // sessionStorage unavailable — scroll just won't be restored.
      }
    }
    setNavigatingId(instance.id);
    startTransition(() => {
      router.push(`/dashboard/agents/${instance.id}`);
    });
    // Platform side effect (mark reviewed / auto-review) runs after navigation
    // is scheduled; order doesn't matter for the optimistic status flip.
    onSessionOpened?.(instance);
  }, [navigatingId, router, onSessionOpened]);

  // Clear the navigation spinner once the route lands on the opened session.
  useEffect(() => {
    if (navigatingId && selectedInstanceId === navigatingId) setNavigatingId(null);
  }, [selectedInstanceId, navigatingId]);

  // Restore the saved scroll position ONCE, after the list first loads. Guarded
  // by a ref so subsequent `recentInstances` changes never touch scrollTop:
  // live WS `instance-update` frames replace the array on every status/message
  // tick, pagination appends a page, and refreshData() re-toggles `isLoading` —
  // without this guard each of those would snap the list back to the saved
  // position, reading as a constant auto-scroll-to-top. The sidebar is a
  // persistent App-Router layout, so once restored the DOM keeps its own scroll
  // across session navigations; we only need to seed it on the initial mount.
  const didRestoreScrollRef = useRef(false);
  useEffect(() => {
    if (didRestoreScrollRef.current) return;
    const container = scrollContainerRef.current;
    // Wait for the first page of rows so the saved offset has content to land on.
    if (isLoading || !container || recentInstances.length === 0) return;
    didRestoreScrollRef.current = true;
    try {
      const saved = sessionStorage.getItem('sidebarScrollTop');
      if (saved) container.scrollTop = parseInt(saved, 10);
    } catch {
      // sessionStorage unavailable — nothing to restore.
    }
  }, [isLoading, recentInstances]);

  // Second pass over the pure groups: fold in live git data to build the
  // rendered worktree layout. A project splits only when worktree display is on
  // and git reports ≥1 worktree; otherwise it stays flat.
  const renderLayout = useMemo(
    () =>
      sidebarGroups.map((group) => {
        const { key, label, instances } = group;
        const isDraggableProject =
          groupBy === 'project' && key !== 'PINNED' && label !== null;
        const flatDirectory = isDraggableProject ? instances[0]?.project ?? null : null;
        const notSplit = {
          group,
          isDraggableProject,
          split: false,
          newSessionDirectory: flatDirectory,
          subs: [] as RenderedSubGroup[],
        };

        if (!worktreesOn || groupBy !== 'project' || label === null || key === 'PINNED')
          return notSplit;

        const view = projectGitViews.get(key);
        const gitWorktrees = view
          ? view.worktrees.map((w) => ({ path: w.path, branch: w.branch, managed: w.managed }))
          : null;
        const { mainInstances, worktrees } = splitProjectByWorktree(instances, gitWorktrees);

        // No worktrees → nothing to sub-group: render the project flat rather
        // than a lone "main" bucket. This also stops a non-git folder (whose
        // `git status` yields no branch) from showing a spurious "main" header.
        if (worktrees.length === 0) return notSplit;

        const repoMachineId = instances[0]?.machine_id ?? null;
        const mainDirectory = instances.find((i) => !i.worktree_name)?.project ?? null;
        const subs: RenderedSubGroup[] = [];
        if (mainInstances.length > 0) {
          subs.push({
            key: `${key}::__main__`,
            label: view?.branch ?? 'main',
            instances: mainInstances,
            directory: mainDirectory,
            remove: null,
          });
        }
        for (const w of worktrees) {
          subs.push({
            key: `${key}::wt::${w.branch}`,
            label: w.branch || '(detached)',
            instances: w.instances,
            directory: w.path,
            worktreeBranch: w.branch || undefined,
            // Any real linked worktree is removable (the daemon confines
            // removal to actual worktrees of the repo, not just managed ones);
            // we only need a reachable machine to route the RPC to — so this
            // works on web over the relay, not just desktop. An offline machine
            // just makes the delete RPC reject, surfaced to the user.
            remove: repoMachineId
              ? { machineId: repoMachineId, path: w.path, branch: w.branch }
              : null,
          });
        }
        if (subs.length === 0) return notSplit;
        // Even when split, keep a "+" on the project label; it starts a session
        // in the repo's main checkout (falling back to any session's cwd).
        const splitDirectory = mainDirectory ?? instances[0]?.project ?? null;
        return { group, isDraggableProject, split: true, newSessionDirectory: splitDirectory, subs };
      }),
    [sidebarGroups, worktreesOn, groupBy, projectGitViews],
  );

  // Session-switching shortcuts: ⌘1–⌘9 jump to the nth session in the list
  // (display order, pinned first), ⌘] / ⌘[ move to the session below / above the
  // current one. Order must match the render exactly.
  const flatSessions = useMemo(
    () =>
      renderLayout.flatMap((entry) =>
        entry.split ? entry.subs.flatMap((s) => s.instances) : entry.group.instances,
      ),
    [renderLayout],
  );

  useEffect(() => {
    if (!enableKeyboardShortcuts) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const currentId = pathname?.match(/^\/dashboard\/agents\/([^/]+)$/)?.[1] ?? null;

      // ⌘N — open the new-session page.
      if (matchesShortcut(event, 'session-new')) {
        event.preventDefault();
        router.push('/dashboard/agents/new-session');
        return;
      }

      // Fixed ⌘1–⌘9 (Ctrl+1–9 on Windows/Linux) jump — not rebindable, it's a
      // 9-key range. Match only the OS's primary modifier so a Mac's Ctrl+digit
      // stays free for the terminal.
      const mac = isMacPlatform();
      if (
        (mac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey) &&
        !event.shiftKey &&
        !event.altKey &&
        /^Digit[1-9]$/.test(event.code)
      ) {
        const target = flatSessions[Number(event.code.slice(5)) - 1];
        if (!target) return;
        event.preventDefault();
        if (target.id !== currentId) openSession(target);
        return;
      }

      const direction = matchesShortcut(event, 'session-next')
        ? 1
        : matchesShortcut(event, 'session-prev')
          ? -1
          : 0;
      if (direction === 0 || flatSessions.length === 0) return;
      const currentIndex = currentId ? flatSessions.findIndex((i) => i.id === currentId) : -1;
      const nextIndex = currentIndex === -1
        ? 0
        : Math.min(Math.max(currentIndex + direction, 0), flatSessions.length - 1);
      const target = flatSessions[nextIndex];
      event.preventDefault();
      if (target && target.id !== currentId) openSession(target);
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [enableKeyboardShortcuts, flatSessions, pathname, openSession, router]);

  const handleSessionListScroll = useCallback(() => {
    if (!enableInfiniteScroll) return;
    const container = scrollContainerRef.current;
    if (!container || isLoadingMoreInstances || !hasMoreInstances) return;
    const remaining = container.scrollHeight - container.scrollTop - container.clientHeight;
    if (remaining <= 240) void loadMoreInstances();
  }, [enableInfiniteScroll, hasMoreInstances, isLoadingMoreInstances, loadMoreInstances]);

  // Auto-fill: if the loaded list is shorter than the viewport, keep loading.
  useEffect(() => {
    if (!enableInfiniteScroll || isLoading || isLoadingMoreInstances || !hasMoreInstances) return;
    const container = scrollContainerRef.current;
    if (!container) return;
    if (container.scrollHeight <= container.clientHeight + 120) void loadMoreInstances();
  }, [enableInfiniteScroll, hasMoreInstances, isLoading, isLoadingMoreInstances, loadMoreInstances, recentInstances.length]);

  const renderSession = useCallback((instance: AgentInstanceResponse) => {
    const isSelected = instance.id === selectedInstanceId;
    const isNavigating = navigatingId === instance.id;
    const done = CLOSED_STATUSES.has(instance.status);
    // `status` is self-reported and freezes at ACTIVE when an agent dies, so
    // gate the working spinner on real liveness — otherwise a dead session
    // animates as though it were busy. A just-resumed session reads live for the
    // resume grace so its stopped dot clears immediately.
    const liveState = isWithinResumeGrace(instance.id, livenessNow)
      ? 'live'
      : resolveLiveState(instance, undefined, livenessNow);
    const active = instance.status === 'ACTIVE' && isReachable(liveState);
    const stopped = !isReachable(liveState) && liveState !== 'unknown';
    const unread = instance.status === 'AWAITING_INPUT';
    const pinned = Boolean(instance.pinned_at);
    const title = getSessionTitle(instance);
    const time = formatSidebarTime(instance);
    const resumeReason = resumeBlockedReason(instance, liveState);

    // One config drives both the hover three-dot (SessionActionsMenu) and the
    // right-click context menu below, so the two menus can never list different
    // actions.
    const sessionActionsConfig: SessionActionsConfig = {
      onResume: () => void handleResumeInstance(instance),
      showResume: canResumeSession(instance, liveState),
      resumeDisabledReason:
        resumingId === instance.id
          ? 'Resuming…'
          : resumeReason
            ? resumeBlockedMessage(resumeReason)
            : null,
      resumeBlockedLabel:
        resumingId === instance.id
          ? 'Resuming…'
          : resumeReason
            ? resumeBlockedShortLabel(resumeReason)
            : null,
      onPin: () => void handleTogglePin(instance),
      isPinned: pinned,
      onRename: () =>
        setRenameDialog({ open: true, sessionId: instance.id, currentName: instance.name ?? title }),
      onCopyId: () => void copySessionId(instance.id, instance.id),
      copied: copiedSessionId === instance.id,
      onMarkDone: instance.status !== 'COMPLETED' ? () => void handleArchive(instance) : undefined,
      showMarkDone: instance.status !== 'COMPLETED',
      onUnread: instance.status === 'REVIEWED' ? () => void handleUnread(instance) : undefined,
      showUnread: instance.status === 'REVIEWED',
      onDelete: () =>
        setDeleteDialog({ open: true, sessionId: instance.id, sessionName: title }),
    };
    const contextMenuActions = buildSessionActions(sessionActionsConfig);

    return (
      // Wrapper hosts the hover-actions as an absolute sibling of the Button so
      // clicking an action never propagates into the row's navigate onClick.
      // Right-click opens the session-actions context menu.
      <ContextMenu key={instance.id}>
        <ContextMenuTrigger asChild>
      <div className="group/session relative">
        <Button
          variant="subtle"
          className={cn(
            'w-full justify-start h-auto px-2 py-1.5 text-left',
            isSelected && ITEM_SELECTED,
            done && 'opacity-50',
          )}
          onClick={() => openSession(instance)}
          disabled={isNavigating}
        >
          <div className="flex items-center justify-between gap-1 w-full min-w-0">
            <span className="flex items-center gap-1 min-w-0 truncate">
              {isNavigating ? (
                <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" />
              ) : active ? (
                <SnakeLoader size={13} />
              ) : (
                <span className="relative flex-shrink-0 flex items-center">
                  <AgentTypeIcon
                    agentTypeName={instance.agent_type_name ?? null}
                    whiteForOpenAI
                  />
                  {stopped && !done && (
                    <span
                      className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full bg-muted-foreground/50 ring-1 ring-background"
                      aria-label={liveStateLabel(liveState) ?? undefined}
                      title={liveStateHint(liveState) ?? undefined}
                    />
                  )}
                </span>
              )}
              {/* One weight for every state; awaiting-input and reviewed share
                  the same color so only the blue dot distinguishes them. */}
              <span
                className={cn(
                  'text-xs truncate font-normal',
                  done
                    ? 'text-muted-foreground/60'
                    : unread || instance.status === 'REVIEWED'
                      ? 'text-foreground'
                      : 'text-foreground/80',
                )}
              >
                {title}
              </span>
            </span>
            {/* Right slot: awaiting-input blue dot, else the time. Reserves room
                for the two hover actions and fades out on hover so they take
                over the same space without covering the title. */}
            <span className="flex-shrink-0 pl-2 min-w-[3rem] flex items-center justify-end transition-opacity group-hover/session:opacity-0">
              {unread ? (
                <span
                  className="h-2 w-2 rounded-full bg-sky-400"
                  aria-label="Awaiting input"
                  title="Awaiting input"
                />
              ) : (
                <span className="text-[10px] text-muted-foreground">{time}</span>
              )}
            </span>
          </div>
        </Button>

        {/* Hover actions: archive + a three-dot menu (same actions as the
            right-click menu). stopPropagation/preventDefault keep the clicks
            from navigating into the session. */}
        <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5 opacity-0 transition-opacity group-hover/session:opacity-100">
          {instance.status !== 'COMPLETED' && (
            <button
              type="button"
              title="Archive"
              aria-label="Archive session"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                void handleArchive(instance);
              }}
              className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground"
            >
              <Archive className="h-3 w-3" />
            </button>
          )}
          <div onClick={(e) => e.stopPropagation()}>
            <SessionActionsMenu {...sessionActionsConfig} className="h-5 w-5 p-0" />
          </div>
        </div>
      </div>
        </ContextMenuTrigger>
        <ContextMenuContent className="font-mono">
          {contextMenuActions.map((action) => (
            <ContextMenuItem
              key={action.key}
              className="text-xs"
              disabled={action.disabled}
              title={action.title}
              onSelect={action.onSelect}
            >
              <SessionActionItemContent action={action} />
            </ContextMenuItem>
          ))}
        </ContextMenuContent>
      </ContextMenu>
    );
  }, [
    selectedInstanceId,
    navigatingId,
    openSession,
    handleTogglePin,
    handleArchive,
    handleUnread,
    handleResumeInstance,
    copySessionId,
    copiedSessionId,
    resumingId,
    livenessNow,
  ]);

  return (
    <>
      <div className="flex-1 flex flex-col min-h-0">
        <div className="pl-4 pr-1.5 pt-1 pb-1 flex items-center justify-between">
          <span className="text-xs font-light text-muted-foreground/70">
            Workspaces
          </span>
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              title="Kanban"
              aria-label="Kanban"
              onClick={() => router.push('/dashboard/kanban')}
              className={cn(
                'flex h-6 w-6 cursor-pointer items-center justify-center rounded-md text-muted-foreground/70 transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground',
                pathname === '/dashboard/kanban' && ITEM_SELECTED,
              )}
            >
              <Kanban className="h-3.5 w-3.5" />
            </button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  title="View options"
                  aria-label="View options"
                  className="flex h-6 w-6 cursor-pointer items-center justify-center rounded-md text-muted-foreground/70 transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground"
                >
                  <ListFilter className="h-3.5 w-3.5" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="w-48 border-menu-border bg-menu-elevated font-mono text-[11px]"
              >
                {/* Nested filter menu: each row is a dimension with its current
                    value; the options live in a submenu. Single-choice picks
                    close the menu; the Project multi-select stays open. */}
                <FilterSubRow
                  label="Group by"
                  value={GROUP_BY_OPTIONS.find((o) => o.value === groupBy)?.label ?? 'Time'}
                >
                  {GROUP_BY_OPTIONS.map(({ value, label }) => (
                    <FilterOptionItem
                      key={value}
                      label={label}
                      selected={groupBy === value}
                      onSelect={() => handleSetGroupBy(value)}
                    />
                  ))}
                </FilterSubRow>
                {/* Worktree is a sub-dimension of project and desktop-only, so
                    the row only appears where it does anything. */}
                {enableWorktrees && groupBy === 'project' && (
                  <FilterSubRow label="Display" value={displayWorktrees ? 'Worktree' : 'Off'}>
                    <FilterOptionItem
                      label="Worktree"
                      selected={displayWorktrees}
                      onSelect={() => handleSetDisplayWorktrees(!displayWorktrees)}
                    />
                  </FilterSubRow>
                )}
                <DropdownMenuSeparator />
                <FilterSubRow
                  label="Status"
                  value={STATUS_FILTER_OPTIONS.find((o) => o.value === statusFilter)?.label ?? 'All'}
                >
                  {STATUS_FILTER_OPTIONS.map(({ value, label }) => (
                    <FilterOptionItem
                      key={value}
                      label={label}
                      selected={statusFilter === value}
                      onSelect={() => handleSetStatusFilter(value)}
                    />
                  ))}
                </FilterSubRow>
                <FilterSubRow label="Agent" value={agentFilter === 'all' ? 'All' : agentFilter}>
                  <FilterOptionItem
                    label="All"
                    selected={agentFilter === 'all'}
                    onSelect={() => handleSetAgentFilter('all')}
                  />
                  {agentNames.map((name) => (
                    <FilterOptionItem
                      key={name}
                      label={name}
                      selected={agentFilter === name}
                      onSelect={() => handleSetAgentFilter(name)}
                    />
                  ))}
                </FilterSubRow>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <div
          ref={scrollContainerRef}
          className="flex-1 overflow-y-auto pl-2 pr-0.5 custom-scrollbar"
          onScroll={enableInfiniteScroll ? handleSessionListScroll : undefined}
        >
          {isLoading && recentInstances.length === 0 ? (
            <div className="px-2 py-4 space-y-3 animate-pulse">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={`session-skeleton-${index}`} className="rounded-md bg-muted/20 p-2">
                  <div className="space-y-2">
                    <div className="h-3 w-9/10 rounded-full bg-muted-foreground/15" />
                    <div className="h-3 w-6/10 rounded-full bg-muted-foreground/10" />
                  </div>
                </div>
              ))}
            </div>
          ) : recentInstances.length === 0 ? (
            <div className="px-2 py-4 text-sm text-muted-foreground text-center">
              No sessions yet
            </div>
          ) : (
            <div className="space-y-1 pb-2">
              {renderLayout.map((entry) => {
                const { key, label, instances } = entry.group;
                const { isDraggableProject, split, newSessionDirectory, subs } = entry;
                if (!split && instances.length === 0) return null;
                const isGroupCollapsed = label !== null && collapsedGroups.has(key);
                const projectMachineId = instances[0]?.machine_id ?? null;
                // The DB project this group maps to (only meaningful when
                // grouping by project — time/status keys aren't project ids).
                // Drives the leading icon, the Archive action, and the settings
                // link's project identity.
                const dbProject = groupBy === 'project' ? projectsById.get(key) : undefined;
                const canArchiveProject =
                  dbProject !== undefined && !dbProject.is_inbox && !dbProject.is_archived;
                // "Project settings" opens the per-project pane in Settings:
                // Display (name/icon) keys off project_id; the worktree-config
                // section needs a machine + repo dir to route its daemon RPC.
                const projectSettingsHref = (() => {
                  if (!dbProject && !(projectMachineId && newSessionDirectory)) return null;
                  const params = new URLSearchParams({ tab: 'project' });
                  if (dbProject) params.set('projectId', dbProject.id);
                  if (projectMachineId) params.set('machineId', projectMachineId);
                  if (newSessionDirectory) params.set('dir', newSessionDirectory);
                  if (label) params.set('label', label);
                  return `/dashboard/settings?${params.toString()}`;
                })();
                const projectHeader = label ? (
                  // Wrapper carries the drag handle and hover group so the
                  // collapse toggle, actions menu, and "+" can be sibling buttons
                  // (a button cannot nest inside a button).
                  <div
                    draggable={isDraggableProject}
                    onDragStart={
                      isDraggableProject
                        ? (event) => {
                            event.dataTransfer.effectAllowed = 'move';
                            event.dataTransfer.setData('text/plain', key);
                            setDraggingProject(key);
                          }
                        : undefined
                    }
                    onDragEnd={isDraggableProject ? handleProjectDragEnd : undefined}
                    className={cn(
                      'group/label flex w-full items-center gap-1 px-2 py-1 mt-2 first:mt-0',
                      isDraggableProject && 'cursor-grab active:cursor-grabbing',
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => toggleGroupCollapsed(key)}
                      aria-expanded={!isGroupCollapsed}
                      className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                    >
                      {/* Project groups show the DB project's icon/image/emoji
                          (or a generated square from the name); time/status
                          groups have no project identity, so no icon (§5a). */}
                      {groupBy === 'project' && (
                        <ProjectIcon
                          project={dbProject ?? { id: key, name: label, is_inbox: false }}
                          className="size-4"
                        />
                      )}
                      <span className="truncate text-[0.8rem] font-normal text-muted-foreground">
                        {label}
                      </span>
                      <ChevronRight
                        className={cn(
                          'h-3 w-3 shrink-0 text-muted-foreground/50 transition-transform group-hover/label:text-muted-foreground',
                          !isGroupCollapsed && 'rotate-90',
                        )}
                      />
                    </button>
                    {(projectSettingsHref || canArchiveProject) && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            title="Project actions"
                            aria-label="Project actions"
                            className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground opacity-0 transition-opacity hover:bg-muted-foreground/20 hover:text-foreground group-hover/label:opacity-100 focus:opacity-100"
                          >
                            <MoreHorizontal className="h-3 w-3" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="font-mono">
                          {projectSettingsHref && (
                            <DropdownMenuItem
                              className="cursor-pointer gap-2 text-xs"
                              onSelect={() => router.push(projectSettingsHref)}
                            >
                              <Settings className="h-3.5 w-3.5" />
                              Project settings
                            </DropdownMenuItem>
                          )}
                          {canArchiveProject && dbProject && (
                            <DropdownMenuItem
                              className="cursor-pointer gap-2 text-xs"
                              onSelect={() => void handleArchiveProject(dbProject.id)}
                            >
                              <Archive className="h-3.5 w-3.5" />
                              Archive project
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                    {newSessionDirectory && (
                      <NewSessionButton
                        directory={newSessionDirectory}
                        label={label}
                        onNavigate={router.push}
                      />
                    )}
                  </div>
                ) : null;
                return (
                  <div
                    key={key}
                    className={cn('mb-1', draggingProject === key && 'opacity-50')}
                    onDragOver={
                      isDraggableProject && draggingProject !== null
                        ? (event) => {
                            event.preventDefault();
                            handleProjectDragOver(key);
                          }
                        : undefined
                    }
                    onDrop={
                      isDraggableProject && draggingProject !== null
                        ? (event) => event.preventDefault()
                        : undefined
                    }
                  >
                    {projectHeader &&
                      (projectSettingsHref ? (
                        <ContextMenu>
                          <ContextMenuTrigger asChild>{projectHeader}</ContextMenuTrigger>
                          <ContextMenuContent className="font-mono">
                            <ContextMenuItem
                              className="cursor-pointer gap-2 text-xs"
                              onSelect={() => router.push(projectSettingsHref)}
                            >
                              <Settings className="h-3.5 w-3.5" />
                              Project settings
                            </ContextMenuItem>
                          </ContextMenuContent>
                        </ContextMenu>
                      ) : (
                        projectHeader
                      ))}
                    {!isGroupCollapsed && (
                      // Indent sessions a step in from their group header so they
                      // read as children, not siblings — matching the worktree
                      // split's pl-2, whether or not worktree display is on.
                      <div className={cn('space-y-0.5', !split && 'pl-2')}>
                        {!split
                          ? instances.map(renderSession)
                          : subs.map((rsub) => {
                              const isSubCollapsed = collapsedGroups.has(rsub.key);
                              const remove = rsub.remove;
                              return (
                                <div key={rsub.key}>
                                  <WorktreeSubGroupHeader
                                    label={rsub.label}
                                    collapsed={isSubCollapsed}
                                    onToggleCollapsed={() => toggleGroupCollapsed(rsub.key)}
                                    newSessionDirectory={rsub.directory}
                                    worktreeBranch={rsub.worktreeBranch}
                                    onNavigate={router.push}
                                    onRequestDelete={
                                      remove
                                        ? () =>
                                            void requestWorktreeDelete({
                                              ...remove,
                                              instances: rsub.instances,
                                            })
                                        : undefined
                                    }
                                  />
                                  {!isSubCollapsed && rsub.instances.length > 0 && (
                                    <div className="space-y-0.5 pl-2">
                                      {rsub.instances.map(renderSession)}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                      </div>
                    )}
                  </div>
                );
              })}
              {enableInfiniteScroll && isLoadingMoreInstances ? (
                <div className="flex items-center justify-center py-3 text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {/* Context-menu confirmations (shared dialogs). */}
      <RenameSessionDialog
        open={renameDialog.open}
        onOpenChange={(open) => setRenameDialog((prev) => ({ ...prev, open }))}
        sessionId={renameDialog.sessionId}
        currentName={renameDialog.currentName}
        onRename={(id, name) => void renameSession(id, name)}
      />
      <DeleteSessionDialog
        open={deleteDialog.open}
        onOpenChange={(open) => setDeleteDialog((prev) => ({ ...prev, open }))}
        sessionId={deleteDialog.sessionId}
        sessionName={deleteDialog.sessionName}
        onDelete={(id) => void handleDelete(id)}
      />
      {enableWorktrees && (
        <WorktreeDeleteDialog
          open={worktreeDelete !== null}
          onOpenChange={(open) => {
            if (!open) setWorktreeDelete(null);
          }}
          branch={worktreeDelete?.branch ?? ''}
          hasSession={worktreeDelete?.hasSession ?? false}
          isDirty={worktreeDelete?.isDirty ?? false}
          busy={worktreeDelete?.busy ?? false}
          error={worktreeDelete?.error ?? null}
          onConfirm={() => void confirmWorktreeDelete()}
        />
      )}
    </>
  );
}

/** One dimension row in the filter menu: label left, current value right,
    options in a submenu (the built-in SubTrigger chevron closes the row). */
function FilterSubRow({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <DropdownMenuSub>
      {/* Label takes the slack (flex-1) so the value hugs the built-in chevron
          at the right edge instead of floating mid-row. */}
      <DropdownMenuSubTrigger className="gap-2 py-1.5 text-[11px]">
        <span className="flex-1 text-foreground/90">{label}</span>
        <span className="max-w-24 truncate font-normal text-muted-foreground">{value}</span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-40 border-menu-border bg-menu-elevated font-mono text-[11px]">
        {children}
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

/** A submenu option: check on the right; selecting closes the menu unless
    `keepOpen` (multi-select rows like the Project visibility toggles). */
function FilterOptionItem({
  label,
  selected,
  onSelect,
  keepOpen = false,
}: {
  label: string;
  selected: boolean;
  onSelect: () => void;
  keepOpen?: boolean;
}) {
  return (
    <DropdownMenuItem
      className={cn('gap-2 py-1 text-[11px]', selected && ITEM_SELECTED)}
      onSelect={(event) => {
        if (keepOpen) event.preventDefault();
        onSelect();
      }}
    >
      <span className="truncate">{label}</span>
      <span className="ml-auto w-3 flex-shrink-0">
        {selected && <Check className="h-3 w-3" />}
      </span>
    </DropdownMenuItem>
  );
}
