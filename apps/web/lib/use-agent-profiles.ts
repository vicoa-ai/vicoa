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
 * Minimum daemon version that understands `system_prompt` in spawn metadata.
 * Mirrors `MIN_DAEMON_VERSION_FOR_SYSTEM_PROMPT` in
 * `backend/src/protocol/system_prompt.py`; kept in sync by hand, like the CLI's
 * copy of the task vocabulary.
 *
 * The gate exists because an old daemon drops metadata it doesn't recognise
 * *silently*: the agent would spawn with none of its instructions while the UI
 * went on showing the profile's name, and the user would just experience it as
 * "this agent doesn't listen".
 */
export const MIN_DAEMON_VERSION_FOR_SYSTEM_PROMPT = '1.7.20';

/** `a >= b` over dotted numeric versions; unparseable input compares as older. */
function versionAtLeast(a: string, b: string): boolean {
  const parse = (v: string) =>
    v
      .trim()
      .split('.')
      .map((part) => Number.parseInt(part, 10));
  const left = parse(a);
  const right = parse(b);
  for (let i = 0; i < Math.max(left.length, right.length); i += 1) {
    const l = left[i];
    const r = right[i] ?? 0;
    if (!Number.isFinite(l)) return false;
    if (l !== r) return l > r;
  }
  return true;
}

/**
 * Why this profile can't run on this machine, or null when it can.
 *
 * Only instructions are gated — a profile that is just a model/config preset
 * works on any daemon, so the check is skipped entirely when `system_prompt` is
 * empty. An unknown version (a machine that never reported one) is treated as
 * too old: failing closed here costs a nudge to update, while failing open
 * costs a silently de-fanged agent.
 */
export function agentProfileBlockedReason(
  profile: AgentProfile,
  machineCliVersion: string | null | undefined,
): string | null {
  if (!(profile.system_prompt || '').trim()) return null;
  if (machineCliVersion && versionAtLeast(machineCliVersion, MIN_DAEMON_VERSION_FOR_SYSTEM_PROMPT)) {
    return null;
  }
  return `Update Vicoa on this machine to ${MIN_DAEMON_VERSION_FOR_SYSTEM_PROMPT} or later to use custom instructions.`;
}
