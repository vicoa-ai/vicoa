/**
 * "Who is this machine?" — the local daemon's cloud machine id.
 *
 * The Electron preload injects only `{mode, wsUrl, apiBase, token}` — never the
 * renderer's own `machine_id`. But the daemon's local server knows it and
 * reports it on `GET /healthz`. Two things need that id:
 *
 *  - onboarding, to find *this* machine in the user's cloud machine list
 *    (`agent-scan-step.tsx`); and
 *  - RPC/pty routing (`getRpcClient()` in ws-client.ts), to decide whether a
 *    machine-bound call rides the local daemon socket (this machine) or the
 *    cloud relay (any other machine).
 *
 * Routing is synchronous, so the id is cached here the moment any
 * `fetchLocalHealth()` succeeds, and `getLocalMachineId()` reads it without a
 * round trip. This module depends only on `runtime-config` (no ws-client), so
 * ws-client can import it without a cycle.
 */

import { getDesktopConfig } from '@/lib/runtime-config';

/** `GET /healthz` on the daemon's local server (`local_server/app.py`). */
export interface LocalHealth {
  status: string;
  mode: 'local-only' | 'cloud';
  machine_id: string | null;
  /** Cloud registration progress: 'connecting' | 'connected' | … | null. */
  cloud: string | null;
}

// This machine's cloud machine_id, cached across the session. Populated as a
// side effect of any successful fetchLocalHealth(); null until the daemon is up
// and has finished cloud registration.
let cachedLocalMachineId: string | null = null;
let inflight: Promise<string | null> | null = null;

/** This machine's id if already known, else null. Never triggers a fetch. */
export function getLocalMachineId(): string | null {
  return cachedLocalMachineId;
}

/**
 * Ask the local daemon who it is.
 *
 * Returns null off-desktop or when the daemon isn't up yet — both are ordinary
 * states during first launch, not errors. A successful response with a
 * machine_id also warms the synchronous cache read by `getLocalMachineId()`.
 */
export async function fetchLocalHealth(): Promise<LocalHealth | null> {
  const desktop = getDesktopConfig();
  if (!desktop) return null;
  try {
    const response = await fetch(`${desktop.apiBase}/healthz`, {
      headers: { Authorization: `Bearer ${desktop.token}` },
    });
    if (!response.ok) return null;
    const health = (await response.json()) as LocalHealth;
    if (health.machine_id) cachedLocalMachineId = health.machine_id;
    return health;
  } catch {
    // Daemon still booting, or restarting after a refresh.
    return null;
  }
}

/**
 * Resolve (and cache) this machine's id. Fire-and-forget safe: concurrent
 * callers share one in-flight request, and a failed attempt (daemon still
 * booting, cloud not yet registered) clears the latch so the next call retries.
 */
export function ensureLocalMachineId(): Promise<string | null> {
  if (cachedLocalMachineId) return Promise.resolve(cachedLocalMachineId);
  if (!inflight) {
    inflight = fetchLocalHealth()
      .then((health) => health?.machine_id ?? null)
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}
