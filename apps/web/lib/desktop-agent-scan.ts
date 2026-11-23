/**
 * Reading which coding agents are installed on this machine.
 *
 * The daemon probes for agents ONCE, at registration, and posts the result to
 * `machines.machine_metadata.available_agents` (`machine_daemon.py`
 * `_detect_available_agents`). It is a flat `{id: boolean}` — presence only,
 * no versions, deliberately (probing versions would put `--version`
 * subprocesses on the heartbeat loop).
 *
 * So there are two paths, with very different costs:
 *
 *  - **Initial scan** reads the value the daemon already computed. Free.
 *  - **Refresh** calls the `scan-agents` RPC, which re-probes. Not free —
 *    `find_npm_cli` falls back to an `npm config get prefix` subprocess with a
 *    5s timeout per miss — so it only ever runs on an explicit user action.
 *
 * Detection is PATH-correct under Electron: `DaemonManager` resolves the login
 * shell's PATH and passes it to the daemon it spawns (`resolve-path.ts`,
 * `daemon-manager.ts`), so the W11 class of false negative (a GUI-launched app
 * inheriting a minimal PATH and never finding `claude`) does not apply here.
 */

import { getRpcClient, RpcError } from '@/lib/ws-client';
import type { MachineSummary } from '@/lib/backend-api';
import type { LocalHealth } from '@/lib/local-machine';

// `fetchLocalHealth` / `LocalHealth` moved to `lib/local-machine.ts` (the
// machine-identity seam RPC routing also needs). Re-exported here so existing
// importers (agent-scan-step.tsx) keep working.
export { fetchLocalHealth } from '@/lib/local-machine';
export type { LocalHealth } from '@/lib/local-machine';

/**
 * Why this machine hasn't turned up yet.
 *
 * - `not_started`: the daemon's local server doesn't answer.
 * - `not_connected`: it answers, but hasn't registered with the cloud (or the
 *   cloud's machine list doesn't have it yet).
 * - `machine_limit` / `auth_failed`: the daemon gave up on the cloud link, so
 *   waiting longer will not help.
 * - `not_desktop`: a browser, where there is no local daemon to ask.
 */
export type ScanStuckReason =
  | 'not_started'
  | 'not_connected'
  | 'machine_limit'
  | 'auth_failed'
  | 'not_desktop';

/** Reasons that won't clear by waiting, so the step says so straight away. */
export function isFinalStuckReason(reason: ScanStuckReason): boolean {
  return reason === 'machine_limit' || reason === 'auth_failed' || reason === 'not_desktop';
}

export type MachineProbe =
  | { kind: 'found'; machine: MachineSummary }
  | { kind: 'waiting'; reason: ScanStuckReason; detail: string };

/**
 * One look for this machine.
 *
 * On desktop, ask the local daemon who it is and find that id in the account's
 * machine list. In a browser there is no local daemon: the only honest match
 * is an account with exactly one machine, which is what a preview of this
 * page has. With two or more, "this computer" can't be told apart.
 */
export async function probeThisMachine(deps: {
  onDesktop: boolean;
  fetchHealth: () => Promise<LocalHealth | null>;
  listMachines: () => Promise<MachineSummary[]>;
}): Promise<MachineProbe> {
  if (!deps.onDesktop) {
    try {
      const machines = await deps.listMachines();
      if (machines.length === 1) return { kind: 'found', machine: machines[0] };
    } catch {
      // Same answer as two machines: nothing to show as "this computer".
    }
    return { kind: 'waiting', reason: 'not_desktop', detail: '' };
  }

  const health = await deps.fetchHealth();
  if (!health) return { kind: 'waiting', reason: 'not_started', detail: '' };
  if (health.cloud === 'machine_limit') {
    return { kind: 'waiting', reason: 'machine_limit', detail: health.cloud_detail ?? '' };
  }
  if (health.cloud === 'auth_failed') {
    return { kind: 'waiting', reason: 'auth_failed', detail: '' };
  }
  if (!health.machine_id) return { kind: 'waiting', reason: 'not_connected', detail: '' };
  try {
    const machines = await deps.listMachines();
    const machine = machines.find((m) => m.machine_id === health.machine_id);
    if (machine) return { kind: 'found', machine };
  } catch {
    // The backend is unreachable or slow; same as not registered yet.
  }
  return { kind: 'waiting', reason: 'not_connected', detail: '' };
}

