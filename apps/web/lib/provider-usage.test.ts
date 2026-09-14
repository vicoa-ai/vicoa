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

import { RpcError } from '@/lib/ws-client';
import {
  fetchProviderUsageWindows,
  machineSupportsProviderUsage,
  providerHasUsageFetcher,
} from './provider-usage';

const WINDOWS = { limits: { windows: [{ id: 'session', label: 'Session', used_pct: 12.5, resets_at: null }] } };

beforeEach(() => callRpc.mockReset());

describe('providerHasUsageFetcher', () => {
  test('matches the daemon registry exactly', () => {
    expect(['claude', 'codex', 'copilot'].map(providerHasUsageFetcher)).toEqual([true, true, true]);
    expect(['gemini', 'cursor', 'opencode', 'qwen', '', null, undefined].map(providerHasUsageFetcher)).toEqual(
      [false, false, false, false, false, false, false],
    );
  });
});

describe('machineSupportsProviderUsage', () => {
  test('reads the capability off either metadata key, missing = unsupported', () => {
    expect(machineSupportsProviderUsage({ metadata: { capabilities: ['worktree', 'provider-usage'] } })).toBe(true);
    expect(machineSupportsProviderUsage({ metadata: null, machine_metadata: { capabilities: ['provider-usage'] } })).toBe(true);
    expect(machineSupportsProviderUsage({ metadata: { capabilities: ['provider-config'] } })).toBe(false);
    expect(machineSupportsProviderUsage({ metadata: {} })).toBe(false);
    expect(machineSupportsProviderUsage(null)).toBe(false);
  });
});

describe('fetchProviderUsageWindows', () => {
  test('calls fetch-provider-usage with the provider and returns the windows', async () => {
    callRpc.mockResolvedValueOnce(WINDOWS);
    await expect(fetchProviderUsageWindows('m1', 'codex')).resolves.toEqual(WINDOWS.limits.windows);
    expect(callRpc).toHaveBeenCalledWith('m1', 'fetch-provider-usage', { provider: 'codex' });
  });

  test('never calls the daemon for a provider without a fetcher', async () => {
    await expect(fetchProviderUsageWindows('m1', 'gemini')).resolves.toBeNull();
    expect(callRpc).not.toHaveBeenCalled();
  });

  test('a daemon error payload or malformed windows resolve to null', async () => {
    callRpc.mockResolvedValueOnce({ error: 'no_oauth_token' });
    await expect(fetchProviderUsageWindows('m1', 'copilot')).resolves.toBeNull();
    callRpc.mockResolvedValueOnce({ limits: { windows: [{ id: 'x' }, 'junk', null] } });
    await expect(fetchProviderUsageWindows('m1', 'copilot')).resolves.toBeNull();
  });

  test('claude falls back to the legacy fetch-claude-usage on an old daemon', async () => {
    callRpc.mockRejectedValueOnce(new RpcError('no_handler')).mockResolvedValueOnce(WINDOWS);
    await expect(fetchProviderUsageWindows('m1', 'claude')).resolves.toEqual(WINDOWS.limits.windows);
    expect(callRpc.mock.calls).toEqual([
      ['m1', 'fetch-provider-usage', { provider: 'claude' }],
      ['m1', 'fetch-claude-usage', {}],
    ]);
  });

  test('other providers on an old daemon hide silently; transport errors too', async () => {
    callRpc.mockRejectedValueOnce(new RpcError('no_handler'));
    await expect(fetchProviderUsageWindows('m1', 'codex')).resolves.toBeNull();
    expect(callRpc).toHaveBeenCalledTimes(1);
    callRpc.mockRejectedValueOnce(new RpcError('target_disconnected'));
    await expect(fetchProviderUsageWindows('m1', 'claude')).resolves.toBeNull();
    expect(callRpc).toHaveBeenCalledTimes(2);
  });
});
