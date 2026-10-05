/**
 * Pure helpers behind Settings → Teams, the join page and the account-menu
 * invitations (collaboration §3.2, §3.3). No React, so the rules a screen
 * applies (who may change whose role, what a link's facts line says) are
 * testable on their own.
 *
 * A team is a group of people you share projects and sessions with. It is not
 * a workspace: nothing here scopes or switches the app.
 */

import {
  seatLimitFromError,
  type TeamInviteLink,
  type TeamMember,
  type TeamRole,
} from '@/lib/backend-api';
import { getDesktopConfig } from '@/lib/runtime-config';

/** The 402 capability for owning a team (creating one, or being handed one). */
export const CAPABILITY_TEAM_OWN = 'collab.team_own';

/**
 * A failed team action as the UI shows it: a 402 is either a plan that cannot
 * own a team (`team-own`, offered Team or Pro) or a seat limit (rendered by
 * `<SeatLimitNotice>`); anything else is a one-line message.
 */
export type TeamActionError =
  | { kind: 'team-own'; detail: string }
  | { kind: 'seat-limit'; detail: string }
  | { kind: 'message'; message: string };

export function toTeamActionError(err: unknown, fallback: string): TeamActionError {
  const limit = seatLimitFromError(err);
  if (limit?.capability === CAPABILITY_TEAM_OWN) return { kind: 'team-own', detail: limit.detail };
  if (limit) return { kind: 'seat-limit', detail: limit.detail };
  const message = err instanceof Error && err.message.trim() ? err.message : fallback;
  return { kind: 'message', message };
}

/** The HTTP status a backend call failed with, when it carried one. */
export function errorStatus(err: unknown): number | null {
  if (!(err instanceof Error)) return null;
  const status = (err as Error & { status?: unknown }).status;
  return typeof status === 'number' ? status : null;
}

export type InvitableRole = Exclude<TeamRole, 'owner'>;

export const TEAMS_SETTINGS_PATH = '/dashboard/settings';

/** Settings → Teams, optionally opened on one team's detail view. */
export function teamsSettingsHref(teamId?: string | null): string {
  const params = new URLSearchParams({ tab: 'teams' });
  if (teamId) params.set('teamId', teamId);
  return `${TEAMS_SETTINGS_PATH}?${params.toString()}`;
}

/** The in-app path an invite link opens (under /dashboard so sign-in bounces
 *  back to it with the token intact). */
export function teamJoinPath(token: string): string {
  return `/dashboard/join/${encodeURIComponent(token)}`;
}

/** `${origin}/dashboard/join/<token>`, tolerant of a trailing slash. */
export function buildTeamJoinUrl(origin: string, token: string): string {
  return `${origin.replace(/\/$/, '')}${teamJoinPath(token)}`;
}

/**
 * The URL an invite link is shared as. Mirrors `shareUrl` in
 * `lib/public-share-api.ts`: on the web it is this deployment's own origin (a
 * self-host shares its own address); the desktop renderer is served from a
 * loopback port, so it names the web deployment it belongs to instead.
 */
export function teamJoinUrl(token: string): string {
  const fallback = process.env.NEXT_PUBLIC_VICOA_WEB_URL ?? 'https://vicoa.ai';
  const origin = getDesktopConfig()
    ? fallback
    : typeof window !== 'undefined'
      ? window.location.origin
      : fallback;
  return buildTeamJoinUrl(origin, token);
}

export const TEAM_ROLE_LABEL: Record<TeamRole, string> = {
  owner: 'Owner',
  admin: 'Admin',
  member: 'Member',
  viewer: 'Viewer',
};

/** One line per assignable role, shown under it in pickers and menus. */
export const TEAM_ROLE_DESCRIPTION: Record<InvitableRole, string> = {
  admin: 'Invite and remove members, manage invite links',
  member: "Works in the team's projects",
  viewer: 'Sees and comments for free, takes no seat',
};

/** The roles that edit, and so take a seat on the owner's plan. */
export function takesSeat(role: TeamRole): boolean {
  return role !== 'viewer';
}

/** "an admin", "a member", "a viewer", "the owner": for "invited you as …". */
export function roleWithArticle(role: TeamRole): string {
  if (role === 'owner') return 'the owner';
  if (role === 'admin') return 'an admin';
  if (role === 'viewer') return 'a viewer';
  return 'a member';
}

/** "Ada invited you as an admin", or "Invited you as a member" with no inviter. */
export function invitedYouLine(inviterName: string | null | undefined, role: TeamRole): string {
  const who = inviterName?.trim();
  return who
    ? `${who} invited you as ${roleWithArticle(role)}`
    : `Invited you as ${roleWithArticle(role)}`;
}

/** Owners and admins manage members and invite links. */
export function canManageTeam(role: TeamRole | null | undefined): boolean {
  return role === 'owner' || role === 'admin';
}

/** Roles the viewer may hand out: only the owner can make admins. Viewers
 *  are free, so anyone who manages the team can invite one. */
export function invitableRoles(viewerRole: TeamRole | null | undefined): InvitableRole[] {
  if (viewerRole === 'owner') return ['member', 'admin', 'viewer'];
  if (viewerRole === 'admin') return ['member', 'viewer'];
  return [];
}

export function memberCountLabel(count: number): string {
  return `${count} ${count === 1 ? 'member' : 'members'}`;
}

/**
 * The name a member row shows. Plain members receive no emails from the
 * backend, so the fallback chain never invents one: name, then the email when
 * the server sent it, then a neutral placeholder.
 */
