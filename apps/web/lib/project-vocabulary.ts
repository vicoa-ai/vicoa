/**
 * What a task's pickers offer, given its project (collaboration §3.3, §3.6).
 *
 * Labels and agents belong to an owner, never to a project: a team's project
 * uses the team's label set and can be assigned the team's agents; anything
 * else uses the caller's own. The backend accepts exactly that (your own
 * labels and agents, plus the project owner's), so a picker that offered
 * another team's would only produce a 404.
 */

import type { AgentProfile, ProjectResponse, TaskLabelResponse } from './backend-api';

type ProjectOwner = Pick<ProjectResponse, 'team_id'> | null | undefined;

/** The label set a task on `project` draws from. Labels the task already
 *  carries stay listed so they can still be removed. */
export function labelsForProject(
  labels: TaskLabelResponse[],
  project: ProjectOwner,
  current: TaskLabelResponse[] = [],
): TaskLabelResponse[] {
  const teamId = project?.team_id ?? null;
  const offered = labels.filter((label) => (label.team_id ?? null) === teamId);
  const seen = new Set(offered.map((l) => l.id));
  for (const label of current) {
    if (!seen.has(label.id)) {
      offered.push(label);
      seen.add(label.id);
    }
  }
  return offered.sort((a, b) => a.name.localeCompare(b.name));
}

/** Where a label typed into the picker is created: the project's team, or
 *  the caller's own set. */
export function labelOwnerForProject(project: ProjectOwner): string | null {
  return project?.team_id ?? null;
}

/** Agents a task on `project` can be assigned: your own, plus the owning
 *  team's when it is a team's project. */
export function agentsForProject(profiles: AgentProfile[], project: ProjectOwner): AgentProfile[] {
  const teamId = project?.team_id ?? null;
  return profiles.filter((p) => !p.team_id || (teamId !== null && p.team_id === teamId));
}
