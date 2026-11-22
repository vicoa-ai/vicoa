import { describe, expect, it } from 'vitest';

import type { GitStatusEntry } from '@/components/files-git-panel/rpc';

import {
  SUMMARY_DOCK_RESERVE,
  SUMMARY_MIN_DOCKED_CHAT,
  canDockSummary,
  changeTotals,
  compactPath,
} from './session-summary';

describe('compactPath', () => {
  it('writes the home directory as ~', () => {
    expect(compactPath('/Users/nick/projects/app', '/Users/nick')).toBe('~/projects/app');
    expect(compactPath('/Users/nick', '/Users/nick/')).toBe('~');
  });

  it('does not treat a sibling with the same prefix as home', () => {
    expect(compactPath('/Users/nicky/app', '/Users/nick')).toBe('/Users/nicky/app');
  });

  it('keeps an already tilde path as it is', () => {
    expect(compactPath('~/projects/app', '/Users/nick')).toBe('~/projects/app');
  });

  it('cuts a long path in the middle, keeping both ends', () => {
    expect(
      compactPath('/Users/nick/vicoa/workspaces/vicoa-worktrees/task-x/vicoa', '/Users/nick'),
    ).toBe('~/vicoa/…/task-x/vicoa');
    expect(compactPath('/srv/a/b/c/d/e')).toBe('/srv/…/d/e');
  });

  it('shows a short path whole', () => {
    expect(compactPath('~/a/b/c/d')).toBe('~/a/b/c/d');
    expect(compactPath('/srv/app/')).toBe('/srv/app');
  });

  it('handles Windows paths', () => {
    expect(compactPath('C:\\Users\\nick\\src\\a\\b\\c\\d', 'C:\\Users\\nick')).toBe(
      '~\\src\\…\\c\\d',
    );
  });
});

describe('changeTotals', () => {
  const entry = (additions: number, deletions: number): GitStatusEntry => ({
    path: 'f',
    status: 'modified',
    additions,
    deletions,
    content_hash: null,
  });

  it('sums staged, unstaged and untracked changes', () => {
    expect(
      changeTotals({
        staged: [entry(3, 1)],
        unstaged: [entry(2, 2), entry(0, 5)],
        untracked: [entry(10, 0)],
      }),
    ).toEqual({ additions: 15, deletions: 8 });
  });

  it('is zero for a clean tree', () => {
    expect(changeTotals({ staged: [], unstaged: [], untracked: [] })).toEqual({
      additions: 0,
      deletions: 0,
    });
  });
});

describe('canDockSummary', () => {
  const threshold = SUMMARY_MIN_DOCKED_CHAT + SUMMARY_DOCK_RESERVE;

  it('docks on a 13-inch laptop with the sidebar open', () => {
    // 1470 window - 256 sidebar
    expect(canDockSummary(1214)).toBe(true);
  });

  it('floats once the chat would get narrower than the minimum', () => {
    expect(canDockSummary(threshold)).toBe(true);
    expect(canDockSummary(threshold - 1)).toBe(false);
  });
});
