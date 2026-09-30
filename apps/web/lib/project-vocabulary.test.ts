import { describe, expect, it } from 'vitest';

import type { AgentProfile, TaskLabelResponse } from './backend-api';
import { agentsForProject, labelOwnerForProject, labelsForProject } from './project-vocabulary';

const label = (id: string, name: string, team_id: string | null = null): TaskLabelResponse => ({
  id,
  name,
  color: '#aa3355',
  team_id,
});

describe('labelsForProject', () => {
  const labels = [label('p1', 'bug'), label('t1', 'infra', 'team'), label('o1', 'ops', 'other')];

  it("offers a team project the team's set", () => {
    expect(labelsForProject(labels, { team_id: 'team' }).map((l) => l.id)).toEqual(['t1']);
  });

  it('offers any other project your own set', () => {
    expect(labelsForProject(labels, { team_id: null }).map((l) => l.id)).toEqual(['p1']);
    expect(labelsForProject(labels, null).map((l) => l.id)).toEqual(['p1']);
  });

  it("keeps a task's current labels removable", () => {
    const out = labelsForProject(labels, { team_id: 'team' }, [label('p1', 'bug')]);
    expect(out.map((l) => l.id)).toEqual(['p1', 't1']);
  });

  it('creates new labels where the project draws from', () => {
    expect(labelOwnerForProject({ team_id: 'team' })).toBe('team');
    expect(labelOwnerForProject(null)).toBeNull();
  });
});

describe('agentsForProject', () => {
  const agent = (id: string, team_id: string | null) => ({ id, team_id }) as AgentProfile;
  const profiles = [agent('mine', null), agent('ours', 'team'), agent('theirs', 'other')];

  it("offers yours plus the owning team's", () => {
    expect(agentsForProject(profiles, { team_id: 'team' }).map((p) => p.id)).toEqual([
      'mine',
      'ours',
    ]);
    expect(agentsForProject(profiles, { team_id: null }).map((p) => p.id)).toEqual(['mine']);
  });
});
