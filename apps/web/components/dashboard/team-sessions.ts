// The sidebar's Team row: inside a project group, the open sessions other
// people started in that project, kept apart from your own and collapsed by
// default.
//
// Apart, not mixed in, because they are a different kind of row: they run on
// someone else's machine, so they can be opened, prompted or forked but never
// resumed, archived or opened in a terminal; they have no place in your
// worktree groups (those come from your own git); an "awaiting input" on one
// is its owner's to-do, not yours; and keeping them out of the main list keeps
// ⌘1–9 pointing at your own sessions.

import type { AgentInstanceResponse, ProjectResponse } from '@/lib/backend-api';
import { CLOSED_STATUSES, compareProjectKeys, type SessionGroup } from './session-grouping';

/** Team rows listed before "Show N more". */
export const TEAM_ROWS_SHOWN = 8;

/** Projects whose Team row is open (a string[]); every other one is collapsed. */
export const TEAM_EXPANDED_STORAGE_KEY = 'sidebar-team-expanded';

/** A project listed among the user's own: theirs, or someone else's they follow. */
function listedInSidebar(project: ProjectResponse | undefined): boolean {
  if (!project || project.is_archived) return false;
  return !project.owner || project.followed === true;
}

function activityTime(instance: AgentInstanceResponse): number {
  return new Date(instance.latest_message_at || instance.started_at).getTime();
}

/**
 * Other people's open sessions (`scope=shared` rows, which carry `owner`) by
 * the project they belong to, most recently active first — only for projects
 * the sidebar lists as the user's own. The rest stay in "Shared with me".
 */
export function teamSessionsByProject(
  others: readonly AgentInstanceResponse[],
  projectsById: ReadonlyMap<string, ProjectResponse>,
): Map<string, AgentInstanceResponse[]> {
  const byProject = new Map<string, AgentInstanceResponse[]>();
  for (const instance of others) {
    if (!instance.owner || CLOSED_STATUSES.has(instance.status)) continue;
    const projectId = instance.project_id;
    if (!projectId || !listedInSidebar(projectsById.get(projectId))) continue;
    const list = byProject.get(projectId);
    if (list) list.push(instance);
    else byProject.set(projectId, [instance]);
  }
  for (const list of byProject.values()) {
    list.sort((a, b) => activityTime(b) - activityTime(a));
  }
  return byProject;
}

/**
 * The user's own project groups (from `groupSessions`), plus an empty group
 * for each project where only other people have open sessions, so its Team
 * row has somewhere to live. New groups take their place by `projectOrder`
 * like the rest; "Pinned" stays first.
 */
export function withTeamOnlyGroups(
  groups: SessionGroup[],
  teamByProject: ReadonlyMap<string, AgentInstanceResponse[]>,
  projectOrder: string[],
  projectsById: ReadonlyMap<string, ProjectResponse>,
): SessionGroup[] {
  const present = new Set(groups.map((group) => group.key));
  const added: SessionGroup[] = [];
  for (const key of teamByProject.keys()) {
    if (present.has(key)) continue;
    added.push({ key, label: projectsById.get(key)?.name ?? key, instances: [] });
  }
  if (added.length === 0) return groups;
  const pinned = groups.filter((group) => group.key === 'PINNED');
  const compareKeys = compareProjectKeys(projectOrder);
  const projects = [...groups.filter((group) => group.key !== 'PINNED'), ...added].sort((a, b) =>
    compareKeys(a.key, b.key),
  );
  return [...pinned, ...projects];
}

/**
 * The Team row's label: "Team" for a team's project or when several people
 * are in it, else the one person whose sessions these are (a project someone
 * shared with you shows "Nick", not "Team").
 */
export function teamRowLabel(
  instances: readonly AgentInstanceResponse[],
  project: ProjectResponse | undefined,
): string {
  if (project?.team_id) return 'Team';
  const owners = new Set(instances.map((instance) => instance.owner?.id ?? null));
  const name = instances[0]?.owner?.name?.trim();
  return owners.size === 1 && name ? name : 'Team';
}
