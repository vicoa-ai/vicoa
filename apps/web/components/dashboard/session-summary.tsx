'use client';

// The session summary: where a session runs (project, folder, branch,
// computer) and what it is for (the task it works on, the tasks it created,
// the automation behind it), in a card the header's toggle opens at the top
// right. With room beside the chat the card takes a column of its own and
// stays open, remembered across sessions; without, it opens over the chat like
// a menu and closes on a click elsewhere.

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { CalendarClock, FolderOpen, GitBranch, LayoutList, Laptop } from 'lucide-react';

import { NO_PROJECT_LABEL, ProjectIcon, StatusIcon, TaskIdentifier } from '@/components/dashboard/task-ui';
import { rpcGitStatus } from '@/components/files-git-panel/rpc';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { NO_DRAG } from '@/lib/app-region';
import type {
  AgentInstanceDetail,
  BackendApiError,
  MachineSummary,
  ProjectResponse,
  TaskResponse,
} from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { machineDisplayName } from '@/lib/machine-display';
import {
  SUMMARY_CARD_WIDTH,
  SUMMARY_COLUMN_EDGE,
  canDockSummary,
  changeTotals,
  compactPath,
} from '@/lib/session-summary';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'session-summary-open';

// The task and the tasks a session created change as its agent works, so they
// follow the transcript; a burst of messages costs one refetch, not one each.
const REFETCH_DEBOUNCE_MS = 1500;

export interface SessionSummaryState {
  /** The window has room for the card beside the chat (and nothing covers it). */
  dockable: boolean;
  /** Shown in its own column beside the chat. */
  docked: boolean;
  /** Shown over the chat, opened from the toggle where there is no room. */
  floating: boolean;
  setFloating: (open: boolean) => void;
  toggle: () => void;
}

/**
 * Where the card shows. `column` is the session column (header, chat and
 * composer, without the files panel), measured to decide whether the card
 * fits beside the chat. `allowDock` is false while something else fills the
 * column (the maximized files panel).
 */
