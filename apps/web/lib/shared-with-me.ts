/**
 * The sidebar's "Shared with me" group (collaboration §8.4, P5): what other
 * people have shared with the signed-in user, sub-grouped by project.
 *
 * Two inputs, deliberately separate from the user's own list:
 *   - sessions from `GET /agent-instances?scope=shared` (the dashboard's main
 *     list stays `scope=me`, so Kanban, search and unread counts never mix
 *     someone else's work in with yours);
 *   - projects from `GET /projects` whose `owner` is set, i.e. that belong to
 *     someone else. A project shared for its tasks only has no sessions to
 *     show but still earns a header, since that is how its board is reached.
 *
 * A session shared on its own (no grant on its project) has no visible
 * project to sit under, so those gather under their owner instead.
 *
 * A shared project the user follows ("Add to sidebar") leaves this group,
 * sessions and all: it is listed among their own projects instead, its
 * sessions under the project's Team row. So do other people's sessions in a
 * project the user owns (a collaborator's, filed there by its remote).
 */

import type { AgentInstanceResponse, PrincipalResponse, ProjectResponse } from './backend-api';

export interface SharedGroup {
  /** The project id, or `owner:<user id>` for sessions shared on their own. */
  key: string;
  kind: 'project' | 'owner';
  project: ProjectResponse | null;
  owner: PrincipalResponse | null;
  label: string;
  instances: AgentInstanceResponse[];
}

export function isSharedProject(project: ProjectResponse): boolean {
  return project.owner != null && !project.is_archived;
}

/** A shared project the user follows into their own list (`followed`). */
export function isFollowedSharedProject(project: ProjectResponse): boolean {
  return isSharedProject(project) && project.followed === true;
}

/**
 * Whether following means anything for this project ("Add to sidebar"): the
 * sidebar lists a project by its sessions, so a board-only grant has nothing
 * to show there.
 */
export function canFollowProject(project: ProjectResponse): boolean {
  return isSharedProject(project) && (project.scopes?.includes('sessions') ?? false);
}

export function groupSharedWithMe(
  instances: AgentInstanceResponse[],
  projects: Iterable<ProjectResponse>,
): SharedGroup[] {
  const groups: SharedGroup[] = [];
  const byProject = new Map<string, SharedGroup>();
  // Projects the sidebar lists as the user's own; their sessions sit there.
  const listed = new Set<string>();
  for (const project of projects) {
    if (!project.owner) {
      listed.add(project.id);
      continue;
    }
    if (!isSharedProject(project)) continue;
    if (isFollowedSharedProject(project)) {
      listed.add(project.id);
      continue;
    }
    const group: SharedGroup = {
      key: project.id,
      kind: 'project',
      project,
      owner: project.owner ?? null,
      label: project.name,
      instances: [],
    };
    byProject.set(project.id, group);
    groups.push(group);
  }

  const byOwner = new Map<string, SharedGroup>();
  for (const instance of instances) {
    if (instance.project_id && listed.has(instance.project_id)) continue;
    const projectGroup = instance.project_id ? byProject.get(instance.project_id) : undefined;
    if (projectGroup) {
      projectGroup.instances.push(instance);
      continue;
    }
    const ownerId = instance.owner?.id ?? 'unknown';
    let ownerGroup = byOwner.get(ownerId);
    if (!ownerGroup) {
      ownerGroup = {
        key: `owner:${ownerId}`,
        kind: 'owner',
        project: null,
        owner: instance.owner ?? null,
        label: instance.owner?.name?.trim() || 'Shared sessions',
        instances: [],
      };
      byOwner.set(ownerId, ownerGroup);
    }
    ownerGroup.instances.push(instance);
  }
  return [...groups, ...byOwner.values()];
}
