'use client';

// The "Display" block of /dashboard/settings' per-project pane: edit a project's
// name + icon (image / emoji / generated) so the sidebar and Tasks board show the
// same identity (project-identity-unification §5d). The pane is opened by
// (machineId, dir); this resolves that to the DB project via its linked
// directories, so the settings entry and the sidebar/Tasks share one identity.

import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { ProjectIconEditor } from '@/components/dashboard/project-icon-editor';
import { getBackendAPI, type ProjectResponse } from '@/lib/backend-api';

/** True when `sessionPath` is `linkedPath` or nested under it (path boundary). */
function pathAtOrUnder(sessionPath: string, linkedPath: string): boolean {
  const base = linkedPath.replace(/\/+$/, '');
  return sessionPath === base || sessionPath.startsWith(base + '/');
}

/** The project whose directory on `machineId` best matches `dir` (longest wins). */
function resolveProject(
  projects: ProjectResponse[],
  machineId: string,
  dir: string,
): ProjectResponse | null {
  let best: ProjectResponse | null = null;
  let bestLen = -1;
  for (const project of projects) {
    for (const directory of project.directories) {
      if (directory.machine_id !== machineId) continue;
      const matches =
        pathAtOrUnder(dir, directory.local_path) ||
        pathAtOrUnder(directory.local_path, dir);
      if (matches && directory.local_path.length > bestLen) {
        best = project;
        bestLen = directory.local_path.length;
      }
    }
  }
  return best;
}

export function ProjectDisplaySection({
  machineId,
  dir,
}: {
  machineId: string;
  dir: string;
}) {
  // undefined = loading, null = no project linked to this directory yet.
  const [project, setProject] = useState<ProjectResponse | null | undefined>(undefined);
  const [name, setName] = useState('');

  const refresh = useCallback(async () => {
    try {
      const projects = await getBackendAPI(true).listProjects(true);
      const match = resolveProject(projects, machineId, dir);
      setProject(match ?? null);
      if (match) setName(match.name);
    } catch {
      setProject(null);
    }
  }, [machineId, dir]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (project === undefined) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading project…
      </div>
    );
  }

  if (project === null) {
    return (
      <p className="text-sm text-muted-foreground">
        No project is linked to this folder yet. Start a session here and one is created
        automatically — then its name and icon can be set.
      </p>
    );
  }

  const api = getBackendAPI(true);

  const commitName = async () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === project.name) {
      setName(project.name);
      return;
    }
    try {
      await api.updateProject(project.id, { name: trimmed });
      await refresh();
    } catch (err) {
      console.error('Failed to rename project:', err);
      setName(project.name);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-medium text-foreground">Display</p>
        <p className="text-xs text-muted-foreground">
          The name and icon shown in the sidebar and Tasks board.
        </p>
      </div>
      <div className="flex items-center gap-3">
        <ProjectIconEditor
          project={project}
          triggerClassName="size-12"
          iconClassName="size-8"
          onUploadImage={async (file) => {
            await api.uploadProjectIcon(project.id, file);
            await refresh();
          }}
          onSetEmoji={async (emoji) => {
            await api.updateProject(project.id, { icon: emoji });
            await refresh();
          }}
          onClearEmoji={async () => {
            await api.updateProject(project.id, { icon: null });
            await refresh();
          }}
          onResetToDefault={async () => {
            if (project.icon_image_uri) await api.deleteProjectIcon(project.id);
            if (project.icon) await api.updateProject(project.id, { icon: null });
            await refresh();
          }}
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => void commitName()}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur();
            if (e.key === 'Escape') {
              setName(project.name);
              e.currentTarget.blur();
            }
          }}
          className="min-w-0 flex-1 rounded-md border bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-label="Project name"
        />
      </div>
    </div>
  );
}
