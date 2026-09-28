import { describe, expect, it } from 'vitest';

import type { TeamMember } from '@/lib/backend-api';
import {
  buildTeamJoinUrl,
  canManageTeam,
  errorStatus,
  expiryDays,
  hasMemberActions,
  inviteLinkExpiryLabel,
  inviteLinkUsesLabel,
  invitableRoles,
  invitedYouLine,
  memberActions,
  memberCountLabel,
  memberDisplayName,
  parseMaxUses,
  partitionMembers,
  roleWithArticle,
  teamJoinPath,
  teamJoinUrl,
  teamsSettingsHref,
  toTeamActionError,
} from './team-settings';

function member(overrides: Partial<TeamMember>): TeamMember {
  return {
    id: 'm',
    user_id: 'u',
    email: null,
    display_name: null,
    avatar_image_uri: null,
    role: 'member',
    status: 'active',
    joined_at: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('toTeamActionError', () => {
  const withStatus = (message: string, status: number, extra: Record<string, unknown> = {}) =>
    Object.assign(new Error(message), { status, ...extra });

  it('turns a 402 into a seat limit carrying the backend detail', () => {
    expect(
      toTeamActionError(withStatus('Your plan has 3 seats', 402, { capability: 'collab.team_seat' }), 'x'),
    ).toEqual({ kind: 'seat-limit', detail: 'Your plan has 3 seats' });
  });

  it('keeps any other message, or falls back', () => {
    expect(toTeamActionError(withStatus('Already on this team', 409), 'x')).toEqual({
      kind: 'message',
      message: 'Already on this team',
    });
    expect(toTeamActionError('boom', 'Failed')).toEqual({ kind: 'message', message: 'Failed' });
  });

  it('reads a status when there is one', () => {
    expect(errorStatus(withStatus('gone', 404))).toBe(404);
    expect(errorStatus(new Error('plain'))).toBeNull();
    expect(errorStatus(null)).toBeNull();
  });
});

describe('hrefs and URLs', () => {
  it('opens the teams tab, optionally on one team', () => {
    expect(teamsSettingsHref()).toBe('/dashboard/settings?tab=teams');
    expect(teamsSettingsHref(null)).toBe('/dashboard/settings?tab=teams');
    expect(teamsSettingsHref('t1')).toBe('/dashboard/settings?tab=teams&teamId=t1');
  });

  it('builds the join URL under /dashboard, tolerating a trailing slash', () => {
    expect(teamJoinPath('abc')).toBe('/dashboard/join/abc');
    expect(buildTeamJoinUrl('https://vicoa.ai', 'abc')).toBe('https://vicoa.ai/dashboard/join/abc');
    expect(buildTeamJoinUrl('https://vicoa.ai/', 'abc')).toBe('https://vicoa.ai/dashboard/join/abc');
    expect(teamJoinPath('a/b')).toBe('/dashboard/join/a%2Fb');
  });

  it('falls back to the web deployment when there is no window', () => {
    const expected = process.env.NEXT_PUBLIC_VICOA_WEB_URL ?? 'https://vicoa.ai';
    expect(teamJoinUrl('tok')).toBe(buildTeamJoinUrl(expected, 'tok'));
  });
});

describe('roles', () => {
  it('lets only owners and admins manage', () => {
    expect(canManageTeam('owner')).toBe(true);
    expect(canManageTeam('admin')).toBe(true);
    expect(canManageTeam('member')).toBe(false);
    expect(canManageTeam(null)).toBe(false);
  });

  it('lets only the owner invite admins', () => {
    expect(invitableRoles('owner')).toEqual(['member', 'admin']);
    expect(invitableRoles('admin')).toEqual(['member']);
    expect(invitableRoles('member')).toEqual([]);
  });

  it('phrases a role for a sentence', () => {
    expect(roleWithArticle('admin')).toBe('an admin');
    expect(roleWithArticle('member')).toBe('a member');
    expect(roleWithArticle('owner')).toBe('the owner');
  });

  it('says who invited you, when the server named them', () => {
    expect(invitedYouLine('Ada', 'admin')).toBe('Ada invited you as an admin');
    expect(invitedYouLine(null, 'member')).toBe('Invited you as a member');
    expect(invitedYouLine('  ', 'member')).toBe('Invited you as a member');
  });

  it('counts members', () => {
    expect(memberCountLabel(1)).toBe('1 member');
    expect(memberCountLabel(0)).toBe('0 members');
    expect(memberCountLabel(4)).toBe('4 members');
  });
});

describe('memberDisplayName', () => {
  it('prefers the name, then an email the server sent, then a placeholder', () => {
    expect(memberDisplayName({ display_name: 'Ada', email: 'ada@x.io' })).toBe('Ada');
    expect(memberDisplayName({ display_name: '  ', email: 'ada@x.io' })).toBe('ada@x.io');
    expect(memberDisplayName({ display_name: null, email: null })).toBe('Vicoa user');
  });
});

describe('partitionMembers', () => {
  it('splits invited from active and orders owner, admins, members, then by name', () => {
    const members = [
      member({ id: '1', display_name: 'Zed', role: 'member' }),
      member({ id: '2', display_name: 'Bob', role: 'admin' }),
      member({ id: '3', display_name: 'Amy', role: 'member' }),
      member({ id: '4', display_name: 'Olga', role: 'owner' }),
      member({ id: '5', email: 'new@x.io', role: 'member', status: 'invited', user_id: null }),
    ];
    const { active, pending } = partitionMembers(members);
    expect(active.map((m) => m.id)).toEqual(['4', '2', '3', '1']);
    expect(pending.map((m) => m.id)).toEqual(['5']);
  });
});

describe('memberActions', () => {
  const owner = { role: 'owner' as const, userId: 'u-owner' };
  const admin = { role: 'admin' as const, userId: 'u-admin' };
  const plain = { role: 'member' as const, userId: 'u-member' };

  const ownerRow = member({ role: 'owner', user_id: 'u-owner' });
  const adminRow = member({ role: 'admin', user_id: 'u-admin' });
  const otherAdminRow = member({ role: 'admin', user_id: 'u-admin-2' });
  const memberRow = member({ role: 'member', user_id: 'u-member' });
  const otherMemberRow = member({ role: 'member', user_id: 'u-member-2' });
  const invitedRow = member({ role: 'member', user_id: null, status: 'invited' });

  it('owner: changes any non-owner role, removes anyone but themselves', () => {
    expect(memberActions(owner, adminRow)).toEqual({
      isSelf: false,
      showChangeRole: true,
      changeRoleLockedReason: null,
      remove: 'remove',
    });
    expect(memberActions(owner, invitedRow).remove).toBe('remove');
  });

  it("owner row: role locked with a reason, and the owner can't leave", () => {
    const actions = memberActions(owner, ownerRow);
    expect(actions.isSelf).toBe(true);
    expect(actions.showChangeRole).toBe(true);
    expect(actions.changeRoleLockedReason).toBe("The owner's role can't be changed");
    expect(actions.remove).toBeNull();
  });

  it('admin: removes members only, never admins or the owner, and cannot change roles', () => {
    expect(memberActions(admin, otherMemberRow)).toMatchObject({ showChangeRole: false, remove: 'remove' });
    expect(memberActions(admin, invitedRow).remove).toBe('remove');
    expect(memberActions(admin, otherAdminRow).remove).toBeNull();
    expect(hasMemberActions(memberActions(admin, otherAdminRow))).toBe(false);
    expect(memberActions(admin, ownerRow).remove).toBeNull();
    expect(hasMemberActions(memberActions(admin, ownerRow))).toBe(false);
  });

  it('anyone but the owner can leave', () => {
    expect(memberActions(admin, adminRow).remove).toBe('leave');
    expect(memberActions(plain, memberRow).remove).toBe('leave');
  });

  it('plain member: no actions on others', () => {
    expect(hasMemberActions(memberActions(plain, otherMemberRow))).toBe(false);
    expect(hasMemberActions(memberActions(plain, ownerRow))).toBe(false);
  });

  it('an unknown viewer id never matches a row with no user id', () => {
    expect(memberActions({ role: 'member', userId: null }, invitedRow).isSelf).toBe(false);
  });
});

describe('invite links', () => {
  it('maps expiry choices to days', () => {
    expect(expiryDays('7')).toBe(7);
    expect(expiryDays('30')).toBe(30);
    expect(expiryDays('never')).toBeNull();
  });

  it('parses the optional max uses field', () => {
    expect(parseMaxUses('')).toEqual({ ok: true, value: null });
    expect(parseMaxUses('  ')).toEqual({ ok: true, value: null });
    expect(parseMaxUses('5')).toEqual({ ok: true, value: 5 });
    expect(parseMaxUses(' 12 ')).toEqual({ ok: true, value: 12 });
    expect(parseMaxUses('0')).toEqual({ ok: false });
    expect(parseMaxUses('-1')).toEqual({ ok: false });
    expect(parseMaxUses('1.5')).toEqual({ ok: false });
    expect(parseMaxUses('abc')).toEqual({ ok: false });
  });

  it('describes uses', () => {
    expect(inviteLinkUsesLabel({ uses: 2, max_uses: 10 })).toBe('2 of 10 uses');
    expect(inviteLinkUsesLabel({ uses: 1, max_uses: null })).toBe('1 use');
    expect(inviteLinkUsesLabel({ uses: 0, max_uses: null })).toBe('0 uses');
  });

  it('describes expiry', () => {
    const now = Date.parse('2026-09-26T12:00:00Z');
    expect(inviteLinkExpiryLabel(null, now)).toBe('Never expires');
    expect(inviteLinkExpiryLabel('2026-09-26T11:00:00Z', now)).toBe('Expired');
    expect(inviteLinkExpiryLabel('2026-09-26T18:00:00Z', now)).toBe('Expires within a day');
    expect(inviteLinkExpiryLabel('2026-10-03T12:00:00Z', now)).toBe('Expires in 7 days');
    expect(inviteLinkExpiryLabel('2026-10-03T11:00:00Z', now)).toBe('Expires in 7 days');
  });
});