export function useSessionSummary(
  column: HTMLElement | null,
  allowDock: boolean,
): SessionSummaryState {
  // Open unless the person closed it; one preference for every session.
  const [preferOpen, setPreferOpen] = useState(true);
  const [room, setRoom] = useState(false);
  const [floating, setFloating] = useState(false);

  useEffect(() => {
    try {
      if (window.localStorage.getItem(STORAGE_KEY) === 'closed') setPreferOpen(false);
    } catch {
      // Storage blocked: the default stands.
    }
  }, []);

  useEffect(() => {
    if (!column) return;
    const measure = () => setRoom(canDockSummary(column.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(column);
    return () => observer.disconnect();
  }, [column]);

  const dockable = room && allowDock;
  // Room came back (window widened, files panel closed): the column takes over
  // from the menu, so the menu must not pop up again when room goes next time.
  useEffect(() => {
    if (dockable) setFloating(false);
  }, [dockable]);

  const toggle = useCallback(() => {
    if (!dockable) {
      setFloating((open) => !open);
      return;
    }
    const next = !preferOpen;
    setPreferOpen(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? 'open' : 'closed');
    } catch {
      // Not remembered; it still applies to this page.
    }
  }, [dockable, preferOpen]);

  return {
    dockable,
    docked: dockable && preferOpen,
    floating: !dockable && floating,
    setFloating,
    toggle,
  };
}

/**
 * The header button. Where the card has a column it shows or hides that
 * column; elsewhere it opens the card as a menu anchored to itself.
 */
export function SessionSummaryToggle({
  state,
  children,
}: {
  state: SessionSummaryState;
  /** The card, for the menu form. */
  children: ReactNode;
}) {
  const shown = state.docked || state.floating;
  return (
    <Popover
      open={state.floating}
      onOpenChange={(open) => (state.dockable ? state.toggle() : state.setFloating(open))}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={shown ? 'Hide session summary' : 'Show session summary'}
          title="Summary"
          className={cn(
            'inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded p-0 hover:bg-muted hover:text-foreground',
            shown ? 'text-foreground' : 'text-muted-foreground',
          )}
        >
          <LayoutList className="h-4 w-4" />
        </button>
      </PopoverTrigger>
      {/* Portaled, but it opens over the header's bottom edge: in the desktop
          app that strip is a window-drag region, which would swallow clicks
          on the card's top rows. */}
      <PopoverContent
        align="end"
        sideOffset={6}
        style={{ ...NO_DRAG, width: SUMMARY_CARD_WIDTH }}
        className="rounded-xl p-0"
      >
        {children}
      </PopoverContent>
    </Popover>
  );
}

/**
 * The docked form: a card at the top right of the chat area, in the column the
 * transcript's lane leaves free (`SUMMARY_CHAT_LANE`). It is laid over the
 * transcript's scroller rather than beside it, so the chat's scrollbar runs
 * down the window's edge instead of between the chat and the card. Only as
 * tall as the card, so a wheel in the empty space under it still scrolls the
 * chat; a very short window scrolls the card rather than cutting it off.
 * Render it inside a positioned box that spans the chat area.
 */
export function SessionSummaryColumn({ children }: { children: ReactNode }) {
  return (
    <aside
      aria-label="Session summary"
      className="custom-scrollbar absolute right-0 top-0 z-20 max-h-full overflow-y-auto pb-3 pt-1"
      style={{ width: SUMMARY_CARD_WIDTH, marginRight: SUMMARY_COLUMN_EDGE }}
    >
      <div className="rounded-xl border border-border bg-popover text-popover-foreground shadow-sm">
        {children}
      </div>
    </aside>
  );
}

export function SessionSummaryCard({
  instance,
  project,
  isOwner,
  messageCount,
  agentWorking,
  onShowChanges,
}: {
  instance: AgentInstanceDetail;
  /** The project it is filed under, once the project list has it. */
  project: ProjectResponse | null;
  isOwner: boolean;
  /** Grows with the transcript; each settled change refetches the tasks. */
  messageCount: number;
  agentWorking: boolean;
  /** Open the files panel on its changes. */
  onShowChanges?: () => void;
}) {
  const projectId = instance.project_id ?? null;
  // The branch and computer are read from the owner's machine; someone the
  // session is shared with gets neither (`machine_id` is null for them).
  const machineId = isOwner ? (instance.machine_id ?? null) : null;
  const git = useGitSummary(machineId, instance.project ?? null, agentWorking);
  const machine = useMachineName(machineId);
  const task = useLinkedTask(instance.task_id ?? null, messageCount);
  const created = useCreatedTasks(instance.id, messageCount).filter((t) => t.id !== task?.id);
  const automation = instance.automation ?? null;

  const where: ReactNode[] = [];
  if (project || !projectId) {
    where.push(
      <Row key="project" icon={<ProjectIcon project={project} className="size-3.5" />}>
        <span className="truncate">{project ? project.name : NO_PROJECT_LABEL}</span>
      </Row>,
    );
  }
  if (instance.project) {
    where.push(
      <Tooltip key="folder">
        <TooltipTrigger asChild>
          <div>
            <Row icon={<FolderOpen className="h-3.5 w-3.5" />}>
              <span className="truncate">{compactPath(instance.project, instance.home_dir)}</span>
            </Row>
          </div>
        </TooltipTrigger>
        <TooltipContent align="start">
          <p>{instance.project}</p>
        </TooltipContent>
      </Tooltip>,
    );
  }
  if (git) {
    const hasChanges = git.additions > 0 || git.deletions > 0;
    where.push(
      <Row
        key="branch"
        icon={<GitBranch className="h-3.5 w-3.5" />}
        onClick={onShowChanges}
        title={onShowChanges ? 'Show changes' : undefined}
        trailing={
          hasChanges ? (
            <span className="shrink-0 text-xs tabular-nums">
              <span className="text-emerald-600 dark:text-emerald-400">+{git.additions}</span>{' '}
              <span className="text-red-600 dark:text-red-400">-{git.deletions}</span>
            </span>
          ) : null
        }
      >
        <span className="truncate">{git.branch}</span>
      </Row>,
    );
  }
  if (machine) {
    where.push(
      <Row key="machine" icon={<Laptop className="h-3.5 w-3.5" />}>
        <span className="truncate">{machine}</span>
      </Row>,
    );
  }

  const groups: ReactNode[] = [];
  if (where.length > 0) groups.push(<div key="where">{where}</div>);
  if (task || created.length > 0) {
    groups.push(
      <div key="tasks">
        {task && (
          <>
            <Label>Task</Label>
            <TaskRow task={task} />
          </>
        )}
        {created.length > 0 && (
          <>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="w-fit">
                  <Label>Created</Label>
                </div>
              </TooltipTrigger>
              <TooltipContent align="start">
                <p>Created in this session</p>
              </TooltipContent>
            </Tooltip>
            {created.map((t) => (
              <TaskRow key={t.id} task={t} />
            ))}
          </>
        )}
      </div>,
    );
  }
  if (automation) {
    groups.push(
      <div key="automation">
        <Label>Automation</Label>
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href={`/dashboard/automation?automation=${automation.id}`}
              className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted"
            >
              <CalendarClock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="truncate">{automation.title}</span>
            </Link>
          </TooltipTrigger>
          <TooltipContent align="start">
            <p>
              {automation.runs_here ? 'The automation ' : 'Started by the automation '}
              &ldquo;{automation.title}&rdquo;
              {automation.runs_here ? ' runs in this session' : ''}
            </p>
          </TooltipContent>
        </Tooltip>
      </div>,
    );
  }

  return (
    <TooltipProvider>
      <div className="p-1.5 font-mono text-sm">
        {groups.length === 0 ? (
          <p className="px-2 py-1.5 text-muted-foreground">Nothing to show yet</p>
        ) : (
          groups.map((group, index) => (
            <div key={index} className={index > 0 ? 'mt-1.5 border-t border-border/60 pt-1.5' : undefined}>
              {group}
            </div>
          ))
        )}
      </div>
    </TooltipProvider>
  );
}

function Label({ children }: { children: ReactNode }) {
  return <div className="px-2 pb-0.5 pt-1 text-[0.8rem] font-normal text-muted-foreground">{children}</div>;
}

function Row({
  icon,
  children,
  trailing,
  onClick,
  title,
}: {
  icon: ReactNode;
  children: ReactNode;
  trailing?: ReactNode;
  onClick?: () => void;
  title?: string;
}) {
  const body = (
    <>
      <span className="flex shrink-0 items-center text-muted-foreground">{icon}</span>
      <span className="flex min-w-0 flex-1 items-center">{children}</span>
      {trailing}
    </>
  );
  const shell = 'flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-left';
  if (onClick) {
    return (
      <button type="button" onClick={onClick} title={title} className={cn(shell, 'cursor-pointer hover:bg-muted')}>
        {body}
      </button>
    );
  }
  return <div className={cn(shell, 'cursor-default')}>{body}</div>;
}

function TaskRow({ task }: { task: TaskResponse }) {
  return (
    <Link
      href={`/dashboard/tasks/${task.id}`}
      title={task.title}
      className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted"
    >
      <StatusIcon status={task.status} className="h-3.5 w-3.5 shrink-0" />
      <TaskIdentifier task={task} className="shrink-0" />
      <span className="truncate">{task.title}</span>
    </Link>
  );
}

/** The folder's branch and its uncommitted line counts, over the machine's git-status RPC. */
function useGitSummary(
  machineId: string | null,
  cwd: string | null,
  agentWorking: boolean,
): { branch: string; additions: number; deletions: number } | null {
  const [summary, setSummary] = useState<{ branch: string; additions: number; deletions: number } | null>(
    null,
  );

  useEffect(() => {
    setSummary(null);
  }, [machineId, cwd]);

  useEffect(() => {
    if (!machineId || !cwd) return;
    let cancelled = false;
    const load = () => {
      rpcGitStatus(machineId, cwd)
        .then((status) => {
          if (cancelled) return;
          // Not a repository, or a detached HEAD: no branch to name.
          setSummary(status.branch ? { branch: status.branch, ...changeTotals(status) } : null);
        })
        .catch(() => {
          if (!cancelled) setSummary(null);
        });
    };
    load();
    // A terminal checkout can change the branch underneath us.
    const onVisibility = () => {
      if (document.visibilityState === 'visible') load();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisibility);
    };
    // `agentWorking` going false is the end of a turn, when the counts move.
  }, [machineId, cwd, agentWorking]);

  return summary;
}

