import { describe, expect, it, vi } from 'vitest';
import type { getBackendAPI, ProjectResponse } from '@/lib/backend-api';
import { createProjectForFolder } from './session-project-choices';

type API = ReturnType<typeof getBackendAPI>;

function project(id: string, name: string, extra: Partial<ProjectResponse> = {}): ProjectResponse {
  return {
    id,
    name,
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
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    role: 'owner',
    scopes: ['sessions'],
    ...extra,
  };
}

describe('createProjectForFolder', () => {
  function fakeApi(linkFails = false) {
    const created = project('new', 'scratch');
    const api = {
      createProject: vi.fn(async () => created),
      setProjectDirectory: vi.fn(async (_id: string, data: { machine_id: string; local_path: string }) => {
        if (linkFails) throw new Error('link failed');
        return { ...created, directories: [{ ...data, machine_name: null }] };
      }),
      deleteProject: vi.fn(async () => undefined),
    };
    return api;
  }

  it('creates the project from the folder name and remote, then links the folder', async () => {
    const api = fakeApi();
    const linked = await createProjectForFolder(api as unknown as API, {
      folder: '~/projects/hq',
      machineId: 'm1',
      gitRemoteUrl: 'git@github.com:someone/hq.git',
    });
    expect(api.createProject).toHaveBeenCalledWith({
      name: 'hq',
      git_remote_url: 'git@github.com:someone/hq.git',
    });
    expect(api.setProjectDirectory).toHaveBeenCalledWith('new', {
      machine_id: 'm1',
      local_path: '~/projects/hq',
    });
    expect(linked.directories).toEqual([
      { machine_id: 'm1', local_path: '~/projects/hq', machine_name: null },
    ]);
    expect(api.deleteProject).not.toHaveBeenCalled();
  });

  it('sends no remote for a non-git folder', async () => {
    const api = fakeApi();
    await createProjectForFolder(api as unknown as API, {
      folder: '~/projects/scratch',
      machineId: 'm1',
    });
    expect(api.createProject).toHaveBeenCalledWith({ name: 'scratch', git_remote_url: null });
  });

  it('deletes the new project again when the link fails', async () => {
    const api = fakeApi(true);
    await expect(
      createProjectForFolder(api as unknown as API, { folder: '~/projects/scratch', machineId: 'm1' }),
    ).rejects.toThrow('link failed');
    expect(api.deleteProject).toHaveBeenCalledWith('new');
  });
});
