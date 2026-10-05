'use client';

import { useEffect, useMemo, useState } from 'react';
import { Check, ChevronDown, Circle, GitBranch, Folder } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { DirectoryPickerPopover } from '@/components/dashboard/directory-picker-popover';
import { WorktreePickerPopover } from '@/components/dashboard/worktree-picker-popover';
import { SessionConfigEditor } from '@/components/dashboard/session-config-editor';
import { rpcGitStatus } from '@/components/files-git-panel/rpc';
import { RpcError } from '@/lib/ws-client';
import { isMachineOnline } from '@/lib/session-liveness';
import { machineSupportsWorktree, type WorktreeMode } from '@/lib/worktree-selection';
import type { AgentCatalog, SessionConfig } from '@/lib/agent-catalog';
import type { AgentProfile, MachineSummary, ProjectResponse } from '@/lib/backend-api';
import {
  directoryChipLabel,
  projectsOnMachine,
  resolveProjectForDirectory,
} from '@/lib/project-paths';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { agentPrincipal } from '@/lib/use-agent-profiles';
import { FieldGroup, FieldRow } from './field-row';

export interface WorktreeDraft {
  mode: WorktreeMode;
  path: string | null;
  branch?: string | null;
}

const VALUE_TRIGGER =
  'flex h-7 max-w-full items-center gap-1.5 rounded-lg px-2 text-sm text-foreground/90 transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 disabled:opacity-50';

function machineLabel(m: MachineSummary): string {
  return m.display_name || m.hostname || `Machine ${m.machine_id.slice(0, 6)}`;
}

function worktreeLabel(w: WorktreeDraft): string {
  if (w.mode === 'new') return 'New worktree each run';
  if (w.mode === 'existing') {
    return w.branch || w.path?.split('/').filter(Boolean).pop() || 'Worktree';
  }
  return 'No worktree';
}

