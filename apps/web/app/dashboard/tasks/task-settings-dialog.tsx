'use client';

// Projects + labels management, opened from the gear in the Tasks header.
// Deliberately a dialog rather than a route: /dashboard/settings is
// account-level (Profile / Billing / Account) and has a separate desktop nav
// shell, so putting workspace vocabulary there would mean maintaining two nav
// surfaces for something you only ever reach from the board.

import { useCallback, useEffect, useState } from 'react';
import {
  ChevronRight,
  Circle,
  FolderOpen,
  Loader2,
  MoreHorizontal,
  Plus,
  Settings,
  Trash2,
  X,
} from 'lucide-react';

import { isMachineOnline } from '@/lib/session-liveness';
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
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { EmojiPicker } from '@/components/ui/emoji-picker';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { DirectoryPickerPopover } from '@/components/dashboard/directory-picker-popover';
import { INLINE_LABEL_COLORS, LabelChip, ProjectIcon } from '@/components/dashboard/task-ui';
import {
  MachineSummary,
  ProjectResponse,
  TaskLabelResponse,
} from '@/lib/backend-api';
import { cn } from '@/lib/utils';

type Tab = 'projects' | 'labels';

const TABS: { id: Tab; label: string }[] = [
  { id: 'projects', label: 'Projects' },
  { id: 'labels', label: 'Labels' },
];

export interface TaskSettingsHandlers {
  updateProject: (
    projectId: string,
    patch: { name?: string; icon?: string | null; is_archived?: boolean },
  ) => Promise<void>;
  deleteProject: (project: ProjectResponse) => Promise<void>;
  setProjectDirectory: (
    projectId: string,
    machineId: string,
    localPath: string,
  ) => Promise<void>;
  removeProjectDirectory: (projectId: string, machineId: string) => Promise<void>;
  createLabel: (name: string) => Promise<TaskLabelResponse>;
  updateLabel: (labelId: string, patch: { name?: string; color?: string }) => Promise<void>;
  deleteLabel: (label: TaskLabelResponse) => Promise<void>;
}

export function TaskSettingsDialog({
  open,
  onClose,
  projects,
  labels,
  machines,
  handlers,
}: {
  open: boolean;
  onClose: () => void;
  projects: ProjectResponse[];
  labels: TaskLabelResponse[];
  machines: MachineSummary[];
  handlers: TaskSettingsHandlers;
}) {
  const [tab, setTab] = useState<Tab>('projects');
  // Held here, not in the tabs: `DialogContent` is `translate-x/y-[-50%]`, and a
  // transformed ancestor re-anchors `position: fixed` descendants to itself, so
  // a confirm dialog rendered inside it would size its backdrop to this dialog's
  // box instead of the viewport. As a sibling of <Dialog> it centers correctly
  // and, being later in DOM order at the same z-index, paints on top.
  const [confirming, setConfirming] = useState<
    { kind: 'project'; project: ProjectResponse } | { kind: 'label'; label: TaskLabelResponse } | null
  >(null);

  if (!open) return null;

  return (
    <>
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="flex h-[30rem] max-w-3xl flex-col gap-0 overflow-hidden p-0 sm:rounded-xl">
        <DialogTitle className="sr-only">Task settings</DialogTitle>

        <div className="flex shrink-0 items-center justify-between px-5 pb-2 pt-3">
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-muted-foreground">Tasks</span>
            <ChevronRight className="size-3 text-muted-foreground/50" />
            <span className="font-medium">Settings</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="cursor-pointer rounded-sm p-1.5 opacity-70 transition-all hover:bg-accent/60 hover:opacity-100"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1">
          {/* Left nav */}
          <nav className="w-36 shrink-0 space-y-0.5 border-r p-2">
            {TABS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                onClick={() => setTab(entry.id)}
                className={cn(
                  'w-full cursor-pointer rounded-md px-2.5 py-1.5 text-left text-xs transition-colors',
                  tab === entry.id
                    ? 'bg-accent font-medium text-foreground'
                    : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
                )}
              >
                {entry.label}
              </button>
            ))}
          </nav>

          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {tab === 'projects' ? (
              <ProjectsTab
                projects={projects}
                machines={machines}
                handlers={handlers}
                onRequestDelete={(project) => setConfirming({ kind: 'project', project })}
              />
            ) : (
              <LabelsTab
                labels={labels}
                handlers={handlers}
                onRequestDelete={(label) => setConfirming({ kind: 'label', label })}
              />
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>

    <ConfirmDeleteDialog
      open={confirming !== null}
      onOpenChange={(next) => { if (!next) setConfirming(null); }}
      title={confirming?.kind === 'label' ? 'Delete label' : 'Delete project'}
      description={
        confirming?.kind === 'label'
          ? 'Are you sure you want to delete this label? It will be removed from every task that uses it. This action cannot be undone.'
          : 'Are you sure you want to delete this project? Its tasks will be deleted with it. This action cannot be undone.'
      }
      subject={
        confirming?.kind === 'label' ? (
          <LabelChip label={confirming.label} />
        ) : confirming?.kind === 'project' ? (
          <div className="flex items-center gap-2">
            <ProjectIcon project={confirming.project} />
            <span className="truncate text-sm font-medium">{confirming.project.name}</span>
          </div>
        ) : null
      }
      onConfirm={async () => {
        if (confirming?.kind === 'label') await handlers.deleteLabel(confirming.label);
        else if (confirming?.kind === 'project') await handlers.deleteProject(confirming.project);
      }}
    />
    </>
  );
}

