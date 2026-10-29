import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

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

import {
  githubPrListRequestedAt,
  PR_CACHE_TTL_MS,
  rpcGithubPrList,
  rpcGithubPrListCached,
} from './rpc';

const PR = { number: 7, title: 'Fix', state: 'merged', url: 'https://x/7', checks: 'pass' };

// The cache is module state shared by every test: each test asks about its own
// repo so none sees another's entries.
let repoSeq = 0;
const nextRepo = () => `/repo-${(repoSeq += 1)}`;

beforeEach(() => {
  callRpc.mockReset();
  vi.useFakeTimers();
  vi.setSystemTime(1_000_000);
});
afterEach(() => vi.useRealTimers());

describe('rpcGithubPrList', () => {
  test('returns the map keyed by branch', async () => {
    callRpc.mockResolvedValue({ prs: { feat: PR } });
    await expect(rpcGithubPrList('m', '/r')).resolves.toEqual({ feat: PR });
  });

  test.each(['not_a_repo', 'gh_missing', 'gh_unauthenticated', 'no_remote'])(
    '%s means "no PRs to show": an empty map',
    async (code) => {
      callRpc.mockResolvedValue({ error: code });
      await expect(rpcGithubPrList('m', '/r')).resolves.toEqual({});
    },
  );

  test('a transient gh failure rejects instead of reading as "no PRs"', async () => {
    callRpc.mockResolvedValue({ error: 'gh_unavailable' });
    await expect(rpcGithubPrList('m', '/r')).rejects.toMatchObject({ code: 'gh_unavailable' });
  });
});

describe('rpcGithubPrListCached', () => {
  test('reuses a request within the TTL and stamps when it went out', async () => {
    const repo = nextRepo();
    callRpc.mockResolvedValue({ prs: { feat: PR } });
    const first = await rpcGithubPrListCached('m', repo);
    vi.setSystemTime(1_000_000 + PR_CACHE_TTL_MS - 1);
    const second = await rpcGithubPrListCached('m', repo);
    expect(callRpc).toHaveBeenCalledTimes(1);
    expect(second).toBe(first);
    expect(first).toEqual({ prs: { feat: PR }, fetchedAt: 1_000_000 });
    expect(githubPrListRequestedAt('m', repo)).toBe(1_000_000);
  });

  test('refetches once the request is older than maxAge', async () => {
    const repo = nextRepo();
    callRpc.mockResolvedValue({ prs: {} });
    await rpcGithubPrListCached('m', repo);
    vi.setSystemTime(1_005_000);
    callRpc.mockResolvedValue({ prs: { feat: PR } });
    const fresh = await rpcGithubPrListCached('m', repo, 5_000);
    expect(callRpc).toHaveBeenCalledTimes(2);
    expect(fresh).toEqual({ prs: { feat: PR }, fetchedAt: 1_005_000 });
    expect(githubPrListRequestedAt('m', repo)).toBe(1_005_000);
  });

  test('caches a settled "no PRs" answer like any other', async () => {
    const repo = nextRepo();
    callRpc.mockResolvedValue({ error: 'no_remote' });
    await expect(rpcGithubPrListCached('m', repo)).resolves.toMatchObject({ prs: {} });
    await rpcGithubPrListCached('m', repo);
    expect(callRpc).toHaveBeenCalledTimes(1);
  });

  test.each([
    ['a transient gh failure', () => callRpc.mockResolvedValueOnce({ error: 'gh_unavailable' })],
    ['a transport failure', () => callRpc.mockRejectedValueOnce(new Error('not_connected'))],
  ])('never caches %s', async (_label, fail) => {
    const repo = nextRepo();
    fail();
    await expect(rpcGithubPrListCached('m', repo)).rejects.toBeDefined();
    expect(githubPrListRequestedAt('m', repo)).toBeNull();
    callRpc.mockResolvedValueOnce({ prs: { feat: PR } });
    await expect(rpcGithubPrListCached('m', repo)).resolves.toMatchObject({ prs: { feat: PR } });
    expect(callRpc).toHaveBeenCalledTimes(2);
  });

  test('a stale request failing does not evict the newer one', async () => {
    const repo = nextRepo();
    let failOld: (reason: Error) => void = () => {};
    callRpc.mockImplementationOnce(
      () => new Promise((_resolve, reject) => (failOld = reject)),
    );
    const old = rpcGithubPrListCached('m', repo);
    vi.setSystemTime(1_001_000);
    callRpc.mockResolvedValueOnce({ prs: { feat: PR } });
    await rpcGithubPrListCached('m', repo, 0);
    failOld(new Error('timeout'));
    await expect(old).rejects.toBeDefined();
    expect(githubPrListRequestedAt('m', repo)).toBe(1_001_000);
  });
});
