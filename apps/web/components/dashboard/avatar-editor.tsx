'use client';

// The editor for any principal's avatar — a user's profile photo or an agent's
// picture. The avatar IS the control: clicking it opens a popover offering the
// two ways to be recognisable, an uploaded image or a picked emoji, and a small
// camera badge on the corner is the affordance.
//
// It is a popover rather than a straight file dialog because an emoji is a
// first-class choice, not a fallback: plenty of people would rather pick 🦊 than
// upload a face, and a photo is the heavier of the two options. Same shape as
// `ProjectIconEditor`, deliberately — a project, a user and an agent all answer
// "what does this thing look like" and should not answer it three ways.
//
// Everything here is round because `<PrincipalAvatar>` is round for every
// principal; the hover scrim and both badges inherit that, so the hover state is
// identical whichever principal is being edited.

import { useRef, useState } from 'react';
import { Camera, ImagePlus, Loader2, Trash2 } from 'lucide-react';

import { EmojiPicker } from '@/components/ui/emoji-picker';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { PrincipalAvatar, type PrincipalAvatarSize } from '@/components/ui/principal-avatar';
import type { Principal } from '@/lib/principals';
import { cn } from '@/lib/utils';

// Matches MAX_AVATAR_UPLOAD_BYTES in backend/api/users.py and
// backend/api/agent_profiles.py — a courtesy check so an oversized file fails
// instantly instead of after the upload.
const MAX_AVATAR_BYTES = 8 * 1024 * 1024;

// The badge has to grow with the avatar or it swamps a 56px one and vanishes on
// an 80px one. Only the two sizes a profile surface actually uses.
const BADGES: Record<'lg' | 'xl', { camera: string; icon: string }> = {
  lg: { camera: 'size-6', icon: 'size-3' },
  xl: { camera: 'size-7', icon: 'size-3.5' },
};

export function AvatarEditor({
  principal,
  size = 'lg',
  onUploadImage,
  onRemoveImage,
  onSetEmoji,
  onClearEmoji,
}: {
  principal: Principal;
  size?: Extract<PrincipalAvatarSize, 'lg' | 'xl'>;
  onUploadImage: (file: File) => Promise<void> | void;
  onRemoveImage: () => Promise<void> | void;
  onSetEmoji: (emoji: string) => Promise<void> | void;
  onClearEmoji: () => Promise<void> | void;
}) {
  const badge = BADGES[size];
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const run = async (action: () => Promise<void> | void) => {
    setOpen(false);
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update the avatar.');
    } finally {
      setBusy(false);
    }
  };

  const onFilePicked = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ''; // allow re-picking the same file
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setError('Please choose an image file.');
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setError('Image must be under 8MB.');
      return;
    }
    await run(() => onUploadImage(file));
  };

  return (
    <div className="space-y-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            disabled={busy}
            aria-label={`Change ${principal.name ?? 'this'} avatar`}
            className="group/avatar relative block w-fit cursor-pointer rounded-full disabled:cursor-default"
          >
            <PrincipalAvatar principal={principal} size={size} />
            <span
              aria-hidden="true"
              className={cn(
                'absolute inset-0 rounded-full bg-black/45 opacity-0 transition-opacity',
                'group-hover/avatar:opacity-100 group-focus-visible/avatar:opacity-100',
                busy && 'opacity-100',
              )}
            />
            {busy && <Loader2 className="absolute inset-0 m-auto size-5 animate-spin text-white" />}
            {/* The affordance: a camera sitting on the avatar's corner, ringed in
                the page background so it reads as a badge at any avatar color. */}
            <span
              aria-hidden="true"
              className={cn(
                'absolute -bottom-0.5 -right-0.5 inline-flex items-center justify-center',
                badge.camera,
                'rounded-full border-2 border-background bg-muted text-muted-foreground',
                'transition-colors group-hover/avatar:bg-foreground group-hover/avatar:text-background',
              )}
            >
              <Camera className={badge.icon} />
            </span>
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
            {/* Only exists once there is a photo to remove. Removing it reveals
                any emoji picked earlier — they are independent fields. */}
            {principal.avatarImageUri && (
              <button
                type="button"
                onClick={() => void run(onRemoveImage)}
                className="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Trash2 className="size-3.5" />
                Remove photo
              </button>
            )}
          </div>
          <EmojiPicker
            variant="avatar"
            onSelect={(emoji) => void run(() => onSetEmoji(emoji))}
            onClear={principal.emoji ? () => void run(onClearEmoji) : undefined}
            clearLabel="Remove emoji"
          />
        </PopoverContent>
      </Popover>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => void onFilePicked(e)}
      />
    </div>
  );
}
