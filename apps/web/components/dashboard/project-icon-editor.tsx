'use client';

// Shared project-icon editor: a ProjectIcon trigger opening a popover with
// "Upload image" / "Reset to default" and the emoji picker. Used by both the
// Tasks settings dialog and the /dashboard/settings Project pane so the two
// surfaces edit a project's identity identically (project-identity-unification
// §5d). Purely controlled — the caller supplies the mutation callbacks.

import { useRef, useState } from 'react';
import { ImagePlus, Loader2, RotateCcw } from 'lucide-react';

import { EmojiPicker } from '@/components/ui/emoji-picker';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import type { ProjectResponse } from '@/lib/backend-api';
import { cn } from '@/lib/utils';

type IconProject = Pick<
  ProjectResponse,
  'id' | 'name' | 'icon' | 'icon_image_uri' | 'updated_at' | 'is_inbox'
>;

const MAX_ICON_BYTES = 8 * 1024 * 1024;

export function ProjectIconEditor({
  project,
  triggerClassName,
  iconClassName,
  onUploadImage,
  onSetEmoji,
  onClearEmoji,
  onResetToDefault,
}: {
  project: IconProject;
  /** Sizes the trigger button box (e.g. `size-7` compact, `size-14` large). */
  triggerClassName?: string;
  /** Sizes the icon/spinner inside the trigger. */
  iconClassName?: string;
  onUploadImage: (file: File) => Promise<void> | void;
  onSetEmoji: (emoji: string) => Promise<void> | void;
  onClearEmoji: () => Promise<void> | void;
  /** Drop any custom image AND emoji → git-avatar seed / generated default. */
  onResetToDefault: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const onFilePicked = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ''; // allow re-picking the same file
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      alert('Please choose an image file.');
      return;
    }
    if (file.size > MAX_ICON_BYTES) {
      alert('Image must be under 8MB.');
      return;
    }
    setOpen(false);
    setUploading(true);
    try {
      await onUploadImage(file);
    } finally {
      setUploading(false);
    }
  };

  const hasCustomIcon = Boolean(project.icon_image_uri || project.icon);

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={`Icon for ${project.name ?? 'project'}`}
            className={cn(
              'flex shrink-0 cursor-pointer items-center justify-center rounded-md transition-colors hover:bg-accent',
              triggerClassName,
            )}
          >
            {uploading ? (
              <Loader2 className={cn('animate-spin text-muted-foreground', iconClassName)} />
            ) : (
              <ProjectIcon project={project} className={iconClassName} />
            )}
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-auto p-0">
          <div className="flex items-center gap-1 border-b p-1.5">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <ImagePlus className="size-3.5" />
              Upload image
            </button>
            {hasCustomIcon && (
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  void onResetToDefault();
                }}
                className="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <RotateCcw className="size-3.5" />
                Reset to default
              </button>
            )}
          </div>
          <EmojiPicker
            onSelect={(emoji) => {
              setOpen(false);
              void onSetEmoji(emoji);
            }}
            onClear={
              project.icon
                ? () => {
                    setOpen(false);
                    void onClearEmoji();
                  }
                : undefined
            }
          />
        </PopoverContent>
      </Popover>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => void onFilePicked(e)}
      />
    </>
  );
}
