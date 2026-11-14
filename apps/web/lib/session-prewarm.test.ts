import { describe, expect, test, vi } from 'vitest';

vi.mock('@/lib/ws-client', () => ({ getWsClient: () => ({ callRpc: vi.fn() }) }));

import {
  PREWARM_REPEAT_MS,
  createSessionPrewarmer,
  machineSupportsPrewarm,
  shouldPrewarm,
  type PrewarmConditions,
} from '@/lib/session-prewarm';

const ready: PrewarmConditions = {
  machineSupports: true,
  worktreeMode: 'none',
  directory: '/Users/me/project',
  hasDraft: true,
  busy: false,
};

describe('shouldPrewarm', () => {
  test('prewarms a session in a folder once the composer has input', () => {
    expect(shouldPrewarm(ready)).toBe(true);
  });

  test('an existing worktree is just a folder and prewarms', () => {
    expect(shouldPrewarm({ ...ready, worktreeMode: 'existing' })).toBe(true);
  });

  test.each<[string, Partial<PrewarmConditions>]>([
    ['the daemon cannot prewarm', { machineSupports: false }],
    ['a new worktree is named from the prompt first', { worktreeMode: 'new' }],
    ['no folder is chosen', { directory: '  ' }],
    ['the composer is empty', { hasDraft: false }],
    ['a send is in flight', { busy: true }],
  ])('does not prewarm when %s', (_why, change) => {
    expect(shouldPrewarm({ ...ready, ...change })).toBe(false);
  });
});

describe('machineSupportsPrewarm', () => {
  test('reads the daemon capability', () => {
    expect(machineSupportsPrewarm({ metadata: { capabilities: ['worktree', 'prewarm'] } })).toBe(true);
    expect(machineSupportsPrewarm({ metadata: { capabilities: ['worktree'] } })).toBe(false);
    expect(machineSupportsPrewarm({ metadata: {} })).toBe(false);
    expect(machineSupportsPrewarm(null)).toBe(false);
  });
});

describe('createSessionPrewarmer', () => {
  const params = { directory: '/p', agent: 'claude', metadata: { model: 'm' } };

  test('asks once per window for the same session while the user types', () => {
    let now = 1_000;
    const callRpc = vi.fn(() => Promise.resolve({ status: 'started' }));
    const prewarmer = createSessionPrewarmer(callRpc, () => now);

    expect(prewarmer.request('machine-1', params)).toBe(true);
    now += 1_000;
    expect(prewarmer.request('machine-1', params)).toBe(false);
    now += PREWARM_REPEAT_MS;
    expect(prewarmer.request('machine-1', params)).toBe(true);

    expect(callRpc).toHaveBeenCalledTimes(2);
    expect(callRpc).toHaveBeenCalledWith('machine-1', 'prewarm-session', params);
  });

  test('changed settings are another session and go out at once', () => {
    const callRpc = vi.fn(() => Promise.resolve({}));
    const prewarmer = createSessionPrewarmer(callRpc, () => 0);
    prewarmer.request('machine-1', params);
    expect(prewarmer.request('machine-1', { ...params, metadata: { model: 'other' } })).toBe(true);
    expect(prewarmer.request('machine-2', params)).toBe(true);
    expect(callRpc).toHaveBeenCalledTimes(3);
  });

  test('a failed prewarm is swallowed', async () => {
    const callRpc = vi.fn(() => Promise.reject(new Error('no_handler')));
    const prewarmer = createSessionPrewarmer(callRpc, () => 0);
    expect(prewarmer.request('machine-1', params)).toBe(true);
    await Promise.resolve();
  });
});
