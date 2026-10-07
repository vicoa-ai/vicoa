'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CalendarClock, Check, ListFilter, Plus, Repeat } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { isMachineOnline, sortMachinesOnlineFirst } from '@/lib/session-liveness';
import { getWsClient, RpcError } from '@/lib/ws-client';
import {
  AGENT_CATALOG_FALLBACK,
  toSpawnMetadata,
  type AgentCatalog,
  type SessionConfig,
} from '@/lib/agent-catalog';
import { useAgentProfiles } from '@/lib/use-agent-profiles';
import { useProjects } from '@/lib/use-projects';
import { resolveWorktreeSpawn } from '@/lib/worktree-selection';
import type {
  AutomationResponse,
  MachineSummary,
  ProjectResponse,
} from '@/lib/backend-api';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { DesktopCollapsedLead } from '@/components/desktop/window-chrome';
import { AutomationList, type AutomationFilter } from './components/automation-list';
import { AutomationListSkeleton } from './components/automation-skeleton';
import { AutomationEmptyState } from './components/empty-state';
import { getAutomationCache, setAutomationCache } from './lib/automation-cache';
import { DetailPanel } from './components/detail-panel';
import { SharedDetailPanel } from './components/shared-detail-panel';
import type { AutomationTemplate } from './lib/templates';
import { NO_PROJECT } from './lib/group-by-project';
import { reorderRows } from './lib/order';

type Selection = AutomationResponse | 'new' | null;

/** Someone else's automation, reaching the viewer through a shared project. */
function isShared(a: AutomationResponse): boolean {
  return a.owner != null;
}

/** Replace a row in place, or put a new one on top. */
function upsert(rows: AutomationResponse[], row: AutomationResponse): AutomationResponse[] {
  return rows.some((a) => a.id === row.id)
    ? rows.map((a) => (a.id === row.id ? row : a))
    : [row, ...rows];
}

/** Projects whose automations the viewer may list: their own, team-owned, or
 *  shared with a grant that covers automations. */
function canListAutomations(p: ProjectResponse): boolean {
  return !p.is_archived && !p.is_inbox && (p.scopes ?? []).includes('automations');
}

// Machine liveness (the "Runs on" online dot) is derived from `last_heartbeat_at`
// vs. the wall clock, so a one-shot fetch goes stale and flips a live machine to
// "offline" after the ~90s threshold. Re-poll the list on this cadence to keep
// the heartbeat fresh. Matches the new-session page.
const MACHINE_REFRESH_INTERVAL_MS = 30_000;

const FILTER_LABELS: Record<AutomationFilter, string> = {
  all: 'All',
  active: 'Active',
  paused: 'Paused',
};

// useSearchParams needs a Suspense boundary for prerender (same pattern as
// sessions/new/page.tsx).
export default function AutomationPage() {
  return (
    <Suspense fallback={null}>
      <AutomationPageInner />
    </Suspense>
  );
}

function AutomationPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { api } = useAgentDashboard();
  const { profiles: agentProfiles } = useAgentProfiles();

  // Seed from the in-memory cache (lib/automation-cache.ts) so revisiting the
  // tab paints the last-loaded list instantly; a cold visit starts empty +
  // loading and shows the skeleton. Both cases revalidate on mount.
  const [automations, setAutomations] = useState<AutomationResponse[]>(
    () => getAutomationCache()?.automations ?? [],
  );
  const [machines, setMachines] = useState<MachineSummary[]>(
    () => getAutomationCache()?.machines ?? [],
  );
  // `automations` is everything you can see: all of yours, plus your
  // collaborators' (read-only) in projects shared with you. The project
  // picker narrows it: null = "All automations", grouped by project; a
  // project id = that project's alone; NO_PROJECT = yours filed nowhere.
  // Archived projects are left out.
  const { projects: allProjects } = useProjects();
  const projects = useMemo(
    () => (allProjects ?? []).filter((p) => !p.is_archived),
    [allProjects],
  );
  const [projectFilter, setProjectFilter] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<AgentCatalog>(
    () => getAutomationCache()?.catalog ?? AGENT_CATALOG_FALLBACK,
  );
  const [isLoading, setIsLoading] = useState(() => getAutomationCache() === null);
  const [error, setError] = useState<string | null>(null);
  // True only when this mount started with no cache — a background revalidate
  // over already-painted cached rows must not raise a blocking error.
  const coldStartRef = useRef(getAutomationCache() === null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [historyKey, setHistoryKey] = useState(0);
  const [filter, setFilter] = useState<AutomationFilter>('all');
  const [deleteTarget, setDeleteTarget] = useState<AutomationResponse | null>(null);
  // Template to seed create mode; null = start from scratch.
  const [newTemplate, setNewTemplate] = useState<AutomationTemplate | null>(null);

  const openCreate = useCallback((template: AutomationTemplate | null = null) => {
    setNewTemplate(template);
    setSelection('new');
  }, []);

  // The drag-order save in flight, if any: a refetch waits for it, or it could
  // land before the save and snap the list back to the old order.
  const orderSaveRef = useRef<Promise<unknown> | null>(null);

  const refresh = useCallback(async () => {
    if (!api) return;
    await orderSaveRef.current;
    const [automationList, machineList] = await Promise.all([
      api.listAutomations({ scope: 'all' }),
      api.listMachines(),
    ]);
    setAutomations(automationList);
    setMachines(sortMachinesOnlineFirst(machineList));
    return automationList;
  }, [api]);

  // Keep only the machine list warm so the "Runs on" online dot stays accurate
  // (heartbeats decay against the wall clock). Silent: failures keep the
  // last-known machines rather than surfacing an error over good data.
  const silentRefreshMachines = useCallback(async () => {
    if (!api) return;
    try {
      const machineList = await api.listMachines();
      setMachines(sortMachinesOnlineFirst(machineList));
    } catch {
      /* ignore */
    }
  }, [api]);

  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    (async () => {
      try {
        // `isLoading` already reflects cache presence (skeleton only on a cold
        // visit); this pass just revalidates without flipping back to loading.
        setError(null);
        await refresh();
        api
          .getAgentCatalog()
          .then((fresh) => !cancelled && setCatalog(fresh))
          .catch(() => {});
      } catch (err) {
        // Only surface the load error on a cold start; over cached rows the
        // error banner would flash despite good data still being on screen.
        if (!cancelled && coldStartRef.current) {
          setError(err instanceof Error ? err.message : 'Failed to load automations');
        } else if (!cancelled) {
          console.error('Failed to revalidate automations:', err);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, refresh]);

  // Poll the machine list so liveness stays fresh while the tab is open.
  useEffect(() => {
    if (!api) return;
    const id = setInterval(silentRefreshMachines, MACHINE_REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [api, silentRefreshMachines]);

  // Deep link from the ⌘K palette: /dashboard/automation?automation={id}
  // opens that automation's detail panel once its row is available (cached
  // rows immediately, else after the fetch lands), then strips the param so
  // refresh/back doesn't reopen it. An unknown id leaves the list as-is.
  useEffect(() => {
    const automationId = searchParams?.get('automation');
    if (!automationId) return;
    if (automationId === 'new') {
      // The task→automation "Repeat…" deep link is handled by its own effect
      // below, which needs an async task fetch; skip the blank-create here.
      if (searchParams?.get('taskId')) return;
      openCreate();
      router.replace('/dashboard/automation', { scroll: false });
      return;
    }
    const target = automations.find((a) => a.id === automationId);
    if (target) {
      setSelection(target);
      router.replace('/dashboard/automation', { scroll: false });
      return;
    }
    // Not in the loaded list (cached rows from before it existed, say):
    // fetch it rather than ignore the link.
    if (!api || isLoading) return;
    router.replace('/dashboard/automation', { scroll: false });
    api
      .getAutomation(automationId)
      .then(setSelection)
      .catch(() => {});
  }, [api, isLoading, searchParams, automations, router, openCreate]);

  // `?project={id}` opens the list on one project (the sidebar's project
  // menu links here), then strips the param like the deep link above.
  useEffect(() => {
    const projectId = searchParams?.get('project');
    if (!projectId) return;
    setProjectFilter(projectId);
    router.replace('/dashboard/automation', { scroll: false });
  }, [searchParams, router]);

  // "Repeat…" from a task: /dashboard/automation?automation=new&taskId={id}.
  // Fetch the task, seed the create form's title + prompt from it, and resolve
  // the machine/directory from the task's linked project (preferring an online
  // machine). Waits for the machine list so directory resolution can pick a
  // live one; consumed once so the stripped URL / re-render can't reopen it.
  const consumedTaskRef = useRef<string | null>(null);
  useEffect(() => {
    if (!api || machines.length === 0) return;
    if (searchParams?.get('automation') !== 'new') return;
    const taskId = searchParams?.get('taskId');
    if (!taskId || consumedTaskRef.current === taskId) return;
    consumedTaskRef.current = taskId;

    (async () => {
      try {
        const [task, projects] = await Promise.all([
          api.getTask(taskId),
          api.listProjects(),
        ]);
        const links = projects.find((p) => p.id === task.project_id)?.directories ?? [];
        const link =
          links.find((d) =>
            machines.some((m) => m.machine_id === d.machine_id && isMachineOnline(m)),
          ) ?? links[0];
        const prompt = [task.title, task.description?.trim()].filter(Boolean).join('\n\n');
        openCreate({
          id: `task-${task.id}`,
          icon: Repeat,
          title: task.title,
          description: task.description ?? '',
          prompt,
          machineId: link?.machine_id ?? undefined,
          directory: link?.local_path ?? undefined,
        });
      } catch {
        // The task fetch failed — still open a blank create so the click isn't
        // a dead end.
        openCreate();
      } finally {
        router.replace('/dashboard/automation', { scroll: false });
      }
    })();
  }, [api, machines, searchParams, router, openCreate]);

  // Keep the in-memory cache warm from the current rows — seeds the next visit.
  // Gated on !isLoading so the pre-load empty state is never cached; every
  // mutation flows through the setters below, so this stays current without
  // touching each handler.
  useEffect(() => {
    if (isLoading) return;
    setAutomationCache({ automations, machines, catalog });
  }, [isLoading, automations, machines, catalog]);

  const handleSaved = useCallback((saved: AutomationResponse) => {
    setAutomations((prev) => upsert(prev, saved));
    setSelection(saved);
  }, []);

  const togglePause = useCallback(
    async (a: AutomationResponse) => {
      if (!api) return;
      const next = !a.enabled;
      const optimistic = { ...a, enabled: next };
      setAutomations((prev) => prev.map((x) => (x.id === a.id ? optimistic : x)));
      setSelection((sel) =>
        sel !== 'new' && sel?.id === a.id ? optimistic : sel,
      );
      try {
        const updated = await api.updateAutomation(a.id, { enabled: next });
        setAutomations((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
        setSelection((sel) => (sel !== 'new' && sel?.id === updated.id ? updated : sel));
      } catch (err) {
        console.error('Failed to toggle automation:', err);
        void refresh();
      }
    },
    [api, refresh],
  );

  // Drag-to-reorder: `rendered` is one group's on-screen rows in their new
  // order. Move them now, then save the whole order (it is the viewer's own,
  // so a collaborator's rows move too). On failure refetch rather than guess.
  const reorder = useCallback(
    (rendered: string[]) => {
      if (!api) return;
      const next = reorderRows(automations, rendered);
      setAutomations(next);
      const save = api
        .setAutomationOrder(next.map((a) => a.id))
        .catch((err) => {
          console.error('Failed to save automation order:', err);
          orderSaveRef.current = null;
          void refresh();
        })
        .finally(() => {
          if (orderSaveRef.current === save) orderSaveRef.current = null;
        });
      orderSaveRef.current = save;
    },
    [api, automations, refresh],
  );

  const deleteAutomation = useCallback(
    async (a: AutomationResponse) => {
      if (!api) return;
      const before = automations;
      setAutomations((prev) => prev.filter((x) => x.id !== a.id));
      setSelection((sel) => (sel !== 'new' && sel?.id === a.id ? null : sel));
      try {
        await api.deleteAutomation(a.id);
      } catch (err) {
        console.error('Failed to delete automation:', err);
        setAutomations(before);
      }
    },
    [api, automations],
  );

  // "Run now" reuses the new-session spawn path (rpc_router is server-process
  // local), then records the outcome so it shows in Run history.
  const runNow = useCallback(
    async (a: AutomationResponse) => {
      // Only the author's own rows carry a machine; a shared row never runs.
      const machineId = a.machine_id;
      if (!api || !machineId) return;
      setBusyId(a.id);
      setError(null);
      // Open this automation's panel (if not already) so the run surfaces in
      // its Run history.
      setSelection((sel) => (sel !== 'new' && sel?.id === a.id ? sel : a));
      // A linked automation runs its saved agent as it is now, the same as a
      // scheduled fire: the agent's current config, and its id, from which the
      // server adds the agent's instructions and stamps the session as that
      // agent. The stored snapshot is only the fallback (agent not loaded here,
      // or archived — the server then ignores the id too).
      const profile = a.agent_profile_id
        ? agentProfiles.find((p) => p.id === a.agent_profile_id && !p.is_archived)
        : undefined;
      const config = profile
        ? ({ ...profile.config, agent: profile.agent } as unknown as SessionConfig)
        : (a.session_config as unknown as SessionConfig);
      const spawn = resolveWorktreeSpawn({
        mode: a.worktree?.mode ?? 'none',
        baseDirectory: a.directory,
        selectedWorktreePath: a.worktree?.path,
      });
      try {
        const result = await getWsClient().callRpc(machineId, 'spawn-session', {
          directory: spawn.directory,
          agent: config.agent,
          metadata: toSpawnMetadata(config, a.prompt),
          ...(spawn.worktree ? { worktree: spawn.worktree } : {}),
          ...(a.agent_profile_id ? { agent_profile_id: a.agent_profile_id } : {}),
        });
        if (result.error) {
          await api
            .recordAutomationRun(a.id, { status: 'failed', detail: String(result.error) })
            .catch(() => {});
          setError(String(result.error));
          setHistoryKey((k) => k + 1);
          void refresh();
          return;
        }
        const instanceId = String(result.agent_instance_id ?? '');
        // The spawn RPC returns before the agent self-registers, so its
        // agent_instances row may not exist yet. Wait (bounded) for it to
        // appear so the backend's record_run can link the run — otherwise it
        // drops the link and the Run history row has no ↗ session to open.
        // Mirrors the scheduler's _await_instance.
        let linkedId: string | null = null;
        if (instanceId) {
          const deadline = Date.now() + 8000;
          while (Date.now() < deadline) {
            try {
              await api.getInstanceDetail(instanceId);
              linkedId = instanceId;
              break;
            } catch {
              await new Promise((r) => setTimeout(r, 500));
            }
          }
        }
        await api
          .recordAutomationRun(a.id, {
            status: 'fired',
            agent_instance_id: linkedId,
          })
          .catch(() => {});
        setHistoryKey((k) => k + 1);
        void refresh();
      } catch (err) {
        const code = err instanceof RpcError ? err.code : 'error';
        const offline = code === 'no_handler' || code === 'not_connected';
        await api
          .recordAutomationRun(a.id, {
            status: offline ? 'missed_offline' : 'failed',
            detail: code,
          })
          .catch(() => {});
        setError(offline ? 'Machine is offline — run could not start.' : `Run failed: ${code}`);
        setHistoryKey((k) => k + 1);
        void refresh();
      } finally {
        setBusyId(null);
      }
    },
    [api, refresh, agentProfiles],
  );

  const selectedId = selection && selection !== 'new' ? selection.id : null;
  const panelOpen = selection !== null;

  const pickableProjects = projects.filter(canListAutomations);
  const pickedProject =
    projectFilter && projectFilter !== NO_PROJECT
      ? (projects.find((p) => p.id === projectFilter) ?? null)
      : null;
  const rows =
    projectFilter === null
      ? automations
      : automations.filter((a) => (a.project_id ?? NO_PROJECT) === projectFilter);
  const pickerLabel =
    projectFilter === null
      ? 'All automations'
      : projectFilter === NO_PROJECT
        ? 'No project'
        : (pickedProject?.name ?? 'Project');

  // "New automation" with a project picked starts in that project's folder on
  // one of your machines (an online one first), when you have it checked out.
  const createHere = useCallback(() => {
    const links = (pickedProject?.directories ?? []).filter((d) =>
      machines.some((m) => m.machine_id === d.machine_id),
    );
    const link =
      links.find((d) =>
        machines.some((m) => m.machine_id === d.machine_id && isMachineOnline(m)),
      ) ?? links[0];
    if (!pickedProject || !link) {
      openCreate();
      return;
    }
    openCreate({
      id: `project-${pickedProject.id}`,
      icon: CalendarClock,
      title: '',
      description: '',
      prompt: '',
      machineId: link.machine_id,
      directory: link.local_path,
    });
  }, [machines, openCreate, pickedProject]);

  // Draggable divider between the list and the detail panel. Only meaningful
  // while the panel is open; persisted so the split survives navigation.
  const [listWidth, setListWidth] = useState(380);
  const listWidthRef = useRef(listWidth);
  listWidthRef.current = listWidth;

  useEffect(() => {
    const saved = Number(window.localStorage.getItem('automation:listWidth'));
    if (saved >= 280 && saved <= 720) setListWidth(saved);
  }, []);

  const startDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = listWidthRef.current;
    let latest = startW;
    const onMove = (ev: MouseEvent) => {
      latest = Math.max(280, Math.min(720, startW + (ev.clientX - startX)));
      setListWidth(latest);
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      try {
        window.localStorage.setItem('automation:listWidth', String(Math.round(latest)));
      } catch {
        /* ignore */
      }
    };
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, []);

  return (
    <main className="flex h-full overflow-hidden">
      {/* List column — full width until an automation/panel is open. A size
          container: its width is the user's divider drag, not the window's, so
          the header below adapts to it with container queries. */}
      <div
        className="@container flex min-w-0 shrink-0 flex-col"
        style={panelOpen ? { width: listWidth } : { flex: 1 }}
      >
        {/* On desktop this header is the window titlebar: a drag region with the
            controls opting back out via NO_DRAG (and the collapsed-sidebar lead
            clearing the macOS traffic lights). As the column narrows, labels
            give way to icons and the title truncates; `overflow-hidden` is the
            backstop that keeps it from ever painting into the detail panel. */}
        <div
          style={DRAG_REGION}
          className="flex h-11 shrink-0 items-center gap-2 overflow-hidden border-b border-border px-4"
        >
          <DesktopCollapsedLead />
          <CalendarClock className="h-4 w-4 shrink-0 text-muted-foreground" />
          <h1 className="min-w-0 truncate text-sm font-medium">Automations</h1>
          <div style={NO_DRAG} className="ml-auto flex min-w-0 items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 min-w-0 max-w-[220px] cursor-pointer gap-1.5 text-xs"
                  title={pickerLabel}
                  aria-label={pickerLabel}
                >
                  {projectFilter === null ? (
                    <CalendarClock className="size-3.5 shrink-0 text-muted-foreground" />
                  ) : (
                    <ProjectIcon project={pickedProject} />
                  )}
                  <span className="truncate @max-xs:hidden">{pickerLabel}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="custom-scrollbar max-h-80 w-60 overflow-y-auto text-xs"
              >
                <DropdownMenuItem
                  className="cursor-pointer gap-2"
                  onSelect={() => setProjectFilter(null)}
                >
                  <CalendarClock className="mr-2 size-3.5 shrink-0 text-muted-foreground" />
                  All automations
                  {projectFilter === null && <Check className="ml-auto h-3 w-3" />}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {pickableProjects.map((p) => (
                  <DropdownMenuItem
                    key={p.id}
                    className="cursor-pointer gap-2"
                    onSelect={() => setProjectFilter(p.id)}
                  >
                    <ProjectIcon project={p} className="mr-2" />
                    <span className="truncate">{p.name}</span>
                    {projectFilter === p.id && <Check className="ml-auto h-3 w-3 shrink-0" />}
                  </DropdownMenuItem>
                ))}
                {/* Yours that sit in no project, pinned last like the Tasks picker. */}
                <DropdownMenuItem
                  className="cursor-pointer gap-2"
                  onSelect={() => setProjectFilter(NO_PROJECT)}
                >
                  <ProjectIcon project={null} className="mr-2" />
                  No project
                  {projectFilter === NO_PROJECT && <Check className="ml-auto h-3 w-3 shrink-0" />}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 shrink-0 cursor-pointer gap-1.5 text-xs"
                  title={`Show: ${FILTER_LABELS[filter]}`}
                  aria-label={`Show: ${FILTER_LABELS[filter]}`}
                >
                  <ListFilter className="size-3.5 text-muted-foreground" />
                  <span className="@max-sm:hidden">{FILTER_LABELS[filter]}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-40 text-xs">
                {(['all', 'active', 'paused'] as AutomationFilter[]).map((f) => (
                  <DropdownMenuItem key={f} onSelect={() => setFilter(f)}>
                    {FILTER_LABELS[f]}
                    {filter === f && <Check className="ml-auto h-3 w-3" />}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              size="sm"
              className="h-7 shrink-0 cursor-pointer gap-1 text-xs"
              onClick={createHere}
              disabled={!api}
              aria-label="New automation"
              title="New automation"
            >
              <Plus className="size-3.5" />
              <span className="@max-lg:hidden">New automation</span>
            </Button>
          </div>
        </div>

        {error && (
          <div className="border-b border-border bg-destructive/10 px-4 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {isLoading ? (
          <AutomationListSkeleton />
        ) : !projectFilter && automations.length === 0 ? (
          <AutomationEmptyState
            onPick={(t) => openCreate(t)}
            onScratch={() => openCreate()}
            disabled={!api}
            compact={panelOpen}
          />
        ) : (
          <AutomationList
            automations={rows}
            groupProjects={projectFilter ? null : projects}
            emptyLabel={
              projectFilter && projectFilter !== NO_PROJECT
                ? 'No automations in this project yet.'
                : undefined
            }
            filter={filter}
            selectedId={selectedId}
            onSelect={(a) => setSelection(a)}
            onRunNow={runNow}
            onTogglePause={togglePause}
            onDelete={(a) => setDeleteTarget(a)}
            onReorder={reorder}
            busyId={busyId}
          />
        )}
      </div>

      {/* Detail / create panel — only rendered when open, with a drag handle. */}
      {panelOpen && (
        <>
          {/* Thin divider with a wider invisible hit area for grabbing. */}
          <div
            onMouseDown={startDrag}
            className="relative w-px shrink-0 cursor-col-resize bg-border transition-colors hover:bg-primary/40 before:absolute before:inset-y-0 before:-left-1.5 before:-right-1.5 before:content-['']"
            title="Drag to resize"
          />
          <div className="min-w-0 flex-1">
            {selection !== 'new' && isShared(selection) ? (
              <SharedDetailPanel
                key={selection.id}
                api={api!}
                automation={selection}
                project={projects.find((p) => p.id === selection.project_id) ?? null}
                catalog={catalog}
                onClose={() => setSelection(null)}
              />
            ) : (
            <DetailPanel
              key={
                selection === 'new'
                  ? `new-${newTemplate?.id ?? 'scratch'}`
                  : (selection as AutomationResponse).id
              }
              api={api!}
              automation={selection === 'new' ? null : (selection as AutomationResponse)}
              template={selection === 'new' ? newTemplate : null}
              machines={machines}
              projects={projects}
              catalog={catalog}
              onSaved={handleSaved}
              onClose={() => setSelection(null)}
              runHistoryRefreshKey={historyKey}
            />
            )}
          </div>
        </>
      )}

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent className="font-mono">
          <DialogHeader>
            <DialogTitle>Delete Automation</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this automation? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          {deleteTarget?.title && (
            <div className="p-3 border rounded-md bg-muted/50">
              <div className="font-medium text-sm">{deleteTarget.title}</div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                const target = deleteTarget;
                setDeleteTarget(null);
                if (target) void deleteAutomation(target);
              }}
              className="text-destructive-foreground"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
