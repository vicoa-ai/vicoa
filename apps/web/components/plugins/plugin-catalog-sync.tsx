'use client';

/**
 * Populates the plugin registry from every online machine's daemon.
 *
 * Mounted once inside the dashboard. On a 60s cadence (and on the machine list
 * changing) it calls each online machine's `plugin-catalog` RPC with the last
 * ETag; unchanged catalogs return `not_modified` and cost nothing. The RPC
 * routes through the same channel as every other daemon call — the local socket
 * on desktop, the cloud relay for a remote machine — so Tier 1 plugins light up
 * on plain web too, for any machine whose daemon is connected.
 *
 * Renders nothing.
 */

import { useEffect, useRef } from 'react';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { getRpcClient } from '@/lib/ws-client';
import { isMachineOnline } from '@/lib/session-liveness';
import { getDesktopConfig } from '@/lib/runtime-config';
import { ensureLocalMachineId } from '@/lib/local-machine';
import { pluginRegistry } from '@/lib/plugins/registry';
import { mapCatalog, type CatalogWire } from '@/lib/plugins/catalog';

const POLL_MS = 60_000;

export function PluginCatalogSync() {
  const { api } = useAgentDashboard();
  const etags = useRef<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      // Target set = online cloud machines + this desktop's local machine. The
      // local daemon is always reachable on desktop even in logged-out local
      // mode (where `listMachines` may be unavailable), so include it directly
      // — that's the primary desktop-first path.
      const targets = new Set<string>();
      if (api) {
        try {
          const now = Date.now();
          for (const m of await api.listMachines()) {
            if (isMachineOnline(m, now)) targets.add(m.machine_id);
          }
        } catch {
          // fall through — the local machine below may still be reachable
        }
      }
      if (getDesktopConfig()) {
        const localId = await ensureLocalMachineId();
        if (localId) targets.add(localId);
      }
      if (cancelled) return;

      // Forget catalogs from machines no longer in the target set.
      for (const id of Object.keys(etags.current)) {
        if (!targets.has(id)) {
          delete etags.current[id];
          pluginRegistry.clearMachine(id);
        }
      }

      await Promise.all(
        [...targets].map(async (machineId) => {
          try {
            const res = (await getRpcClient(machineId).callRpc(machineId, 'plugin-catalog', {
              etag: etags.current[machineId],
            })) as CatalogWire;
            if (cancelled) return;
            if (res.not_modified) return;
            if (res.etag) etags.current[machineId] = res.etag;
            pluginRegistry.setMachinePlugins(machineId, mapCatalog(machineId, res));
          } catch {
            // Machine unreachable or daemon too old to know the RPC; keep prior
            // state rather than dropping the plugins mid-session.
          }
        }),
      );
    };

    void tick();
    const id = window.setInterval(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [api]);

  return null;
}
