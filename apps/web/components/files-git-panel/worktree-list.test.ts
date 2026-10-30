import { describe, test, expect, vi, beforeEach } from 'vitest';

const callRpc = vi.fn();
vi.mock('@/lib/ws-client', () => ({
  getRpcClient: () => ({ callRpc }),
  RpcError: class RpcError extends Error {
    code: string;
    constructor(code: string) {
      super(`rpc call failed: ${code}`);
      this.code = code;
    }
  },
}));

import { rpcGitWorktreeListWithMain } from './rpc';

const WT = { path: '/wt/a', branch: 'a', upstream: 'a-remote', head: 'abc', managed: true };

beforeEach(() => callRpc.mockReset());

describe('rpcGitWorktreeListWithMain', () => {
  test("carries the main checkout's branch and each worktree's upstream", async () => {
    callRpc.mockResolvedValue({
      main_path: '/repo',
      main_display_path: '~/repo',
      main_branch: 'main',
      worktrees: [WT],
    });
    await expect(rpcGitWorktreeListWithMain('m', '/repo')).resolves.toEqual({
      mainPath: '/repo',
      mainDisplayPath: '~/repo',
      mainBranch: 'main',
      worktrees: [WT],
    });
  });

  test('a detached main checkout is an empty branch, not a missing one', async () => {
    callRpc.mockResolvedValue({ main_path: '/repo', main_branch: '', worktrees: [] });
    expect((await rpcGitWorktreeListWithMain('m', '/repo')).mainBranch).toBe('');
  });

  test('a daemon that predates the field reports null', async () => {
    callRpc.mockResolvedValue({ worktrees: [] });
    const listing = await rpcGitWorktreeListWithMain('m', '/repo');
    expect(listing.mainBranch).toBeNull();
    expect(listing.mainPath).toBeNull();
  });

  test('an error rejects', async () => {
    callRpc.mockResolvedValue({ error: 'not_a_repo' });
    await expect(rpcGitWorktreeListWithMain('m', '/x')).rejects.toMatchObject({ code: 'not_a_repo' });
  });
});
