/**
 * Executing plugin actions (sidebar items) and the trust round-trip.
 * Composer behaviors live in `composer.ts` (they need the live composer handle).
 */

import { openExternalUrl } from '@/lib/open-external';
import { getRpcClient } from '@/lib/ws-client';
import { pluginRegistry } from './registry';
import type { SidebarItemAction } from './types';

export interface SidebarActionEnv {
  machineId: string;
  /** Router push for in-app navigation (internal open-url / surface routes). */
  navigate: (href: string) => void;
}

/** Run a Tier 1 sidebar item's action. */
export async function runSidebarAction(
  action: SidebarItemAction,
  pluginId: string,
  env: SidebarActionEnv,
): Promise<void> {
  switch (action.type) {
    case 'open-url':
      if (action.external || /^https?:\/\//.test(action.url)) {
        openExternalUrl(action.url);
      } else {
        env.navigate(action.url);
      }
      return;
    case 'rpc':
      try {
        await getRpcClient(env.machineId).callRpc(env.machineId, action.method, action.params ?? {});
      } catch {
        // A failed plugin RPC must not surface as an app error; the plugin's own
        // UI (a surface/panel) is where richer feedback belongs.
      }
      return;
    case 'surface':
      // Tier 2 surfaces are wired in P2; route to the (future) surface page.
      env.navigate(`/dashboard/plugin/${env.machineId}/${pluginId}/${action.surfaceId}`);
      return;
  }
}

/** Grant trust for a plugin and reflect it locally so it starts contributing. */
export async function grantPluginTrust(machineId: string, pluginId: string): Promise<boolean> {
  try {
    const res = (await getRpcClient(machineId).callRpc(machineId, 'plugin-trust-grant', {
      plugin_id: pluginId,
    })) as { ok?: boolean; error?: string };
    if (res.ok) {
      pluginRegistry.setTrusted(machineId, pluginId, true);
      return true;
    }
  } catch {
    // fall through
  }
  return false;
}
