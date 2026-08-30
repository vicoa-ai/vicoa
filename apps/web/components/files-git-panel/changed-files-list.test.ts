import { describe, test, expect } from 'vitest';
import { changedFileEntries } from './changed-files-list';
import type { GitStatusResult, GitStatusEntry } from './rpc';

const entry = (path: string, status = 'M'): GitStatusEntry => ({
  path,
  status,
  additions: 1,
  deletions: 0,
  content_hash: null,
});

const status = (over: Partial<GitStatusResult>): GitStatusResult => ({
  branch: 'main',
  ahead: 0,
  behind: 0,
  staged: [],
  unstaged: [],
  untracked: [],
  ...over,
});

describe('changedFileEntries', () => {
  test('null status → empty list', () => {
    expect(changedFileEntries(null)).toEqual([]);
  });

  test('orders staged → unstaged → untracked and de-dupes by path', () => {
    const result = changedFileEntries(
      status({
        staged: [entry('a.ts', 'A')],
        unstaged: [entry('a.ts', 'M'), entry('b.ts', 'M')],
        untracked: [entry('c.ts', '??')],
      }),
    );
    // a.ts appears in both staged + unstaged → kept once, first (staged) wins.
    expect(result.map((e) => e.path)).toEqual(['a.ts', 'b.ts', 'c.ts']);
    expect(result[0].status).toBe('A');
  });

  test('skips trailing-slash directory rows (embedded repos)', () => {
    const result = changedFileEntries(status({ untracked: [entry('vendor/', '??'), entry('x.ts', '??')] }));
    expect(result.map((e) => e.path)).toEqual(['x.ts']);
  });
});
