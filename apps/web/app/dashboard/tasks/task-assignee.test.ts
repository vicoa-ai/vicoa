import { describe, expect, it } from 'vitest';

import type { AgentProfile } from '@/lib/backend-api';
import { agentStartHint, assigneeFitsProject } from './task-assignee';

describe('agentStartHint', () => {
  const mine = { name: 'haiku-bot', team_id: null };

  it('says the agent starts once the task is created', () => {
    expect(agentStartHint(mine, 'todo')).toBe("haiku-bot will work on this as soon as it's created.");
    expect(agentStartHint(mine, 'in_progress')).toBe(
      "haiku-bot will work on this as soon as it's created.",
    );
  });

  it('says nothing starts in Backlog or a closed status', () => {
    expect(agentStartHint(mine, 'backlog')).toBe('haiku-bot will work on this once it leaves Backlog.');
    expect(agentStartHint(mine, 'done')).toBe('haiku-bot will work on this if it is reopened.');
    expect(agentStartHint(mine, 'cancelled')).toBe('haiku-bot will work on this if it is reopened.');
  });

  it("says a team agent doesn't start at all", () => {
    expect(agentStartHint({ name: 'team-bot', team_id: 'team' }, 'todo')).toBe(
      "Team agents can't start work yet, so nothing will run.",
    );
  });
});

describe('assigneeFitsProject', () => {
  const agent = (id: string, team_id: string | null) => ({ id, team_id }) as AgentProfile;
  const agentProfiles = [agent('mine', null), agent('ours', 'team')];
  const team = { team_id: 'team' };
  const otherTeam = { team_id: 'other' };
  const personal = { team_id: null };
  const fits = (
    assignee: { type: 'user' | 'agent'; id: string },
    from: { team_id: string | null } | null,
    to: { team_id: string | null } | null,
  ) => assigneeFitsProject(assignee, { viewerId: 'me', from, to, agentProfiles });

  it('keeps you on any project', () => {
    expect(fits({ type: 'user', id: 'me' }, team, null)).toBe(true);
    expect(fits({ type: 'user', id: 'me' }, null, otherTeam)).toBe(true);
  });

  it('keeps a teammate only within the same team', () => {
    expect(fits({ type: 'user', id: 'alex' }, team, team)).toBe(true);
    expect(fits({ type: 'user', id: 'alex' }, team, otherTeam)).toBe(false);
    expect(fits({ type: 'user', id: 'alex' }, team, personal)).toBe(false);
    expect(fits({ type: 'user', id: 'alex' }, team, null)).toBe(false);
  });

  it('keeps an agent the new project offers', () => {
    expect(fits({ type: 'agent', id: 'mine' }, team, null)).toBe(true);
    expect(fits({ type: 'agent', id: 'ours' }, null, team)).toBe(true);
    expect(fits({ type: 'agent', id: 'ours' }, team, personal)).toBe(false);
    expect(fits({ type: 'agent', id: 'ours' }, team, otherTeam)).toBe(false);
  });
});
