/**
 * Naming and status labels for machine rows — the web mirror of the mobile
 * app's `machine_utils.dart`, shared by the Machines and Providers settings
 * tabs. Liveness thresholds live in lib/session-liveness.ts; this module only
 * formats.
 */

import type { MachineSummary } from '@/lib/backend-api';
import { isMachineOnline } from '@/lib/session-liveness';

/**
 * Display name with fallbacks: explicit name → hostname → short id. Same
 * chain the new-session machine picker uses.
 */
export function machineDisplayName(
  machine: Pick<MachineSummary, 'display_name' | 'hostname' | 'machine_id'>,
): string {
  return (
    machine.display_name?.trim() ||
    machine.hostname?.trim() ||
    `Machine ${machine.machine_id.slice(0, 6)}`
  );
}

/**
 * OS family from the daemon's `platform.platform()` string — the first token,
 * so "macOS-15.4-arm64-arm-64bit" → "macOS", "Windows-11-…" → "Windows".
 */
export function machinePlatformLabel(platform: string | null | undefined): string | null {
  const token = platform?.split('-')[0]?.trim();
  return token || null;
}

/** Compact duration: "45s", "5m", "3h", "2d". */
export function humanizeDuration(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

/**
 * Status line for a machine row: "Online" while the heartbeat is fresh, then
 * a relative "Last seen 5m ago", or "Never connected" when the machine has
 * yet to beat at all (registered but its daemon never reached the cloud).
 */
export function lastSeenLabel(
  machine: { last_heartbeat_at?: string | null },
  now: number = Date.now(),
): string {
  if (!machine.last_heartbeat_at) return 'Never connected';
  if (isMachineOnline(machine, now)) return 'Online';
  const beat = new Date(machine.last_heartbeat_at).getTime();
  if (Number.isNaN(beat)) return 'Never connected';
  return `Last seen ${humanizeDuration(now - beat)} ago`;
}

/** Vicoa CLI version the daemon reported, or null on older daemons. */
export function machineCliVersion(machine: Pick<MachineSummary, 'metadata'>): string | null {
  const version = machine.metadata?.cli_version;
  return typeof version === 'string' && version ? version : null;
}
