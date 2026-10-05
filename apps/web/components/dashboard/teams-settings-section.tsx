'use client';

/**
 * Settings → Teams (collaboration §3.2, §3.3). Mounted by both the web
 * settings page and the desktop settings surface, like the Tasks and Machines
 * sections.
 *
 * Two views, both addressed by the URL so they survive a reload and
 * back/forward: `?tab=teams` is the list (invitations waiting on you, your
 * teams, a new-team field) and `?tab=teams&teamId=<id>` is one team: its
 * name and picture, members, what it owns (projects, agents, labels), invite
 * links, the seats it takes on the owner's plan, and leave/delete.
 *
 * A team is a group of people you share projects and sessions with. It is not
 * a workspace: nothing here switches or scopes the rest of the app.
 */

import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Copy,
  Link2,
  Loader2,
  LogOut,
  MoreHorizontal,
  Plus,
  Crown,
  Trash2,
  UserCog,
  UserMinus,
} from 'lucide-react';

import { ConfirmChargeDialog } from '@/components/billing/confirm-charge-dialog';
import { BILLING_SEATS_KEY } from '@/components/billing/seats-card';
import { SeatLimitNotice } from '@/components/billing/seat-limit-notice';
import { AvatarEditor } from '@/components/dashboard/avatar-editor';
import { ConfirmDeleteDialog } from '@/components/dashboard/session-dialogs';
import {
  TeamAgentsSection,
  TeamLabelsSection,
  TeamProjectsSection,
  TeamSeatsSection,
} from '@/components/dashboard/team-work-sections';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  getBackendAPI,
  type BillingSeats,
  type TeamDetail,
  type TeamInvitation,
  type TeamInviteLink,
  type TeamMember,
  type TeamMemberInvite,
  type TeamRole,
  type TeamSummary,
  type UserProfile,
} from '@/lib/backend-api';
import { SEATS_PAGE_HREF, formatSeatPrice } from '@/lib/billing';
import { useCopyToClipboard } from '@/lib/hooks/use-session-operations';
import type { Principal } from '@/lib/principals';
import { isDesktopLocal } from '@/lib/runtime-config';
import {
  INVITE_LINK_EXPIRY_OPTIONS,
  TEAM_ROLE_DESCRIPTION,
  TEAM_ROLE_LABEL,
  canManageTeam,
  errorStatus,
  expiryDays,
  hasMemberActions,
  invitableRoles,
  invitedYouLine,
  inviteLinkExpiryLabel,
  inviteLinkUsesLabel,
  memberActions,
  memberCountLabel,
  memberDisplayName,
  parseMaxUses,
  partitionMembers,
  teamJoinUrl,
  teamsSettingsHref,
  toTeamActionError,
  type InvitableRole,
  type InviteLinkExpiryValue,
  type MemberActions,
  type TeamActionError,
} from '@/lib/team-settings';
import { TEAMS_KEY, useTeamInvitations } from '@/lib/use-team-invitations';
import { cn } from '@/lib/utils';

const ME_KEY = 'teams-settings:me';
const teamKey = (teamId: string) => ['team', teamId] as const;
const inviteLinksKey = (teamId: string) => ['team-invite-links', teamId] as const;

const SELECT_TRIGGER =
  'h-9 cursor-pointer text-xs focus:ring-0 focus:ring-offset-0 focus-visible:ring-2 focus-visible:ring-ring';

function teamPrincipal(team: {
  id: string;
  name: string;
  avatar_image_uri: string | null;
  updated_at?: string;
}): Principal {
  return {
    type: 'team',
    id: team.id,
    name: team.name,
    avatarImageUri: team.avatar_image_uri,
    updatedAt: team.updated_at,
  };
}

function memberPrincipal(member: TeamMember): Principal {
  return {
    type: 'user',
    id: member.user_id,
    // Only what the server sent: a plain member's view carries no emails.
    name: member.display_name || member.email,
    avatarImageUri: member.avatar_image_uri,
  };
}

// --- small building blocks ---------------------------------------------------

function SectionCard({ children }: { children: ReactNode }) {
  return (
    <div className="divide-y divide-border/50 overflow-hidden rounded-xl border border-border/60 bg-foreground/[0.03]">
      {children}
    </div>
  );
}

function SectionHeading({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 text-sm text-foreground/90">{children}</h2>;
}

function GroupLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('text-[0.8rem] font-normal text-muted-foreground', className)}>{children}</div>;
}

function Pill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'warning' | 'success' }) {
  return (
    <span
      className={cn(
        'shrink-0 rounded border px-1.5 py-px text-[10px]',
        tone === 'neutral' && 'border-border/70 bg-foreground/[0.06] text-muted-foreground',
        tone === 'warning' && 'border-warning/30 bg-warning/10 text-warning',
        tone === 'success' && 'border-success/30 bg-success/10 text-success',
      )}
    >
      {children}
    </span>
  );
}

function ActionError({ error, className }: { error: TeamActionError | null; className?: string }) {
  if (!error) return null;
  if (error.kind === 'team-own') return <TeamOwnOffer className={className} />;
  if (error.kind === 'seat-limit') return <SeatLimitNotice detail={error.detail} className={className} />;
  return <p className={cn('text-xs text-destructive', className)}>{error.message}</p>;
}

