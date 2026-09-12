/**
 * Settings → Providers' Add / Remove / Check: the `provider-*` daemon RPCs.
 *
 * A provider is machine-local — an entry in that machine's
 * `~/.vicoa/config.json` — so every call is routed to one machine, the way
 * `scan-agents` is. The daemon advertises `provider-config` in its
 * capabilities when these RPCs are routable (old daemons don't, and the page
 * then falls back to copy-the-install-command text). Mirrors
 * lib/desktop-agent-scan.ts; see backend `vicoa/rpc/provider_ops.py` for the
 * shapes.
 */

import { getRpcClient, RpcError } from '@/lib/ws-client';
import type { MachineSummary } from '@/lib/backend-api';
import type { AcpCatalogEntry } from '@/lib/agent-catalog';

export type { AcpCatalogEntry };

export const PROVIDER_CONFIG_CAPABILITY = 'provider-config';

type MachineLike =
  | (Pick<MachineSummary, 'metadata'> & { machine_metadata?: Record<string, unknown> | null })
  | null
  | undefined;

function metadataOf(machine: MachineLike): Record<string, unknown> | null {
  if (!machine) return null;
  const metadata = machine.metadata ?? machine.machine_metadata;
  return metadata && typeof metadata === 'object' ? (metadata as Record<string, unknown>) : null;
}

export function machineSupportsProviderConfig(machine: MachineLike): boolean {
  const caps = metadataOf(machine)?.capabilities;
  return Array.isArray(caps) && caps.some((c) => String(c) === PROVIDER_CONFIG_CAPABILITY);
}

/**
 * Display names the daemon publishes beside `available_agents`, for ids no
 * client catalog can know (a provider from the machine's own config).
 */
export function readAgentLabels(machine: MachineLike): Record<string, string> {
  const raw = metadataOf(machine)?.agent_labels;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const out: Record<string, string> = {};
  for (const [id, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === 'string' && value) out[id] = value;
  }
  return out;
}

export interface ProviderRow {
  id: string;
  label: string;
  source: 'builtin' | 'config';
  enabled: boolean;
  installed: boolean;
  binary: string | null;
  command: string[];
  install_hint: string;
}

export interface ProviderProbeResult {
  id: string;
  label: string;
  ok: boolean;
  stage: 'binary' | 'spawn' | 'initialize' | 'session_new' | 'ok';
  installed: boolean;
  command: string[];
  binary?: string;
  error?: string;
  stderr?: string[];
  elapsed_ms?: number;
  protocol_version?: number | string;
  agent?: { name?: string; title?: string; version?: string };
  auth_methods?: string[];
  models?: { id: string; label: string }[];
  modes?: { id: string; label: string }[];
}

/** Daemon handlers report failure as a successful rpc-result carrying `error`. */
function unwrap<T>(result: Record<string, unknown>): T {
  if (typeof result.error === 'string') throw new RpcError(result.error);
  return result as unknown as T;
}

export async function rpcProviderList(machineId: string): Promise<ProviderRow[]> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'provider-list', {});
  const parsed = unwrap<{ providers?: ProviderRow[] }>(result);
  return Array.isArray(parsed.providers) ? parsed.providers : [];
}

export interface ProviderMutationResult {
  available_agents?: Record<string, boolean>;
}

/**
 * Write a catalog entry (or any `{id, label, command, env?}`) into the
 * machine's config. Returns the row plus the machine's fresh
 * `available_agents`, which the daemon has already pushed to the cloud row.
 */
export async function rpcProviderAdd(
  machineId: string,
  entry: AcpCatalogEntry | { id: string; label: string; command: string[]; env?: Record<string, string> },
): Promise<ProviderRow & ProviderMutationResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'provider-add', { entry });
  return unwrap<ProviderRow & ProviderMutationResult>(result);
}

export async function rpcProviderRemove(
  machineId: string,
  providerId: string,
): Promise<ProviderMutationResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'provider-remove', {
    provider_id: providerId,
  });
  return unwrap<ProviderMutationResult>(result);
}

/**
 * Spawn the provider once and run the session handshake. Slow (an agent's
 * cold start) — only on an explicit click. A probe that *fails* still
 * resolves: the failure is the answer, carried in `ok`/`stage`/`error`.
 */
export async function rpcProviderProbe(
  machineId: string,
  providerId: string,
): Promise<ProviderProbeResult> {
  const result = await getRpcClient(machineId).callRpc(machineId, 'provider-probe', {
    provider_id: providerId,
  });
  if (typeof result.error === 'string' && typeof result.stage !== 'string') {
    throw new RpcError(result.error);
  }
  return result as unknown as ProviderProbeResult;
}

/** Human summary of a probe, for the row's status line. */
export function describeProbe(probe: ProviderProbeResult): string {
  if (probe.ok) {
    const who = [probe.agent?.name, probe.agent?.version].filter(Boolean).join(' ');
    const models = probe.models?.length ?? 0;
    const parts = [
      `Works${who ? ` (${who})` : ''}`,
      models ? `${models} model${models === 1 ? '' : 's'}` : null,
      typeof probe.elapsed_ms === 'number' ? `${(probe.elapsed_ms / 1000).toFixed(1)}s` : null,
    ].filter(Boolean);
    return parts.join(' · ');
  }
  const stage: Record<ProviderProbeResult['stage'], string> = {
    binary: 'Not installed',
    spawn: "Couldn't start",
    initialize: "Didn't answer the ACP handshake",
    session_new: "Couldn't open a session",
    ok: 'Works',
  };
  return `${stage[probe.stage] ?? 'Failed'}${probe.error ? ` — ${probe.error}` : ''}`;
}
