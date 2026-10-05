import { describe, expect, it } from 'vitest';
import type { AutomationResponse, ProjectResponse } from '@/lib/backend-api';
import { groupByProject, NO_PROJECT } from './group-by-project';

const project = (id: string, name: string) => ({ id, name }) as ProjectResponse;
const row = (id: string, projectId: string | null) =>
  ({ id, project_id: projectId }) as AutomationResponse;

describe('groupByProject', () => {
  it('follows the project order and puts "No project" last', () => {
    const groups = groupByProject(
      [row('a', null), row('b', 'p2'), row('c', 'p1'), row('d', 'p2')],
      [project('p1', 'One'), project('p2', 'Two')],
    );
    expect(groups.map((g) => g.key)).toEqual(['p1', 'p2', NO_PROJECT]);
    expect(groups[1].rows.map((r) => r.id)).toEqual(['b', 'd']);
    expect(groups[0].project?.name).toBe('One');
    expect(groups[2].project).toBeNull();
  });

  it('keeps a project the list does not know, before "No project"', () => {
    const groups = groupByProject([row('a', null), row('b', 'gone')], [project('p1', 'One')]);
    expect(groups.map((g) => g.key)).toEqual(['gone', NO_PROJECT]);
    expect(groups[0].project).toBeNull();
  });

  it('draws no group for a project without automations', () => {
    expect(groupByProject([], [project('p1', 'One')])).toEqual([]);
  });
});
