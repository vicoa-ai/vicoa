'use client';

// "Assign <task> to <agent>": the confirm step between picking an agent in a
// task's assignee picker and the agent starting work (plans/todos/task-
// assignment-agents.md, B1). Assigning an agent hands it the task, and that
// starts a session on one of your computers, so it says where first: the
// new-session page's computer and folder chips. There is no worktree chip: the
// session runs in the folder as it is, and the agent makes a worktree itself
// when the work changes code. Anything the agent should know belongs in the
// task itself; the dialog only confirms.
//
// Enter starts. "Assign only" records the agent as the assignee without
// starting anything. When the server can't place the run (no computer, no
// folder for this project, a team agent) it says why, and only "Assign only"
// is offered. "Don't ask again" turns the dialog off on this device
// (Settings → Tasks turns it back on); then picking an agent starts it with
// the defaults straight away (task-property-rail.tsx).

import { useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import { Check, Circle, CornerDownLeft, Folder, Monitor, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { DirectoryPickerPopover } from '@/components/dashboard/directory-picker-popover';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import {
  getBackendAPI,
  refusalReason,
  type AgentProfile,
  type MachineSummary,
  type TaskResponse,
  type TaskRunFields,
  type TaskRunTargetResponse,
} from '@/lib/backend-api';
import { setConfirmAgentStart } from '@/lib/assign-agent-pref';
import { directoryChipLabel, projectsOnMachine, resolveProjectForDirectory } from '@/lib/project-paths';
import { agentPrincipal } from '@/lib/use-agent-profiles';
import { useProjects } from '@/lib/use-projects';
import { cn } from '@/lib/utils';

/** The new-session page's setup chips (machine · directory). */
const SETUP_CHIP_CLASS =
  'flex h-7 min-w-0 items-center gap-1.5 rounded-lg bg-background dark:bg-menu px-2.5 text-xs font-mono text-foreground/90 transition-colors hover:bg-menu-elevated disabled:cursor-not-allowed disabled:opacity-50';

export function AssignAgentDialog({
  task,
  profile,
  onClose,
  onConfirm,
}: {
  task: Pick<TaskResponse, 'id' | 'status' | 'title' | 'identifier'>;
  /** The agent picked; null = closed. */
  profile: AgentProfile | null;
  onClose: () => void;
  /** The assignment PATCH, with the run fields. Reject to keep the dialog open. */
  onConfirm: (run: TaskRunFields) => Promise<void>;
}) {
  const open = profile !== null;
  const [target, setTarget] = useState<TaskRunTargetResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [machineId, setMachineId] = useState<string | null>(null);
  const [directory, setDirectory] = useState('');
  const [sending, setSending] = useState<false | 'start' | 'assign'>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [dontAskAgain, setDontAskAgain] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const startRef = useRef<HTMLButtonElement>(null);

  const profileId = profile?.id ?? null;
  useEffect(() => {
    if (!profileId) return;
    let cancelled = false;
    setTarget(null);
    setLoadError(null);
    setSubmitError(null);
    setDontAskAgain(false);
    getBackendAPI(true)
      .getTaskRunTarget(task.id, profileId)
      .then((result) => {
        if (cancelled) return;
        setTarget(result);
        setMachineId(result.machine_id);
        setDirectory(result.directory ?? '');
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(refusalReason(err) ?? "Couldn't check where it can run.");
      });
    return () => {
      cancelled = true;
    };
  }, [task.id, profileId]);

  // The full machine rows behind the candidates the server offered, for the
  // folder chip's label (the home dir).
  const { data: machineRows } = useSWR<MachineSummary[]>(
    open ? 'assign-agent-dialog:machines' : null,
    () => getBackendAPI(true).listMachines(),
    { shouldRetryOnError: false },
  );
  const { projects } = useProjects();

  const machines = useMemo(() => target?.machines ?? [], [target]);
  const selected = machines.find((m) => m.machine_id === machineId) ?? null;
  const selectedRow = machineRows?.find((m) => m.machine_id === machineId) ?? null;
  const online = selected?.online ?? false;

  const pickerProjects = useMemo(
    () => (machineId && projects ? projectsOnMachine(projects, machineId) : []),
    [projects, machineId],
  );
  const directoryProject = useMemo(
    () =>
      machineId && projects
        ? resolveProjectForDirectory(directory, machineId, projects, selectedRow?.home_dir)
        : null,
    [directory, machineId, projects, selectedRow?.home_dir],
  );
  const directoryLabel = directoryChipLabel(directory, directoryProject);

  const pickMachine = (id: string) => {
    setMachineId(id);
    // The folder follows the computer: this project's folder there, if any.
    setDirectory(machines.find((m) => m.machine_id === id)?.directory ?? '');
  };

  // The server's `problem` describes its own pick; once there are computers to
  // choose from, what matters is whether the user's choice is complete.
  const problem = (() => {
    if (!target) return null;
    if (machines.length === 0) return target.problem ?? 'No computer to run it on.';
    if (!machineId) return 'Pick a computer to run it on.';
    if (!directory.trim()) return `Pick a folder on ${selected?.name ?? 'that computer'}.`;
    return null;
  })();
  const waitsForBacklog = task.status === 'backlog';
  const closed = task.status === 'done' || task.status === 'cancelled';
  const canStart = !!target && problem === null && !closed;
  const agentName = profile?.name ?? 'the agent';

  const status = loadError
    ? loadError
    : submitError
      ? submitError
      : problem
        ? problem
        : closed
          ? 'The task is closed, so nothing starts until it is reopened.'
          : waitsForBacklog
            ? `The task is in Backlog: ${agentName} will work on it once you move it out.`
            : selected && !online
              ? `${selected.name} is offline. ${agentName} will work on it once it comes back online.`
              : null;
  const statusIsWarning = !!loadError || !!submitError || !!problem;

  // Once it can start, the Start button takes the focus, so Enter starts it as
  // Enter starts a new session. Deferred a beat: the assignee picker hands the
  // focus back to its trigger as it closes. Focus the user already moved into
  // the dialog (a chip) is left alone.
  useEffect(() => {
    if (!open || !canStart) return;
    const timer = window.setTimeout(() => {
      const content = contentRef.current;
      const active = document.activeElement;
      if (!content || (active && content.contains(active))) return;
      startRef.current?.focus();
    }, 50);
    return () => window.clearTimeout(timer);
  }, [open, canStart]);

  const submit = async (start: boolean) => {
    if (sending) return;
    if (start && !canStart) return;
    setSending(start ? 'start' : 'assign');
    setSubmitError(null);
    try {
      await onConfirm(
        start
          ? {
              start: true,
              run_target: { machine_id: machineId, directory: directory.trim() || null },
            }
          : { start: false },
      );
      if (dontAskAgain) setConfirmAgentStart(false);
      onClose();
    } catch (err) {
      setSubmitError(refusalReason(err) ?? "Couldn't assign it.");
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !sending && onClose()}>
      <DialogContent ref={contentRef} className="max-w-md gap-4 p-5">
        <DialogHeader className="space-y-1.5">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium">
            {profile && <PrincipalAvatar principal={agentPrincipal(profile)} size="sm" />}
            <span className="min-w-0 truncate">
              Assign {task.identifier ?? 'this task'} to {agentName}
            </span>
          </DialogTitle>
          <DialogDescription className="text-xs">
            {waitsForBacklog || closed
              ? `${agentName} becomes the assignee.`
              : `${agentName} will work on it and assign it back to you when it needs you.`}
          </DialogDescription>
        </DialogHeader>

        {!target && !loadError ? (
          <div className="flex items-center gap-2 py-2 font-mono text-xs text-muted-foreground">
            <RefreshCw className="size-3.5 animate-spin" />
            Finding where it can run…
          </div>
        ) : (
          <div className="min-w-0">
            {/* Setup chips: computer · folder, as on a new session. */}
            {machines.length > 0 && (
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button type="button" title="Computer" className={SETUP_CHIP_CLASS}>
                      <Monitor className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                      {selected ? (
                        <>
                          <span className="max-w-32 truncate">{selected.name}</span>
                          <Circle
                            className={cn(
                              'h-1.5 w-1.5 flex-shrink-0',
                              selected.online
                                ? 'fill-green-500 text-green-500'
                                : 'fill-muted-foreground/30 text-muted-foreground/30',
                            )}
                            strokeWidth={0}
                          />
                        </>
                      ) : (
                        <span className="text-muted-foreground">Choose computer</span>
                      )}
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-64 font-mono">
                    {machines.map((m) => (
                      <DropdownMenuItem
                        key={m.machine_id}
                        onClick={() => pickMachine(m.machine_id)}
                        className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-xs"
                      >
                        <span
                          className={cn(
                            'inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full',
                            m.online ? 'bg-green-500' : 'bg-muted-foreground/30',
                          )}
                        />
                        <span className={cn('flex-1 truncate', !m.online && 'text-muted-foreground')}>
                          {m.name}
                        </span>
                        {!m.directory && (
                          <span className="shrink-0 text-[10px] text-muted-foreground">no project folder</span>
                        )}
                        {m.machine_id === machineId && <Check className="h-3.5 w-3.5 flex-shrink-0" />}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>

                {/* Not gated on the computer being online: the run waits for it. */}
                <DirectoryPickerPopover
                  value={directory}
                  onChange={setDirectory}
                  projects={pickerProjects}
                  selectedProjectId={directoryProject?.project.id ?? null}
                  disabled={!selected}
                >
                  <button
                    type="button"
                    title={directory.trim() || 'Project folder'}
                    disabled={!selected}
                    className={SETUP_CHIP_CLASS}
                  >
                    {directoryProject ? (
                      <ProjectIcon project={directoryProject.project} className="size-3.5" />
                    ) : (
                      <Folder className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                    )}
                    <span className={cn('max-w-44 truncate', !directory.trim() && 'text-muted-foreground/60')}>
                      {directoryLabel || 'Choose folder'}
                    </span>
                  </button>
                </DirectoryPickerPopover>

              </div>
            )}

            {status && (
              <p
                className={cn(
                  'text-xs',
                  statusIsWarning ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground',
                )}
              >
                {status}
              </p>
            )}
          </div>
        )}

        <div className="flex items-center gap-2">
          <label className="mr-auto flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={dontAskAgain}
              onChange={(e) => setDontAskAgain(e.target.checked)}
              className="size-3.5 cursor-pointer accent-primary"
            />
            Don&apos;t ask again
          </label>
          {!waitsForBacklog && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void submit(false)}
              disabled={!!sending || !target}
              className="h-8 px-3 text-xs"
            >
              {sending === 'assign' && <RefreshCw className="size-3 animate-spin" />}
              Assign only
            </Button>
          )}
          <Button
            ref={startRef}
            size="sm"
            onClick={() => void submit(true)}
            disabled={!!sending || !canStart}
            className="h-8 gap-1.5 px-3 text-xs"
          >
            {sending === 'start' && <RefreshCw className="size-3 animate-spin" />}
            {waitsForBacklog ? 'Assign' : 'Start'}
            {!sending && <CornerDownLeft className="size-3 opacity-60" aria-hidden />}
          </Button>
        </div>
        {dontAskAgain && (
          <p className="-mt-2 text-[11px] text-muted-foreground/60">
            You can turn it back on in Settings → Tasks.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
