import { describe, expect, it } from 'vitest';

import type { AgentProfile, TeamSummary } from './backend-api';
import { groupAgentsByOwner, nextAgentName } from './agent-owners';

function agent(id: string, name: string, team_id: string | null = null): AgentProfile {
  return {
    id,
    team_id,
    name,
    description: null,
    avatar_image_uri: null,
    avatar_source: null,
    color: null,
    emoji: null,
    agent: 'claude',
    config: {},
    system_prompt: null,
    default_machine_id: null,
    default_project_id: null,
    position: 0,
    is_archived: false,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  };
}

const team = (id: string, name: string) =>
  ({ id, name, slug: id, avatar_image_uri: null, role: 'member', member_count: 2 }) as TeamSummary;

describe('groupAgentsByOwner', () => {
  it('keeps a solo list as one unlabelled group', () => {
    const groups = groupAgentsByOwner([agent('a', 'Mine')], []);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBeNull();
  });

  it('puts yours first, then teams by name', () => {
    const groups = groupAgentsByOwner(
      [agent('a', 'Z', 't2'), agent('b', 'Mine'), agent('c', 'Y', 't1')],
      [team('t1', 'Beta'), team('t2', 'Alpha')],
    );
    expect(groups.map((g) => g.label)).toEqual(['Yours', 'Alpha', 'Beta']);
  });

  it('omits an empty personal group', () => {
    const groups = groupAgentsByOwner([agent('a', 'Z', 't1')], [team('t1', 'Alpha')]);
    expect(groups.map((g) => g.key)).toEqual(['t1']);
  });
});

describe('nextAgentName', () => {
  it('counts within one owner only', () => {
    const profiles = [agent('a', 'New agent'), agent('b', 'New agent', 't1')];
    expect(nextAgentName(profiles, null)).toBe('New agent 2');
    expect(nextAgentName(profiles, 't1')).toBe('New agent 2');
    expect(nextAgentName(profiles, 't2')).toBe('New agent');
  });
});