function useMachineName(machineId: string | null): string | null {
  const { api } = useAgentDashboard();
  const { data } = useSWR<MachineSummary[]>(
    machineId && api ? 'session-summary:machines' : null,
    () => api!.listMachines(),
    { shouldRetryOnError: false, revalidateOnFocus: false },
  );
  const machine = data?.find((m) => m.machine_id === machineId);
  return machine ? machineDisplayName(machine) : null;
}

/** The task this session works on, as the viewer may see it (none when they can't). */
function useLinkedTask(taskId: string | null, messageCount: number): TaskResponse | null {
  const { api } = useAgentDashboard();
  const [task, setTask] = useState<TaskResponse | null>(null);
  // The task last fetched: the first fetch of a task goes at once, later ones
  // wait for the transcript to settle.
  const fetchedFor = useRef<string | null>(null);

  useEffect(() => {
    setTask(null);
  }, [taskId]);

  useEffect(() => {
    if (!api || !taskId) return;
    let cancelled = false;
    const load = () => {
      api
        .getTask(taskId)
        .then((row) => {
          if (cancelled) return;
          fetchedFor.current = taskId;
          setTask(row);
        })
        .catch((err: unknown) => {
          // Gone, or not the viewer's to see: nothing to show. Anything else
          // (offline, a 500) keeps the last answer.
          const status = (err as Partial<BackendApiError>).status;
          if (!cancelled && (status === 403 || status === 404)) setTask(null);
        });
    };
    const delay = fetchedFor.current === taskId ? REFETCH_DEBOUNCE_MS : 0;
    const timer = window.setTimeout(load, delay);
    window.addEventListener('focus', load);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.removeEventListener('focus', load);
    };
  }, [api, taskId, messageCount]);

  return task;
}

/**
 * The tasks a session created (`vicoa task create` run inside it), filtered
 * by the server through the same task lens as the board.
 */
function useCreatedTasks(instanceId: string, messageCount: number): TaskResponse[] {
  const { api } = useAgentDashboard();
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const fetchedFor = useRef<string | null>(null);

  useEffect(() => {
    setTasks([]);
  }, [instanceId]);

  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    const load = () => {
      api
        .listTasks({ createdInInstanceId: instanceId })
        .then((rows) => {
          if (cancelled) return;
          fetchedFor.current = instanceId;
          setTasks(rows);
        })
        // Provenance is a nicety: a failed fetch keeps the last list.
        .catch(() => {});
    };
    const delay = fetchedFor.current === instanceId ? REFETCH_DEBOUNCE_MS : 0;
    const timer = window.setTimeout(load, delay);
    window.addEventListener('focus', load);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.removeEventListener('focus', load);
    };
  }, [api, instanceId, messageCount]);

  return tasks;
}
