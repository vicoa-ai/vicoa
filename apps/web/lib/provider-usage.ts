import { getRpcClient, RpcError } from '@/lib/ws-client';
import type { MachineSummary, SessionUsageWindow } from '@/lib/backend-api';

/**
 * Providers the daemon can fetch account rate-limit windows for out-of-band
 * (`fetch-provider-usage` RPC → backend `vicoa/rpc/provider_usage.py`
 * registry). Claude reads the Claude Code OAuth credential, Codex the Codex
 * CLI's `auth.json`, Copilot the `gh` token. Anything else has no on-demand
 * source, so the usage indicator stays on whatever the wrapper stamped
 * in-band (or hidden). Keep in sync with the backend registry and mobile
 * `chat_usage_indicator.dart`.
 */
const PROVIDERS_WITH_USAGE_FETCHER: ReadonlySet<string> = new Set(['claude', 'codex', 'copilot']);

export function providerHasUsageFetcher(agent: string | null | undefined): boolean {
  return !!agent && PROVIDERS_WITH_USAGE_FETCHER.has(agent);
}

/** Daemon capability flag for the `fetch-provider-usage` RPC. */
export const PROVIDER_USAGE_CAPABILITY = 'provider-usage';

type MachineLike =
  | (Pick<MachineSummary, 'metadata'> & { machine_metadata?: Record<string, unknown> | null })
  | null
  | undefined;

/**
 * Whether the machine's daemon serves `fetch-provider-usage`. An old daemon
 * only knows the Claude-specific `fetch-claude-usage`; callers that have the
 * machine to hand use this to skip a doomed call for Codex/Copilot (the
 * server's RPC router sits out a 3s grace window before answering
 * `no_handler`) while still asking about Claude via the legacy name.
 */
export function machineSupportsProviderUsage(machine: MachineLike): boolean {
  if (!machine) return false;
  const metadata = machine.metadata ?? machine.machine_metadata;
  const caps = metadata && typeof metadata === 'object' ? (metadata as Record<string, unknown>).capabilities : null;
  return Array.isArray(caps) && caps.some((c) => String(c) === PROVIDER_USAGE_CAPABILITY);
}

function parseWindows(result: Record<string, unknown>): SessionUsageWindow[] | null {
  const limits = result.limits as { windows?: unknown } | undefined;
  if (!limits || !Array.isArray(limits.windows)) return null;
  const windows = limits.windows.filter(
    (w): w is SessionUsageWindow =>
      !!w &&
      typeof w === 'object' &&
      typeof (w as SessionUsageWindow).id === 'string' &&
      typeof (w as SessionUsageWindow).used_pct === 'number',
  );
  return windows.length > 0 ? windows : null;
}

/**
 * Fetch a provider account's live rate-limit windows from the machine's
 * daemon. Works with no session running and returns fresher data than the
 * last end-of-turn stamp on `instance_metadata.usage`.
 *
 * Best-effort by design: an old daemon (`no_handler`), an offline machine, a
 * CLI that isn't logged in, or a network failure all resolve to `null` so
 * callers silently keep whatever stale windows they already show.
 *
 * Claude falls back to the pre-registry `fetch-claude-usage` name when the
 * daemon doesn't route `fetch-provider-usage` yet, so a CLI update pending on
 * one machine never costs the Claude limits that already worked there.
 */
export async function fetchProviderUsageWindows(
  machineId: string,
  provider: string,
): Promise<SessionUsageWindow[] | null> {
  if (!providerHasUsageFetcher(provider)) return null;
  const client = getRpcClient(machineId);
  try {
    const result = await client.callRpc(machineId, 'fetch-provider-usage', { provider });
    const windows = parseWindows(result);
    if (!windows) {
      // A daemon that routed the call but had no usable data reports why
      // (`no_oauth_token`, `http_401`, ...) — keep that visible for debugging.
      console.debug(`fetch-provider-usage(${provider}): no windows`, result.error ?? result);
    }
    return windows;
  } catch (err) {
    if (provider === 'claude' && err instanceof RpcError && err.code === 'no_handler') {
      try {
        const legacy = await client.callRpc(machineId, 'fetch-claude-usage', {});
        return parseWindows(legacy);
      } catch (legacyErr) {
        console.debug('fetch-claude-usage failed', legacyErr);
        return null;
      }
    }
    // `no_handler` here means the machine's daemon predates the RPC (CLI
    // update pending); `target_disconnected`/`timeout` mean the machine is
    // unreachable. All fall back silently to stale in-band data.
    console.debug(`fetch-provider-usage(${provider}) failed`, err);
    return null;
  }
}
