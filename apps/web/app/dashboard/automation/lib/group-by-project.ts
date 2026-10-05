import type { AutomationResponse, ProjectResponse } from '@/lib/backend-api';

/** Key of the group for automations filed in no project. */
export const NO_PROJECT = 'none';

export interface AutomationGroup {
  /** The project id, or `NO_PROJECT`. */
  key: string;
  /** Null for "No project", and for a project the caller's list doesn't hold. */
  project: ProjectResponse | null;
  rows: AutomationResponse[];
}

/**
 * Rows grouped under the project each is filed in. Groups follow `projects`
 * (the order the sidebar shows them in), then any project that list doesn't
 * know, then "No project" last. Rows keep their order inside a group.
 */
export function groupByProject(
  rows: AutomationResponse[],
  projects: ProjectResponse[],
): AutomationGroup[] {
  const known = new Map(projects.map((p, i) => [p.id, { project: p, index: i }]));
  const groups = new Map<string, AutomationGroup>();
  for (const row of rows) {
    const key = row.project_id ?? NO_PROJECT;
    let group = groups.get(key);
    if (!group) {
      group = { key, project: known.get(key)?.project ?? null, rows: [] };
      groups.set(key, group);
    }
    group.rows.push(row);
  }
  const rank = (g: AutomationGroup): number =>
    g.key === NO_PROJECT ? projects.length + 1 : (known.get(g.key)?.index ?? projects.length);
  return [...groups.values()].sort((a, b) => rank(a) - rank(b));
}
