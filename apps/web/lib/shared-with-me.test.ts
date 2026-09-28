import { describe, expect, it } from 'vitest';
import type { AgentInstanceResponse, PrincipalResponse, ProjectResponse } from './backend-api';
import { groupSharedWithMe } from './shared-with-me';

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
});
