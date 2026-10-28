'use client';

import { FolderPlus } from 'lucide-react';

import type { SessionActionChoice } from '@/components/dashboard/session-actions-menu';
import { NO_PROJECT_LABEL, ProjectIcon } from '@/components/dashboard/task-ui';
import { projectRoleAtLeast, type getBackendAPI, type ProjectResponse } from '@/lib/backend-api';
import { pathBasename } from '@/lib/project-paths';
import { addCachedProject } from '@/lib/use-projects';

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
    project, the current one checked, then "New project “<folder>”" when
    `newProject` is given (see `newProjectFolder`). Undefined when there is
    nowhere to file it (no projects API, or none the caller can add to), which
    hides the item. The sidebar and the session header both build from this,
    so their menus list the same thing. */
export function sessionProjectChoices(
  fileable: ProjectResponse[],
  currentProjectId: string | null,
  onMove: (projectId: string | null) => void,
  newProject?: { folder: string; onCreate: () => void },
): SessionActionChoice[] | undefined {
  if (fileable.length === 0) return undefined;
  const choices: SessionActionChoice[] = [
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
  if (newProject) {
    choices.push({
      key: 'new-project',
      label: `New project “${pathBasename(newProject.folder)}”`,
      leading: <FolderPlus className="size-3.5 shrink-0 text-muted-foreground" />,
      separatorBefore: true,
      onSelect: newProject.onCreate,
    });
  }
  return choices;
}

/** "New project “<folder>”": a project named after `folder` (with the
    session's git remote, when it has one), linked to that folder on
    `machineId` so the folder's next sessions land in it too. Deleted again if
    the link fails, so a failure leaves no empty project behind. Added to the
    shared projects list; the caller then moves the session in. */
export async function createProjectForFolder(
  api: ReturnType<typeof getBackendAPI>,
  { folder, machineId, gitRemoteUrl }: { folder: string; machineId: string; gitRemoteUrl?: unknown },
): Promise<ProjectResponse> {
  const created = await api.createProject({
    name: pathBasename(folder),
    git_remote_url: typeof gitRemoteUrl === 'string' && gitRemoteUrl ? gitRemoteUrl : null,
  });
  let linked: ProjectResponse;
  try {
    linked = await api.setProjectDirectory(created.id, { machine_id: machineId, local_path: folder });
  } catch (error) {
    await api.deleteProject(created.id).catch(() => undefined);
    throw error;
  }
  addCachedProject(linked);
  return linked;
}
