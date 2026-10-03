'use client';

/**
 * The team page's view of what the team owns (collaboration §3.2, §3.3, §3.6,
 * §6): its projects, its label set, its agents, and, for the owner, the seats
 * the team takes up on their plan. Mounted by `TeamDetailView` in
 * `teams-settings-section.tsx`, which web and desktop settings share.
 */

import { useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import { ChevronRight, Loader2, Plus } from 'lucide-react';

import { BILLING_SEATS_KEY } from '@/components/billing/seats-card';
import { MoveProjectDialog } from '@/components/dashboard/move-project-dialog';
import { LabelVocabulary } from '@/components/dashboard/tasks-settings-section';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import {
  getBackendAPI,
  projectRoleAtLeast,
  type AgentProfile,
  type BillingSeats,
  type ProjectResponse,
  type TeamDetail,
  type TeamSummary,
} from '@/lib/backend-api';
import { SEATS_PAGE_HREF, seatSummary } from '@/lib/billing';
import { notifyProjectsChanged, projectSettingsHref } from '@/lib/project-settings-route';
import { moveDestinations } from '@/lib/project-transfer';
import { isDesktopLocal } from '@/lib/runtime-config';
import { canManageTeam, nextTeamAgentName } from '@/lib/team-settings';
import { agentPrincipal } from '@/lib/use-agent-profiles';
import { TEAMS_KEY } from '@/lib/use-team-invitations';
import { cn } from '@/lib/utils';

const PROJECTS_KEY = 'team-settings:projects';
const AGENTS_KEY = 'agent-profiles';

function SectionCard({ children }: { children: ReactNode }) {
  return (
    <div className="divide-y divide-border/50 overflow-hidden rounded-xl border border-border/60 bg-foreground/[0.03]">
      {children}
    </div>
  );
}

function SectionHeading({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-sm text-foreground/90">{children}</h2>
      {action}
    </div>
  );
}

function EmptyRow({ children }: { children: ReactNode }) {
  return <div className="px-4 py-4 text-xs text-muted-foreground">{children}</div>;
}

const ROW =
  'flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-foreground/[0.04]';

// --- projects -------------------------------------------------------------------

export function TeamProjectsSection({ team }: { team: TeamDetail }) {
  const local = isDesktopLocal();
  const { mutate } = useSWRConfig();
  const { data: projects } = useSWR<ProjectResponse[]>(
    local ? null : PROJECTS_KEY,
    () => getBackendAPI(true).listProjects(true),
    { shouldRetryOnError: false },
  );
  const { data: teams } = useSWR<TeamSummary[]>(
    local ? null : TEAMS_KEY,
    () => getBackendAPI(true).listTeams(),
    { shouldRetryOnError: false },
  );
  const [moving, setMoving] = useState<ProjectResponse | null>(null);

  const teamProjects = useMemo(
    () =>
      (projects ?? [])
        .filter((p) => p.team_id === team.id && !p.is_archived)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [projects, team.id],
  );
  // What the caller could bring in: projects they own personally.
  const movable = useMemo(
    () =>
      (projects ?? [])
        .filter((p) => !p.team_id && !p.owner && projectRoleAtLeast(p.role, 'owner') && !p.is_archived)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [projects],
  );

  // A viewer reads the team's work but brings nothing into it.
  const moveMenu =
    team.role !== 'viewer' && movable.length > 0 ? (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" size="sm" variant="outline" className="h-7 cursor-pointer gap-1.5 text-xs">
            <Plus className="h-3.5 w-3.5" />
            Move a project here
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="custom-scrollbar max-h-72 w-64 overflow-y-auto font-mono">
          {movable.map((project) => (
            <DropdownMenuItem
              key={project.id}
              className="cursor-pointer gap-2 text-xs"
              onSelect={() => setMoving(project)}
            >
              <ProjectIcon project={project} />
              <span className="truncate">{project.name}</span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    ) : null;

  return (
    <div className="mt-8">
      <SectionHeading action={moveMenu}>Projects</SectionHeading>
      <SectionCard>
        {!projects ? (
          <div className="flex items-center gap-2.5 px-4 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading projects…
          </div>
        ) : teamProjects.length === 0 ? (
          <EmptyRow>
            No projects yet. Move one of yours here to work on it together: everyone on the team
            sees its tasks and sessions.
          </EmptyRow>
        ) : (
          teamProjects.map((project) => {
            const href = projectRoleAtLeast(project.role, 'admin')
              ? projectSettingsHref(project.id)
              : `/dashboard/tasks?project=${encodeURIComponent(project.id)}`;
            return (
              <Link key={project.id} href={href} className={ROW}>
                <ProjectIcon project={project} className="size-4" />
                <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{project.name}</span>
                {project.key && <span className="shrink-0 text-xs text-muted-foreground">{project.key}</span>}
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
              </Link>
            );
          })
        )}
      </SectionCard>
      {moving && (
        <MoveProjectDialog
          open={moving !== null}
          onOpenChange={(open) => !open && setMoving(null)}
          project={moving}
          destinations={moveDestinations(moving, teams ?? [team])}
          currentTeam={null}
          initialTeamId={team.id}
          onMoved={() => {
            setMoving(null);
            void mutate(PROJECTS_KEY);
            notifyProjectsChanged();
          }}
        />
      )}
    </div>
  );
}

// --- labels ---------------------------------------------------------------------

export function TeamLabelsSection({ team }: { team: TeamDetail }) {
  return (
    <div className="mt-8">
      <SectionHeading>Labels</SectionHeading>
      <p className="-mt-1.5 mb-3 text-xs text-muted-foreground">
        Used on the team&apos;s projects, by everyone on the team.
      </p>
      <LabelVocabulary teamId={team.id} />
    </div>
  );
}

// --- agents ---------------------------------------------------------------------

export function TeamAgentsSection({ team }: { team: TeamDetail }) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const { data: profiles } = useSWR<AgentProfile[]>(
    isDesktopLocal() ? null : AGENTS_KEY,
    () => getBackendAPI(true).listAgentProfiles(),
    { shouldRetryOnError: false },
  );
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canAdd = canManageTeam(team.role);
  const agents = (profiles ?? []).filter((p) => p.team_id === team.id);

  const create = async () => {
    if (creating) return;
    setCreating(true);
    setError(null);
    try {
      const profile = await getBackendAPI(true).createAgentProfile({
        name: nextTeamAgentName(agents.map((a) => a.name)),
        agent: 'claude',
        team_id: team.id,
      });
      await mutate(AGENTS_KEY);
      router.push(`/dashboard/agents?agent=${encodeURIComponent(profile.id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create the agent');
      setCreating(false);
    }
  };

  return (
    <div className="mt-8">
      <SectionHeading
        action={
          canAdd ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={creating}
              onClick={() => void create()}
              className="h-7 cursor-pointer gap-1.5 text-xs"
            >
              {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              New team agent
            </Button>
          ) : null
        }
      >
        Agents
      </SectionHeading>
      <SectionCard>
        {!profiles ? (
          <div className="flex items-center gap-2.5 px-4 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading agents…
          </div>
        ) : agents.length === 0 ? (
          <EmptyRow>
            No team agents yet. A team agent is a saved provider, model and instructions that
            everyone on the team can start sessions with.
            {canAdd ? '' : " The team's owner and admins create them."}
          </EmptyRow>
        ) : (
          agents.map((profile) => (
            <Link
              key={profile.id}
              href={`/dashboard/agents?agent=${encodeURIComponent(profile.id)}`}
              className={ROW}
            >
              <PrincipalAvatar principal={agentPrincipal(profile)} size="sm" />
              <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{profile.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{profile.agent}</span>
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
            </Link>
          ))
        )}
      </SectionCard>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </div>
  );
}

// --- seats ----------------------------------------------------------------------

/**
 * The owner pays for the team (§6, owner-pays), so only they see this. Reads
 * the hosted billing endpoint; anywhere it isn't served (self-hosted, where
 * seats are unmetered) the section simply isn't there.
 */
export function TeamSeatsSection({ team }: { team: TeamDetail }) {
  const isOwner = team.role === 'owner';
  const { data: seats, error } = useSWR<BillingSeats>(
    isOwner && !isDesktopLocal() ? BILLING_SEATS_KEY : null,
    () => getBackendAPI(true).getBillingSeats(),
    { shouldRetryOnError: false },
  );
  if (!isOwner || error || !seats) return null;
  const summary = seatSummary(seats);

  return (
    <div className="mt-8">
      <SectionHeading>Seats</SectionHeading>
      <SectionCard>
        <div className="flex items-center justify-between gap-4 px-4 py-3">
          <div className="min-w-0 space-y-0.5">
            <p className={cn('text-[13px]', seats.over ? 'text-warning' : 'text-foreground')}>
              {summary.headline}
            </p>
            <p className="text-xs text-muted-foreground">{summary.detail}</p>
          </div>
          <Button asChild size="sm" variant="outline" className="h-8 shrink-0 cursor-pointer text-xs">
            <Link href={SEATS_PAGE_HREF}>{seats.purchased !== null ? 'Manage seats' : 'Get Vicoa Team'}</Link>
          </Button>
        </div>
      </SectionCard>
    </div>
  );
}
