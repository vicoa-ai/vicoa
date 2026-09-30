/**
 * Agents are personal or a team's (collaboration §3.6). The Agents page and
 * the new-session picker list them grouped by owner: yours first, then each
 * team's, teams by name. A solo user (no team agents) gets one unlabelled
 * group, so nothing about their list changes.
 */

import type { AgentProfile, TeamSummary } from './backend-api';

export interface AgentOwnerGroup {
  /** `personal`, or the team id. */
  key: string;
  /** Null for the caller's own when there is nothing to tell it apart from. */
  label: string | null;
  team: TeamSummary | null;
  profiles: AgentProfile[];
}

export function groupAgentsByOwner(
  profiles: AgentProfile[],
  teams: TeamSummary[] | undefined,
): AgentOwnerGroup[] {
  const personal = profiles.filter((p) => !p.team_id);
  const byTeam = new Map<string, AgentProfile[]>();
  for (const profile of profiles) {
    if (!profile.team_id) continue;
    const list = byTeam.get(profile.team_id) ?? [];
    list.push(profile);
    byTeam.set(profile.team_id, list);
  }
  if (byTeam.size === 0) {
    return personal.length ? [{ key: 'personal', label: null, team: null, profiles: personal }] : [];
  }
  const teamById = new Map((teams ?? []).map((t) => [t.id, t]));
  const teamGroups: AgentOwnerGroup[] = [...byTeam.entries()]
    .map(([teamId, list]) => {
      const team = teamById.get(teamId) ?? null;
      return { key: teamId, label: team?.name ?? 'Team', team, profiles: list };
    })
    .sort((a, b) => (a.label ?? '').localeCompare(b.label ?? ''));
  const groups: AgentOwnerGroup[] = [];
  if (personal.length) groups.push({ key: 'personal', label: 'Yours', team: null, profiles: personal });
  return [...groups, ...teamGroups];
}

/** A free "New agent", "New agent 2", … within one owner's list. */
export function nextAgentName(profiles: AgentProfile[], teamId: string | null): string {
  const taken = new Set(
    profiles.filter((p) => (p.team_id ?? null) === teamId).map((p) => p.name.toLowerCase()),
  );
  let name = 'New agent';
  for (let i = 2; taken.has(name.toLowerCase()); i += 1) name = `New agent ${i}`;
  return name;
}
