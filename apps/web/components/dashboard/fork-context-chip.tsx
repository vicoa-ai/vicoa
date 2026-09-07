'use client';

import { Split, X } from 'lucide-react';

/**
 * Chat history carried into the composer by a fork — the visual twin of the
 * folder/file attachment chips, but it carries text: the source transcript is
 * prepended to the first message at send time. Removing it starts the session
 * with a clean slate.
 */
export function ForkContextChip({
  title,
  messageCount,
  onRemove,
}: {
  title: string;
  messageCount: number;
  onRemove: () => void;
}) {
  return (
    <div className="relative">
      <span
        className="flex h-14 w-40 items-center gap-2 rounded-lg border border-border bg-muted-foreground/5 px-3"
        title={`Chat history from ${title || 'an earlier session'}`}
      >
        <Split className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        <span className="flex min-w-0 flex-col text-left">
          <span className="truncate text-[11px] font-medium">{title || 'Chat history'}</span>
          <span className="text-[10px] text-muted-foreground">
            {messageCount} message{messageCount === 1 ? '' : 's'}
          </span>
        </span>
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="absolute -top-1.5 -right-1.5 flex h-5 w-5 cursor-pointer items-center justify-center rounded-full border border-border bg-background hover:bg-accent"
        title="Remove chat history"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