export function memberDisplayName(member: Pick<TeamMember, 'display_name' | 'email'>): string {
  return member.display_name?.trim() || member.email?.trim() || 'Vicoa user';
}

const ROLE_RANK: Record<TeamRole, number> = { owner: 0, admin: 1, member: 2, viewer: 3 };

/** Active members (owner first, then admins, members and viewers, by name)
 *  and the invited ones, which the detail view lists apart. */
export function partitionMembers(members: TeamMember[]): {
  active: TeamMember[];
  pending: TeamMember[];
} {
  const byRoleThenName = (a: TeamMember, b: TeamMember) =>
    ROLE_RANK[a.role] - ROLE_RANK[b.role] ||
    memberDisplayName(a).localeCompare(memberDisplayName(b));
  return {
    active: members.filter((m) => m.status === 'active').sort(byRoleThenName),
    pending: members.filter((m) => m.status === 'invited').sort(byRoleThenName),
  };
}

export interface MemberActions {
  isSelf: boolean;
  /** Show "Change role" at all. */
  showChangeRole: boolean;
  /** Set when "Change role" is shown but locked, with the reason to show. */
  changeRoleLockedReason: string | null;
  /** "Remove" (someone else) or "Leave team" (yourself), or null for none. */
  remove: 'remove' | 'leave' | null;
  /** "Make owner": the owner handing the team to another active member. */
  makeOwner: boolean;
}

/**
 * What the `⋯` menu on a member row offers the viewer. Mirrors the backend's
 * rules so the UI never offers an action that can only fail:
 * - only the owner changes roles, and the owner row can never be changed;
 * - owners and admins remove others, but admins cannot remove admins;
 * - members and viewers remove nobody but themselves;
 * - anyone but the owner may remove themselves (leaving the team);
 * - nobody removes the owner;
 * - the owner may hand the team to anyone who has joined (not a pending
 *   invite), staying on as an admin.
 */
export function memberActions(
  viewer: { role: TeamRole; userId: string | null | undefined },
  member: Pick<TeamMember, 'role' | 'user_id'> & { status?: TeamMember['status'] },
): MemberActions {
  const isSelf = !!viewer.userId && member.user_id === viewer.userId;
  const isOwnerRow = member.role === 'owner';

  const showChangeRole = viewer.role === 'owner';
  const changeRoleLockedReason =
    showChangeRole && isOwnerRow ? "The owner's role can't be changed" : null;

  let remove: MemberActions['remove'] = null;
  if (isOwnerRow) {
    remove = null;
  } else if (isSelf) {
    remove = 'leave';
  } else if (viewer.role === 'owner') {
    remove = 'remove';
  } else if (viewer.role === 'admin' && (member.role === 'member' || member.role === 'viewer')) {
    remove = 'remove';
  }

  const makeOwner =
    viewer.role === 'owner' &&
    !isSelf &&
    !isOwnerRow &&
    !!member.user_id &&
    (member.status ?? 'active') === 'active';

  return { isSelf, showChangeRole, changeRoleLockedReason, remove, makeOwner };
}

export function hasMemberActions(actions: MemberActions): boolean {
  return actions.showChangeRole || actions.remove !== null || actions.makeOwner;
}

/** "Team agent", then "Team agent 2", … — agent names are unique within
 *  their owner, and a team is one. */
export function nextTeamAgentName(existing: string[]): string {
  const taken = new Set(existing.map((name) => name.trim().toLowerCase()));
  if (!taken.has('team agent')) return 'Team agent';
  let n = 2;
  while (taken.has(`team agent ${n}`)) n += 1;
  return `Team agent ${n}`;
}

export const INVITE_LINK_EXPIRY_OPTIONS = [
  { value: '7', label: '7 days', days: 7 },
  { value: '30', label: '30 days', days: 30 },
  { value: 'never', label: 'Never', days: null },
] as const;

export type InviteLinkExpiryValue = (typeof INVITE_LINK_EXPIRY_OPTIONS)[number]['value'];

export function expiryDays(value: InviteLinkExpiryValue): number | null {
  return INVITE_LINK_EXPIRY_OPTIONS.find((o) => o.value === value)?.days ?? null;
}

/**
 * The optional "max uses" field: blank means unlimited (null), a positive
 * whole number is the cap, anything else is invalid.
 */
export function parseMaxUses(input: string): { ok: true; value: number | null } | { ok: false } {
  const trimmed = input.trim();
  if (!trimmed) return { ok: true, value: null };
  if (!/^\d+$/.test(trimmed)) return { ok: false };
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value < 1) return { ok: false };
  return { ok: true, value };
}

/** "3 of 10 uses", or "3 uses" for an unlimited link. */
export function inviteLinkUsesLabel(link: Pick<TeamInviteLink, 'uses' | 'max_uses'>): string {
  if (link.max_uses != null) return `${link.uses} of ${link.max_uses} uses`;
  return `${link.uses} ${link.uses === 1 ? 'use' : 'uses'}`;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** "Never expires", "Expires in 3 days", "Expired". */
export function inviteLinkExpiryLabel(expiresAt: string | null, now: number = Date.now()): string {
  if (!expiresAt) return 'Never expires';
  const at = Date.parse(expiresAt);
  if (Number.isNaN(at)) return 'Never expires';
  const remaining = at - now;
  if (remaining <= 0) return 'Expired';
  const days = Math.ceil(remaining / DAY_MS);
  if (days <= 1) return 'Expires within a day';
  return `Expires in ${days} days`;
}