// --- Delete confirmation ----------------------------------------------------

/**
 * Destructive-action confirm, same shape as `DeleteSessionDialog` in
 * components/dashboard/session-dialogs.tsx: header + consequence copy, the
 * subject echoed in a muted card, Cancel / destructive Delete. Nests inside the
 * settings dialog — Radix gives each its own focus scope, so the settings
 * dialog stays open behind it and returns focus on close.
 */
function ConfirmDeleteDialog({
  open,
  onOpenChange,
  title,
  description,
  subject,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  /** Rendered in the muted card — the row being deleted. */
  subject: React.ReactNode;
  onConfirm: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);

  const handleDelete = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <DialogContent className="font-mono">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="rounded-md border bg-muted/50 p-3">{subject}</div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            className="text-destructive-foreground"
            onClick={() => void handleDelete()}
            disabled={busy}
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Delete'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Projects ---------------------------------------------------------------

function ProjectsTab({
  projects,
  machines,
  handlers,
  onRequestDelete,
}: {
  projects: ProjectResponse[];
  machines: MachineSummary[];
  handlers: TaskSettingsHandlers;
  onRequestDelete: (project: ProjectResponse) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-1">
      {projects.map((project) => (
        <ProjectRow
          key={project.id}
          project={project}
          machines={machines}
          handlers={handlers}
          expanded={expanded === project.id}
          onToggle={() => setExpanded((prev) => (prev === project.id ? null : project.id))}
          onRequestDelete={() => onRequestDelete(project)}
        />
      ))}
      <p className="px-2 pt-3 text-xs text-muted-foreground">
        Link a project to a folder and sessions started from its tasks open there, with
        <span className="font-mono"> @</span> file search in task descriptions.
      </p>
    </div>
  );
}

function ProjectRow({
  project,
  machines,
  handlers,
  expanded,
  onToggle,
  onRequestDelete,
}: {
  project: ProjectResponse;
  machines: MachineSummary[];
  handlers: TaskSettingsHandlers;
  expanded: boolean;
  onToggle: () => void;
  onRequestDelete: () => void;
}) {
  const [name, setName] = useState(project.name);
  const [iconPickerOpen, setIconPickerOpen] = useState(false);

  // Re-seed when the project is replaced by a server response.
  useEffect(() => setName(project.name), [project.name]);

  const commitName = () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === project.name) {
      setName(project.name);
      return;
    }
    void handlers.updateProject(project.id, { name: trimmed });
  };

  const linkedMachineIds = new Set(project.directories.map((d) => d.machine_id));
  const unlinkedMachines = machines.filter((m) => !linkedMachineIds.has(m.machine_id));

  return (
    <div className={cn('rounded-lg border', project.is_archived && 'opacity-60')}>
      <div className="flex items-center gap-2 px-2 py-1.5">
        <Popover open={iconPickerOpen} onOpenChange={setIconPickerOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={`Icon for ${project.name}`}
              className="flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-sm transition-colors hover:bg-accent"
            >
              <ProjectIcon project={project} />
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-auto p-0">
            <EmojiPicker
              onSelect={(emoji) => {
                setIconPickerOpen(false);
                void handlers.updateProject(project.id, { icon: emoji });
              }}
              onClear={
                project.icon
                  ? () => {
                      setIconPickerOpen(false);
                      void handlers.updateProject(project.id, { icon: null });
                    }
                  : undefined
              }
            />
          </PopoverContent>
        </Popover>

        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur();
            if (e.key === 'Escape') {
              setName(project.name);
              e.currentTarget.blur();
            }
          }}
          disabled={project.is_inbox}
          className={cn(
            'min-w-0 flex-1 rounded-md bg-transparent px-1.5 py-1 text-sm outline-none',
            project.is_inbox
              ? 'cursor-default text-muted-foreground'
              : 'hover:bg-accent/40 focus-visible:bg-accent/40',
          )}
        />

        {project.is_archived && (
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[0.65rem] uppercase tracking-wider text-muted-foreground">
            Archived
          </span>
        )}

        {/* Inbox is the "No project" bucket — it can't be renamed, archived,
            deleted, or linked to a folder (the backend rejects each). */}
        {!project.is_inbox && (
          <>
            <button
              type="button"
              onClick={onToggle}
              className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <FolderOpen className="size-3.5" />
              {project.directories.length > 0
                ? `${project.directories.length} folder${project.directories.length > 1 ? 's' : ''}`
                : 'Link folder'}
              <ChevronRight className={cn('size-3 transition-transform', expanded && 'rotate-90')} />
            </button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label={`Actions for ${project.name}`}
                  className="shrink-0 cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <MoreHorizontal className="size-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-40 text-xs">
                <DropdownMenuItem
                  onSelect={() =>
                    void handlers.updateProject(project.id, {
                      is_archived: !project.is_archived,
                    })
                  }
                >
                  {project.is_archived ? 'Unarchive' : 'Archive'}
                </DropdownMenuItem>
                <DropdownMenuItem variant="destructive" onSelect={onRequestDelete}>
                  <Trash2 className="mr-2 size-3.5" />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        )}
      </div>

      {expanded && !project.is_inbox && (
        <div className="space-y-1 border-t px-2 py-2">
          {project.directories.map((directory) => {
            const machine = machines.find((m) => m.machine_id === directory.machine_id);
            return (
              <div key={directory.machine_id} className="flex items-center gap-2">
                <span className="w-28 shrink-0 truncate text-xs text-muted-foreground">
                  {directory.machine_name ?? machine?.display_name ?? 'Unknown machine'}
                </span>
                <DirectoryPickerPopover
                  value={directory.local_path}
                  onChange={(path) =>
                    void handlers.setProjectDirectory(project.id, directory.machine_id, path)
                  }
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
                  aria-label="Remove folder"
                  onClick={() =>
                    void handlers.removeProjectDirectory(project.id, directory.machine_id)
                  }
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
                  className="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <Plus className="size-3.5" />
                  Link a folder
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-56 text-xs">
                {unlinkedMachines.map((machine) => {
                  const online = isMachineOnline(machine);
                  return (
                    <DropdownMenuItem
                      key={machine.machine_id}
                      onSelect={() =>
                        void handlers.setProjectDirectory(
                          project.id,
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
                      <span className="truncate">
                        {machine.display_name ?? machine.hostname ?? 'Machine'}
                      </span>
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            machines.length === 0 && (
              <p className="px-2 py-1 text-xs text-muted-foreground">
                No machines connected. Run <span className="font-mono">vicoa daemon</span> to
                connect one.
              </p>
            )
          )}
        </div>
      )}
    </div>
  );
}

// --- Labels -----------------------------------------------------------------

function LabelsTab({
  labels,
  handlers,
  onRequestDelete,
}: {
  labels: TaskLabelResponse[];
  handlers: TaskSettingsHandlers;
  onRequestDelete: (label: TaskLabelResponse) => void;
}) {
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const create = useCallback(async () => {
    const trimmed = newName.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    try {
      await handlers.createLabel(trimmed);
      setNewName('');
    } catch (err) {
      console.error('Failed to create label:', err);
    } finally {
      setCreating(false);
    }
  }, [newName, creating, handlers]);

  return (
    <div className="space-y-1">
      {labels.map((label) => (
        <LabelRow
          key={label.id}
          label={label}
          handlers={handlers}
          onRequestDelete={() => onRequestDelete(label)}
        />
      ))}

      <div className="flex items-center gap-2 rounded-lg border border-dashed px-2 py-1.5">
        {creating ? (
          <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
        ) : (
          <Plus className="size-4 shrink-0 text-muted-foreground" />
        )}
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void create();
            }
          }}
          placeholder="New label…"
          className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
        />
      </div>
    </div>
  );
}

function LabelRow({
  label,
  handlers,
  onRequestDelete,
}: {
  label: TaskLabelResponse;
  handlers: TaskSettingsHandlers;
  onRequestDelete: () => void;
}) {
  const [name, setName] = useState(label.name);
  const [colorOpen, setColorOpen] = useState(false);

  useEffect(() => setName(label.name), [label.name]);

  const commitName = () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === label.name) {
      setName(label.name);
      return;
    }
    void handlers.updateLabel(label.id, { name: trimmed });
  };

  return (
    <div className="flex items-center gap-2 rounded-lg border px-2 py-1.5">
      <Popover open={colorOpen} onOpenChange={setColorOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={`Color for ${label.name}`}
            style={{ backgroundColor: label.color }}
            className="size-4 shrink-0 cursor-pointer rounded-full ring-offset-2 ring-offset-popover transition-shadow hover:ring-2 hover:ring-ring/50"
          />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-auto p-2">
          <div className="grid grid-cols-5 gap-1.5">
            {INLINE_LABEL_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                aria-label={color}
                style={{ backgroundColor: color }}
                onClick={() => {
                  setColorOpen(false);
                  void handlers.updateLabel(label.id, { color });
                }}
                className={cn(
                  'size-6 cursor-pointer rounded-full transition-transform hover:scale-110',
                  color === label.color && 'ring-2 ring-ring ring-offset-2 ring-offset-popover',
                )}
              />
            ))}
          </div>
        </PopoverContent>
      </Popover>

      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={commitName}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur();
          if (e.key === 'Escape') {
            setName(label.name);
            e.currentTarget.blur();
          }
        }}
        className="min-w-0 flex-1 rounded-md bg-transparent px-1.5 py-1 text-sm outline-none hover:bg-accent/40 focus-visible:bg-accent/40"
      />

      <LabelChip label={label} />

      <button
        type="button"
        aria-label={`Delete ${label.name}`}
        onClick={onRequestDelete}
        className="shrink-0 cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}

/** Gear trigger for the Tasks page header. */
export function TaskSettingsButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-7 w-7 p-0 text-muted-foreground"
      onClick={onClick}
      aria-label="Task settings"
      title="Projects & labels"
    >
      <Settings className="size-3.5" />
    </Button>
  );
}
