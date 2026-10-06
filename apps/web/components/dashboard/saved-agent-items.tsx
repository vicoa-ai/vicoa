'use client';

import { Fragment } from 'react';

import type { AgentProfile, TeamSummary } from '@/lib/backend-api';
import { groupAgentsByOwner } from '@/lib/agent-owners';
import { agentPrincipal, agentProfileBlockedReason } from '@/lib/use-agent-profiles';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { TickItem } from '@/components/dashboard/session-config-dropdown';

/**
 * The saved-agent section at the top of an Agent dropdown: one group per owner
 * (yours, then each team's), then a divider before the raw providers the
 * caller renders. Shared by the new-session picker and the automation editor so
 * both offer the same agents with the same machine gate. Renders nothing when
 * there are no saved agents, so nobody pays for a feature they haven't used.
 */
export function SavedAgentItems({
  profiles,
  teams,
  selectedId,
  machine,
  onPick,
}: {
  profiles: AgentProfile[];
  /** Names the team groups; only needed once a team agent is listed. */
  teams: TeamSummary[] | undefined;
  selectedId: string | null;
  /** The machine the agent will run on, for the instructions gate below. */
  machine: { metadata?: Record<string, unknown> | null } | null | undefined;
  onPick: (profile: AgentProfile) => void;
}) {
  return (
    <>
      {groupAgentsByOwner(profiles, teams).map((group) => (
        <Fragment key={group.key}>
          <div className="px-2 pt-1 pb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {group.team ? group.label : 'My agents'}
          </div>
          {group.profiles.map((profile) => {
            // Instructions need a daemon new enough to carry them; an older one
            // drops the metadata silently, so offer the profile as unavailable
            // rather than let it spawn a quietly de-fanged agent.
            const blocked = agentProfileBlockedReason(profile, machine);
            return (
              <TickItem
                key={profile.id}
                label={profile.name}
                sublabel={blocked ? 'Update required' : undefined}
                disabled={!!blocked}
                leading={<PrincipalAvatar principal={agentPrincipal(profile)} size="xs" plain />}
                isSelected={profile.id === selectedId}
                isPending={false}
                onClick={() => onPick(profile)}
              />
            );
          })}
          <div className="my-1 h-px bg-border" />
        </Fragment>
      ))}
    </>
  );
}
