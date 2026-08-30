import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getDefaultCommands,
  mergeCommands,
  type SlashCommand,
  type AgentType,
} from '@/lib/constants/slash-commands';
import {
  fetchCustomCommands,
  getCachedCustomCommands,
  type CustomCommand,
  type SlashCommandSource,
} from '@/lib/slash-commands-store';

interface MetadataShape {
  metadata?: Record<string, unknown> | null;
  machine_metadata?: Record<string, unknown> | null;
}

interface UseSlashCommandsOptions {
  agentType: AgentType;
  /** Machine the session runs on. Without it, custom commands read the DB copy. */
  machineId?: string | null;
  /** Session's project path — scopes project-local `.claude/commands`. */
  projectPath?: string | null;
  /** Machine object when the call site has one — skips a doomed RPC. */
  machine?: MetadataShape | null;
  enabled?: boolean; // Allow disabling the hook
}

interface UseSlashCommandsResult {
  commands: SlashCommand[];
  isLoading: boolean;
  error: Error | null;
  /** Which source produced the custom commands; null before the first load. */
  source: SlashCommandSource | null;
  refetch: () => Promise<void>;
}

function merge(agentType: AgentType, custom: CustomCommand[]): SlashCommand[] {
  return mergeCommands(getDefaultCommands(agentType), custom);
}

/**
 * Fetch and merge slash commands (and skills) from the built-in defaults and
 * the user's installed set.
 *
 * Reads custom commands through `lib/slash-commands-store`, which prefers the
 * live daemon index (`scan-commands`) so a skill installed mid-session shows up
 * without a restart, and falls back to the CLI-synced DB copy otherwise. The
 * defaults render on the first frame so the `/` menu is never empty while the
 * fetch is in flight.
 *
 * @example
 * ```tsx
 * const { commands } = useSlashCommands({ agentType, machineId, projectPath });
 * ```
 */
export function useSlashCommands({
  agentType,
  machineId,
  projectPath,
  machine,
  enabled = true,
}: UseSlashCommandsOptions): UseSlashCommandsResult {
  const [commands, setCommands] = useState<SlashCommand[]>(() =>
    merge(agentType, enabled ? getCachedCustomCommands(agentType, machineId, projectPath) ?? [] : []),
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [source, setSource] = useState<SlashCommandSource | null>(() =>
    enabled && getCachedCustomCommands(agentType, machineId, projectPath) ? 'cache' : null,
  );
  const mounted = useRef(true);
  const inFlight = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    if (!enabled) return;
    if (inFlight.current) return;
    inFlight.current = true;
    setIsLoading(true);
    setError(null);

    try {
      const result = await fetchCustomCommands({ agentType, machineId, projectPath, machine });
      if (!mounted.current) return;
      // The store keeps commands and skills apart (for a future Skills tab);
      // the `/` menu shows both — commands first, then skills.
      setCommands(merge(agentType, [...result.commands, ...result.skills]));
      setSource(result.source);
    } catch (err) {
      if (!mounted.current) return;
      const error = err instanceof Error ? err : new Error('Failed to load slash commands');
      setError(error);
      console.warn('Failed to fetch custom slash commands:', err);
      // Defaults are always usable even when the custom fetch fails.
      setCommands(merge(agentType, []));
    } finally {
      inFlight.current = false;
      if (mounted.current) setIsLoading(false);
    }
    // `machine` is a fresh object identity each parent render; the capability
    // it carries is stable per machine, so keying on the id is enough.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentType, machineId, projectPath, enabled]);

  const refetch = useCallback(() => load(), [load]);

  useEffect(() => {
    const cached = enabled ? getCachedCustomCommands(agentType, machineId, projectPath) : undefined;
    if (cached) {
      // Serve the cache on the first frame, then freshen behind it.
      setCommands(merge(agentType, cached));
      setSource('cache');
    }
    void load();
  }, [agentType, machineId, projectPath, enabled, load]);

  return {
    commands,
    isLoading,
    error,
    source,
    refetch,
  };
}
