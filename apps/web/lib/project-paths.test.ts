import { describe, expect, it } from 'vitest';
import type { ProjectResponse } from '@/lib/backend-api';
import {
  canonicalPath,
  directoryChipLabel,
  joinSubpath,
  pathBasename,
  projectsOnMachine,
  relativeSubpath,
  resolveProjectForDirectory,
} from '@/lib/project-paths';

const HOME = '/Users/nick';

function project(
  name: string,
  directories: { machine_id: string; local_path: string }[],
  extra: Partial<ProjectResponse> = {},
): ProjectResponse {
  return {
    id: `id-${name}`,
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
    directories: directories.map((d) => ({ ...d, machine_name: null })),
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...extra,
  };
}

describe('canonicalPath', () => {
  it('expands ~ and drops trailing slashes', () => {
    expect(canonicalPath('~/src/app/', HOME)).toBe('/Users/nick/src/app');
    expect(canonicalPath('/', HOME)).toBe('/');
  });

  it('leaves ~ alone when the home dir is unknown', () => {
    expect(canonicalPath('~/src/app', null)).toBe('~/src/app');
  });
});

describe('relativeSubpath', () => {
  it('is empty for the root itself, in either form', () => {
    expect(relativeSubpath('~/src/app', '/Users/nick/src/app', HOME)).toBe('');
    expect(relativeSubpath('/Users/nick/src/app/', '~/src/app', HOME)).toBe('');
  });

  it('is the part below the root', () => {
    expect(relativeSubpath('~/src/app/apps/web', '~/src/app', HOME)).toBe('apps/web');
  });

  it('is null outside the root, on a path boundary', () => {
    expect(relativeSubpath('~/src/apple', '~/src/app', HOME)).toBeNull();
    expect(relativeSubpath('~/other', '~/src/app', HOME)).toBeNull();
    // A worktree lives OUTSIDE the repo — never "inside" its root.
    expect(
      relativeSubpath('~/vicoa/workspaces/app-worktrees/feat/app', '~/src/app', HOME),
    ).toBeNull();
  });
});

describe('joinSubpath', () => {
  it('joins without doubled slashes and keeps a bare base', () => {
    expect(joinSubpath('/wt/app/', 'apps/web')).toBe('/wt/app/apps/web');
    expect(joinSubpath('/wt/app', '')).toBe('/wt/app');
    expect(joinSubpath('/', 'x')).toBe('/x');
  });
});

describe('resolveProjectForDirectory', () => {
  const projects = [
    project('vicoa', [
      { machine_id: 'm1', local_path: '~/projects/vicoa-ai/vicoa' },
      { machine_id: 'm2', local_path: '/srv/vicoa' },
    ]),
    project('umbrella', [{ machine_id: 'm1', local_path: '~/projects/vicoa-ai' }]),
  ];

  it('picks the longest linked folder on the machine and splits the subpath', () => {
    const match = resolveProjectForDirectory(
      '~/projects/vicoa-ai/vicoa/apps/web',
      'm1',
      projects,
      HOME,
    );
    expect(match?.project.name).toBe('vicoa');
    expect(match?.root).toBe('~/projects/vicoa-ai/vicoa');
    expect(match?.subpath).toBe('apps/web');
  });

  it('falls back to the enclosing project for a sibling folder', () => {
    const match = resolveProjectForDirectory('~/projects/vicoa-ai/plans', 'm1', projects, HOME);
    expect(match?.project.name).toBe('umbrella');
    expect(match?.subpath).toBe('plans');
  });

  it('only considers folders on the selected machine', () => {
    expect(resolveProjectForDirectory('/srv/vicoa', 'm1', projects, HOME)).toBeNull();
    expect(resolveProjectForDirectory('/srv/vicoa', 'm2', projects, HOME)?.project.name).toBe(
      'vicoa',
    );
  });

  it('is null for a folder no project claims', () => {
    expect(resolveProjectForDirectory('~/scratch', 'm1', projects, HOME)).toBeNull();
    expect(resolveProjectForDirectory('', 'm1', projects, HOME)).toBeNull();
  });
});

describe('projectsOnMachine', () => {
  it('lists linked projects newest activity first, archived excluded', () => {
    const rows = projectsOnMachine(
      [
        project('old', [{ machine_id: 'm1', local_path: '/a' }], {
          last_activity_at: '2026-01-01T00:00:00Z',
        }),
        project('new', [{ machine_id: 'm1', local_path: '/b' }], {
          last_activity_at: '2026-02-01T00:00:00Z',
        }),
        project('never', [{ machine_id: 'm1', local_path: '/c' }]),
        project('elsewhere', [{ machine_id: 'm2', local_path: '/d' }]),
        project('gone', [{ machine_id: 'm1', local_path: '/e' }], { is_archived: true }),
      ],
      'm1',
    );
    expect(rows.map((r) => r.project.name)).toEqual(['new', 'old', 'never']);
    expect(rows[0].path).toBe('/b');
  });

  it('puts the projects the user ranked first, in rank order, ahead of recency', () => {
    const rows = projectsOnMachine(
      [
        project('newest', [{ machine_id: 'm1', local_path: '/a' }], {
          last_activity_at: '2026-03-01T00:00:00Z',
        }),
        project('second', [{ machine_id: 'm1', local_path: '/b' }], {
          position: 1,
          last_activity_at: '2026-01-01T00:00:00Z',
        }),
        project('first', [{ machine_id: 'm1', local_path: '/c' }], { position: 0 }),
        project('older', [{ machine_id: 'm1', local_path: '/d' }], {
          last_activity_at: '2026-02-01T00:00:00Z',
        }),
      ],
      'm1',
    );
    expect(rows.map((r) => r.project.name)).toEqual(['first', 'second', 'newest', 'older']);
  });
});

describe('directoryChipLabel', () => {
  const vicoa = project('vicoa', [{ machine_id: 'm1', local_path: '~/src/vicoa' }]);

  it('is the project name, with the subfolder when below the root', () => {
    expect(
      directoryChipLabel('~/src/vicoa', { project: vicoa, root: '~/src/vicoa', subpath: '' }),
    ).toBe('vicoa');
    expect(
      directoryChipLabel('~/src/vicoa/apps/web', {
        project: vicoa,
        root: '~/src/vicoa',
        subpath: 'apps/web',
      }),
    ).toBe('vicoa · apps/web');
  });

  it("is the folder's own name when no project claims it", () => {
    expect(directoryChipLabel('~/scratch/thing/', null)).toBe('thing');
    expect(pathBasename('/')).toBe('/');
  });
});
