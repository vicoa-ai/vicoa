'use client';

import { useState } from 'react';
import { File as FileIcon } from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';

/** Shape of one entry in message_metadata.attachments (stamped by the backend). */
export interface ChatAttachmentMeta {
  id: string;
  mime_type?: string;
  size_bytes?: number;
  width?: number;
  height?: number;
  filename?: string | null;
}

/** Parse message_metadata.attachments defensively; unknown shapes → []. */
export function extractChatAttachments(metadata: unknown): ChatAttachmentMeta[] {
  if (!metadata || typeof metadata !== 'object') return [];
  const raw = (metadata as Record<string, unknown>).attachments;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (item): item is ChatAttachmentMeta =>
      !!item && typeof item === 'object' && typeof (item as ChatAttachmentMeta).id === 'string'
  );
}

/** Only raster types render inline as <img>; SVG and other non-raster image
 * types download as file chips (matches the backend's inline allowlist). Rows
 * with no mime predate file upload, so are raster images. */
const INLINE_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp']);
function isImageAttachment(meta: ChatAttachmentMeta): boolean {
  return !meta.mime_type || INLINE_IMAGE_TYPES.has(meta.mime_type);
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let size = bytes / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size < 10 ? size.toFixed(1) : Math.round(size)} ${units[unit]}`;
}

/**
 * Attachments inside a chat bubble. Images load through the cookie-authenticated
 * /api/attachments/[id] proxy and open a lightbox on click; other files render
 * as a downloadable chip.
 */
export function ChatAttachments({ attachments }: { attachments: ChatAttachmentMeta[] }) {
  const [lightboxId, setLightboxId] = useState<string | null>(null);

  if (attachments.length === 0) return null;

  return (
    <>
      <div className="flex flex-wrap gap-2 mb-1">
        {attachments.map((attachment) =>
          isImageAttachment(attachment) ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={attachment.id}
              src={`/api/attachments/${attachment.id}`}
              alt={attachment.filename ?? 'Image attachment'}
              width={attachment.width}
              height={attachment.height}
              className="rounded-lg max-h-64 max-w-full w-auto object-contain cursor-zoom-in bg-muted-foreground/5"
              loading="lazy"
              onClick={() => setLightboxId(attachment.id)}
            />
          ) : (
            <a
              key={attachment.id}
              href={`/api/attachments/${attachment.id}`}
              download={attachment.filename ?? undefined}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-lg border border-foreground/15 bg-muted-foreground/5 px-3 py-2 max-w-[16rem] hover:bg-muted-foreground/10 transition-colors"
            >
              <FileIcon className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-xs font-medium">
                  {attachment.filename ?? 'File'}
                </span>
                {attachment.size_bytes != null && (
                  <span className="text-[10px] text-muted-foreground">
                    {formatFileSize(attachment.size_bytes)}
                  </span>
                )}
              </span>
            </a>
          )
        )}
      </div>
      <Dialog open={lightboxId !== null} onOpenChange={(open) => !open && setLightboxId(null)}>
        <DialogContent className="max-w-[90vw] sm:max-w-[90vw] w-auto p-2 bg-background/95">
          <DialogTitle className="sr-only">Image attachment</DialogTitle>
          {lightboxId && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`/api/attachments/${lightboxId}`}
              alt="Image attachment"
              className="max-h-[85vh] max-w-full w-auto h-auto object-contain rounded-md"
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
