'use client';

/**
 * Per-project Settings pane, shared by the web settings page and the desktop
 * settings surface. Routed by project id (`?tab=project&projectId=`); the
 * `section` param picks a tab:
 *
 *   General         Display (name / icon) · Folders (one row per machine) ·
 *                   Danger zone (archive / delete)
 *   Git & Worktree  Worktree hooks, bound to one linked folder
 *   Tasks           Task key prefix · pointer to the labels
 *
 * The pane owns the project row and the machine list; sub-sections mutate
 * through the API and hand the server's row back via `onUpdated`, so the
 * header, the nav and the other tabs see one truth. Labels are deliberately
 * not here: they are the user's vocabulary across every project, managed under
 * Settings → Tasks.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ChevronRight, Circle, GitBranch, Loader2, Plus, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { DirectoryPickerPopover } from '@/components/dashboard/directory-picker-popover';
import { ProjectDisplaySection } from '@/components/dashboard/project-display-section';
import { ConfirmDeleteDialog } from '@/components/dashboard/session-dialogs';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import { WorktreeSetupSection } from '@/components/dashboard/worktree-setup-section';
import {
  getBackendAPI,
  type MachineSummary,
  type ProjectResponse,
  type ProjectSummaryResponse,
} from '@/lib/backend-api';
import { ensureLocalMachineId } from '@/lib/local-machine';
import { machineDisplayName } from '@/lib/machine-display';
import { getDesktopConfig } from '@/lib/runtime-config';
import {
  PROJECT_SETTINGS_SECTIONS,
  notifyProjectsChanged,
  type ProjectSettingsSection,
} from '@/lib/project-settings-route';
import { isMachineOnline } from '@/lib/session-liveness';
import { cn } from '@/lib/utils';

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="divide-y divide-border/50 overflow-hidden rounded-xl border border-border/60 bg-foreground/[0.03]">
      {children}
    </div>
  );
}

function SectionHeading({ title, description }: { title: string; description?: React.ReactNode }) {
  return (
    <div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && <p className="text-xs text-muted-foreground">{description}</p>}
    </div>
  );
}

export function ProjectSettingsPane({
  projectId,
  section,
  onSectionChange,
  onProjectDeleted,
}: {
  projectId: string;
  section: ProjectSettingsSection;
  onSectionChange: (section: ProjectSettingsSection) => void;
  /** The project is gone — the caller navigates away. */
  onProjectDeleted: () => void;
}) {
  // undefined = loading, null = not found (deleted, or not visible to us).
  const [project, setProject] = useState<ProjectResponse | null | undefined>(undefined);
  const [machines, setMachines] = useState<MachineSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    setProject(undefined);
    const api = getBackendAPI(true);
    // Two independent loads: a machine-list failure (offline daemon, cloud
    // hiccup) must not blank the whole pane — only the folder pickers need it.
    api
      .listProjects(true)
      .then((list) => {
        if (!cancelled) setProject(list.find((p) => p.id === projectId) ?? null);
      })
      .catch(() => {
        if (!cancelled) setProject(null);
      });
    api
      .listMachines()
      .then((list) => {
        if (!cancelled) setMachines(list);
      })
      .catch((err) => console.error('Failed to load machines:', err));
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Every mutation lands here: the pane re-renders from the server's row and
  // the settings nav (which keeps its own list) is told to refetch.
  const onUpdated = useCallback((next: ProjectResponse) => {
    setProject(next);
    notifyProjectsChanged();
  }, []);

  if (project === undefined) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading project…
      </div>
    );
  }

  if (project === null) {
    return (
      <p className="text-sm text-muted-foreground">
        This project no longer exists. Pick another one from the list.
      </p>
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <ProjectIcon project={project} className="size-8 rounded-md" />
        <h1 className="min-w-0 truncate text-2xl font-light tracking-tight text-foreground">
          {project.name}
        </h1>
        {project.is_archived && (
          <span className="shrink-0 rounded border border-border/70 bg-foreground/[0.06] px-1.5 py-px text-[10px] uppercase tracking-wider text-muted-foreground">
            Archived
          </span>
        )}
      </div>

      <div role="tablist" className="flex gap-1 border-b border-border/60">
        {PROJECT_SETTINGS_SECTIONS.map((entry) => {
          const active = entry.id === section;
          return (
            <button
              key={entry.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onSectionChange(entry.id)}
              className={cn(
                '-mb-px cursor-pointer border-b-2 px-3 py-2 text-xs transition-colors',
                active
                  ? 'border-foreground text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              {entry.label}
            </button>
          );
        })}
      </div>

      {section === 'general' ? (
        <GeneralTab
          project={project}
          machines={machines}
          onUpdated={onUpdated}
          onDeleted={() => {
            notifyProjectsChanged();
            onProjectDeleted();
          }}
        />
      ) : section === 'worktree' ? (
        <WorktreeTab
          project={project}
          machines={machines}
          onGoToGeneral={() => onSectionChange('general')}
        />
      ) : (
        <TasksTab project={project} onUpdated={onUpdated} />
      )}
    </section>
  );
}

// --- General ------------------------------------------------------------------

function GeneralTab({
  project,
  machines,
  onUpdated,
  onDeleted,
}: {
  project: ProjectResponse;
  machines: MachineSummary[];
  onUpdated: (project: ProjectResponse) => void;
  onDeleted: () => void;
}) {
  return (
    <div className="flex flex-col gap-8">
      <ProjectDisplaySection project={project} onUpdated={onUpdated} />
      <FoldersSection project={project} machines={machines} onUpdated={onUpdated} />
      <DangerZone project={project} onUpdated={onUpdated} onDeleted={onDeleted} />
    </div>
  );
}

function FoldersSection({
  project,
  machines,
  onUpdated,
}: {
  project: ProjectResponse;
  machines: MachineSummary[];
  onUpdated: (project: ProjectResponse) => void;
}) {
  const api = getBackendAPI(true);
  const [error, setError] = useState<string | null>(null);

  const linkedMachineIds = new Set(project.directories.map((d) => d.machine_id));
  const unlinkedMachines = machines.filter((m) => !linkedMachineIds.has(m.machine_id));

  const setDirectory = async (machineId: string, localPath: string) => {
    setError(null);
    try {
      onUpdated(await api.setProjectDirectory(project.id, { machine_id: machineId, local_path: localPath }));
    } catch (err) {
      console.error('Failed to link the folder:', err);
      setError(err instanceof Error ? err.message : 'Failed to link the folder');
    }
  };

  const removeDirectory = async (machineId: string) => {
    setError(null);
    try {
      onUpdated(await api.deleteProjectDirectory(project.id, machineId));
    } catch (err) {
      console.error('Failed to unlink the folder:', err);
      setError(err instanceof Error ? err.message : 'Failed to unlink the folder');
    }
  };

  return (
    <div className="space-y-3">
      <SectionHeading
        title="Folders"
        description={
          <>
            Where this project lives on each machine. Sessions started from its tasks open
            there, and <span className="font-mono">@</span> file search in task descriptions
            reads from it.
          </>
        }
      />
      <SectionCard>
        {project.directories.map((directory) => {
          const machine = machines.find((m) => m.machine_id === directory.machine_id);
          const name = directory.machine_name ?? (machine ? machineDisplayName(machine) : 'Unknown machine');
          return (
            <div key={directory.machine_id} className="flex items-center gap-2 px-3 py-2">
              <span className="w-32 shrink-0 truncate text-xs text-muted-foreground" title={name}>
                {name}
              </span>
              <DirectoryPickerPopover
                value={directory.local_path}
                onChange={(path) => void setDirectory(directory.machine_id, path)}
                recentDirectories={machine?.recent_directories ?? []}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 cursor-pointer truncate rounded-md px-2 py-1 text-left font-mono text-xs transition-colors hover:bg-accent"
                >
                  {directory.local_path}
                </button>
              </DirectoryPickerPopover>
              <button
                type="button"
                aria-label={`Unlink folder on ${name}`}
                title="Unlink folder"
                onClick={() => void removeDirectory(directory.machine_id)}
                className="shrink-0 cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
              >
                <X className="size-3.5" />
              </button>
            </div>
          );
        })}

        {unlinkedMachines.length > 0 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex w-full cursor-pointer items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
              >
                <Plus className="size-3.5" />
                Link a folder on…
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-56 font-mono text-xs">
              {unlinkedMachines.map((machine) => {
                const online = isMachineOnline(machine);
                return (
                  <DropdownMenuItem
                    key={machine.machine_id}
                    className="cursor-pointer text-xs"
                    onSelect={() =>
                      // Seed with the machine's most recent directory; the row's
                      // picker is where the real path gets chosen.
                      void setDirectory(
                        machine.machine_id,
                        machine.recent_directories[0] ?? machine.home_dir ?? '~/',
                      )
                    }
                  >
                    <Circle
                      className={cn(
                        'size-2 shrink-0',
                        online
                          ? 'fill-green-500 text-green-500'
                          : 'fill-muted-foreground/40 text-muted-foreground/40',
                      )}
                    />
                    <span className="truncate">{machineDisplayName(machine)}</span>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : machines.length === 0 ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            No machines connected. Run <span className="font-mono">vicoa daemon</span> to connect
            one.
          </p>
        ) : null}
      </SectionCard>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

function DangerZone({
  project,
  onUpdated,
  onDeleted,
}: {
  project: ProjectResponse;
  onUpdated: (project: ProjectResponse) => void;
  onDeleted: () => void;
}) {
  const api = getBackendAPI(true);
  const [archiving, setArchiving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [summary, setSummary] = useState<ProjectSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggleArchive = async () => {
    if (archiving) return;
    setArchiving(true);
    setError(null);
    try {
      onUpdated(await api.updateProject(project.id, { is_archived: !project.is_archived }));
    } catch (err) {
      console.error('Failed to archive project:', err);
      setError(err instanceof Error ? err.message : 'Failed to update project');
    } finally {
      setArchiving(false);
    }
  };

  const openDelete = () => {
    setSummary(null);
    setError(null);
    setConfirming(true);
    // Counts are a courtesy; the dialog reads fine without them.
    api
      .getProjectSummary(project.id)
      .then(setSummary)
      .catch(() => setSummary(null));
  };

  const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? '' : 's'}`;
  const consequence = summary
    ? `${plural(summary.task_count, 'task')} and ${plural(summary.session_count, 'session')} move to No project`
    : 'Its tasks and sessions move to No project';

  return (
    <div className="space-y-3">
      <SectionHeading title="Danger zone" />
      <SectionCard>
        <div className="flex items-center justify-between gap-4 px-4 py-3">
          <div className="min-w-0 space-y-0.5">
            <p className="text-sm text-foreground">
              {project.is_archived ? 'Unarchive this project' : 'Archive this project'}
            </p>
            <p className="text-xs text-muted-foreground">
              {project.is_archived
                ? 'Show it in the sidebar and Tasks board again.'
                : 'Hide it from the sidebar and Tasks board. Its tasks and sessions stay attached, and it comes back the next time you start a session here.'}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 cursor-pointer"
            disabled={archiving}
            onClick={() => void toggleArchive()}
          >
            {archiving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : project.is_archived ? (
              'Unarchive'
            ) : (
              'Archive'
            )}
          </Button>
        </div>
        <div className="flex items-center justify-between gap-4 px-4 py-3">
          <div className="min-w-0 space-y-0.5">
            <p className="text-sm text-foreground">Delete this project</p>
            <p className="text-xs text-muted-foreground">
              Its tasks and sessions move to No project and shares are revoked. This can&apos;t be
              undone.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 cursor-pointer text-destructive hover:text-destructive"
            onClick={openDelete}
          >
            Delete…
          </Button>
        </div>
      </SectionCard>
      {error && <p className="text-xs text-destructive">{error}</p>}

      <ConfirmDeleteDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Delete project"
        description={`Remove this project. ${consequence} (tasks lose their KEY-n ids), shares are revoked. This can't be undone.`}
        subject={
          <div className="flex items-center gap-2">
            <ProjectIcon project={project} />
            <span className="truncate text-sm font-medium">{project.name}</span>
          </div>
        }
        onConfirm={async () => {
          try {
            await api.deleteProject(project.id);
          } catch (err) {
            console.error('Failed to delete project:', err);
            setError(err instanceof Error ? err.message : 'Failed to delete project');
            throw err;
          }
          onDeleted();
        }}
      />
    </div>
  );
}

// --- Git & Worktree -----------------------------------------------------------

function WorktreeTab({
  project,
  machines,
  onGoToGeneral,
}: {
  project: ProjectResponse;
  machines: MachineSummary[];
  onGoToGeneral: () => void;
}) {
  const rows = project.directories;
  const [localMachineId, setLocalMachineId] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);

  // Desktop: prefer this computer's folder — that's the daemon the file RPC
  // is cheapest to route to, and the repo the user is looking at.
  useEffect(() => {
    if (getDesktopConfig()) void ensureLocalMachineId().then(setLocalMachineId);
  }, []);

  const defaultMachineId = useMemo(() => {
    if (rows.length === 0) return null;
    if (localMachineId && rows.some((r) => r.machine_id === localMachineId)) return localMachineId;
    const online = rows.find((r) => isMachineOnline(machines.find((m) => m.machine_id === r.machine_id)));
    return (online ?? rows[0]).machine_id;
  }, [rows, localMachineId, machines]);

  const machineId = chosen && rows.some((r) => r.machine_id === chosen) ? chosen : defaultMachineId;
  const row = rows.find((r) => r.machine_id === machineId) ?? null;
  const rowName = (r: ProjectResponse['directories'][number]) => {
    const machine = machines.find((m) => m.machine_id === r.machine_id);
    return r.machine_name ?? (machine ? machineDisplayName(machine) : 'Unknown machine');
  };

  if (!row) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 shrink-0 text-muted-foreground" />
          <h2 className="text-sm font-medium text-foreground">Worktree hooks</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Worktree hooks live in the repo (<code className="font-mono text-xs">.vicoa/config.json</code>),
          so this project needs a folder on one of your machines first.
        </p>
        <div>
          <Button variant="outline" size="sm" className="cursor-pointer" onClick={onGoToGeneral}>
            Link a folder in General
            <ChevronRight className="ml-1 h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {rows.length > 1 && (
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <p className="text-sm text-foreground">Machine</p>
            <p className="text-xs text-muted-foreground">
              The config is read from and written to this machine&apos;s checkout.
            </p>
          </div>
          <Select value={row.machine_id} onValueChange={setChosen}>
            <SelectTrigger
              aria-label="Machine"
              className="h-7 w-auto gap-1.5 border-border/70 bg-foreground/[0.06] px-2.5 py-0 text-xs shadow-none focus:ring-0 focus:ring-offset-0"
            >
              <SelectValue>{rowName(row)}</SelectValue>
            </SelectTrigger>
            <SelectContent align="end" className="bg-menu font-mono">
              {rows.map((r) => (
                <SelectItem
                  key={r.machine_id}
                  value={r.machine_id}
                  className="cursor-pointer text-xs focus:bg-foreground/[0.06] dark:focus:bg-foreground/10 focus:text-foreground"
                >
                  {rowName(r)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {project.git_remote_url && (
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-foreground">Remote</p>
          <span className="min-w-0 truncate font-mono text-xs text-muted-foreground" title={project.git_remote_url}>
            {project.git_remote_url}
          </span>
        </div>
      )}

      {/* Keyed so switching machines remounts the editor with a fresh load. */}
      <WorktreeSetupSection key={`${row.machine_id}:${row.local_path}`} machineId={row.machine_id} dir={row.local_path} />
    </div>
  );
}

// --- Tasks --------------------------------------------------------------------

const KEY_PATTERN = /^[A-Z][A-Z0-9]{1,7}$/;

function TasksTab({
  project,
  onUpdated,
}: {
  project: ProjectResponse;
  onUpdated: (project: ProjectResponse) => void;
}) {
  const api = getBackendAPI(true);
  const [key, setKey] = useState(project.key ?? '');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => setKey(project.key ?? ''), [project.key]);

  const commitKey = async () => {
    const next = key.trim().toUpperCase();
    setKey(next);
    if (!next || next === project.key) {
      setKey(project.key ?? '');
      setError(null);
      return;
    }
    if (!KEY_PATTERN.test(next)) {
      setError('2–8 letters and digits, starting with a letter.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onUpdated(await api.updateProject(project.id, { key: next }));
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(
        status === 409
          ? 'That key is already used by another project.'
          : err instanceof Error
            ? err.message
            : 'Failed to update the key',
      );
    } finally {
      setSaving(false);
    }
  };

  // Null until the project's first task — the backend derives one then.
  const unset = project.key === null;

  return (
    <div className="flex flex-col gap-8">
      <div className="space-y-3">
        <SectionHeading
          title="Task key"
          description="The prefix in this project's task identifiers — VIC makes them read VIC-42. Changing it renames every task."
        />
        <div className="flex items-center gap-3">
          <Label htmlFor="project-key" className="sr-only">
            Task key
          </Label>
          <input
            id="project-key"
            value={key}
            disabled={unset || saving}
            maxLength={8}
            spellCheck={false}
            autoCapitalize="characters"
            placeholder={unset ? 'Set on the first task' : 'KEY'}
            onChange={(e) => {
              setKey(e.target.value.toUpperCase());
              setError(null);
            }}
            onBlur={() => void commitKey()}
            onKeyDown={(e) => {
              if (e.key === 'Enter') e.currentTarget.blur();
              if (e.key === 'Escape') {
                setKey(project.key ?? '');
                setError(null);
                e.currentTarget.blur();
              }
            }}
            className="h-9 w-32 rounded-md border bg-transparent px-2.5 font-mono text-sm uppercase outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-60"
            aria-label="Task key"
          />
          {saving && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          {!saving && project.key && (
            <span className="text-xs text-muted-foreground">
              e.g. <span className="font-mono">{project.key}-42</span>
            </span>
          )}
        </div>
        {unset && (
          <p className="text-xs text-muted-foreground">
            Assigned automatically when this project gets its first task.
          </p>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>

      <div className="space-y-3">
        <SectionHeading title="Labels" />
        <SectionCard>
          <div className="flex items-center justify-between gap-4 px-4 py-3">
            <p className="text-xs text-muted-foreground">
              Labels are shared across all your projects.
            </p>
            <Link
              href="/dashboard/settings?tab=tasks"
              className="flex shrink-0 items-center gap-1 text-xs text-foreground/80 underline-offset-4 hover:underline"
            >
              Manage labels
              <ChevronRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
