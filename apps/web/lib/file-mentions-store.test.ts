import { beforeEach, describe, expect, it, vi } from 'vitest';

// Both sources are mocked so these tests pin down the *selection* logic —
// which source is consulted, in what order, and what happens when one fails.
const rpcScanFiles = vi.fn();
const getFileMentions = vi.fn();

vi.mock('@/components/files-git-panel/rpc', () => ({
  rpcScanFiles: (...args: unknown[]) => rpcScanFiles(...args),
}));
vi.mock('@/lib/backend-api', () => ({
  getBackendAPI: () => ({ getFileMentions: (p: string) => getFileMentions(p) }),
}));

import { RpcError } from '@/lib/ws-client';
import {
  clearFileMentionsCache,
  fetchFileMentions,
  getCachedFileMentions,
  machineSupportsFileIndex,
} from './file-mentions-store';

const INDEX = { files: ['src/', 'src/a.ts'], file_count: 2, hash: 'h1', truncated: false, scanned_at: 0 };

beforeEach(() => {
  clearFileMentionsCache();
  rpcScanFiles.mockReset();
  getFileMentions.mockReset();
  getFileMentions.mockResolvedValue({ files: ['db/old.ts'], file_count: 1, project_path: '/p' });
});

describe('machineSupportsFileIndex', () => {
  it('is true when metadata.capabilities lists file-index', () => {
    expect(machineSupportsFileIndex({ metadata: { capabilities: ['worktree', 'file-index'] } })).toBe(
      true,
    );
  });

  it('reads the WS machine_metadata shape too', () => {
    expect(machineSupportsFileIndex({ machine_metadata: { capabilities: ['file-index'] } })).toBe(true);
  });

  it('is false for an older daemon that omits it', () => {
    // Missing reads as unsupported: that daemon answers `no_handler`, so
    // trying costs a 3s grace window for nothing.
    expect(machineSupportsFileIndex({ metadata: { capabilities: ['worktree'] } })).toBe(false);
    expect(machineSupportsFileIndex({ metadata: null })).toBe(false);
    expect(machineSupportsFileIndex(null)).toBe(false);
  });
});

describe('source selection', () => {
  it('prefers the live daemon index when a machine is known', async () => {
    rpcScanFiles.mockResolvedValue(INDEX);

    const result = await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });

    expect(result.source).toBe('rpc');
    expect(result.files.map((f) => f.path)).toEqual(['src/', 'src/a.ts']);
    expect(getFileMentions).not.toHaveBeenCalled();
  });

  it('reads the DB copy when the session has no machine', async () => {
    // ~36% of recent sessions — the fallback is the common path, not an edge.
    const result = await fetchFileMentions({ projectPath: '/p' });

    expect(result.source).toBe('rest');
    expect(rpcScanFiles).not.toHaveBeenCalled();
  });

  it('skips the RPC when the machine advertises no file-index capability', async () => {
    const result = await fetchFileMentions({
      projectPath: '/p',
      machineId: 'm1',
      machine: { metadata: { capabilities: ['worktree'] } },
    });

    expect(rpcScanFiles).not.toHaveBeenCalled();
    expect(result.source).toBe('rest');
  });

  it.each(['no_handler', 'target_disconnected', 'timeout', 'not_connected'])(
    'falls back to the DB copy on %s',
    async (code) => {
      rpcScanFiles.mockRejectedValue(new RpcError(code));

      const result = await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });

      expect(result.source).toBe('rest');
      expect(result.files.map((f) => f.path)).toEqual(['db/old.ts']);
    },
  );

  it.each(['path_not_found', 'not_a_directory', 'permission_denied'])(
    'trusts the daemon on %s and does NOT fall back',
    async (code) => {
      // The daemon is authoritative about its own disk. Serving the DB copy
      // here would resurrect paths that no longer exist on that machine.
      rpcScanFiles.mockRejectedValue(new RpcError(code));

      const result = await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });

      expect(result.files).toEqual([]);
      expect(getFileMentions).not.toHaveBeenCalled();
    },
  );

  it('serves the stale cache when both sources are down', async () => {
    rpcScanFiles.mockResolvedValue(INDEX);
    await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });
    rpcScanFiles.mockRejectedValue(new RpcError('timeout'));
    getFileMentions.mockRejectedValue(new Error('offline'));

    const result = await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });

    expect(result.source).toBe('cache');
    expect(result.files.map((f) => f.path)).toEqual(['src/', 'src/a.ts']);
  });

  it('throws only when there is no cache and both sources fail', async () => {
    rpcScanFiles.mockRejectedValue(new RpcError('timeout'));
    getFileMentions.mockRejectedValue(new Error('offline'));

    await expect(fetchFileMentions({ projectPath: '/p', machineId: 'm1' })).rejects.toThrow('offline');
  });
});

describe('no_handler negative cache', () => {
  it('stops retrying a daemon that is too old to serve the index', async () => {
    rpcScanFiles.mockRejectedValue(new RpcError('no_handler'));

    await fetchFileMentions({ projectPath: '/p', machineId: 'old' });
    await fetchFileMentions({ projectPath: '/p', machineId: 'old' });
    await fetchFileMentions({ projectPath: '/other', machineId: 'old' });

    // One attempt total: every later mention skips straight to the DB rather
    // than burning the server's 3s no-handler grace window again.
    expect(rpcScanFiles).toHaveBeenCalledTimes(1);
  });

  it('does not blacklist a machine for a transient timeout', async () => {
    rpcScanFiles.mockRejectedValue(new RpcError('timeout'));

    await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });
    await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });

    expect(rpcScanFiles).toHaveBeenCalledTimes(2);
  });
});

describe('cache', () => {
  it('keys by machine as well as path', async () => {
    // `file_mentions` in Postgres is keyed only by (user_id, project_path), so
    // the same path on two machines collides there. The live index must not.
    rpcScanFiles.mockResolvedValueOnce(INDEX);
    await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });
    rpcScanFiles.mockResolvedValueOnce({ ...INDEX, files: ['other.ts'], hash: 'h2' });
    await fetchFileMentions({ projectPath: '/p', machineId: 'm2' });

    expect(getCachedFileMentions('/p', 'm1')?.map((f) => f.path)).toEqual(['src/', 'src/a.ts']);
    expect(getCachedFileMentions('/p', 'm2')?.map((f) => f.path)).toEqual(['other.ts']);
  });

  it('sends the cached hash back and keeps the list on `unchanged`', async () => {
    rpcScanFiles.mockResolvedValueOnce(INDEX);
    await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });

    rpcScanFiles.mockResolvedValueOnce({ unchanged: true, hash: 'h1' });
    const result = await fetchFileMentions({ projectPath: '/p', machineId: 'm1' });

    expect(rpcScanFiles).toHaveBeenLastCalledWith('m1', '/p', 'h1');
    expect(result.files.map((f) => f.path)).toEqual(['src/', 'src/a.ts']);
  });

  it('has nothing cached before the first fetch', () => {
    expect(getCachedFileMentions('/p', 'm1')).toBeUndefined();
    expect(getCachedFileMentions(undefined, 'm1')).toBeUndefined();
  });
});
