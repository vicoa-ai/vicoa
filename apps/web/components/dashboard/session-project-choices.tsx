'use client';

import type { SessionActionChoice } from '@/components/dashboard/session-actions-menu';
import { NO_PROJECT_LABEL, ProjectIcon } from '@/components/dashboard/task-ui';
import { projectRoleAtLeast, type ProjectResponse } from '@/lib/backend-api';

/** Where one of your sessions can be filed: projects in your own list (yours,
    your team's, shared ones you follow), not archived, where you may add
    sessions — the backend's floor for a move is `editor` covering sessions.
    Keeps the order given (the dashboard's). */
export function fileableProjects(projects: Iterable<ProjectResponse>): ProjectResponse[] {
  return Array.from(projects).filter(
    (p) =>
      !p.is_archived &&
      (p.followed ?? !p.owner) &&
      projectRoleAtLeast(p.role, 'editor') &&
      (p.scopes ?? []).includes('sessions'),
  );
}

/** The session menu's "Project ▸" choices: `fileable` (see above), then No
    project, the current one checked. Undefined when there is nowhere to file
    it (no projects API, or none the caller can add to), which hides the item.
    The sidebar and the session header both build from this, so their menus
    list the same thing. */
export function sessionProjectChoices(
  fileable: ProjectResponse[],
  currentProjectId: string | null,
  onMove: (projectId: string | null) => void,
): SessionActionChoice[] | undefined {
  if (fileable.length === 0) return undefined;
  return [
    ...fileable.map((project) => ({
      key: project.id,
      label: project.name,
      leading: <ProjectIcon project={project} />,
      checked: project.id === currentProjectId,
      onSelect: () => onMove(project.id),
    })),
    {
      key: 'no-project',
      label: NO_PROJECT_LABEL,
      leading: <ProjectIcon project={null} />,
      checked: currentProjectId === null,
      separatorBefore: true,
      onSelect: () => onMove(null),
    },
  ];
}