/** Creating (or being handed) a team on Free: the owner edits everything the
 *  team owns, so it takes Pro or Vicoa Team. Offer both. */
function TeamOwnOffer({ className }: { className?: string }) {
  return (
    <div
      role="alert"
      className={cn(
        'rounded-md border border-warning/30 bg-warning/10 px-3 py-2.5 text-xs text-foreground/90',
        className,
      )}
    >
      <p className="font-medium">Teams need Pro or Vicoa Team</p>
      <p className="mt-0.5 text-muted-foreground">
        With Vicoa Team you pay a seat for everyone who edits. With Pro, you edit alongside teammates who have
        their own Pro. Viewers are free.
      </p>
      <div className="mt-2.5 flex flex-wrap gap-2">
        <Button asChild size="sm" className="h-8 cursor-pointer text-xs">
          <Link href={SEATS_PAGE_HREF}>Get Vicoa Team</Link>
        </Button>
        <Button asChild size="sm" variant="outline" className="h-8 cursor-pointer text-xs">
          <Link href="/dashboard/upgrade">Get Pro</Link>
        </Button>
      </div>
    </div>
  );
}

function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 px-4 py-5 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

function RoleSelect({
  value,
  onChange,
  roles,
  id,
  className,
}: {
  value: InvitableRole;
  onChange: (role: InvitableRole) => void;
  roles: InvitableRole[];
  id?: string;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as InvitableRole)}>
      <SelectTrigger id={id} className={cn(SELECT_TRIGGER, className)} aria-label="Role">
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="font-mono text-xs">
        {roles.map((role) => (
          <SelectItem key={role} value={role} className="cursor-pointer text-xs">
            {TEAM_ROLE_LABEL[role]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** The signed-in user's backend id: how the detail view finds your own row. */
function useMe(): UserProfile | undefined {
  const { data } = useSWR<UserProfile>(
    isDesktopLocal() ? null : ME_KEY,
    () => getBackendAPI(true).getCurrentUserProfile(),
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  return data;
}

// --- entry -------------------------------------------------------------------

export function TeamsSettingsSection() {
  const searchParams = useSearchParams();
  const teamId = searchParams.get('teamId');
  // Teams live on the cloud backend; the logged-out desktop only talks to its
  // local daemon. Read post-mount (runtime config is client-only).
  const [localMode, setLocalMode] = useState(false);
  useEffect(() => setLocalMode(isDesktopLocal()), []);

  if (localMode) {
    return (
      <section>
        <SectionHeader />
        <p className="mt-8 text-sm text-muted-foreground">Sign in to create or join a team.</p>
      </section>
    );
  }
  return teamId ? <TeamDetailView key={teamId} teamId={teamId} /> : <TeamsListView />;
}

function SectionHeader() {
  return (
    <>
      <h1 className="text-2xl font-light tracking-tight text-foreground">Teams</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Teams are groups of people you can share projects and sessions with.
      </p>
    </>
  );
}

// --- list view ---------------------------------------------------------------

function TeamsListView() {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const { data: teams, error: loadError } = useSWR<TeamSummary[]>(
    isDesktopLocal() ? null : TEAMS_KEY,
    () => getBackendAPI(true).listTeams(),
    { shouldRetryOnError: false },
  );
  const { invitations, accept, decline } = useTeamInvitations();

  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<TeamActionError | null>(null);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const team = await getBackendAPI(true).createTeam(name);
      setNewName('');
      void mutate(TEAMS_KEY);
      router.push(teamsSettingsHref(team.id), { scroll: false });
    } catch (err) {
      setCreateError(toTeamActionError(err, 'Failed to create the team'));
    } finally {
      setCreating(false);
    }
  };

  return (
    <section>
      <SectionHeader />

      {invitations.length > 0 && (
        <div className="mt-8">
          <SectionHeading>Invitations</SectionHeading>
          <SectionCard>
            {invitations.map((invitation) => (
              <InvitationRow
                key={invitation.team_id}
                invitation={invitation}
                onAccept={() => accept(invitation.team_id)}
                onDecline={() => decline(invitation.team_id)}
              />
            ))}
          </SectionCard>
        </div>
      )}

      <div className="mt-8">
        <SectionHeading>Your teams</SectionHeading>
        <SectionCard>
          {teams === undefined && !loadError ? (
            <LoadingRow label="Loading teams…" />
          ) : teams === undefined ? (
            <p className="px-4 py-5 text-xs text-destructive">
              Couldn&apos;t load your teams. Check your connection.
            </p>
          ) : teams.length === 0 ? (
            <div className="px-4 py-5 text-sm text-muted-foreground">
              You&apos;re not in any teams yet. Create one below, or open an invite link from a teammate.
            </div>
          ) : (
            teams.map((team) => (
              <Link
                key={team.id}
                href={teamsSettingsHref(team.id)}
                scroll={false}
                className="flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors hover:bg-foreground/[0.04]"
              >
                <PrincipalAvatar principal={teamPrincipal(team)} size="md" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] text-foreground">{team.name}</div>
                  <div className="mt-0.5 truncate text-xs text-muted-foreground">
                    {memberCountLabel(team.member_count)}
                  </div>
                </div>
                <Pill>{TEAM_ROLE_LABEL[team.role]}</Pill>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/70" />
              </Link>
            ))
          )}
        </SectionCard>
        {loadError && teams !== undefined && (
          <p className="mt-2 text-xs text-warning">Couldn&apos;t reach the server, so this list may be out of date.</p>
        )}
      </div>

      <div className="mt-8">
        <SectionHeading>New team</SectionHeading>
        <form onSubmit={create} className="flex items-center gap-2">
          <Input
            value={newName}
            onChange={(e) => {
              setNewName(e.target.value);
              if (createError) setCreateError(null);
            }}
            placeholder="Team name"
            aria-label="Team name"
            maxLength={100}
            className="h-9 flex-1 text-xs"
          />
          <Button type="submit" size="sm" className="h-9 text-xs" disabled={!newName.trim() || creating}>
            {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Create team
          </Button>
        </form>
        <ActionError error={createError} className="mt-2" />
      </div>
    </section>
  );
}

function InvitationRow({
  invitation,
  onAccept,
  onDecline,
}: {
  invitation: TeamInvitation;
  onAccept: () => Promise<unknown>;
  onDecline: () => Promise<unknown>;
}) {
  const [busy, setBusy] = useState<'accept' | 'decline' | null>(null);
  const [error, setError] = useState<TeamActionError | null>(null);

  const run = async (which: 'accept' | 'decline', action: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(which);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(toTeamActionError(err, which === 'accept' ? 'Failed to join' : 'Failed to decline'));
      setBusy(null);
    }
  };

  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-3">
        <PrincipalAvatar principal={teamPrincipal({ ...invitation, id: invitation.team_id })} size="md" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] text-foreground">{invitation.name}</div>
          <div className="mt-0.5 truncate text-xs text-muted-foreground">
            {invitedYouLine(invitation.invited_by_display_name, invitation.role)}
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          className="h-8 text-xs"
          disabled={busy !== null}
          onClick={() => void run('accept', onAccept)}
        >
          {busy === 'accept' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Accept
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-8 text-xs text-muted-foreground"
          disabled={busy !== null}
          onClick={() => void run('decline', onDecline)}
        >
          {busy === 'decline' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Decline
        </Button>
      </div>
      <ActionError error={error} className="mt-2" />
    </div>
  );
}

// --- detail view -------------------------------------------------------------

type PendingConfirm =
  | { kind: 'remove'; member: TeamMember }
  | { kind: 'transfer'; member: TeamMember }
  | { kind: 'leave' }
  | { kind: 'delete' }
  | { kind: 'revoke-link'; link: TeamInviteLink };

function TeamDetailView({ teamId }: { teamId: string }) {
  const router = useRouter();
  const { mutate: globalMutate } = useSWRConfig();
  const me = useMe();
  const {
    data: team,
    error: loadError,
    mutate: mutateTeam,
  } = useSWR<TeamDetail>(
    isDesktopLocal() ? null : teamKey(teamId),
    () => getBackendAPI(true).getTeam(teamId),
    { shouldRetryOnError: false },
  );

  const canManage = canManageTeam(team?.role);
  const {
    data: links,
    error: linksError,
    mutate: mutateLinks,
  } = useSWR<TeamInviteLink[]>(
    team && canManage ? inviteLinksKey(teamId) : null,
    () => getBackendAPI(true).listTeamInviteLinks(teamId),
    { shouldRetryOnError: false },
  );

  // The pending action outlives `open` so the dialog keeps its copy while it
  // fades out instead of blanking mid-animation.
  const [confirm, setConfirmState] = useState<PendingConfirm | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const setConfirm = useCallback((next: PendingConfirm) => {
    setConfirmState(next);
    setConfirmOpen(true);
  }, []);
  const [membersError, setMembersError] = useState<TeamActionError | null>(null);
  const [dangerError, setDangerError] = useState<TeamActionError | null>(null);
  const [linksActionError, setLinksActionError] = useState<TeamActionError | null>(null);

  // Member counts show in the list view, so any membership change refreshes it.
  const refreshTeam = useCallback(async () => {
    await mutateTeam();
    void globalMutate(TEAMS_KEY);
  }, [mutateTeam, globalMutate]);

  const backToList = useCallback(() => {
    void globalMutate(TEAMS_KEY);
    router.replace(teamsSettingsHref(), { scroll: false });
  }, [globalMutate, router]);

  const backLink = (
    <Link
      href={teamsSettingsHref()}
      scroll={false}
      className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft className="h-3.5 w-3.5" />
      All teams
    </Link>
  );

  if (!team) {
    const missing = loadError && [403, 404].includes(errorStatus(loadError) ?? 0);
    return (
      <section>
        {backLink}
        <div className="mt-6">
          {!loadError ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading team…
            </div>
          ) : missing ? (
            <p className="text-sm text-muted-foreground">
              This team doesn&apos;t exist, or you&apos;re no longer a member.
            </p>
          ) : (
            <p className="text-xs text-destructive">Couldn&apos;t load this team. Check your connection.</p>
          )}
        </div>
      </section>
    );
  }

  const viewer = { role: team.role, userId: me?.id };
  const { active, pending } = partitionMembers(team.members);
  const myMember = me ? team.members.find((m) => m.user_id === me.id) : undefined;
  const isOwner = team.role === 'owner';

  const changeRole = async (member: TeamMember, role: InvitableRole) => {
    if (member.role === role) return;
    setMembersError(null);
    try {
      await getBackendAPI(true).updateTeamMemberRole(teamId, member.id, role);
      await refreshTeam();
    } catch (err) {
      setMembersError(toTeamActionError(err, 'Failed to change the role'));
    }
  };

  const runConfirmed = async () => {
    if (!confirm) return;
    const api = getBackendAPI(true);
    try {
      if (confirm.kind === 'remove') {
        setMembersError(null);
        await api.removeTeamMember(teamId, confirm.member.id);
        await refreshTeam();
      } else if (confirm.kind === 'transfer') {
        setMembersError(null);
        await api.transferTeamOwnership(teamId, confirm.member.id);
        await refreshTeam();
        // The payer changed, so whose seats these are did too.
        void globalMutate(BILLING_SEATS_KEY);
      } else if (confirm.kind === 'leave') {
        setDangerError(null);
        if (!myMember) throw new Error("Couldn't find your membership. Reload and try again.");
        await api.removeTeamMember(teamId, myMember.id);
        backToList();
      } else if (confirm.kind === 'delete') {
        setDangerError(null);
        await api.deleteTeam(teamId);
        backToList();
      } else {
        setLinksActionError(null);
        await api.revokeTeamInviteLink(teamId, confirm.link.id);
        await mutateLinks();
      }
    } catch (err) {
      if (confirm.kind === 'remove') setMembersError(toTeamActionError(err, 'Failed to remove the member'));
      else if (confirm.kind === 'transfer')
        setMembersError(toTeamActionError(err, 'Failed to transfer the team'));
      else if (confirm.kind === 'leave') setDangerError(toTeamActionError(err, 'Failed to leave the team'));
      else if (confirm.kind === 'delete') setDangerError(toTeamActionError(err, 'Failed to delete the team'));
      else setLinksActionError(toTeamActionError(err, 'Failed to revoke the link'));
    }
  };

  const memberRow = (member: TeamMember) => {
    const actions = memberActions(viewer, member);
    return (
      <MemberRow
        key={member.id}
        member={member}
        actions={actions}
        onChangeRole={(role) => void changeRole(member, role)}
        onMakeOwner={() => {
          setMembersError(null);
          setConfirm({ kind: 'transfer', member });
        }}
        onRemove={() => {
          setMembersError(null);
          setDangerError(null);
          setConfirm(actions.remove === 'leave' ? { kind: 'leave' } : { kind: 'remove', member });
        }}
      />
    );
  };

  const teamSubject = (
    <div className="flex items-center gap-2 text-sm">
      <PrincipalAvatar principal={teamPrincipal(team)} size="sm" />
      <span className="truncate">{team.name}</span>
    </div>
  );

  const dialog = confirmDialogCopy(confirm, team.name);

  return (
    <section>
      {backLink}

      <TeamHeader team={team} canEdit={canManage} onChanged={refreshTeam} />

      {canManage && (
        <div className="mt-8">
          <SectionHeading>Invite people</SectionHeading>
          <InviteCard teamId={teamId} viewerRole={team.role} onInvited={refreshTeam} />
        </div>
      )}

      <div className="mt-8">
        <SectionHeading>Members</SectionHeading>
        <SectionCard>
          {active.map(memberRow)}
        </SectionCard>
        {pending.length > 0 && (
          <>
            <GroupLabel className="mt-5 mb-2">Pending</GroupLabel>
            <SectionCard>
              {pending.map(memberRow)}
            </SectionCard>
          </>
        )}
        <ActionError error={membersError} className="mt-2" />
      </div>

      <TeamProjectsSection team={team} />
      <TeamAgentsSection team={team} />
      <TeamLabelsSection team={team} />

      {canManage && (
        <div className="mt-8">
          <SectionHeading>Invite links</SectionHeading>
          <InviteLinksCard
            teamId={teamId}
            viewerRole={team.role}
            links={links}
            loadFailed={!!linksError}
            onCreated={(link) => mutateLinks((prev) => [link, ...(prev ?? [])], { revalidate: false })}
            onRevoke={(link) => setConfirm({ kind: 'revoke-link', link })}
          />
          <ActionError error={linksActionError} className="mt-2" />
        </div>
      )}

      <TeamSeatsSection team={team} />

      <div className="mt-8">
        <SectionHeading>Danger zone</SectionHeading>
        <SectionCard>
          {isOwner ? (
            <DangerRow
              title="Delete team"
              description="Its projects, agents and labels move back to whoever created them, and anyone who had access through this team loses it."
              action="Delete team"
              icon={Trash2}
              onClick={() => {
                setDangerError(null);
                setConfirm({ kind: 'delete' });
              }}
            />
          ) : (
            <DangerRow
              title="Leave team"
              description="You lose access to anything shared with this team until someone invites you again."
              action="Leave team"
              icon={LogOut}
              disabled={!myMember}
              onClick={() => {
                setDangerError(null);
                setConfirm({ kind: 'leave' });
              }}
            />
          )}
        </SectionCard>
        <ActionError error={dangerError} className="mt-2" />
      </div>

      <ConfirmDeleteDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={dialog.title}
        description={dialog.description}
        confirmLabel={dialog.confirmLabel}
        subject={
          confirm?.kind === 'remove' || confirm?.kind === 'transfer' ? (
            <div className="flex items-center gap-2 text-sm">
              <PrincipalAvatar principal={memberPrincipal(confirm.member)} size="sm" />
              <span className="truncate">{memberDisplayName(confirm.member)}</span>
            </div>
          ) : confirm?.kind === 'revoke-link' ? (
            <div className="text-xs text-muted-foreground">
              {TEAM_ROLE_LABEL[confirm.link.role]} link · {inviteLinkUsesLabel(confirm.link)}
            </div>
          ) : confirm ? (
            teamSubject
          ) : null
        }
        onConfirm={runConfirmed}
      />
    </section>
  );
}

function confirmDialogCopy(
  confirm: PendingConfirm | null,
  teamName: string,
): { title: string; description: string; confirmLabel: string } {
  switch (confirm?.kind) {
    case 'remove':
      return confirm.member.status === 'invited'
        ? {
            title: 'Cancel invitation',
            description: `${memberDisplayName(confirm.member)} will no longer be able to join ${teamName} with this invitation.`,
            confirmLabel: 'Cancel invitation',
          }
        : {
            title: 'Remove member',
            description: `${memberDisplayName(confirm.member)} will lose access to everything shared with ${teamName}.`,
            confirmLabel: 'Remove',
          };
    case 'transfer':
      return {
        title: 'Make owner',
        description: `${memberDisplayName(confirm.member)} becomes the owner of ${teamName} and pays for its seats from then on. You stay on as an admin, and only they can make you owner again.`,
        confirmLabel: 'Make owner',
      };
    case 'leave':
      return {
        title: 'Leave team',
        description: `You will lose access to everything shared with ${teamName}. To come back, someone on the team has to invite you again.`,
        confirmLabel: 'Leave team',
      };
    case 'delete':
      return {
        title: 'Delete team',
        description:
          "The team's projects, agents and labels move back to whoever created them, and anyone who had access through this team loses it. This can't be undone.",
        confirmLabel: 'Delete team',
      };
    case 'revoke-link':
      return {
        title: 'Revoke invite link',
        description: 'Nobody can join with this link any more. People who already joined stay on the team.',
        confirmLabel: 'Revoke',
      };
    default:
      return { title: '', description: '', confirmLabel: 'Delete' };
  }
}

function TeamHeader({
  team,
  canEdit,
  onChanged,
}: {
  team: TeamDetail;
  /** Owner/admin: rename and change the picture. */
  canEdit: boolean;
  onChanged: () => Promise<void>;
}) {
  const [name, setName] = useState(team.name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<TeamActionError | null>(null);

  useEffect(() => setName(team.name), [team.name]);

  const cancelRef = useRef(false);

  const commit = async () => {
    if (cancelRef.current) {
      cancelRef.current = false;
      return;
    }
    const trimmed = name.trim();
    if (!trimmed || trimmed === team.name) {
      setName(team.name);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await getBackendAPI(true).renameTeam(team.id, trimmed);
      await onChanged();
    } catch (err) {
      setName(team.name);
      setError(toTeamActionError(err, 'Failed to rename the team'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-5">
      <div className="flex items-center gap-4">
        {canEdit ? (
          <AvatarEditor
            principal={teamPrincipal(team)}
            size="lg"
            onUploadImage={async (file) => {
              await getBackendAPI(true).uploadTeamAvatar(team.id, file);
              await onChanged();
            }}
            onRemoveImage={async () => {
              await getBackendAPI(true).deleteTeamAvatar(team.id);
              await onChanged();
            }}
          />
        ) : (
          <PrincipalAvatar principal={teamPrincipal(team)} size="lg" />
        )}
        <div className="min-w-0 flex-1">
          {canEdit ? (
            <div className="flex items-center gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onBlur={() => void commit()}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') e.currentTarget.blur();
                  if (e.key === 'Escape') {
                    // Blur commits; this one must not (it still sees the edit).
                    cancelRef.current = true;
                    setName(team.name);
                    e.currentTarget.blur();
                  }
                }}
                aria-label="Team name"
                maxLength={100}
                disabled={saving}
                className="-mx-1.5 w-full min-w-0 rounded-md bg-transparent px-1.5 py-0.5 text-2xl font-light tracking-tight text-foreground outline-none hover:bg-accent/40 focus-visible:bg-accent/40"
              />
              {saving && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />}
            </div>
          ) : (
            <h1 className="truncate text-2xl font-light tracking-tight text-foreground">{team.name}</h1>
          )}
          <div className="mt-1 flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
            <span className="truncate" title="Team slug">
              {team.slug}
            </span>
            <span aria-hidden>·</span>
            <span className="shrink-0">{memberCountLabel(team.member_count)}</span>
            <Pill>{TEAM_ROLE_LABEL[team.role]}</Pill>
          </div>
        </div>
      </div>
      <ActionError error={error} className="mt-2" />
    </div>
  );
}

function InviteCard({
  teamId,
  viewerRole,
  onInvited,
}: {
  teamId: string;
  viewerRole: TeamRole;
  onInvited: () => Promise<void>;
}) {
  const roles = invitableRoles(viewerRole);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<InvitableRole>('member');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<TeamActionError | null>(null);
  // The address and role a seat limit refused, kept so "Add a seat" or
  // "Invite as a viewer" can finish the same invite.
  const [refused, setRefused] = useState<{ email: string; role: InvitableRole } | null>(null);
  const [result, setResult] = useState<{ email: string; invite: TeamMemberInvite } | null>(null);
  const { copied, copy } = useCopyToClipboard();

  const send = async (address: string, asRole: InvitableRole) => {
    setSending(true);
    setError(null);
    setRefused(null);
    setResult(null);
    try {
      const invite = await getBackendAPI(true).inviteTeamMember(teamId, address, asRole);
      setResult({ email: address, invite });
      setEmail('');
      await onInvited();
    } catch (err) {
      const actionError = toTeamActionError(err, 'Failed to send the invite');
      setError(actionError);
      if (actionError.kind === 'seat-limit') setRefused({ email: address, role: asRole });
    } finally {
      setSending(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const address = email.trim();
    if (!address || sending) return;
    await send(address, role);
  };

  return (
    <SectionCard>
      <div className="px-4 py-3.5">
        <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Input
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (error) setError(null);
            }}
            placeholder="name@example.com"
            aria-label="Email address"
            autoComplete="off"
            className="h-9 min-w-0 flex-1 text-xs"
          />
          <RoleSelect value={role} onChange={setRole} roles={roles} className="sm:w-28" />
          <Button type="submit" size="sm" className="h-9 text-xs" disabled={!email.trim() || sending}>
            {sending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Invite
          </Button>
        </form>
        <p className="mt-2 text-[11px] text-muted-foreground">
          {roles
            .map((r) => `${TEAM_ROLE_LABEL[r]}: ${TEAM_ROLE_DESCRIPTION[r]}.`)
            .join(' ')}
        </p>
        {error?.kind === 'seat-limit' && refused ? (
          <InviteSeatLimit
            detail={error.detail}
            isOwner={viewerRole === 'owner'}
            busy={sending}
            onInviteAsViewer={() => void send(refused.email, 'viewer')}
            onSeatAdded={() => send(refused.email, refused.role)}
            className="mt-2"
          />
        ) : (
          <ActionError error={error} className="mt-2" />
        )}
        {result &&
          (result.invite.email_sent ? (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-success">
              <Check className="h-3.5 w-3.5" />
              Invite sent to {result.email}.
            </p>
          ) : (
            <div className="mt-3 grid gap-2">
              <p className="text-xs text-foreground/90">This server can&apos;t send email, share this link instead:</p>
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={result.invite.join_url}
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label="Invite link"
                  className="h-8 min-w-0 flex-1 text-xs"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs"
                  onClick={() => void copy(result.invite.join_url, 'invite')}
                >
                  {copied === 'invite' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied === 'invite' ? 'Copied' : 'Copy'}
                </Button>
              </div>
            </div>
          ))}
        {result && (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            {result.email} can also accept under Settings → Teams after signing in with that address.
          </p>
        )}
      </div>
    </SectionCard>
  );
}

/**
 * An editor invite past the seats the owner pays for. Fixed in place, without
 * leaving the team page: an owner on Vicoa Team adds a seat (confirmed, since
 * it bills the live subscription) and the invite goes out; any other owner is
 * pointed at the seats page; and anyone can send the same invite as a viewer,
 * which is free.
 */
function InviteSeatLimit({
  detail,
  isOwner,
  busy,
  onInviteAsViewer,
  onSeatAdded,
  className,
}: {
  detail: string;
  isOwner: boolean;
  busy: boolean;
  onInviteAsViewer: () => void;
  onSeatAdded: () => Promise<void>;
  className?: string;
}) {
  const { mutate } = useSWRConfig();
  const { data: seats } = useSWR<BillingSeats>(
    isOwner && !isDesktopLocal() ? BILLING_SEATS_KEY : null,
    () => getBackendAPI(true).getBillingSeats(),
    { shouldRetryOnError: false },
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const onTeam = seats?.purchased != null;
  const addInPlace = isOwner && onTeam && seats?.change_mode === 'in_place';
  const nextQuantity = (seats?.purchased ?? 0) + 1;
  const interval = seats?.billing_interval ?? 'monthly';
  const price = seats?.prices?.[interval] ?? null;
  const unit = interval === 'annual' ? 'year' : 'month';

  const addSeat = async () => {
    setAddError(null);
    try {
      const here = window.location.href;
      await getBackendAPI(true).changeBillingSeats({
        quantity: nextQuantity,
        billing_interval: interval,
        success_url: here,
        cancel_url: here,
      });
      void mutate(BILLING_SEATS_KEY);
      void mutate('billing-subscription');
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add a seat.');
      return;
    }
    await onSeatAdded();
  };

  return (
    <div
      role="alert"
      className={cn(
        'rounded-md border border-warning/30 bg-warning/10 px-3 py-2.5 text-xs text-foreground/90',
        className,
      )}
    >
      <p className="font-medium">No seat left for another editor</p>
      <p className="mt-0.5 text-muted-foreground">{detail}</p>
      <div className="mt-2.5 flex flex-wrap gap-2">
        {addInPlace ? (
          <Button
            type="button"
            size="sm"
            className="h-8 cursor-pointer text-xs"
            disabled={busy}
            onClick={() => setConfirmOpen(true)}
          >
            Add a seat and invite
          </Button>
        ) : isOwner ? (
          <Button asChild size="sm" className="h-8 cursor-pointer text-xs">
            <Link href={SEATS_PAGE_HREF}>{onTeam ? 'Add seats' : 'Get Vicoa Team'}</Link>
          </Button>
        ) : null}
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 cursor-pointer text-xs"
          disabled={busy}
          onClick={onInviteAsViewer}
        >
          Invite as a viewer instead
        </Button>
      </div>
      {addError && <p className="mt-2 text-destructive">{addError}</p>}
      <ConfirmChargeDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Add a seat?"
        description={`Your Vicoa Team goes from ${seats?.purchased ?? 0} to ${nextQuantity} seats now, and the invite goes out. The difference is prorated on your next invoice.`}
        summary={
          price ? (
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-muted-foreground">New total</span>
              <span className="tabular-nums text-foreground">
                {formatSeatPrice({ ...price, unit_amount: price.unit_amount * nextQuantity })} per {unit}
              </span>
            </div>
          ) : undefined
        }
        confirmLabel="Add seat"
        onConfirm={addSeat}
      />
    </div>
  );
}

function MemberRow({
  member,
  actions,
  onChangeRole,
  onMakeOwner,
  onRemove,
}: {
  member: TeamMember;
  actions: MemberActions;
  onChangeRole: (role: InvitableRole) => void;
  onMakeOwner: () => void;
  onRemove: () => void;
}) {
  const name = memberDisplayName(member);
  // The email line only when the server sent one and it isn't already the name.
  const showEmail = !!member.email && !!member.display_name?.trim();
  const invited = member.status === 'invited';

  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <PrincipalAvatar principal={memberPrincipal(member)} size="md" />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="truncate text-[13px] text-foreground" title={name}>
            {name}
          </span>
          {actions.isSelf && <span className="shrink-0 text-xs text-muted-foreground">(you)</span>}
        </div>
        {showEmail && <div className="mt-0.5 truncate text-xs text-muted-foreground">{member.email}</div>}
      </div>
      {member.lapsed_role && (
        <span
          title={`Was ${TEAM_ROLE_LABEL[member.lapsed_role].toLowerCase()}. Editing comes back when the owner adds seats.`}
        >
          <Pill tone="warning">Seat lapsed</Pill>
        </span>
      )}
      {invited && <Pill tone="warning">Invited</Pill>}
      <span className="w-14 shrink-0 text-right text-xs text-muted-foreground">{TEAM_ROLE_LABEL[member.role]}</span>
      {hasMemberActions(actions) ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label={`Actions for ${name}`}
              className="shrink-0 cursor-pointer rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground dark:hover:bg-foreground/10"
            >
              <MoreHorizontal className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 font-mono text-xs">
            {actions.showChangeRole &&
              (actions.changeRoleLockedReason ? (
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger
                    disabled
                    className="cursor-not-allowed items-start gap-2 text-xs data-[disabled]:opacity-60"
                  >
                    <UserCog className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div>Change role</div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">
                        {actions.changeRoleLockedReason}
                      </div>
                    </div>
                  </DropdownMenuSubTrigger>
                </DropdownMenuSub>
              ) : (
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger className="cursor-pointer gap-2 text-xs">
                    <UserCog className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    Change role
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent className="w-64 font-mono text-xs">
                    {(['admin', 'member', 'viewer'] as const).map((role) => (
                      <DropdownMenuItem
                        key={role}
                        onSelect={() => onChangeRole(role)}
                        className="cursor-pointer items-start gap-2 text-xs"
                      >
                        <div className="min-w-0 flex-1">
                          <div>{TEAM_ROLE_LABEL[role]}</div>
                          <div className="mt-0.5 text-[11px] text-muted-foreground">
                            {TEAM_ROLE_DESCRIPTION[role]}
                          </div>
                        </div>
                        {member.role === role && <Check className="mt-0.5 h-3.5 w-3.5" />}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
              ))}
            {actions.makeOwner && (
              <DropdownMenuItem onSelect={onMakeOwner} className="cursor-pointer gap-2 text-xs">
                <Crown className="h-3.5 w-3.5 text-muted-foreground" />
                Make owner
              </DropdownMenuItem>
            )}
            {(actions.showChangeRole || actions.makeOwner) && actions.remove && <DropdownMenuSeparator />}
            {actions.remove && (
              <DropdownMenuItem
                variant="destructive"
                onSelect={onRemove}
                className="cursor-pointer gap-2 text-xs"
              >
                {actions.remove === 'leave' ? (
                  <LogOut className="h-3.5 w-3.5" />
                ) : (
                  <UserMinus className="h-3.5 w-3.5" />
                )}
                {actions.remove === 'leave' ? 'Leave team' : invited ? 'Cancel invitation' : 'Remove'}
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        // Keeps the role column aligned on rows without a menu.
        <span className="w-7 shrink-0" aria-hidden />
      )}
    </div>
  );
}

function InviteLinksCard({
  teamId,
  viewerRole,
  links,
  loadFailed,
  onCreated,
  onRevoke,
}: {
  teamId: string;
  viewerRole: TeamRole;
  links: TeamInviteLink[] | undefined;
  loadFailed: boolean;
  onCreated: (link: TeamInviteLink) => void;
  onRevoke: (link: TeamInviteLink) => void;
}) {
  const roles = invitableRoles(viewerRole);
  const [role, setRole] = useState<InvitableRole>('member');
  const [expiry, setExpiry] = useState<InviteLinkExpiryValue>('7');
  const [maxUses, setMaxUses] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<TeamActionError | null>(null);
  const { copied, copy } = useCopyToClipboard();
  const parsedMaxUses = parseMaxUses(maxUses);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (creating || !parsedMaxUses.ok) return;
    setCreating(true);
    setError(null);
    try {
      const link = await getBackendAPI(true).createTeamInviteLink(teamId, {
        role,
        expires_in_days: expiryDays(expiry),
        max_uses: parsedMaxUses.value,
      });
      setMaxUses('');
      onCreated(link);
      // One click: the new link is on the clipboard straight away.
      void copy(teamJoinUrl(link.token), link.id);
    } catch (err) {
      setError(toTeamActionError(err, 'Failed to create the link'));
    } finally {
      setCreating(false);
    }
  };

  // Evaluated per render; the labels only need day resolution.
  const now = Date.now();

  return (
    <SectionCard>
      <form onSubmit={create} className="px-4 py-3.5">
        <p className="text-xs text-muted-foreground">
          Anyone with the link can join until it expires or runs out of uses.
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <div className="grid gap-1.5">
            <Label htmlFor="team-link-role" className="text-[11px] font-normal text-muted-foreground">
              Role
            </Label>
            <RoleSelect id="team-link-role" value={role} onChange={setRole} roles={roles} className="w-28" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="team-link-expiry" className="text-[11px] font-normal text-muted-foreground">
              Expires after
            </Label>
            <Select value={expiry} onValueChange={(v) => setExpiry(v as InviteLinkExpiryValue)}>
              <SelectTrigger id="team-link-expiry" className={cn(SELECT_TRIGGER, 'w-28')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="font-mono text-xs">
                {INVITE_LINK_EXPIRY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value} className="cursor-pointer text-xs">
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="team-link-max-uses" className="text-[11px] font-normal text-muted-foreground">
              Max uses
            </Label>
            <Input
              id="team-link-max-uses"
              inputMode="numeric"
              value={maxUses}
              onChange={(e) => setMaxUses(e.target.value)}
              placeholder="No limit"
              aria-invalid={!parsedMaxUses.ok}
              className="h-9 w-28 text-xs"
            />
          </div>
          <Button type="submit" size="sm" className="h-9 text-xs" disabled={creating || !parsedMaxUses.ok}>
            {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link2 className="h-3.5 w-3.5" />}
            Create link
          </Button>
        </div>
        {!parsedMaxUses.ok && (
          <p className="mt-2 text-xs text-destructive">Max uses must be a whole number of at least 1.</p>
        )}
        <ActionError error={error} className="mt-2" />
      </form>

      {links === undefined && !loadFailed ? (
        <LoadingRow label="Loading links…" />
      ) : loadFailed ? (
        <p className="px-4 py-3.5 text-xs text-destructive">Couldn&apos;t load invite links. Check your connection.</p>
      ) : (
        links?.map((link) => {
          const url = teamJoinUrl(link.token);
          return (
            <div key={link.id} className="flex items-center gap-3 px-4 py-3">
              <Link2 className="h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] text-foreground">
                  {TEAM_ROLE_LABEL[link.role]}
                  <span className="text-muted-foreground">
                    {' · '}
                    {inviteLinkUsesLabel(link)}
                    {' · '}
                    {inviteLinkExpiryLabel(link.expires_at, now)}
                  </span>
                </div>
                <div className="mt-0.5 truncate text-xs text-muted-foreground" title={url}>
                  {url.replace(/^https?:\/\//, '')}
                </div>
              </div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
                aria-label="Copy invite link"
                onClick={() => void copy(url, link.id)}
              >
                {copied === link.id ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                {copied === link.id ? 'Copied' : 'Copy'}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 gap-1.5 px-2 text-xs text-muted-foreground hover:text-destructive"
                aria-label="Revoke invite link"
                onClick={() => onRevoke(link)}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Revoke
              </Button>
            </div>
          );
        })
      )}
    </SectionCard>
  );
}

function DangerRow({
  title,
  description,
  action,
  icon: Icon,
  disabled = false,
  onClick,
}: {
  title: string;
  description: string;
  action: string;
  icon: typeof LogOut;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <div className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-[13px] text-foreground">{title}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{description}</div>
      </div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={disabled}
        onClick={onClick}
        className="h-8 shrink-0 gap-1.5 text-xs text-destructive hover:text-destructive disabled:cursor-not-allowed"
      >
        <Icon className="h-3.5 w-3.5" />
        {action}
      </Button>
    </div>
  );
}
