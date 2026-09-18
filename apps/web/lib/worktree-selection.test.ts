import { describe, expect, it } from 'vitest';
import {
  isManagedWorktreePath,
  machineSupportsWorktree,
  machineSupportsWorktreeName,
  resolveWorktreeSpawn,
  validateWorktreeName,
} from '@/lib/worktree-selection';

describe('machineSupportsWorktree', () => {
  it('is true when metadata.capabilities lists worktree', () => {
    expect(
      machineSupportsWorktree({ metadata: { capabilities: ['worktree'] } }),
    ).toBe(true);
  });

  it('reads the WS-envelope machine_metadata shape too', () => {
    expect(
      machineSupportsWorktree({ machine_metadata: { capabilities: ['worktree'] } }),
    ).toBe(true);
  });

  it('is false when capabilities is absent (old daemon)', () => {
    // The §8 landmine: a missing capability MUST read as unsupported so the UI
    // hides the option rather than silently spawning in the base dir.
    expect(
      machineSupportsWorktree({ metadata: { available_agents: { claude: true } } }),
    ).toBe(false);
  });

  it('is false when capabilities lacks worktree', () => {
    expect(machineSupportsWorktree({ metadata: { capabilities: ['other'] } })).toBe(false);
  });

  it('is false for null / malformed', () => {
    expect(machineSupportsWorktree(null)).toBe(false);
    expect(machineSupportsWorktree({})).toBe(false);
  });
});

describe('machineSupportsWorktreeName', () => {
  it('is true only when capabilities lists worktree-name', () => {
    expect(
      machineSupportsWorktreeName({ metadata: { capabilities: ['worktree', 'worktree-name'] } }),
    ).toBe(true);
    // `worktree` alone is an old daemon that would drop `name` silently and
    // spawn a random slug — the field must stay hidden.
    expect(machineSupportsWorktreeName({ metadata: { capabilities: ['worktree'] } })).toBe(
      false,
    );
    expect(machineSupportsWorktreeName(null)).toBe(false);
  });
});

describe('validateWorktreeName', () => {
  it('accepts plain, hyphenated and slash-nested names', () => {
    for (const ok of ['feat-login', 'fix_123', 'feat/login', 'a.b', 'v1.2.3']) {
      expect(validateWorktreeName(ok)).toBeNull();
    }
  });

  it('treats blank as fine (random name)', () => {
    expect(validateWorktreeName('')).toBeNull();
    expect(validateWorktreeName('   ')).toBeNull();
  });

  it('rejects the common git ref mistakes with a reason', () => {
    for (const bad of [
      'has space',
      '-leading',
      'two..dots',
      'tilde~',
      'star*',
      'q?',
      'br[x]',
      'back\\slash',
      'colon:',
      'caret^',
      'trailing.',
      'feat/',
      '/feat',
      'feat//login',
      'feat/.hidden',
      'name.lock',
      'a/b.lock/c',
      '@',
      'x@{1}',
    ]) {
      expect(validateWorktreeName(bad), bad).not.toBeNull();
    }
  });
});

describe('resolveWorktreeSpawn', () => {
  it('none → base directory, no worktree param', () => {
    expect(resolveWorktreeSpawn({ mode: 'none', baseDirectory: '~/app' })).toEqual({
      directory: '~/app',
      worktree: undefined,
    });
  });

  it('new → base directory + worktree {new:true}', () => {
    expect(resolveWorktreeSpawn({ mode: 'new', baseDirectory: '~/app' })).toEqual({
      directory: '~/app',
      worktree: { new: true },
    });
  });

  it('new with a name → worktree {new:true, name} (trimmed)', () => {
    expect(
      resolveWorktreeSpawn({ mode: 'new', baseDirectory: '~/app', newWorktreeName: ' feat-login ' }),
    ).toEqual({
      directory: '~/app',
      worktree: { new: true, name: 'feat-login' },
    });
  });

  it('new with a blank name omits the key so the daemon picks a random slug', () => {
    expect(
      resolveWorktreeSpawn({ mode: 'new', baseDirectory: '~/app', newWorktreeName: '  ' }),
    ).toEqual({
      directory: '~/app',
      worktree: { new: true },
    });
  });

  it('a name is ignored outside `new` mode', () => {
    expect(
      resolveWorktreeSpawn({ mode: 'none', baseDirectory: '~/app', newWorktreeName: 'x' }),
    ).toEqual({ directory: '~/app', worktree: undefined });
  });

  it('existing → the selected worktree path, no worktree param', () => {
    expect(
      resolveWorktreeSpawn({
        mode: 'existing',
        baseDirectory: '~/app',
        selectedWorktreePath: '/u/vicoa/workspaces/app-1a2b/brave-river',
      }),
    ).toEqual({
      directory: '/u/vicoa/workspaces/app-1a2b/brave-river',
      worktree: undefined,
    });
  });

  it('existing carries the subfolder into the worktree', () => {
    // A monorepo session picked at `repo/apps/web` on a worktree starts at
    // `<worktree>/apps/web`, not at the worktree root.
    expect(
      resolveWorktreeSpawn({
        mode: 'existing',
        baseDirectory: '~/app/apps/web',
        subpath: 'apps/web',
        selectedWorktreePath: '/u/vicoa/workspaces/app-1a2b/brave-river',
      }),
    ).toEqual({
      directory: '/u/vicoa/workspaces/app-1a2b/brave-river/apps/web',
      worktree: undefined,
    });
  });

  it('new sends the subfolder itself — the daemon forks the whole repo', () => {
    expect(
      resolveWorktreeSpawn({ mode: 'new', baseDirectory: '~/app/apps/web', subpath: 'apps/web' }),
    ).toEqual({
      directory: '~/app/apps/web',
      worktree: { new: true },
    });
  });

  it('existing with no path falls back to the base directory', () => {
    expect(resolveWorktreeSpawn({ mode: 'existing', baseDirectory: '~/app' })).toEqual({
      directory: '~/app',
      worktree: undefined,
    });
  });
});

describe('isManagedWorktreePath', () => {
  it('is true under vicoa/workspaces', () => {
    expect(isManagedWorktreePath('/u/vicoa/workspaces/app/wt')).toBe(true);
  });
  it('is false for an ordinary directory', () => {
    expect(isManagedWorktreePath('/u/projects/app')).toBe(false);
  });
});
