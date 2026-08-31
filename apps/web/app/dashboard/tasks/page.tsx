'use client';

// Human task tracker (plans/todos/tasks-and-projects-feature.md §5), UI
// modeled on multica's issues surface: status-section list, tinted board
// columns, Linear-style status/priority icons. Distinct from the Kanban tab
// (agent sessions) — this is the human backlog.

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Check,
  Columns3,
  List,
  ListTodo,
  Plus,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AgentInstanceResponse,
  CreateTaskRequest,
  MachineSummary,
  ProjectResponse,
  TaskLabelResponse,
  TaskResponse,
  TaskStatus,
  UpdateTaskRequest,
} from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { notifyOnboardingProgress } from '@/lib/onboarding-progress';
import {
  ProjectIcon,
  inlineLabelColor,
  projectLabel,
} from '@/components/dashboard/task-ui';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { DesktopCollapsedLead } from '@/components/desktop/window-chrome';
import { TaskBoard } from './task-board';
import { TaskList } from './task-list';
import { StartSessionDialog } from './start-session-dialog';
import { CreateProjectDialog, TaskDialog, TaskFormValues } from './task-dialog';
import {
  TaskSettingsButton,
  TaskSettingsDialog,
  TaskSettingsHandlers,
} from './task-settings-dialog';
import { TaskViewsBar } from './task-views-bar';
import { TaskDisplayMenu } from './task-display-menu';
import { TaskListSkeleton } from './task-skeleton';
import { getTasksCache, setTasksCache } from './task-cache';
import {
  TaskView,
  cloneView,
  compareTasks,
  defaultView,
  loadActiveViewId,
  loadViews,
  saveActiveViewId,
  saveViews,
} from './task-views';

/** ISO timestamp from a yyyy-mm-dd date input ('' → null). */
function fromDateInputValue(value: string): string | null {
  return value ? `${value}T00:00:00Z` : null;
}

// useSearchParams needs a Suspense boundary for prerender (same pattern as
// new-session/page.tsx).
export default function TasksPage() {
  return (
    <Suspense fallback={null}>
      <TasksPageInner />
    </Suspense>
  );
}

function TasksPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { api } = useAgentDashboard();
  // Seed from the in-memory cache (task-cache.ts) so revisiting the tab paints
  // the last-loaded board instantly; a cold visit starts empty + loading and
  // shows the skeleton. Both cases revalidate on mount.
  const [projects, setProjects] = useState<ProjectResponse[]>(
    () => getTasksCache()?.projects ?? [],
  );
  const [labels, setLabels] = useState<TaskLabelResponse[]>(
    () => getTasksCache()?.labels ?? [],
  );
  const [tasks, setTasks] = useState<TaskResponse[]>(() => getTasksCache()?.tasks ?? []);
  const [isLoading, setIsLoading] = useState(() => getTasksCache() === null);
  const [error, setError] = useState<string | null>(null);
  // True only when this mount started with no cache — a background revalidate
  // over already-painted cached rows must not blank them with an error screen
  // (mirrors the chat page's cached-conversation handling).
  const coldStartRef = useRef(getTasksCache() === null);
  // Saved views (local, per device). `views` is empty until the first
  // client-side load resolves; the active view drives mode/filter/collapse.
  const [views, setViews] = useState<TaskView[]>([]);
  const [activeViewId, setActiveViewId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<{
    open: boolean;
    task: TaskResponse | null;
    defaults?: { status?: TaskStatus };
  }>({ open: false, task: null });
  // Sessions started from the task the dialog is editing (agent instances whose
  // task_id points here). Fetched on open so the dialog can show a linked-
  // sessions strip; empty in create mode and for tasks that never ran one.
  const [dialogSessions, setDialogSessions] = useState<AgentInstanceResponse[]>([]);
  const [projectDialogOpen, setProjectDialogOpen] = useState(false);
  // Set when "Start session" is fired on a task that has sub-tasks — opens the
  // picker to choose which children ride along. Null = no picker open.
  const [sessionDialog, setSessionDialog] = useState<{
    task: TaskResponse;
    subtasks: TaskResponse[];
  } | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Only needed to name/pick folders in the settings dialog, so it's fetched
  // lazily on first open rather than on every visit to the board.
  const [machines, setMachines] = useState<MachineSummary[]>([]);
  // The settings dialog also lists archived projects (otherwise "Unarchive"
  // would be unreachable — archived ones drop out of the board's list).
  const [allProjects, setAllProjects] = useState<ProjectResponse[]>([]);

  const refresh = useCallback(async () => {
    if (!api) return;
    const [projectList, taskList, labelList] = await Promise.all([
      api.listProjects(),
      api.listTasks(),
      api.listTaskLabels(),
    ]);
    setProjects(projectList);
    setTasks(taskList);
    setLabels(labelList);
  }, [api]);

  /** Both project lists at once — the board shows active, settings shows all. */
  const refreshProjects = useCallback(async () => {
    if (!api) return;
    const [active, all] = await Promise.all([
      api.listProjects(),
      api.listProjects(true),
    ]);
    setProjects(active);
    setAllProjects(all);
  }, [api]);

  const openSettings = useCallback(() => {
    setSettingsOpen(true);
    if (!api) return;
    void refreshProjects();
    if (machines.length > 0) return;
    api
      .listMachines()
      .then(setMachines)
      .catch((err) => console.error('Failed to load machines:', err));
  }, [api, machines.length, refreshProjects]);

  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    (async () => {
      try {
        // `isLoading` already reflects cache presence (skeleton only on a cold
        // visit); this pass just revalidates without flipping back to loading.
        setError(null);
        await refresh();
      } catch (err) {
        // Only surface the error screen on a cold start. Over cached rows, keep
        // them on screen and let the next revalidate clear the failure.
        if (!cancelled && coldStartRef.current) {
          setError(err instanceof Error ? err.message : 'Failed to load tasks');
        } else if (!cancelled) {
          console.error('Failed to revalidate tasks:', err);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, refresh]);

  // Deep link from the ⌘K palette: /dashboard/tasks?task={id} opens that
  // task's dialog once its row is available (cached rows immediately, else
  // after the fetch lands), then strips the param so refresh/back doesn't
  // reopen it. An unknown id (e.g. deleted task) just leaves the board as-is.
  useEffect(() => {
    const taskId = searchParams?.get('task');
    if (!taskId) return;
    if (taskId === 'new') {
      setDialog({ open: true, task: null });
      router.replace('/dashboard/tasks', { scroll: false });
      return;
    }
    const target = tasks.find((t) => t.id === taskId);
    if (!target) return;
    setDialog({ open: true, task: target });
    router.replace('/dashboard/tasks', { scroll: false });
  }, [searchParams, tasks, router]);

  // Keep the in-memory cache warm from the current rows — seeds the next visit.
  // Gated on !isLoading so the pre-load empty state is never cached; every
  // optimistic mutation flows through setProjects/setTasks/setLabels, so this
  // stays current without touching each handler.
  useEffect(() => {
    if (isLoading) return;
    setTasksCache({ projects, tasks, labels });
  }, [isLoading, projects, tasks, labels]);

  // Load saved views once, client-side (localStorage / settings.json aren't
  // available during SSR). The active view falls back to the first one.
  useEffect(() => {
    const loaded = loadViews();
    setViews(loaded);
    const storedId = loadActiveViewId();
    setActiveViewId(loaded.some((v) => v.id === storedId) ? storedId : loaded[0].id);
  }, []);

  // The current view (mode / filter / collapsed sections). Falls back to a
  // default while views are still loading so the first paint has sane values.
  const activeView = useMemo(
    () => views.find((v) => v.id === activeViewId) ?? views[0] ?? defaultView(),
    [views, activeViewId],
  );
  const view = activeView.mode;
  const projectFilter = activeView.projectFilter;
  const showSubTasks = activeView.showSubTasks;
  const properties = activeView.properties;
  const sortBy = activeView.sortBy;
  const sortDirection = activeView.sortDirection;
  const collapsed = useMemo(() => new Set(activeView.collapsed), [activeView.collapsed]);

  // Mutate the active view and persist. Guards on a loaded view id so the
  // pre-load default isn't accidentally written back as a real view.
  const updateActiveView = useCallback(
    (patch: Partial<Omit<TaskView, 'id'>>) => {
      if (!activeViewId) return;
      setViews((prev) => {
        const next = prev.map((v) => (v.id === activeViewId ? { ...v, ...patch } : v));
        saveViews(next);
        return next;
      });
    },
    [activeViewId],
  );

  const selectView = useCallback((id: string) => {
    setActiveViewId(id);
    saveActiveViewId(id);
  }, []);

  const createView = useCallback(() => {
    const created = cloneView(activeView, `View ${views.length + 1}`);
    setViews((prev) => {
      const next = [...prev, created];
      saveViews(next);
      return next;
    });
    setActiveViewId(created.id);
    saveActiveViewId(created.id);
  }, [activeView, views.length]);

  const renameView = useCallback((id: string, name: string) => {
    setViews((prev) => {
      const next = prev.map((v) => (v.id === id ? { ...v, name } : v));
      saveViews(next);
      return next;
    });
  }, []);

  const duplicateView = useCallback(
    (id: string) => {
      const source = views.find((v) => v.id === id);
      if (!source) return;
      const copy = cloneView(source, `${source.name} copy`);
      setViews((prev) => {
        const next = [...prev, copy];
        saveViews(next);
        return next;
      });
      setActiveViewId(copy.id);
      saveActiveViewId(copy.id);
    },
    [views],
  );

  const deleteView = useCallback(
    (id: string) => {
      setViews((prev) => {
        if (prev.length <= 1) return prev; // never delete the last view
        const next = prev.filter((v) => v.id !== id);
        saveViews(next);
        if (id === activeViewId) {
          setActiveViewId(next[0].id);
          saveActiveViewId(next[0].id);
        }
        return next;
      });
    },
    [activeViewId],
  );

  // Optimistic patch: apply locally, PATCH, reconcile with the server row,
  // refresh on error (use-session-operations style).
  const patchTask = useCallback(
    async (taskId: string, patch: UpdateTaskRequest) => {
      if (!api) return;
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? ({ ...t, ...patch } as TaskResponse) : t)),
      );
      try {
        const updated = await api.updateTask(taskId, patch);
        setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
      } catch (err) {
        console.error('Failed to update task:', err);
        void refresh();
      }
    },
    [api, refresh],
  );

  const deleteTask = useCallback(
    async (task: TaskResponse) => {
      if (!api) return;
      if (!window.confirm(`Delete task "${task.title}"?`)) return;
      const before = tasks;
      setTasks((prev) => prev.filter((t) => t.id !== task.id));
      try {
        await api.deleteTask(task.id);
      } catch (err) {
        console.error('Failed to delete task:', err);
        setTasks(before);
      }
    },
    [api, tasks],
  );

  const submitDialog = useCallback(
    async (values: TaskFormValues) => {
      if (!api) return;
      const payload: CreateTaskRequest & UpdateTaskRequest = {
        title: values.title.trim(),
        description: values.description.trim() || null,
        project_id: values.project_id || null,
        status: values.status,
        priority: values.priority,
        label_ids: values.label_ids,
        parent_task_id: values.parent_task_id,
        start_date: fromDateInputValue(values.start_date),
        due_date: fromDateInputValue(values.due_date),
      };
      try {
        if (dialog.task) {
          const updated = await api.updateTask(dialog.task.id, payload);
          setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
          return updated;
        }
        // Append to the end of its status group.
        const maxPosition = tasks.reduce((max, t) => Math.max(max, t.position), 0);
        const created = await api.createTask({ ...payload, position: maxPosition + 1 });
        setTasks((prev) => [...prev, created]);
        notifyOnboardingProgress();
        return created;
      } catch (err) {
        console.error('Failed to save task:', err);
        alert(err instanceof Error ? err.message : 'Failed to save task');
        throw err;
      }
    },
    [api, dialog.task, tasks],
  );

  const createProject = useCallback(
    async (values: { name: string; icon: string | null }) => {
      if (!api) return;
      try {
        const project = await api.createProject(values);
        setProjects((prev) => [...prev, project]);
        updateActiveView({ projectFilter: project.id });
      } catch (err) {
        console.error('Failed to create project:', err);
        alert(err instanceof Error ? err.message : 'Failed to create project');
        throw err;
      }
    },
    [api, updateActiveView],
  );

  // Inline label creation from the picker; color derives from the name
  // (multica INLINE_COLORS) so the same name always gets the same color.
  const createLabel = useCallback(
    async (name: string): Promise<TaskLabelResponse> => {
      if (!api) throw new Error('API not ready');
      const label = await api.createTaskLabel({ name, color: inlineLabelColor(name) });
      setLabels((prev) => [...prev, label].sort((a, b) => a.name.localeCompare(b.name)));
      return label;
    },
    [api],
  );

  // Sub-tasks: children live in the same flat list; the dialog adds them
  // with parent_task_id and the same project as the parent.
  const addSubtask = useCallback(
    async (parent: TaskResponse, title: string) => {
      if (!api) return;
      const maxPosition = tasks.reduce((max, t) => Math.max(max, t.position), 0);
      const created = await api.createTask({
        title,
        parent_task_id: parent.id,
        project_id: parent.project_id,
        position: maxPosition + 1,
      });
      setTasks((prev) => [...prev, created]);
      notifyOnboardingProgress();
    },
    [api, tasks],
  );

  // Projects/labels management (settings dialog). Each mutation reconciles the
  // one row it touched; deletes fall back to a full refresh because dropping a
  // project takes its tasks with it (FK CASCADE) and dropping a label unlinks
  // it from every task.
  const settingsHandlers: TaskSettingsHandlers = useMemo(
    () => ({
      updateProject: async (projectId, patch) => {
        if (!api) return;
        try {
          await api.updateProject(projectId, patch);
          // Archiving moves the project between the two lists, so refetch both
          // rather than splicing the row into one of them.
          await refreshProjects();
        } catch (err) {
          console.error('Failed to update project:', err);
          alert(err instanceof Error ? err.message : 'Failed to update project');
          void refreshProjects();
        }
      },
      // Confirmation lives in the settings dialog (ConfirmDeleteDialog), so
      // these two just delete.
      deleteProject: async (project) => {
        if (!api) return;
        try {
          await api.deleteProject(project.id);
          if (projectFilter === project.id) updateActiveView({ projectFilter: 'all' });
          await Promise.all([refresh(), refreshProjects()]);
        } catch (err) {
          console.error('Failed to delete project:', err);
          alert(err instanceof Error ? err.message : 'Failed to delete project');
        }
      },
      setProjectDirectory: async (projectId, machineId, localPath) => {
        if (!api) return;
        try {
          const updated = await api.setProjectDirectory(projectId, {
            machine_id: machineId,
            local_path: localPath,
          });
          const splice = (prev: ProjectResponse[]) =>
            prev.map((p) => (p.id === projectId ? updated : p));
          setProjects(splice);
          setAllProjects(splice);
        } catch (err) {
          console.error('Failed to link the folder:', err);
          alert(err instanceof Error ? err.message : 'Failed to link the folder');
        }
      },
      removeProjectDirectory: async (projectId, machineId) => {
        if (!api) return;
        try {
          const updated = await api.deleteProjectDirectory(projectId, machineId);
          const splice = (prev: ProjectResponse[]) =>
            prev.map((p) => (p.id === projectId ? updated : p));
          setProjects(splice);
          setAllProjects(splice);
        } catch (err) {
          console.error('Failed to unlink the folder:', err);
        }
      },
      createLabel,
      updateLabel: async (labelId, patch) => {
        if (!api) return;
        try {
          const updated = await api.updateTaskLabel(labelId, patch);
          setLabels((prev) =>
            prev
              .map((l) => (l.id === labelId ? updated : l))
              .sort((a, b) => a.name.localeCompare(b.name)),
          );
          // Chips on the board embed the label, so re-read the tasks too.
          const taskList = await api.listTasks();
          setTasks(taskList);
        } catch (err) {
          console.error('Failed to update label:', err);
        }
      },
      deleteLabel: async (label) => {
        if (!api) return;
        try {
          await api.deleteTaskLabel(label.id);
          await refresh();
        } catch (err) {
          console.error('Failed to delete label:', err);
        }
      },
    }),
    [api, createLabel, projectFilter, refresh, refreshProjects, updateActiveView],
  );

  // "Start session" seeds a new agent session from the task (plan §7). With
  // sub-tasks, open the picker first so the user can choose which ride along;
  // without, go straight to the New Session page as before.
  const startSession = useCallback(
    (task: TaskResponse) => {
      const children = tasks.filter((t) => t.parent_task_id === task.id);
      if (children.length === 0) {
        router.push(`/dashboard/agents/new-session?taskId=${task.id}`);
        return;
      }
      setSessionDialog({ task, subtasks: children });
    },
    [router, tasks],
  );

  // "Repeat…" turns a task into a scheduled automation: hand the task id to the
  // Automation page, which fetches it, seeds title + prompt from the task, and
  // resolves the machine/directory from the task's linked project.
  const createAutomationFromTask = useCallback(
    (task: TaskResponse) => {
      router.push(`/dashboard/automation?automation=new&taskId=${task.id}`);
    },
    [router],
  );

  // Picker confirmed: carry the chosen sub-task ids to the New Session page,
  // which seeds them into the prompt and advances their status with the parent.
  const confirmStartSession = useCallback(
    (selectedIds: string[]) => {
      if (!sessionDialog) return;
      const params = new URLSearchParams({ taskId: sessionDialog.task.id });
      if (selectedIds.length > 0) params.set('subtasks', selectedIds.join(','));
      setSessionDialog(null);
      router.push(`/dashboard/agents/new-session?${params.toString()}`);
    },
    [router, sessionDialog],
  );

  const toggleSection = useCallback(
    (status: TaskStatus) => {
      const next = new Set(collapsed);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      updateActiveView({ collapsed: [...next] });
    },
    [collapsed, updateActiveView],
  );

  const openCreateDialog = useCallback(
    (defaults?: { status?: TaskStatus }) =>
      setDialog({ open: true, task: null, defaults }),
    [],
  );
  const openEditDialog = useCallback(
    (task: TaskResponse) => setDialog({ open: true, task }),
    [],
  );
  const closeDialog = useCallback(() => setDialog({ open: false, task: null }), []);

  // Jump from a task's linked-sessions strip straight into that session. The
  // dialog persists any pending edits first (mirrors its sub-task navigation).
  const openSession = useCallback(
    (instanceId: string) => {
      closeDialog();
      router.push(`/dashboard/agents/${instanceId}`);
    },
    [closeDialog, router],
  );

  const visibleTasks = useMemo(() => {
    const filtered = tasks.filter((t) => {
      if (projectFilter !== 'all' && t.project_id !== projectFilter) return false;
      // "Show sub-tasks" off → hide anything with a parent (parents only).
      if (!showSubTasks && t.parent_task_id) return false;
      return true;
    });
    // Order within each status group per the active view. buildColumns (list +
    // board) preserves this order as it buckets by status, so sorting the flat
    // list here drives both views.
    return [...filtered].sort((a, b) => compareTasks(a, b, sortBy, sortDirection));
  }, [tasks, projectFilter, showSubTasks, sortBy, sortDirection]);

  // task id -> task, for resolving a sub-task's parent chip. Built over ALL
  // tasks so a parent hidden by the current filter still resolves.
  const tasksById = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks]);

  // parent id -> {done, total} across ALL tasks (not just the filtered view).
  const childProgressMap = useMemo(() => {
    const map = new Map<string, { done: number; total: number }>();
    for (const task of tasks) {
      if (!task.parent_task_id) continue;
      const entry = map.get(task.parent_task_id) ?? { done: 0, total: 0 };
      entry.total += 1;
      if (task.status === 'done') entry.done += 1;
      map.set(task.parent_task_id, entry);
    }
    return map;
  }, [tasks]);

  const dialogChildren = useMemo(
    () =>
      dialog.task
        ? tasks.filter((t) => t.parent_task_id === dialog.task!.id)
        : [],
    [dialog.task, tasks],
  );

  // Load the linked sessions whenever the dialog opens on an existing task.
  // Clears first so the previous task's list never flashes under a new one; a
  // fetch failure just leaves the strip empty (it's supplementary context).
  const dialogTaskId = dialog.open ? dialog.task?.id ?? null : null;
  useEffect(() => {
    setDialogSessions([]);
    if (!api || !dialogTaskId) return;
    let cancelled = false;
    api
      .listTaskSessions(dialogTaskId)
      .then((sessions) => {
        if (!cancelled) setDialogSessions(sessions);
      })
      .catch((err) => console.error('Failed to load task sessions:', err));
    return () => {
      cancelled = true;
    };
  }, [api, dialogTaskId]);

  const filterProject = projects.find((p) => p.id === projectFilter);

  return (
    <main className="flex h-full flex-col overflow-hidden">
      {/* Page header (multica PageHeader style). On desktop it is the window
          titlebar: a drag region whose interactive controls opt back out via
          NO_DRAG, with the collapsed-sidebar lead clearing the macOS traffic
          lights. Draggable from the title area + any empty toolbar space. */}
      <div
        style={DRAG_REGION}
        className="flex h-11 shrink-0 items-center gap-2 border-b border-border/60 px-4"
      >
        <DesktopCollapsedLead />
        <ListTodo className="h-4 w-4 shrink-0 text-muted-foreground" />
        <h1 className="shrink-0 text-sm font-medium">Tasks</h1>

        <div style={NO_DRAG} className="flex min-w-0 flex-1 items-center gap-2">
        {/* Projects & labels settings sits next to the title, before the tabs. */}
        <TaskSettingsButton onClick={openSettings} />

        {/* Saved view tabs */}
        <div className="mx-1 min-w-0 flex-1">
          <TaskViewsBar
            views={views}
            activeViewId={activeViewId}
            onSelect={selectView}
            onCreate={createView}
            onRename={renameView}
            onDuplicate={duplicateView}
            onDelete={deleteView}
          />
        </div>

        {/* Project filter */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
              {projectFilter === 'all' ? (
                <ListTodo className="size-3.5 text-muted-foreground" />
              ) : (
                <ProjectIcon project={filterProject} />
              )}
              <span className="hidden md:inline">
                {projectFilter === 'all' ? 'All projects' : projectLabel(filterProject)}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52 text-xs">
            <DropdownMenuItem onSelect={() => updateActiveView({ projectFilter: 'all' })}>
              All projects
              {projectFilter === 'all' && <Check className="ml-auto h-3 w-3" />}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {projects.map((project) => (
              <DropdownMenuItem
                key={project.id}
                onSelect={() => updateActiveView({ projectFilter: project.id })}
              >
                <ProjectIcon project={project} className="mr-2" />
                {projectLabel(project)}
                {projectFilter === project.id && <Check className="ml-auto h-3 w-3" />}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setProjectDialogOpen(true)}>
              <Plus className="mr-2 h-3.5 w-3.5" />
              New project
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* View mode (multica view dropdown) */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs">
              {view === 'board' ? <Columns3 className="size-3.5" /> : <List className="size-3.5" />}
              <span className="hidden md:inline">{view === 'board' ? 'Board' : 'List'}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-32 text-xs">
            <DropdownMenuItem onSelect={() => updateActiveView({ mode: 'list' })}>
              <List className="mr-2 size-3.5" />
              List
              {view === 'list' && <Check className="ml-auto h-3 w-3" />}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => updateActiveView({ mode: 'board' })}>
              <Columns3 className="mr-2 size-3.5" />
              Board
              {view === 'board' && <Check className="ml-auto h-3 w-3" />}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Display options — ordering + show sub-tasks + which properties show */}
        <TaskDisplayMenu
          showSubTasks={showSubTasks}
          properties={properties}
          sortBy={sortBy}
          sortDirection={sortDirection}
          onShowSubTasksChange={(v) => updateActiveView({ showSubTasks: v })}
          onPropertyChange={(key, value) =>
            updateActiveView({ properties: { ...properties, [key]: value } })
          }
          onSortByChange={(value) => updateActiveView({ sortBy: value })}
          onSortDirectionChange={(value) => updateActiveView({ sortDirection: value })}
        />

        <Button size="sm" className="h-7 gap-1 text-xs" onClick={() => openCreateDialog()} disabled={!api}>
          <Plus className="size-3.5" />
          New task
        </Button>
        </div>
      </div>

      {/* Body */}
      {isLoading ? (
        <TaskListSkeleton />
      ) : error ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            Retry
          </Button>
        </div>
      ) : visibleTasks.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-foreground">
          <ListTodo className="h-10 w-10 text-muted-foreground/40" />
          <p className="text-sm">
            {projectFilter === 'all' ? 'No tasks yet' : 'No tasks in this project'}
          </p>
          <p className="text-xs">Capture what needs doing, then start a session from a task.</p>
          <Button size="sm" className="mt-2 gap-1 text-xs" onClick={() => openCreateDialog()}>
            <Plus className="size-3.5" />
            New task
          </Button>
        </div>
      ) : view === 'board' ? (
        <div className="custom-scrollbar min-h-0 flex-1 overflow-x-auto p-3">
          <TaskBoard
            tasks={visibleTasks}
            projects={projects}
            parentById={tasksById}
            childProgressMap={childProgressMap}
            display={properties}
            manualOrder={sortBy === 'position'}
            onEdit={openEditDialog}
            onPatch={patchTask}
            onDelete={deleteTask}
            onStartSession={startSession}
            onCreateAutomation={createAutomationFromTask}
            onCreate={(status) => openCreateDialog({ status })}
          />
        </div>
      ) : (
        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-2 pt-1">
          <TaskList
            tasks={visibleTasks}
            projects={projects}
            parentById={tasksById}
            childProgressMap={childProgressMap}
            display={properties}
            manualOrder={sortBy === 'position'}
            collapsed={collapsed}
            onToggle={toggleSection}
            onEdit={openEditDialog}
            onPatch={patchTask}
            onDelete={deleteTask}
            onStartSession={startSession}
            onCreateAutomation={createAutomationFromTask}
            onCreate={(status) => openCreateDialog({ status })}
          />
        </div>
      )}

      <TaskDialog
        open={dialog.open}
        task={dialog.task}
        defaults={dialog.defaults}
        projects={projects}
        labels={labels}
        allTasks={tasks}
        childTasks={dialogChildren}
        sessions={dialogSessions}
        onCreateLabel={createLabel}
        onAddSubtask={addSubtask}
        onOpenTask={openEditDialog}
        onOpenSession={openSession}
        onClose={closeDialog}
        onSubmit={submitDialog}
      />
      <CreateProjectDialog
        open={projectDialogOpen}
        onClose={() => setProjectDialogOpen(false)}
        onSubmit={createProject}
      />
      <TaskSettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        projects={allProjects}
        labels={labels}
        machines={machines}
        handlers={settingsHandlers}
      />
      <StartSessionDialog
        open={!!sessionDialog}
        parentTask={sessionDialog?.task ?? null}
        subtasks={sessionDialog?.subtasks ?? []}
        onClose={() => setSessionDialog(null)}
        onConfirm={confirmStartSession}
      />
    </main>
  );
}
