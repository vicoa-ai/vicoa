/**
 * Client-side store for the custom slash command / skill index.
 *
 * The sibling of `lib/file-mentions-store.ts` for the composer's `/` menu.
 * Two jobs:
 *
 * 1. **Source selection.** Prefer the live daemon index (`scan-commands` RPC)
 *    so a skill installed mid-session (e.g. `npx skills add`) is invocable
 *    without restarting; fall back to the CLI-synced copy in Postgres when the
 *    machine is unknown, offline, or too old to serve it. The DB copy is only
 *    written for Claude sessions today and only at session start, so the
 *    fallback is load-bearing rather than a safety net.
 *
 * 2. **Cache.** Memoized for the life of the page so route changes are free and
 *    the `/` panel opens against a warm list. In-memory only, like the file
 *    index: the payload is small and a live scan is ~0.1s.
 *
 * Unlike files, an empty result is a valid answer (an agent may have no custom
 * commands), so there are no authoritative path error codes — every RPC
 * failure falls through to REST.
 */

import { getBackendAPI } from '@/lib/backend-api';
import type { SlashCommandItem } from '@/lib/backend-api';
import { RpcError } from '@/lib/ws-client';
import { rpcScanCommands } from '@/components/files-git-panel/rpc';

/** Capability advertised by daemons that serve `scan-commands`. */
export const COMMAND_INDEX_CAPABILITY = 'command-index';

type MetadataShape = {
  metadata?: Record<string, unknown> | null;
  machine_metadata?: Record<string, unknown> | null;
};

/**
 * Whether this machine's daemon advertises the live command index. A MISSING
 * capability reads as unsupported, same as `machineSupportsFileIndex`.
 */
export function machineSupportsCommandIndex(
  machine: MetadataShape | null | undefined,
): boolean {
  if (!machine) return false;
  const meta = machine.metadata ?? machine.machine_metadata;
  if (!meta || typeof meta !== 'object') return false;
  const caps = (meta as Record<string, unknown>).capabilities;
  return Array.isArray(caps) && caps.some((c) => String(c) === COMMAND_INDEX_CAPABILITY);
}

export type CommandKind = 'command' | 'skill';
export type SlashCommandSource = 'rpc' | 'rest' | 'cache';

/** A user-installed command or skill, normalized for the composer. */
export interface CustomCommand {
  /** Always leads with `/` — this is what the `/` menu shows and filters on. */
  command: string;
  description: string;
  kind: CommandKind;
  /** Text to insert on selection when it differs from `command` (Codex `$name`). */
  insert?: string;
  source: 'custom';
}

interface CacheEntry {
  /** Plain slash commands (kind === 'command'). */
  commands: CustomCommand[];
  /** Installed skills (kind === 'skill'), stored apart so a future Skills tab
   *  can read them without the command list. */
  skills: CustomCommand[];
  /** Daemon index hash, for the `known_hash` no-op round-trip. Unset for REST. */
  hash?: string;
  source: SlashCommandSource;
}

/** Partition a mixed list into commands and skills by `kind`. */
function splitByKind(list: CustomCommand[]): {
  commands: CustomCommand[];
  skills: CustomCommand[];
} {
  const commands: CustomCommand[] = [];
  const skills: CustomCommand[] = [];
  for (const entry of list) {
    (entry.kind === 'skill' ? skills : commands).push(entry);
  }
  return { commands, skills };
}

/** Keyed by agent, machine AND path — project-local commands differ per repo. */
function cacheKey(
  agentType: string,
  machineId: string | null | undefined,
  projectPath: string | null | undefined,
): string {
  return `${agentType} ${machineId ?? '-'} ${projectPath ?? '-'}`;
}

const cache = new Map<string, CacheEntry>();

/**
 * Machines that answered `no_handler` — daemons predating `scan-commands`.
 * Skips the RPC (and its 3s server-side grace window) on every subsequent
 * open for that machine. Not persisted: a daemon upgrade takes effect next
 * page load.
 */
const withoutCommandIndex = new Set<string>();

/** Transport failures that mean "this daemon can't answer right now". */
const FALLBACK_CODES = new Set([
  'no_handler',
  'target_disconnected',
  'timeout',
  'not_connected',
  'rpc_failed',
]);