/** One row in the scan UI. */
export interface ScannedAgent {
  id: string;
  label: string;
  installed: boolean;
}

/**
 * Pull `available_agents` off a machine record.
 *
 * Spans both wire shapes: REST `MachineSummary` uses `metadata`, the WS
 * `machine-update` frame uses `machine_metadata`. Same fallback the
 * `machineSupportsWorktree` helper uses (`lib/worktree-selection.ts`).
 *
 * Returns `null` for "we don't know" — distinct from `{}` ("we asked and the
 * answer is none"). The scan must not render 8 red rows just because a machine
 * registered with an older daemon that never sent the key.
 */
export function readAvailableAgents(
  machine: Pick<MachineSummary, 'metadata'> & { machine_metadata?: Record<string, unknown> | null },
): Record<string, boolean> | null {
  const metadata = machine.metadata ?? machine.machine_metadata;
  if (!metadata || typeof metadata !== 'object') return null;
  const raw = (metadata as Record<string, unknown>).available_agents;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;

  const out: Record<string, boolean> = {};
  for (const [id, value] of Object.entries(raw as Record<string, unknown>)) {
    // The daemon sends booleans; be defensive about anything else rather than
    // coercing a stray string into a truthy "installed".
    if (typeof value === 'boolean') out[id] = value;
  }
  return out;
}

/**
 * Join detection results onto the agent catalog.
 *
 * The catalog is the display registry — its ids and `label`s are the wire
 * contract, so agents Vicoa gains later show up here without a web change.
 * Installed agents sort first; catalog order is preserved within each group so
 * the list doesn't reshuffle between scans.
 */
export function buildScannedAgents(
  catalogAgents: { id: string; label: string }[],
  available: Record<string, boolean> | null,
): ScannedAgent[] {
  const rows = catalogAgents.map((agent) => ({
    id: agent.id,
    label: agent.label,
    installed: available?.[agent.id] === true,
  }));
  return [
    ...rows.filter((row) => row.installed),
    ...rows.filter((row) => !row.installed),
  ];
}

export interface ScanAgentsResult {
  available_agents: Record<string, boolean>;
}

/**
 * Force the daemon to re-probe and return the fresh result.
 *
 * Requires a daemon carrying the `scan-agents` RPC; check
 * `machineSupportsAgentScan` before offering the button, because an older daemon
 * fails with `no_handler`.
 */
export async function rpcScanAgents(machineId: string): Promise<Record<string, boolean>> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'scan-agents', {});
  // Daemon handlers report failure as a successful rpc-result carrying
  // `error`; convert to the same RpcError the transport throws.
  if (typeof result.error === 'string') throw new RpcError(result.error);
  const parsed = (result as unknown as ScanAgentsResult).available_agents;
  return parsed && typeof parsed === 'object' ? parsed : {};
}

/**
 * Whether this machine's daemon advertises the `scan-agents` RPC.
 *
 * `metadata.capabilities` is a flat string list (`["worktree", ...]`), same
 * shape `machineSupportsWorktree` reads. A MISSING capability reads as
 * unsupported: an older daemon answers `no_handler`, so the Refresh button must
 * stay hidden rather than throw.
 */
export const AGENT_SCAN_CAPABILITY = 'agent-scan';

export function machineSupportsAgentScan(
  machine:
    | (Pick<MachineSummary, 'metadata'> & { machine_metadata?: Record<string, unknown> | null })
    | null
    | undefined,
): boolean {
  if (!machine) return false;
  const metadata = machine.metadata ?? machine.machine_metadata;
  if (!metadata || typeof metadata !== 'object') return false;
  const caps = (metadata as Record<string, unknown>).capabilities;
  return Array.isArray(caps) && caps.some((c) => String(c) === AGENT_SCAN_CAPABILITY);
}
