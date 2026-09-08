'use client';

// Profile-photo editor: a large PrincipalAvatar next to upload/remove actions.
// The sibling of project-icon-editor.tsx (same 8MB client-side bound, same
// "controlled — the caller supplies the mutations" shape), minus the emoji
// picker: a person is not an emoji.

import { useRef, useState } from 'react';
import { ImagePlus, Loader2, Trash2 } from 'lucide-react';

import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import type { Principal } from '@/lib/principals';
import { Button } from '@/components/ui/button';

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
    <div className="flex items-center gap-4">
      {busy ? (
        <span className="inline-flex size-14 items-center justify-center rounded-full bg-muted">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </span>
      ) : (
        <PrincipalAvatar principal={principal} size="lg" />
      )}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
          >
            <ImagePlus className="mr-2 size-3.5" />
            {principal.avatarImageUri ? 'Change photo' : 'Upload photo'}
          </Button>
          {principal.avatarImageUri && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => void run(onRemoveImage)}
            >
              <Trash2 className="mr-2 size-3.5" />
              Remove
            </Button>
          )}
        </div>
        <p className={error ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}>
          {error ?? 'PNG, JPEG, WebP or GIF, up to 8MB. Shown wherever you appear.'}
        </p>
      </div>
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
