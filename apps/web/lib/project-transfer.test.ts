import { describe, expect, it } from 'vitest';

import type { TeamSummary } from './backend-api';
import {
  isValidProjectKey,
  moveConsequences,
  moveDestinations,
  normalizeProjectKey,
  projectKeyConflict,
} from './project-transfer';

function team(id: string, name: string, role: TeamSummary['role'] = 'member'): TeamSummary {
  return {
    id,
    name,
    slug: name.toLowerCase(),
    avatar_image_uri: null,
    role,
    member_count: 2,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  };
}

describe('moveDestinations', () => {
  const teams = [team('b', 'Beta'), team('a', 'Alpha')];

  it('offers every team, by name, for a personal project', () => {
    expect(moveDestinations({ team_id: null }, teams).map((d) => d.name)).toEqual([
      'Alpha',
      'Beta',
    ]);
  });

  it("offers personal first and skips the project's own team", () => {
    const out = moveDestinations({ team_id: 'a' }, teams);
    expect(out.map((d) => d.teamId)).toEqual([null, 'b']);
    expect(out[0].name).toBe('Personal');
  });

  it('skips teams where the caller is only a viewer', () => {
    const out = moveDestinations({ team_id: null }, [...teams, team('c', 'Gamma', 'viewer')]);
    expect(out.map((d) => d.teamId)).toEqual(['a', 'b']);
  });
});

describe('project keys', () => {
  it('normalizes and validates like the backend', () => {
    expect(normalizeProjectKey(' vic2 ')).toBe('VIC2');
    expect(isValidProjectKey('vic2')).toBe(true);
    expect(isValidProjectKey('2VIC')).toBe(false);
    expect(isValidProjectKey('V')).toBe(false);
    expect(isValidProjectKey('ABCDEFGHI')).toBe(false);
  });

  it('reads a key clash off the 409 and nothing else', () => {
    const clash = Object.assign(new Error('taken'), {
      status: 409,
      code: 'project_key_taken',
      suggestedKey: 'VIC2',
    });
    expect(projectKeyConflict(clash)).toEqual({ suggestedKey: 'VIC2' });
    expect(projectKeyConflict(Object.assign(new Error('x'), { status: 409 }))).toBeNull();
    expect(projectKeyConflict(Object.assign(new Error('x'), { status: 402 }))).toBeNull();
    expect(projectKeyConflict('nope')).toBeNull();
  });
});

describe('moveConsequences', () => {
  const alpha = { teamId: 'a', name: 'Alpha', team: team('a', 'Alpha') };

  it('tells a member they become an editor', () => {
    const lines = moveConsequences(alpha, { teamName: null }, 'member');
    expect(lines[0]).toContain('Everyone on Alpha');
    expect(lines.join(' ')).toContain('editor access as a member');
  });

  it('names the team that loses access on a team-to-team move', () => {
    const lines = moveConsequences(alpha, { teamName: 'Beta' }, 'owner');
    expect(lines).toContain('People on Beta lose access unless it is shared with them.');
  });

  it('describes taking it personal', () => {
    const lines = moveConsequences(
      { teamId: null, name: 'Personal', team: null },
      { teamName: 'Beta' },
      null,
    );
    expect(lines[0]).toContain('your personal project');
    expect(lines[0]).toContain('People on Beta');
  });

  it('never uses an em dash in copy', () => {
    const all = [
      ...moveConsequences(alpha, { teamName: 'Beta' }, 'member'),
      ...moveConsequences({ teamId: null, name: 'Personal', team: null }, { teamName: 'B' }, null),
    ].join(' ');
    expect(all).not.toContain('—');
  });
});
