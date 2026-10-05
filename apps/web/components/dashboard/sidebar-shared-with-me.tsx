'use client';

// "Shared with me" (collaboration §8.4, P5): the sidebar group that holds
// other people's projects and sessions the signed-in user was given access to.
//
// It is read-only chrome on purpose. Its headers have no "+" (you cannot start
// a session on someone else's machine), no drag (the order is theirs to keep
// in their own sidebar) and no Archive; the owner's picture sits on the
// project icon so it never reads as one of your own. A session opens in the
// normal session page, which degrades itself to the viewer's role.
//
// "Add to sidebar" moves a shared project out of here and into the
// user's own project list, its sessions under the project's Team row. The list
// itself is `useSharedSessions`, owned by `SidebarSessions` so both places
// read one fetch.
//
// Mounted by `SidebarSessions`, which web and desktop both render, so this is
// the one implementation for both.

import { useMemo, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  CalendarClock,
  ChevronRight,
  ListTodo,
  LogOut,
  MoreHorizontal,
  PanelLeftOpen,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import { ConfirmDeleteDialog } from '@/components/dashboard/session-dialogs';
import { formatSidebarTime, getSessionTitle } from '@/components/dashboard/session-display';
import type BackendAPI from '@/lib/backend-api';
import type { AgentInstanceResponse, PrincipalResponse, ProjectResponse } from '@/lib/backend-api';
import { CLOSED_STATUSES } from '@/components/dashboard/session-grouping';
import { principalFromResponse } from '@/lib/principals';
import { canFollowProject, groupSharedWithMe } from '@/lib/shared-with-me';
import { sessionRowPeople } from '@/lib/session-people';
import { SessionRowAvatars } from '@/components/dashboard/session-participants';
import { cn } from '@/lib/utils';

const ITEM_SELECTED = 'bg-foreground/[0.08] dark:bg-foreground/10 text-foreground';

function sessionHref(instanceId: string): string {
  return `/dashboard/sessions/${instanceId}`;
}

function SharedSessionRow({
  instance,
  selected,
  onOpen,
}: {
  instance: AgentInstanceResponse;
  selected: boolean;
  onOpen: () => void;
}) {
  const done = CLOSED_STATUSES.has(instance.status);
  return (
    <Button
      variant="subtle"
      className={cn(
        'h-auto w-full cursor-pointer justify-start px-2 py-1.5 text-left',
        selected && ITEM_SELECTED,
        done && 'opacity-50',
      )}
      onClick={onOpen}
    >
      <span className="flex w-full min-w-0 items-center justify-between gap-1">
        <span className="flex min-w-0 items-center gap-1 truncate">
          <AgentTypeIcon agentTypeName={instance.agent_type_name ?? null} whiteForOpenAI />
          <span
            className={cn(
              'truncate text-xs font-normal',
              done ? 'text-muted-foreground/60' : 'text-foreground/80',
            )}
          >
            {getSessionTitle(instance)}
          </span>
        </span>
        <span className="flex min-w-[3rem] shrink-0 items-center justify-end gap-1.5 pl-2 text-[10px] text-muted-foreground">
          <SessionRowAvatars people={sessionRowPeople(instance)} />
          {formatSidebarTime(instance)}
        </span>
      </span>
    </Button>
  );
}

/**
 * A project icon with its owner's picture tucked into the corner, so someone
 * else's project never reads as one of your own — wherever it is listed.
 */
export function ProjectIconWithOwner({
  project,
  owner,
}: {
  project: Pick<ProjectResponse, 'id' | 'name'> & Partial<ProjectResponse>;
  owner: PrincipalResponse | null | undefined;
}) {
  const principal = principalFromResponse(owner ?? null);
  return (
    <span className="relative inline-flex shrink-0">
      <ProjectIcon project={project} className="size-4" />
      {principal && (
        <PrincipalAvatar
          principal={principal}
          size="xs"
          className="absolute -bottom-1 -right-1 size-2.5 ring-1 ring-background"
        />
      )}
    </span>
  );
}

/** "Leave <project>?" — drops the caller's own grant on a shared project. */
export function LeaveProjectDialog({
  api,
  project,
  onClose,
  onLeft,
}: {
  api: BackendAPI | null;
  project: ProjectResponse | null;
  onClose: () => void;
  onLeft: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const leave = async () => {
    if (!api || !project) return;
    setError(null);
    try {
      await api.leaveProject(project.id);
      onLeft();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to leave the project.');
    }
  };
  return (
    <>
      {error && <p className="px-2 text-[11px] text-destructive">{error}</p>}
      <ConfirmDeleteDialog
        open={project !== null}
        onOpenChange={(open) => {
          if (!open) onClose();
        }}
        title={`Leave ${project?.name ?? 'project'}?`}
        description="You lose access until someone shares it with you again."
        confirmLabel="Leave"
        onConfirm={leave}
      />
    </>
  );
}

export function SidebarSharedWithMe({
  api,
  instances,
  projectsById,
  onProjectsChanged,
  onSetFollowed,
}: {
  api: BackendAPI | null;
  /** `useSharedSessions` — every session shared with the user. */
  instances: AgentInstanceResponse[];
  /** The sidebar's own `listProjects(true)` result; shared ones carry `owner`. */
  projectsById: Map<string, ProjectResponse>;
  /** Refetch the project list and the shared sessions, after leaving one. */
  onProjectsChanged: () => void;
  /** List a shared project among the user's own (or take it out again). */
  onSetFollowed: (project: ProjectResponse, followed: boolean) => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [sectionCollapsed, setSectionCollapsed] = useState(false);
  const [leaving, setLeaving] = useState<ProjectResponse | null>(null);

  const groups = useMemo(
    () => groupSharedWithMe(instances, projectsById.values()),
    [instances, projectsById],
  );
  if (groups.length === 0) return null;

  const toggle = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className="mt-3 border-t border-border/40 pt-2">
      <button
        type="button"
        onClick={() => setSectionCollapsed((v) => !v)}
        aria-expanded={!sectionCollapsed}
        className="group/label flex w-full cursor-pointer items-center gap-1 px-2 py-1 text-left"
      >
        <span className="truncate text-[0.8rem] font-normal text-muted-foreground">Shared with me</span>
        <ChevronRight
          className={cn(
            'h-3 w-3 shrink-0 text-muted-foreground/50 transition-transform group-hover/label:text-muted-foreground',
            !sectionCollapsed && 'rotate-90',
          )}
        />
      </button>
      {!sectionCollapsed &&
        groups.map((group) => {
          const isCollapsed = collapsed.has(group.key);
          const project = group.project;
          const hasBoard = project?.scopes?.includes('tasks') ?? false;
          const ownerName = group.owner?.name?.trim();
          return (
            <div key={group.key} className="mb-1">
              <div className="group/label flex w-full items-center gap-1 px-2 py-1">
                <button
                  type="button"
                  onClick={() => toggle(group.key)}
                  aria-expanded={!isCollapsed}
                  title={ownerName ? `Shared by ${ownerName}` : undefined}
                  className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left"
                >
                  {group.kind === 'owner' ? (
                    <PrincipalAvatar
                      principal={principalFromResponse(group.owner) ?? { type: 'user' }}
                      size="xs"
                    />
                  ) : (
                    <ProjectIconWithOwner
                      project={project ?? { id: group.key, name: group.label }}
                      owner={group.owner}
                    />
                  )}
                  <span className="truncate text-[0.8rem] font-normal text-muted-foreground">
                    {group.label}
                  </span>
                  <ChevronRight
                    className={cn(
                      'h-3 w-3 shrink-0 text-muted-foreground/50 transition-transform group-hover/label:text-muted-foreground',
                      !isCollapsed && 'rotate-90',
                    )}
                  />
                </button>
                {project && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        title="Project actions"
                        aria-label="Project actions"
                        className="flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded text-muted-foreground opacity-0 transition-opacity hover:bg-muted-foreground/20 hover:text-foreground focus:opacity-100 group-hover/label:opacity-100"
                      >
                        <MoreHorizontal className="h-3 w-3" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="font-mono">
                      {canFollowProject(project) && (
                        <DropdownMenuItem
                          className="cursor-pointer gap-2 text-xs"
                          onSelect={() => onSetFollowed(project, true)}
                        >
                          <PanelLeftOpen className="h-3.5 w-3.5" />
                          Add to sidebar
                        </DropdownMenuItem>
                      )}
                      {hasBoard && (
                        <DropdownMenuItem
                          className="cursor-pointer gap-2 text-xs"
                          onSelect={() =>
                            router.push(`/dashboard/tasks?project=${encodeURIComponent(project.id)}`)
                          }
                        >
                          <ListTodo className="h-3.5 w-3.5" />
                          Tasks
                        </DropdownMenuItem>
                      )}
                      {(project.scopes ?? []).includes('automations') && (
                        <DropdownMenuItem
                          className="cursor-pointer gap-2 text-xs"
                          onSelect={() =>
                            router.push(
                              `/dashboard/automation?project=${encodeURIComponent(project.id)}`,
                            )
                          }
                        >
                          <CalendarClock className="h-3.5 w-3.5" />
                          Automations
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuItem
                        className="cursor-pointer gap-2 text-xs"
                        onSelect={() => setLeaving(project)}
                      >
                        <LogOut className="h-3.5 w-3.5" />
                        Leave project
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
              {!isCollapsed && (
                <div className="space-y-0.5 pl-2">
                  {group.instances.map((instance) => {
                    const href = sessionHref(instance.id);
                    return (
                      <SharedSessionRow
                        key={instance.id}
                        instance={instance}
                        selected={pathname === href}
                        onOpen={() => router.push(href)}
                      />
                    );
                  })}
                  {group.instances.length === 0 && hasBoard && project && (
                    <button
                      type="button"
                      onClick={() =>
                        router.push(`/dashboard/tasks?project=${encodeURIComponent(project.id)}`)
                      }
                      className="flex w-full cursor-pointer items-center gap-1.5 rounded px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-muted"
                    >
                      <ListTodo className="h-3.5 w-3.5" />
                      Task board
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      <LeaveProjectDialog
        api={api}
        project={leaving}
        onClose={() => setLeaving(null)}
        onLeft={onProjectsChanged}
      />
    </div>
  );
}
