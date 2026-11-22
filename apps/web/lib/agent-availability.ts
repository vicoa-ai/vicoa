/**
 * Which agents can start a session on a machine, as the new-session page reads
 * the daemon's `available_agents` (see `lib/desktop-agent-scan.ts`).
 *
 * A machine whose daemon is too old to report installs reads as `known: false`
 * and every agent counts as installed: the page then behaves as it always has
 * and lets the daemon answer, rather than blocking on a guess.
 */

import { PLAN_CHOICES } from '@/lib/desktop-agent-install';

export interface AgentAvailability {
  /** Whether the daemon reports installs at all. */
  known: boolean;
  isInstalled: (agentId: string) => boolean;
}

export function agentAvailability(available: Record<string, boolean> | null): AgentAvailability {
  if (!available) return { known: false, isInstalled: () => true };
  return { known: true, isInstalled: (agentId) => available[agentId] === true };
}

/** Split picker entries into installed and not, keeping each group's order. */
export function splitByInstalled<T extends { id: string }>(
  entries: readonly T[],
  availability: AgentAvailability,
): { installed: T[]; missing: T[] } {
  const installed: T[] = [];
  const missing: T[] = [];
  for (const entry of entries) {
    (availability.isInstalled(entry.id) ? installed : missing).push(entry);
  }
  return { installed, missing };
}

/**
 * The agent to start with when the current one isn't installed: the first
 * installed of the plan choices (Claude Code, Codex, OpenCode), else the first
 * installed entry. Null when nothing is installed.
 */
export function firstInstalledAgent(
  entryIds: readonly string[],
  availability: AgentAvailability,
): string | null {
  const ordered = [...PLAN_CHOICES.map((choice) => choice.id), ...entryIds];
  return ordered.find((id) => entryIds.includes(id) && availability.isInstalled(id)) ?? null;
}

/**
 * Settings → Providers, opened on one agent for one machine: where an agent
 * the machine lacks gets set up. The new-session page links here rather than
 * installing anything itself, so the composer stays about the session.
 */
export function providerSetupHref(agentId: string, machineId: string | null): string {
  const params = new URLSearchParams({ tab: 'providers', agent: agentId });
  if (machineId) params.set('machine', machineId);
  return `/dashboard/settings?${params.toString()}`;
}
