/**
 * Pure logic behind the "Open in…" menu — the per-machine app cache, the menu
 * grouping, and the error copy. Split out of `open-in-menu.tsx` so it can be
 * unit-tested without a DOM (see `open-in-apps.test.ts`).
 */

import { rpcListOpenApps, type OpenApp, type OpenAppKind } from './rpc';

/** Menu order; also where the separators go. */
export const KIND_ORDER: OpenAppKind[] = ['file-manager', 'editor', 'terminal'];

export interface OpenAppGroup {
  kind: OpenAppKind;
  apps: OpenApp[];
}

/**
 * Bucket `apps` by kind in menu order, dropping empty buckets — separators are
 * rendered between groups, so a kind this machine has none of must not survive
 * as an empty one and leave a stray divider.
 */
export function groupOpenApps(apps: readonly OpenApp[]): OpenAppGroup[] {
  return KIND_ORDER.map((kind) => ({ kind, apps: apps.filter((app) => app.kind === kind) })).filter(
    (group) => group.apps.length > 0,
  );
}

const ERROR_MESSAGES: Record<string, string> = {
  path_not_found: 'That path no longer exists on the machine.',
  outside_project: 'That path is outside the project.',
  app_not_found: 'That app is no longer installed on the machine.',
  unknown_app: 'That app is not supported.',
  launch_failed: 'The machine could not launch that app.',
  target_disconnected: 'The machine is offline.',
  not_connected: 'Not connected — reconnecting…',
  timeout: 'The machine did not respond.',
  no_handler: 'This machine needs a newer Vicoa daemon.',
};

/** User-facing copy for a failed `open-path`, keyed off the `RpcError` code. */
export function openErrorMessage(error: unknown): string {
  const code = (error as { code?: string } | null)?.code;
  return (code && ERROR_MESSAGES[code]) || 'Could not open that path.';
}

/**
 * Per-machine app list, shared by every mounted menu — the session header and
 * the files panel would otherwise each pay the round trip.
 *
 * A failure caches too, but only briefly, so a machine that comes back online
 * (or a daemon that gets upgraded past the `open-in` capability) recovers
 * without a page reload. `null` means "nothing to offer here".
 */
export const FAILURE_TTL_MS = 2 * 60 * 1000;

interface CacheEntry {
  apps: OpenApp[] | null;
  at: number;
  inflight?: Promise<OpenApp[] | null>;
}

const appCache = new Map<string, CacheEntry>();

export function loadOpenApps(
  machineId: string,
  now: () => number = Date.now,
): Promise<OpenApp[] | null> {
  const cached = appCache.get(machineId);
  if (cached?.inflight) return cached.inflight;
  if (cached && (cached.apps !== null || now() - cached.at < FAILURE_TTL_MS)) {
    return Promise.resolve(cached.apps);
  }
  const inflight = rpcListOpenApps(machineId)
    .then((result) => result.apps)
    .catch(() => null)
    .then((apps) => {
      appCache.set(machineId, { apps, at: now() });
      return apps;
    });
  appCache.set(machineId, { apps: cached?.apps ?? null, at: cached?.at ?? 0, inflight });
  return inflight;
}

/** Test seam — the cache is module state that would leak between cases. */
export function resetOpenAppCache(): void {
  appCache.clear();
}
