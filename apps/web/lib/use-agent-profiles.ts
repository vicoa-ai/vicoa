'use client';

/**
 * Shared read of the caller's saved agents (collaboration P1).
 *
 * Several surfaces need the same list — the session header, the sidebar rows,
 * the new-session picker — and they need it only to turn an
 * `agent_instances.agent_profile_id` into a name and an avatar. SWR's cache key
 * dedupes that to one request per page rather than one per component.
 *
 * Resolving client-side (rather than joining the profile onto every instance
 * server-side) is deliberate: the list is tiny and already loaded for the
 * picker, while a join would put an extra query on every session-list response
 * to serve a purely cosmetic field.
 */

import useSWR from 'swr';

import { getBackendAPI, type AgentProfile } from '@/lib/backend-api';
import type { Principal } from '@/lib/principals';

const KEY = 'agent-profiles';

export function useAgentProfiles(): {
  profiles: AgentProfile[];
  byId: Map<string, AgentProfile>;
} {
  const { data } = useSWR<AgentProfile[]>(KEY, () =>
    getBackendAPI(true).listAgentProfiles(),
  );
  const profiles = data ?? [];
  return { profiles, byId: new Map(profiles.map((p) => [p.id, p])) };
}

/** `<PrincipalAvatar>` input for a profile. */
export function agentPrincipal(profile: AgentProfile): Principal {
  return {
    type: 'agent',
    id: profile.id,
    name: profile.name,
    avatarImageUri: profile.avatar_image_uri,
    updatedAt: profile.updated_at,
  };
}

/**
 * Whether a machine's daemon forwards `system_prompt` to the agent, read from
 * the `capabilities` list it publishes in `metadata` — the same feature-detect
 * mechanism `machineSupportsWorktree` and the Files/Git panels already use.
 *
 * Capability, not version number: the daemon declares what it can actually do,
 * so this needs no release number to be predicted or kept in sync, and a
 * developer running the daemon from source gets the right answer immediately.
 */
function machineSupportsSystemPrompt(
  machine: { metadata?: Record<string, unknown> | null } | null | undefined,
): boolean {
  const caps = machine?.metadata?.capabilities;
  return Array.isArray(caps) && caps.some((c) => String(c) === 'system-prompt');
}

/**
 * Why this profile can't run on this machine, or null when it can.
 *
 * Only instructions are gated — a profile that is just a model/config preset
 * works on any daemon, so the check is skipped entirely when `system_prompt` is
 * empty. A daemon that doesn't advertise the capability is treated as unable:
 * failing closed costs a nudge to update, while failing open costs a silently
 * de-fanged agent, which is the harder failure to diagnose.
 */
export function agentProfileBlockedReason(
  profile: AgentProfile,
  machine: { metadata?: Record<string, unknown> | null } | null | undefined,
): string | null {
  if (!(profile.system_prompt || '').trim()) return null;
  if (machineSupportsSystemPrompt(machine)) return null;
  return 'Update Vicoa on this machine to use an agent with custom instructions.';
}
