'use client';

// The "Display" block of the per-project Settings pane (General tab): edit a
// project's name + icon (image / emoji / generated) so the sidebar and Tasks
// board show the same identity (project-identity-unification §5d). The pane
// owns the project row and passes it in; every mutation reports the server's
// updated row back through `onUpdated` so the header and nav stay in sync.

import { useEffect, useState } from 'react';

import { ProjectIconEditor } from '@/components/dashboard/project-icon-editor';
import { getBackendAPI, type ProjectResponse } from '@/lib/backend-api';
import { cn } from '@/lib/utils';

export function ProjectDisplaySection({
  project,
  onUpdated,
}: {
  project: ProjectResponse;
  onUpdated: (project: ProjectResponse) => void;
}) {
  const [name, setName] = useState(project.name);

  // Re-seed when the project is replaced by a server response.
  useEffect(() => setName(project.name), [project.name]);

  const api = getBackendAPI(true);
  const isImage = Boolean(project.icon_image_uri);
  const isEmoji = !isImage && Boolean(project.icon);

  const commitName = async () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === project.name) {
      setName(project.name);
      return;
    }
    try {
      onUpdated(await api.updateProject(project.id, { name: trimmed }));
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
          // Border only for a (transparent) emoji, so it reads as a framed box;
          // an image or the generated square is already self-contained. Same
          // height (h-9) as the name input beside it.
          triggerClassName={cn('h-9 w-9', isEmoji && 'border border-border')}
          // Larger shared radius on the big Display icon; sidebar/nav keep the
          // small default. Emoji's frame radius comes from the trigger.
          iconClassName={isEmoji ? 'size-9 text-xl' : 'size-9 rounded-md'}
          onUploadImage={async (file) => {
            onUpdated(await api.uploadProjectIcon(project.id, file));
          }}
          onSetEmoji={async (emoji) => {
            // Emoji wins over a current image (render order image → emoji).
            if (project.icon_image_uri) await api.deleteProjectIcon(project.id);
            onUpdated(await api.updateProject(project.id, { icon: emoji }));
          }}
          onClearEmoji={async () => {
            onUpdated(await api.updateProject(project.id, { icon: null }));
          }}
          onResetToDefault={async () => {
            onUpdated(await api.deleteProjectIcon(project.id));
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
          className="h-9 min-w-0 flex-1 rounded-md border bg-transparent px-2.5 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-label="Project name"
        />
      </div>
    </div>
  );
}
