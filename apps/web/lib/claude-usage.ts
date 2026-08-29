import { getWsClient } from '@/lib/ws-client';
import type { SessionUsageWindow } from '@/lib/backend-api';

/**
 * Fetch the Claude account's live Session/Weekly rate-limit windows from the
 * machine's daemon (`fetch-claude-usage` RPC). The daemon reads the Claude
 * Code OAuth credential locally and calls Anthropic's usage endpoint, so this
 * works with no session running and returns fresher data than the last
 * end-of-turn stamp on `instance_metadata.usage`.
 *
 * Best-effort by design: an old daemon (`no_handler`), an offline machine, an
 * API-key-only Claude setup, or a network failure all resolve to `null` so
 * callers silently keep whatever stale windows they already show.
 */
export async function fetchClaudeUsageWindows(
  machineId: string,
): Promise<SessionUsageWindow[] | null> {
  try {
    const result = await getWsClient().callRpc(machineId, 'fetch-claude-usage', {});
    const limits = result.limits as { windows?: unknown } | undefined;
    if (!limits || !Array.isArray(limits.windows)) return null;
    const windows = limits.windows.filter(
      (w): w is SessionUsageWindow =>
        !!w &&
        typeof w === 'object' &&
        typeof (w as SessionUsageWindow).id === 'string' &&
        typeof (w as SessionUsageWindow).used_pct === 'number',
    );
    if (windows.length === 0) {
      // A daemon that routed the call but had no usable data reports why
      // (`no_oauth_token`, `http_401`, ...) — keep that visible for debugging.
      console.debug('fetch-claude-usage: no windows', result.error ?? result);
      return null;
    }
    return windows;
  } catch (err) {
    // `no_handler` here means the machine's daemon predates the RPC (CLI
    // update pending); `target_disconnected`/`timeout` mean the machine is
    // unreachable. All fall back silently to stale in-band data.
    console.debug('fetch-claude-usage failed', err);
    return null;
  }
}
