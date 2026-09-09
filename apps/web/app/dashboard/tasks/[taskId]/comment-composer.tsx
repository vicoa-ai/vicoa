'use client';

// The task-detail comment box. Deliberately the same object as the session
// composer (`components/chat-input.tsx`): same `bg-composer` surface, same
// `border-border/50`, same auto-growing textarea, same round 28px send button
// with an ArrowUp. Two boxes that take typed text and send it should not be two
// different-looking controls in one product.
//
// It corners tighter than the chat composer (`rounded-xl`, not `rounded-3xl`).
// The chat box is that page's primary affordance and sits alone above the
// fold; this one ends a column of square-ish cards, where a pill silhouette
// reads as a different kind of object than the things it is answering.
//
// What it deliberately does NOT inherit: attachments, slash commands, the
// config chips and the usage ring. Those address an agent session; a comment
// has no model, no permission mode and no rate limit.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const MIN_HEIGHT = 36;
const MAX_HEIGHT = 200;

export function CommentComposer({
  onSubmit,
  disabled = false,
  placeholder = 'Leave a comment…',
  autoFocus = false,
  className,
}: {
  onSubmit: (body: string) => Promise<void>;
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
}) {
  const [value, setValue] = useState('');
  const [sending, setSending] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Same rAF-coalesced auto-resize as the chat composer: reading scrollHeight
  // after writing height='auto' forces a synchronous layout, so collapse a
  // burst of keystrokes into one reflow per frame.
  const frameRef = useRef<number | null>(null);
  const autoResize = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = 'auto';
      el.style.height = `${Math.max(MIN_HEIGHT, Math.min(el.scrollHeight, MAX_HEIGHT))}px`;
    });
  }, []);

  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  const send = useCallback(async () => {
    const body = value.trim();
    if (!body || sending || disabled) return;
    setSending(true);
    try {
      await onSubmit(body);
      setValue('');
      const el = textareaRef.current;
      if (el) el.style.height = `${MIN_HEIGHT}px`;
    } finally {
      setSending(false);
    }
  }, [value, sending, disabled, onSubmit]);

  return (
    <div
      className={cn(
        'relative w-full rounded-xl border border-border/50 bg-composer px-3 py-2.5 font-mono shadow-sm',
        className,
      )}
    >
      {/* No author avatar. Every timeline row above needs one because it says
          *who* — but there is only one person who can be typing here, and their
          own face is not information. It was just an indent. */}
      <div className="flex items-start gap-2">
        <textarea
          ref={textareaRef}
          value={value}
          autoFocus={autoFocus}
          onChange={(e) => {
            setValue(e.target.value);
            autoResize();
          }}
          onKeyDown={(e) => {
            // Enter sends, Shift+Enter breaks the line — the same contract the
            // session composer teaches.
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
            if (e.key === 'Escape') {
              e.preventDefault();
              textareaRef.current?.blur();
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          style={{ height: MIN_HEIGHT, minHeight: MIN_HEIGHT, maxHeight: MAX_HEIGHT }}
          className="custom-scrollbar w-full resize-none border-0 bg-transparent px-1 py-2 text-sm leading-5 placeholder:text-muted-foreground/50 focus:outline-none focus:ring-0 disabled:cursor-not-allowed disabled:opacity-50"
        />
      </div>
      <div className="flex items-center justify-end">
        <Button
          onClick={() => void send()}
          aria-label="Post comment"
          disabled={disabled || sending || value.trim().length === 0}
          variant="default"
          size="icon"
          className="h-7 w-7 shrink-0 rounded-full border-0 p-0 focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0"
        >
          {sending ? (
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ArrowUp className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>
    </div>
  );
}
