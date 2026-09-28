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

export function groupSharedWithMe(
  instances: AgentInstanceResponse[],
  projects: Iterable<ProjectResponse>,
): SharedGroup[] {
  const groups: SharedGroup[] = [];
  const byProject = new Map<string, SharedGroup>();
  for (const project of projects) {
    if (!isSharedProject(project)) continue;
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