function toCommand(item: SlashCommandItem | ScanCommandLike): CustomCommand {
  const name = item.name.startsWith('/') ? item.name : `/${item.name}`;
  const insert = item.insert ? String(item.insert) : undefined;
  return {
    command: name,
    description: item.description ?? '',
    kind: item.kind === 'skill' ? 'skill' : 'command',
    insert,
    source: 'custom',
  };
}

interface ScanCommandLike {
  name: string;
  description?: string;
  kind?: string;
  insert?: string | null;
}

/** Cached commands + skills combined — what the `/` menu shows. */
export function getCachedCustomCommands(
  agentType: string,
  machineId?: string | null,
  projectPath?: string | null,
): CustomCommand[] | undefined {
  const entry = cache.get(cacheKey(agentType, machineId, projectPath));
  return entry ? [...entry.commands, ...entry.skills] : undefined;
}

/** Cached skills only — for a future Skills tab. */
export function getCachedSkills(
  agentType: string,
  machineId?: string | null,
  projectPath?: string | null,
): CustomCommand[] | undefined {
  return cache.get(cacheKey(agentType, machineId, projectPath))?.skills;
}

/** Cached plain commands only (no skills). */
export function getCachedCommandsOnly(
  agentType: string,
  machineId?: string | null,
  projectPath?: string | null,
): CustomCommand[] | undefined {
  return cache.get(cacheKey(agentType, machineId, projectPath))?.commands;
}

async function fetchFromRest(agentType: string): Promise<CustomCommand[]> {
  const response = await getBackendAPI().getSlashCommandsByAgentType(agentType);
  return response.commands.map(toCommand);
}

export interface FetchOptions {
  agentType: string;
  machineId?: string | null;
  projectPath?: string | null;
  /** Machine object, when the call site has one — enables the capability gate. */
  machine?: MetadataShape | null;
}

export interface FetchResult {
  /** Plain slash commands. */
  commands: CustomCommand[];
  /** Installed skills, stored/returned apart from commands. */
  skills: CustomCommand[];
  source: SlashCommandSource;
}

/**
 * Resolve the custom command index for an agent, preferring the live daemon.
 * Commands and skills come back as two separate lists (split by `kind`).
 *
 * Always resolves to a usable result: on any transport failure it serves the
 * DB copy, then the cached copy. Only a total failure of both paths throws.
 */
export async function fetchCustomCommands({
  agentType,
  machineId,
  projectPath,
  machine,
}: FetchOptions): Promise<FetchResult> {
  const key = cacheKey(agentType, machineId, projectPath);
  const cached = cache.get(key);

  const rpcUsable =
    !!machineId &&
    !withoutCommandIndex.has(machineId) &&
    (machine === undefined || machine === null || machineSupportsCommandIndex(machine));

  if (rpcUsable && machineId) {
    try {
      const result = await rpcScanCommands(machineId, agentType, projectPath, cached?.hash);
      if ('unchanged' in result) {
        // Nothing changed on disk — keep the split lists, refresh the hash.
        const entry: CacheEntry = {
          commands: cached?.commands ?? [],
          skills: cached?.skills ?? [],
          hash: result.hash,
          source: 'rpc',
        };
        cache.set(key, entry);
        return { commands: entry.commands, skills: entry.skills, source: 'rpc' };
      }
      const { commands, skills } = splitByKind(result.commands.map(toCommand));
      cache.set(key, { commands, skills, hash: result.hash, source: 'rpc' });
      return { commands, skills, source: 'rpc' };
    } catch (err) {
      const code = err instanceof RpcError ? err.code : 'rpc_failed';
      if (code === 'no_handler') {
        withoutCommandIndex.add(machineId);
      } else if (!FALLBACK_CODES.has(code)) {
        console.warn(`command index RPC failed (${code}); falling back to the DB copy`);
      }
      // Every remaining code means "ask the DB instead".
    }
  }

  try {
    const { commands, skills } = splitByKind(await fetchFromRest(agentType));
    cache.set(key, { commands, skills, hash: cached?.hash, source: 'rest' });
    return { commands, skills, source: 'rest' };
  } catch (err) {
    // Both sources are down. A stale list beats an empty menu.
    if (cached) return { commands: cached.commands, skills: cached.skills, source: 'cache' };
    throw err;
  }
}

/** Drop every cached index. Exported for tests and debug resets. */
export function clearCustomCommandsCache(): void {
  cache.clear();
  withoutCommandIndex.clear();
}
