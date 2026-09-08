'use client';

// Profile-photo editor: the avatar IS the control. Clicking it opens the file
// picker; a small camera badge on the corner is the affordance, and hovering
// dims the image so the badge reads as an action rather than decoration.
//
// No separate "Upload photo" button and no permanent help text: a 56px avatar
// with a camera on it is already the web's most recognisable "change your
// picture" idiom, and the constraints (type, size) are enforced server-side —
// they only need saying when something is actually rejected.

import { useRef, useState } from 'react';
import { Camera, Loader2, X } from 'lucide-react';

import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import type { Principal } from '@/lib/principals';
import { cn } from '@/lib/utils';

// Matches MAX_AVATAR_UPLOAD_BYTES in backend/api/users.py — this is only a
// courtesy check so an oversized file fails instantly instead of after upload.
const MAX_AVATAR_BYTES = 8 * 1024 * 1024;

export function UserAvatarEditor({
  principal,
  onUploadImage,
  onRemoveImage,
}: {
  principal: Principal;
  onUploadImage: (file: File) => Promise<void> | void;
  onRemoveImage: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const run = async (action: () => Promise<void> | void) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update photo.');
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
      <div className="group/avatar relative w-fit">
        <button
          type="button"
          disabled={busy}
          onClick={() => fileInputRef.current?.click()}
          aria-label={principal.avatarImageUri ? 'Change profile photo' : 'Upload a profile photo'}
          className="group/trigger relative block cursor-pointer rounded-full disabled:cursor-default"
        >
          <PrincipalAvatar principal={principal} size="lg" />
          <span
            aria-hidden="true"
            className={cn(
              'absolute inset-0 rounded-full bg-black/45 opacity-0 transition-opacity',
              'group-hover/avatar:opacity-100 group-focus-visible/trigger:opacity-100',
              busy && 'opacity-100',
            )}
          />
          {busy && (
            <Loader2 className="absolute inset-0 m-auto size-5 animate-spin text-white" />
          )}
          {/* The affordance: a camera sitting on the avatar's corner, ringed in
              the page background so it reads as a badge at any avatar color. */}
          <span
            aria-hidden="true"
            className={cn(
              'absolute -bottom-0.5 -right-0.5 inline-flex size-6 items-center justify-center',
              'rounded-full border-2 border-background bg-muted text-muted-foreground',
              'transition-colors group-hover/avatar:bg-foreground group-hover/avatar:text-background',
            )}
          >
            <Camera className="size-3" />
          </span>
        </button>
        {/* Remove only exists once there is something to remove. */}
        {principal.avatarImageUri && !busy && (
          <button
            type="button"
            onClick={() => void run(onRemoveImage)}
            aria-label="Remove profile photo"
            title="Remove photo"
            className={cn(
              'absolute -right-1 -top-1 inline-flex size-5 cursor-pointer items-center justify-center',
              'rounded-full border-2 border-background bg-muted text-muted-foreground opacity-0',
              'transition-opacity hover:text-foreground',
              'group-hover/avatar:opacity-100 focus-visible:opacity-100',
            )}
          >
            <X className="size-3" />
          </button>
        )}
      </div>
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
