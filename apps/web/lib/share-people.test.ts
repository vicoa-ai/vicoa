import { describe, expect, it } from 'vitest';
import type { ProjectPerson, ProjectGrantCreated, SessionShare } from './backend-api';
import {
  GRANT_ROLE_OPTIONS,
  SCOPE_LABELS,
  SCOPE_ORDER,
  SESSION_ACCESS_OPTIONS,
  automationsDeniedMessage,
  inviteOutcome,
  looksLikeEmail,
  personLines,
  reachCount,
  roleLabel,
  scopeSummary,
  sessionReach,
  sessionShareLines,
  toggleScope,
} from './share-people';

function person(overrides: Partial<ProjectPerson> = {}): ProjectPerson {
  return {
    id: 'g1',
    principal: {
      type: 'user',
      id: 'u1',
      name: 'Ada',
      avatar_image_uri: null,
      emoji: null,
      updated_at: null,
    },
    email: 'ada@example.com',
    pending: false,
    role: 'viewer',
    scopes: ['tasks', 'sessions'],
    member_count: null,
    is_owner: false,
    is_self: false,
    created_at: null,
    ...overrides,
  };
}

describe('personLines', () => {
  it('names a person and puts the address underneath', () => {
    expect(personLines(person())).toEqual({ primary: 'Ada', secondary: 'ada@example.com' });
  });

  it('falls back to the address, then a neutral label, never "Unknown"', () => {
    const nameless = person({ principal: { ...person().principal, name: null } });
    expect(personLines(nameless)).toEqual({ primary: 'ada@example.com', secondary: null });
    expect(personLines({ ...nameless, email: null }).primary).toBe('Vicoa user');
  });

  it('marks a pending invite', () => {
    const pending = person({
      pending: true,
      principal: { ...person().principal, id: null, name: null },
    });
    expect(personLines(pending)).toEqual({
      primary: 'ada@example.com',
      secondary: 'Pending, joins when they sign up',
    });
  });

  it('reads a team as "Team · n members"', () => {
    const team = person({
      principal: { ...person().principal, type: 'team', name: 'Crew' },
      email: null,
      member_count: 1,
    });
    expect(personLines(team)).toEqual({ primary: 'Crew', secondary: 'Team · 1 member' });
    expect(personLines({ ...team, member_count: 3 }).secondary).toBe('Team · 3 members');
  });
});

describe('sessionShareLines', () => {
  const share: SessionShare = {
    id: 's1',
    principal_type: 'user',
    email: 'bo@example.com',
    access: 'READ',
    user_id: 'u2',
    team_id: null,
    display_name: 'Bo',
    avatar_image_uri: null,
    member_count: null,
    invited: false,
    is_owner: false,
    created_at: '',
    updated_at: '',
  };

  it('mirrors the project row rules', () => {
    expect(sessionShareLines(share)).toEqual({ primary: 'Bo', secondary: 'bo@example.com' });
    expect(sessionShareLines({ ...share, invited: true, display_name: null }).secondary).toBe(
      'Pending, joins when they sign up',
    );
    expect(
      sessionShareLines({ ...share, principal_type: 'team', display_name: 'Crew', member_count: 2 }),
    ).toEqual({ primary: 'Crew', secondary: 'Team · 2 members' });
  });
});

describe('toggleScope', () => {
  it('adds and removes in canonical order', () => {
    expect(toggleScope(['sessions'], 'tasks')).toEqual(['tasks', 'sessions']);
    expect(toggleScope(['tasks', 'sessions'], 'tasks')).toEqual(['sessions']);
  });

  it('never leaves a grant with no scope', () => {
    expect(toggleScope(['tasks'], 'tasks')).toEqual(['tasks']);
    expect(toggleScope(['automations'], 'automations')).toEqual(['automations']);
  });

  it('keeps automations last, wherever it was added', () => {
    expect(toggleScope(['tasks', 'sessions'], 'automations')).toEqual(['tasks', 'sessions', 'automations']);
    expect(toggleScope(['automations'], 'tasks')).toEqual(['tasks', 'automations']);
    expect(toggleScope(['tasks', 'sessions', 'automations'], 'sessions')).toEqual(['tasks', 'automations']);
  });
});

