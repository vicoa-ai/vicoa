import { describe, expect, it } from 'vitest';
import type { AgentInstanceResponse, PrincipalResponse, ProjectResponse } from '@/lib/backend-api';
import { NO_PROJECT_KEY, type SessionGroup } from './session-grouping';
import { teamRowLabel, teamSessionsByProject, withTeamOnlyGroups } from './team-sessions';

function person(id: string, name: string): PrincipalResponse {
  return { type: 'user', id, name, avatar_image_uri: null, emoji: null, updated_at: null };
}

const nick = person('nick', 'Nick');
const bo = person('bo', 'Bo');

const session = (over: Partial<AgentInstanceResponse> & { id: string }): AgentInstanceResponse => ({
  agent_type_id: 't',
  agent_type_name: 'claude',
  name: null,
  status: 'ACTIVE',
  started_at: '2026-01-01T00:00:00.000Z',
  ended_at: null,
  latest_message: null,
  latest_message_at: null,
  chat_length: 0,
  project: null,
  pinned_at: null,
  ...over,
});

const project = (over: Partial<ProjectResponse> & { id: string }): ProjectResponse => ({
  name: over.id,
  key: null,
  git_remote_url: null,
  color: null,
  icon: null,
  icon_image_uri: null,
  icon_source: null,
  is_inbox: false,
  is_archived: false,
  archived_at: null,
  directories: [],
  created_at: '2026-01-01T00:00:00.000Z',
  updated_at: '2026-01-01T00:00:00.000Z',
  ...over,
});

const projects = (...ps: ProjectResponse[]) => new Map(ps.map((p) => [p.id, p]));

describe('teamSessionsByProject', () => {
  const mine = project({ id: 'mine' });
  const added = project({ id: 'added', owner: nick, followed: true });
  const notAdded = project({ id: 'not-added', owner: nick, followed: false });
  const archived = project({ id: 'archived', is_archived: true });
  const all = projects(mine, added, notAdded, archived);

  it("files other people's open sessions under the projects you list", () => {
    const byProject = teamSessionsByProject(
      [
        session({ id: 'a', owner: bo, project_id: 'mine' }),
        session({ id: 'b', owner: nick, project_id: 'added' }),
        session({ id: 'c', owner: nick, project_id: 'not-added' }),
        session({ id: 'd', owner: nick, project_id: 'archived' }),
        session({ id: 'e', owner: nick, project_id: null }),
      ],
      all,
    );
    expect([...byProject.keys()].sort()).toEqual(['added', 'mine']);
  });

  it('leaves out finished sessions and rows without an owner', () => {
    const byProject = teamSessionsByProject(
      [
        session({ id: 'a', owner: bo, project_id: 'mine', status: 'COMPLETED' }),
        session({ id: 'b', project_id: 'mine' }),
      ],
      all,
    );
    expect(byProject.size).toBe(0);
  });

  it('puts the most recently active first', () => {
    const byProject = teamSessionsByProject(
      [
        session({ id: 'old', owner: bo, project_id: 'mine', latest_message_at: '2026-01-02T00:00:00Z' }),
        session({ id: 'new', owner: nick, project_id: 'mine', latest_message_at: '2026-01-03T00:00:00Z' }),
        session({ id: 'quiet', owner: bo, project_id: 'mine' }),
      ],
      all,
    );
    expect(byProject.get('mine')?.map((i) => i.id)).toEqual(['new', 'old', 'quiet']);
  });
});

describe('withTeamOnlyGroups', () => {
  const group = (key: string): SessionGroup => ({ key, label: key, instances: [] });
  const all = projects(project({ id: 'p1', name: 'One' }), project({ id: 'p2', name: 'Two' }), project({ id: 'p3', name: 'Three' }));

  it('adds a group for a project only other people are working in, in project order', () => {
    const groups = withTeamOnlyGroups(
      [group('PINNED'), group('p1'), group('p3'), group(NO_PROJECT_KEY)],
      new Map([['p2', [session({ id: 's', owner: bo, project_id: 'p2' })]]]),
      ['p1', 'p2', 'p3'],
      all,
    );
    expect(groups.map((g) => g.key)).toEqual(['PINNED', 'p1', 'p2', 'p3', NO_PROJECT_KEY]);
    expect(groups[2]).toMatchObject({ label: 'Two', instances: [] });
  });

  it('leaves the groups alone when every team project already has one', () => {
    const own = [group('p1')];
    expect(withTeamOnlyGroups(own, new Map([['p1', []]]), ['p1'], all)).toBe(own);
  });
});

describe('teamRowLabel', () => {
  it("says Team for a team's project", () => {
    expect(teamRowLabel([session({ id: 'a', owner: nick })], project({ id: 'p', team_id: 't' }))).toBe('Team');
  });

  it('names the one person whose sessions these are', () => {
    expect(teamRowLabel([session({ id: 'a', owner: nick }), session({ id: 'b', owner: nick })], project({ id: 'p' }))).toBe(
      'Nick',
    );
  });

  it('says Team once several people are in it', () => {
    expect(teamRowLabel([session({ id: 'a', owner: nick }), session({ id: 'b', owner: bo })], project({ id: 'p' }))).toBe(
      'Team',
    );
  });
});