export function DetailsSection({
  machines,
  projects,
  machineId,
  onMachineChange,
  directory,
  onDirectoryChange,
  worktree,
  onWorktreeChange,
  sessionConfig,
  onSessionConfigChange,
  agentProfiles,
  agentProfileId,
  onAgentProfileChange,
  catalog,
}: {
  machines: MachineSummary[];
  /** Every project the user can see; the picker lists the ones linked to a
   *  folder on the selected machine, like the new-session picker. */
  projects: ProjectResponse[];
  machineId: string;
  onMachineChange: (id: string) => void;
  directory: string;
  onDirectoryChange: (dir: string) => void;
  worktree: WorktreeDraft;
  onWorktreeChange: (w: WorktreeDraft) => void;
  sessionConfig: SessionConfig;
  onSessionConfigChange: (c: SessionConfig) => void;
  agentProfiles: AgentProfile[];
  /** Set ⇒ this automation follows a saved agent, resolved at dispatch. */
  agentProfileId: string | null;
  onAgentProfileChange: (profile: AgentProfile | null) => void;
  catalog: AgentCatalog;
}) {
  const selected = machines.find((m) => m.machine_id === machineId);
  const online = selected ? isMachineOnline(selected) : false;
  const worktreeSupported = selected ? machineSupportsWorktree(selected) : false;

  // Whether the working folder is a git repo — worktrees are meaningless in a
  // plain folder, so this gates the worktree chip. `null` means unknown (offline
  // machine or a failed probe) and keeps the chip visible, so a transport
  // hiccup can't strip the option off a real repo; only the daemon's definitive
  // `not_a_repo` hides it. Mirrors the new-session page.
  const [isGitRepo, setIsGitRepo] = useState<boolean | null>(null);
  useEffect(() => {
    const cwd = directory.trim();
    if (!machineId || !cwd || !online) {
      setIsGitRepo(null);
      return;
    }
    let cancelled = false;
    rpcGitStatus(machineId, cwd)
      .then(() => {
        if (!cancelled) setIsGitRepo(true);
      })
      .catch((e) => {
        if (cancelled) return;
        setIsGitRepo(e instanceof RpcError && e.code === 'not_a_repo' ? false : null);
      });
    return () => {
      cancelled = true;
    };
  }, [machineId, directory, online]);

  const selectedProfile = agentProfiles.find((p) => p.id === agentProfileId) ?? null;

  // Project-first, as on the new-session page: the picker lists the projects
  // linked to a folder on this machine, and the chip names the project the
  // folder falls under (`vicoa · apps/web` for a subfolder), or the folder's
  // own name when no project claims it yet.
  const pickerProjects = useMemo(
    () => (machineId ? projectsOnMachine(projects, machineId) : []),
    [projects, machineId],
  );
  const directoryProject = useMemo(
    () => resolveProjectForDirectory(directory, machineId, projects, selected?.home_dir),
    [directory, machineId, projects, selected?.home_dir],
  );
  const directoryLabel = directoryChipLabel(directory, directoryProject);

  return (
    <FieldGroup title="Details">
      {/* Runs on — machine dropdown opens below, flipping up only when cramped. */}
      <FieldRow label="Runs on">
        <DropdownMenu>
          <DropdownMenuTrigger asChild disabled={machines.length === 0}>
            <button type="button" className={VALUE_TRIGGER} title="Machine">
              {selected ? (
                <>
                  <span className="truncate">{machineLabel(selected)}</span>
                  <Circle
                    className={cn(
                      'h-1.5 w-1.5 flex-shrink-0',
                      online
                        ? 'fill-green-500 text-green-500'
                        : 'fill-muted-foreground/30 text-muted-foreground/30',
                    )}
                    strokeWidth={0}
                  />
                </>
              ) : (
                <span className="text-muted-foreground">No machines</span>
              )}
              <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64 rounded-xl font-mono">
            {machines.map((m) => {
              const isOnline = isMachineOnline(m);
              return (
                <DropdownMenuItem
                  key={m.machine_id}
                  onClick={() => onMachineChange(m.machine_id)}
                  className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-xs"
                >
                  <span
                    className={cn(
                      'inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full',
                      isOnline ? 'bg-green-500' : 'bg-muted-foreground/30',
                    )}
                  />
                  <span className={cn('flex-1 truncate', !isOnline && 'text-muted-foreground')}>
                    {machineLabel(m)}
                  </span>
                  {m.machine_id === machineId && (
                    <Check className="ml-auto h-3.5 w-3.5 flex-shrink-0" />
                  )}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      </FieldRow>

      {/* Project — working folder + optional worktree. */}
      <FieldRow label="Project">
        {/* Not gated on the machine being online (the new-session picker is):
            the machine an automation targets is often asleep while it's set up. */}
        <DirectoryPickerPopover
          value={directory}
          onChange={onDirectoryChange}
          projects={pickerProjects}
          selectedProjectId={directoryProject?.project.id ?? null}
          disabled={!selected}
        >
          <button
            type="button"
            title={directory.trim() || 'Project folder'}
            disabled={!selected}
            className={VALUE_TRIGGER}
          >
            {directoryProject ? (
              <ProjectIcon project={directoryProject.project} className="size-3.5" />
            ) : (
              <Folder className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
            )}
            <span className={cn('truncate', !directory.trim() && 'text-muted-foreground/60')}>
              {directoryLabel || 'Choose folder'}
            </span>
            <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
          </button>
        </DirectoryPickerPopover>

        {worktreeSupported && isGitRepo !== false && (
          <WorktreePickerPopover
            machineId={machineId}
            cwd={directory}
            mode={worktree.mode}
            selectedPath={worktree.path}
            onSelect={(mode, path, branch) => onWorktreeChange({ mode, path, branch })}
            disabled={!online || !directory.trim()}
          >
            <button
              type="button"
              title="Worktree"
              disabled={!online || !directory.trim()}
              className={VALUE_TRIGGER}
            >
              <GitBranch className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
              <span className="truncate">{worktreeLabel(worktree)}</span>
              <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
            </button>
          </WorktreePickerPopover>
        )}
      </FieldRow>

      {/* Agent — reuses the new-session config chips. When a saved agent is
          referenced the chips go read-only: an automation resolves its agent at
          dispatch, so the config shown must be the agent's, and "what will this
          run with?" needs exactly one answer. Unlinking is explicit rather than
          "editing any chip silently unlinks", which would quietly drop the live
          link the moment someone poked a value to see what it did. */}
      <FieldRow label="Agent" align="start">
        <div className="flex min-w-0 flex-col gap-1.5">
          {agentProfiles.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="flex h-6 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-xs text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground dark:hover:bg-foreground/10"
                  >
                    {selectedProfile ? (
                      <>
                        <PrincipalAvatar
                          principal={agentPrincipal(selectedProfile)}
                          size="xs"
                        />
                        <span className="min-w-0 truncate">{selectedProfile.name}</span>
                      </>
                    ) : (
                      <span>Use a saved agent</span>
                    )}
                    <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-56">
                  {agentProfiles.map((profile) => (
                    <DropdownMenuItem
                      key={profile.id}
                      onSelect={() => onAgentProfileChange(profile)}
                    >
                      {profile.name}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
              {selectedProfile && (
                <button
                  type="button"
                  onClick={() => onAgentProfileChange(null)}
                  className="cursor-pointer rounded-lg px-2 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  Unlink to customize
                </button>
              )}
            </div>
          )}
          <SessionConfigEditor
            value={sessionConfig}
            onChange={onSessionConfigChange}
            catalog={catalog}
            disabled={!!agentProfileId}
          />
          {selectedProfile && (
            <p className="text-xs text-muted-foreground">
              Follows {selectedProfile.name}. Editing that agent changes what the next
              run does.
            </p>
          )}
        </div>
      </FieldRow>
    </FieldGroup>
  );
}
