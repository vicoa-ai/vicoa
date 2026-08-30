'use client';

import { Folder, X } from 'lucide-react';
import { folderDisplayName } from '@/lib/chat-drop';

/**
 * A pending FOLDER reference in the composer — the visual twin of a file
 * attachment chip, but it carries no bytes: the folder is referenced by path
 * (`@folder/`) and expanded into the message text at send time. Shown for
 * desktop "Add folder" and desktop folder-drops. `path` is the absolute path;
 * the chip labels it by basename with the full path on hover.
 */
export function FolderRefChip({
  path,
  onRemove,
}: {
  path: string;
  onRemove: () => void;
}) {
  return (
    <div className="relative">
      <span
        className="flex items-center gap-2 h-14 w-40 px-3 rounded-lg border border-border bg-muted-foreground/5"
        title={path}
      >
        <Folder className="w-4 h-4 flex-shrink-0 text-muted-foreground" />
        <span className="flex min-w-0 flex-col text-left">
          <span className="truncate text-[11px] font-medium">{folderDisplayName(path)}</span>
          <span className="text-[10px] text-muted-foreground">Folder</span>
        </span>
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-background border border-border flex items-center justify-center hover:bg-accent"
        title="Remove folder"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}
