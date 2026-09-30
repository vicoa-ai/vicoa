import { describe, expect, it } from 'vitest';
import type { AgentInstanceResponse, PrincipalResponse, ProjectResponse } from './backend-api';
import { canFollowProject, groupSharedWithMe, isFollowedSharedProject } from './shared-with-me';

const ada: PrincipalResponse = {
  type: 'user',
  id: 'ada',
  name: 'Ada',
  avatar_image_uri: null,
  emoji: null,
  updated_at: null,
};

function project(id: string, overrides: Partial<ProjectResponse> = {}): ProjectResponse {
  return {
    id,
    name: id,
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
    created_at: '',
    updated_at: '',
    owner: ada,
    role: 'viewer',
    scopes: ['tasks', 'sessions'],
    ...overrides,
  };
}

function session(id: string, projectId: string | null, owner = ada): AgentInstanceResponse {
  return {
    id,
    agent_type_id: 't',
    agent_type_name: 'claude code',
    name: id,
    status: 'ACTIVE',
    started_at: '',
    ended_at: null,
    latest_message: null,
    latest_message_at: null,
    chat_length: 0,
    project_id: projectId,
    owner,
    viewer_role: 'viewer',
  };
}

describe('groupSharedWithMe', () => {
  it('lists shared projects in server order, sessions under them', () => {
    const groups = groupSharedWithMe(
      [session('s1', 'beta'), session('s2', 'alpha')],
      [project('alpha'), project('beta')],
    );
    expect(groups.map((g) => [g.key, g.instances.map((i) => i.id)])).toEqual([
      ['alpha', ['s2']],
      ['beta', ['s1']],
    ]);
  });

  it('keeps a tasks-only share with no sessions, and skips my own and archived projects', () => {
    const groups = groupSharedWithMe(
      [],
      [
        project('board', { scopes: ['tasks'] }),
        project('mine', { owner: null, role: 'owner' }),
        project('old', { is_archived: true }),
      ],
    );
    expect(groups.map((g) => g.key)).toEqual(['board']);
  });

  it("lists a team's project you are on as your own, not as shared", () => {
    const groups = groupSharedWithMe(
      [session('s1', 'crew')],
      [
        project('crew', {
          owner: { type: 'team', id: 't1', name: 'Crew', avatar_image_uri: null, emoji: null, updated_at: null },
          followed: true,
          is_team_member: true,
        }),
      ],
    );
    expect(groups).toEqual([]);
  });

  it('gathers sessions shared on their own under their owner', () => {
    const bo: PrincipalResponse = { ...ada, id: 'bo', name: 'Bo' };
    const groups = groupSharedWithMe(
      [session('s1', 'hidden'), session('s2', null, bo), session('s3', null)],
      [],
    );
    expect(groups.map((g) => [g.key, g.label, g.instances.map((i) => i.id)])).toEqual([
      ['owner:ada', 'Ada', ['s1', 's3']],
      ['owner:bo', 'Bo', ['s2']],
    ]);
  });

  it('leaves out a project added to the sidebar, sessions and all', () => {
    const groups = groupSharedWithMe(
      [session('s1', 'added'), session('s2', 'alpha')],
      [project('added', { followed: true }), project('alpha')],
    );
    expect(groups.map((g) => [g.key, g.instances.map((i) => i.id)])).toEqual([
      ['alpha', ['s2']],
    ]);
  });

  it("leaves out a collaborator's session in a project of my own", () => {
    // It sits under that project's Team row, not under its author's name.
    const groups = groupSharedWithMe(
      [session('s1', 'mine'), session('s2', 'alpha')],
      [project('mine', { owner: null }), project('alpha')],
    );
    expect(groups.map((g) => [g.key, g.instances.map((i) => i.id)])).toEqual([
      ['alpha', ['s2']],
    ]);
  });
});

describe('sidebar membership of shared projects', () => {
  it('is added only when the server says so', () => {
    expect(isFollowedSharedProject(project('p', { followed: true }))).toBe(true);
    expect(isFollowedSharedProject(project('p'))).toBe(false);
    // Your own project is not "added" — it is simply yours.
    expect(isFollowedSharedProject(project('p', { owner: null, followed: true }))).toBe(false);
    // A project of a team you are on is your team's work, not a share.
    expect(
      isFollowedSharedProject(project('p', { followed: true, is_team_member: true })),
    ).toBe(false);
  });

  it('can be added only with the sessions scope', () => {
    expect(canFollowProject(project('p'))).toBe(true);
    expect(canFollowProject(project('p', { scopes: ['tasks'] }))).toBe(false);
    expect(canFollowProject(project('p', { owner: null }))).toBe(false);
  });
});
