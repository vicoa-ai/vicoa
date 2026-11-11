/**
 * Executing plugin actions (sidebar items) and the trust round-trip.
 * Composer behaviors live in `composer.ts` (they need the live composer handle).
 */

import { openExternalUrl } from '@/lib/open-external';
import { getRpcClient } from '@/lib/ws-client';
import { pluginRegistry } from './registry';
import { isSupportedSidebarAction, opensExternally, sidebarItemHref } from './sidebar';
import type { SidebarItemAction } from './types';

export interface SidebarActionEnv {
  machineId: string;
  /** Router push for in-app navigation (internal open-url / surface routes). */
  navigate: (href: string) => void;
}

/** Run a sidebar item's action. Unsupported actions do nothing. */
export function runSidebarAction(
  action: SidebarItemAction,
  pluginId: string,
  env: SidebarActionEnv,
): void {
  if (!isSupportedSidebarAction(action)) return;
  if (action.type === 'open-url' && opensExternally(action)) {
    openExternalUrl(action.url);
    return;
  }
  const href = sidebarItemHref(action, pluginId, env.machineId);
  if (href) env.navigate(href);
}

export type TrustResult = 'ok' | 'changed' | 'failed';

/**
 * Grant trust for a plugin and reflect it locally so it starts contributing.
 *
 * `manifestHash` is the hash of the manifest the user was shown; the daemon
 * refuses (`changed`) if plugin.json changed since, and the catalog is
 * fetched again so the prompt shows the new one.
 */
export async function grantPluginTrust(
  machineId: string,
  pluginId: string,
  manifestHash?: string | null,
): Promise<TrustResult> {
  try {
    const res = (await getRpcClient(machineId).callRpc(machineId, 'plugin-trust-grant', {
      plugin_id: pluginId,
      ...(manifestHash ? { manifest_sha256: manifestHash } : {}),
    })) as { ok?: boolean; error?: string };
    if (res.ok) {
      pluginRegistry.setTrusted(machineId, pluginId, true);
      return 'ok';
    }
    if (res.error === 'manifest_changed') {
      pluginRegistry.requestSync();
      return 'changed';
    }
  } catch {
    // fall through
  }
  return 'failed';
}
