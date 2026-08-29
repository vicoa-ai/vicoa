import { describe, expect, it } from 'vitest';
import {
  isManagedWorktreePath,
  machineSupportsWorktree,
  resolveWorktreeSpawn,
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