describe('scopeSummary', () => {
  it('reads naturally', () => {
    expect(scopeSummary(['sessions', 'tasks'])).toBe('Tasks and sessions');
    expect(scopeSummary(['sessions'])).toBe('Sessions');
  });

  it('lists three as a sentence, in canonical order', () => {
    expect(scopeSummary(['automations', 'sessions', 'tasks'])).toBe('Tasks, sessions and automations');
    expect(scopeSummary(['automations', 'tasks'])).toBe('Tasks and automations');
    expect(scopeSummary(['automations'])).toBe('Automations');
    expect(scopeSummary([])).toBe('');
  });

  it('offers every scope, automations included', () => {
    expect(SCOPE_ORDER).toEqual(['tasks', 'sessions', 'automations']);
    expect(SCOPE_LABELS.automations).toBe('Automations');
  });
});

describe('automationsDeniedMessage', () => {
  const forbidden = Object.assign(new Error('Requires admin access'), { status: 403 });

  it('explains a refusal over automations in plain words', () => {
    expect(automationsDeniedMessage(forbidden, ['tasks', 'sessions', 'automations'], 'invite')).toMatch(
      /Untick Automations/,
    );
    expect(automationsDeniedMessage(forbidden, ['automations'], 'change')).toMatch(/change access/);
    expect(automationsDeniedMessage(forbidden, ['tasks', 'automations'], 'remove')).toMatch(/remove access/);
  });

  it('leaves every other failure to the generic message', () => {
    // A 403 on a write that never touched automations is a different refusal.
    expect(automationsDeniedMessage(forbidden, ['tasks', 'sessions'], 'change')).toBeNull();
    const conflict = Object.assign(new Error('Already shared'), { status: 409 });
    expect(automationsDeniedMessage(conflict, ['automations'], 'invite')).toBeNull();
    expect(automationsDeniedMessage(new Error('offline'), ['automations'], 'invite')).toBeNull();
    expect(automationsDeniedMessage('nope', ['automations'], 'invite')).toBeNull();
  });
});

describe('inviteOutcome', () => {
  const created = (overrides: Partial<ProjectGrantCreated>): ProjectGrantCreated => ({
    ...person(),
    email_sent: false,
    ...overrides,
  });

  it('says the email went out', () => {
    expect(inviteOutcome(created({ email_sent: true }))).toBe('Invite sent to ada@example.com.');
  });

  it('is honest when the server cannot send mail', () => {
    expect(inviteOutcome(created({}))).toMatch(/can't send email/);
  });

  it('names a team', () => {
    const team = created({
      principal: { ...person().principal, type: 'team', name: 'Crew' },
      email: null,
    });
    expect(inviteOutcome(team)).toBe('Shared with Crew.');
  });
});

describe('copy rules', () => {
  const strings = [
    ...GRANT_ROLE_OPTIONS.flatMap((o) => [o.label, o.description]),
    ...SESSION_ACCESS_OPTIONS.flatMap((o) => [o.label, o.description]),
    inviteOutcome({ ...person(), email_sent: false }),
    personLines(person({ pending: true })).secondary ?? '',
    ...Object.values(SCOPE_LABELS),
    scopeSummary(SCOPE_ORDER),
    ...(['invite', 'change', 'remove'] as const).map(
      (action) =>
        automationsDeniedMessage(Object.assign(new Error(''), { status: 403 }), ['automations'], action) ?? '',
    ),
  ];

  it('has no em or en dashes in user-facing copy', () => {
    for (const s of strings) {
      expect(s).not.toContain('—');
      expect(s).not.toContain('–');
    }
  });

  it('labels roles', () => {
    expect(roleLabel('owner')).toBe('Owner');
    expect(roleLabel('commenter')).toBe('Commenter');
    expect(roleLabel('WRITE')).toBe('Editor');
  });
});

describe('looksLikeEmail / sessionReach', () => {
  it('catches the obvious', () => {
    expect(looksLikeEmail(' a@b.co ')).toBe(true);
    expect(looksLikeEmail('crew')).toBe(false);
  });

  it('counts only grants that reach sessions, never the owner', () => {
    const owner = person({ id: null, is_owner: true, role: 'owner' });
    const tasksOnly = person({ id: 'g2', scopes: ['tasks'] });
    expect(sessionReach([owner, person(), tasksOnly]).map((p) => p.id)).toEqual(['g1']);
  });
});

describe('reachCount', () => {
  it('expands a team into its members', () => {
    const team = person({
      id: 'g3',
      principal: { ...person().principal, type: 'team', name: 'Crew' },
      member_count: 4,
    });
    expect(reachCount([person(), team])).toBe(5);
  });
});
