/**
 * Wire shape of the daemon's `plugin-catalog` RPC and the mapper into the
 * renderer's `RegisteredPlugin`. Mirrors `plugin_ops.plugin_catalog` in the
 * backend.
 */

import type { PluginManifest } from './types';
import type { RegisteredPlugin } from './registry';

export interface CatalogPluginWire {
  id: string;
  /** On-disk directory name; the authoritative key for enable/trust/remove. */
  dir: string;
  manifest: PluginManifest;
  enabled: boolean;
  trusted: boolean;
  server_available: boolean;
  source?: string | null;
  api_compatible: boolean;
}

export interface CatalogWire {
  etag?: string;
  plugins_enabled?: boolean;
  plugins?: CatalogPluginWire[];
  not_modified?: boolean;
}

/**
 * Turn a catalog payload into registry entries. The global `plugins_enabled`
 * master switch is folded into each plugin's effective `enabled` so a disabled
 * master switch contributes nothing, while per-plugin state stays visible to the
 * settings surface (which queries `plugin-list` directly).
 */
export function mapCatalog(machineId: string, res: CatalogWire): RegisteredPlugin[] {
  const enabledGlobally = res.plugins_enabled !== false;
  return (res.plugins ?? [])
    .filter((p) => p.manifest && p.api_compatible)
    .map((p) => ({
      machineId,
      pluginId: p.dir,
      manifest: p.manifest,
      enabled: enabledGlobally && p.enabled,
      trusted: p.trusted,
      serverAvailable: p.server_available,
      builtin: false,
    }));
}
