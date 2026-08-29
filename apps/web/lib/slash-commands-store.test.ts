import { beforeEach, describe, expect, it, vi } from 'vitest';

// Both sources are mocked so these tests pin down the *selection* logic —
// which source is consulted, in what order, and what happens when one fails.
const rpcScanCommands = vi.fn();
const getSlashCommandsByAgentType = vi.fn();

vi.mock('@/components/files-git-panel/rpc', () => ({
  rpcScanCommands: (...args: unknown[]) => rpcScanCommands(...args),
}));
vi.mock('@/lib/backend-api', () => ({
  getBackendAPI: () => ({
    getSlashCommandsByAgentType: (a: string) => getSlashCommandsByAgentType(a),
  }),
}));

import { RpcError } from '@/lib/ws-client';
import {
  clearCustomCommandsCache,
  fetchCustomCommands,
  getCachedCustomCommands,
  getCachedCommandsOnly,
  getCachedSkills,
  machineSupportsCommandIndex,
} from './slash-commands-store';

const RPC_INDEX = {
  commands: [
    { name: 'review', description: 'Review', kind: 'skill', insert: '$review' },
    { name: 'gstack:ship', description: 'Ship', kind: 'command' },
  ],
  command_count: 2,
  hash: 'h1',
  scanned_at: 0,
};

beforeEach(() => {
  clearCustomCommandsCache();
  rpcScanCommands.mockReset();
  getSlashCommandsByAgentType.mockReset();
  getSlashCommandsByAgentType.mockResolvedValue({
    agent_type: 'claude',
    commands: [{ name: 'db-only', description: 'From DB', kind: 'command' }],
  });
});

describe('machineSupportsCommandIndex', () => {
  it('is true when metadata.capabilities lists command-index', () => {
    expect(
      machineSupportsCommandIndex({ metadata: { capabilities: ['file-index', 'command-index'] } }),
    ).toBe(true);
  });

  it('reads the WS machine_metadata shape too', () => {
    expect(machineSupportsCommandIndex({ machine_metadata: { capabilities: ['command-index'] } })).toBe(
      true,
    );
  });

  it('is false for an older daemon that omits it', () => {
    expect(machineSupportsCommandIndex({ metadata: { capabilities: ['file-index'] } })).toBe(false);
    expect(machineSupportsCommandIndex(null)).toBe(false);
  });
});

describe('source selection', () => {
  it('prefers the live daemon index and splits commands from skills', async () => {
    rpcScanCommands.mockResolvedValue(RPC_INDEX);

    const result = await fetchCustomCommands({
      agentType: 'claude',
      machineId: 'm1',
      projectPath: '/p',
    });

    expect(result.source).toBe('rpc');
    // Skills and commands are returned as separate lists.
    expect(result.commands.map((c) => c.command)).toEqual(['/gstack:ship']);
    expect(result.skills.map((c) => c.command)).toEqual(['/review']);
    // Skill carries its kind and Codex-style insert through unchanged.
    expect(result.skills[0]).toMatchObject({ kind: 'skill', insert: '$review' });
    expect(getSlashCommandsByAgentType).not.toHaveBeenCalled();
  });

  it('reads the DB copy when the session has no machine', async () => {
    const result = await fetchCustomCommands({ agentType: 'claude' });

    expect(result.source).toBe('rest');
    expect(result.commands.map((c) => c.command)).toEqual(['/db-only']);
    expect(result.skills).toEqual([]);
    expect(rpcScanCommands).not.toHaveBeenCalled();
  });

  it('skips the RPC when the machine advertises no command-index capability', async () => {
    const result = await fetchCustomCommands({
      agentType: 'claude',
      machineId: 'm1',
      projectPath: '/p',
      machine: { metadata: { capabilities: ['file-index'] } },
    });

    expect(rpcScanCommands).not.toHaveBeenCalled();
    expect(result.source).toBe('rest');
  });
});

describe('fallback + negative cache', () => {
  it('falls back to the DB copy on a transport error', async () => {
    rpcScanCommands.mockRejectedValue(new RpcError('timeout'));

    const result = await fetchCustomCommands({ agentType: 'claude', machineId: 'm1', projectPath: '/p' });

    expect(result.source).toBe('rest');
  });

  it('stops attempting the RPC after a no_handler for that machine', async () => {
    rpcScanCommands.mockRejectedValue(new RpcError('no_handler'));

    await fetchCustomCommands({ agentType: 'claude', machineId: 'old', projectPath: '/p' });
    await fetchCustomCommands({ agentType: 'claude', machineId: 'old', projectPath: '/p' });

    // Second call must not pay the grace window again.
    expect(rpcScanCommands).toHaveBeenCalledTimes(1);
  });

  it('serves the cached list when both sources fail', async () => {
    rpcScanCommands.mockResolvedValue(RPC_INDEX);
    await fetchCustomCommands({ agentType: 'claude', machineId: 'm1', projectPath: '/p' });

    rpcScanCommands.mockRejectedValue(new RpcError('timeout'));
    getSlashCommandsByAgentType.mockRejectedValue(new Error('backend down'));
    const result = await fetchCustomCommands({ agentType: 'claude', machineId: 'm1', projectPath: '/p' });

    expect(result.source).toBe('cache');
    expect([...result.commands, ...result.skills].map((c) => c.command).sort()).toEqual(
      ['/gstack:ship', '/review'],
    );
  });

  it('keeps the cached split on an {unchanged} reply', async () => {
    rpcScanCommands.mockResolvedValueOnce(RPC_INDEX);
    await fetchCustomCommands({ agentType: 'claude', machineId: 'm1', projectPath: '/p' });

    rpcScanCommands.mockResolvedValueOnce({ unchanged: true, hash: 'h1' });
    const result = await fetchCustomCommands({ agentType: 'claude', machineId: 'm1', projectPath: '/p' });

    expect(rpcScanCommands).toHaveBeenLastCalledWith('m1', 'claude', '/p', 'h1');
    expect(result.commands.map((c) => c.command)).toEqual(['/gstack:ship']);
    expect(result.skills.map((c) => c.command)).toEqual(['/review']);
  });
});

describe('cache keying', () => {
  it('keys by agent, machine and path so entries do not collide', async () => {
    rpcScanCommands.mockResolvedValue(RPC_INDEX);
    await fetchCustomCommands({ agentType: 'claude', machineId: 'm1', projectPath: '/p' });

    expect(getCachedCustomCommands('claude', 'm1', '/p')).toBeDefined();
    expect(getCachedCustomCommands('claude', 'm2', '/p')).toBeUndefined();
    expect(getCachedCustomCommands('codex', 'm1', '/p')).toBeUndefined();
  });
});

describe('separate command/skill accessors', () => {
  it('caches commands and skills apart, with a combined view for the menu', async () => {
    rpcScanCommands.mockResolvedValue(RPC_INDEX);
    await fetchCustomCommands({ agentType: 'claude', machineId: 'm1', projectPath: '/p' });

    expect(getCachedCommandsOnly('claude', 'm1', '/p')?.map((c) => c.command)).toEqual([
      '/gstack:ship',
    ]);
    expect(getCachedSkills('claude', 'm1', '/p')?.map((c) => c.command)).toEqual(['/review']);
    // The `/` menu still sees both.
    expect(getCachedCustomCommands('claude', 'm1', '/p')?.map((c) => c.command)).toEqual([
      '/gstack:ship',
      '/review',
    ]);
  });
});
