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
//
// Two variants. `default` is the box at the foot of the page that starts a new
// thread. `inline` is the "Leave a reply…" row that ends every thread card:
// borderless, one line tall, and it takes an avatar — inside a thread the
// avatar is not decoration, it holds the row on the same column as the comments
// above it and marks the box as part of that conversation rather than a control
// floating under it.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const MIN_HEIGHT = 36;
// The inline reply row is one line tall at rest so a thread ends in a hint, not
// in a second composer competing with the page's own.
const INLINE_HEIGHT = 28;
const MAX_HEIGHT = 200;

export function CommentComposer({
  onSubmit,
  disabled = false,
  placeholder = 'Leave a comment…',
  autoFocus = false,
  variant = 'default',
  leading,
  className,
}: {
  onSubmit: (body: string) => Promise<void>;
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  /** `inline` is the reply row inside a thread card; see the header comment. */
  variant?: 'default' | 'inline';
  /** Rendered left of the textarea — the viewer's avatar, on `inline`. */
  leading?: React.ReactNode;
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
      const floor = variant === 'inline' ? INLINE_HEIGHT : MIN_HEIGHT;
      el.style.height = `${Math.max(floor, Math.min(el.scrollHeight, MAX_HEIGHT))}px`;
    });
  }, [variant]);

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
      if (el) el.style.height = `${variant === 'inline' ? INLINE_HEIGHT : MIN_HEIGHT}px`;
    } finally {
      setSending(false);
    }
  }, [value, sending, disabled, onSubmit, variant]);

  const inline = variant === 'inline';
  const empty = value.trim().length === 0;

  return (
    <div
      className={cn(
        'relative w-full font-mono',
        // The inline row has no edge of its own: the thread card is already a
        // surface, and a second border inside it reads as a nested object.
        inline
          ? 'flex items-center gap-2'
          : 'rounded-xl border border-border/50 bg-composer px-3 py-2.5 shadow-sm',
        className,
      )}
    >
      {/* The page-bottom variant carries no avatar: only one person can be
          typing there, and their own face is not information — it was just an
          indent. Inside a thread it earns its place (see the header). */}
      {inline && leading}
      <div className={cn(inline ? 'min-w-0 flex-1' : 'flex items-start gap-2')}>
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
          style={{
            height: inline ? INLINE_HEIGHT : MIN_HEIGHT,
            minHeight: inline ? INLINE_HEIGHT : MIN_HEIGHT,
            maxHeight: MAX_HEIGHT,
          }}
          className={cn(
            // `block` is load-bearing, not tidiness: a textarea is inline-block
            // by default, so inside the inline variant's plain wrapper it sits
            // on a text baseline and leaves ~4px of descender space beneath
            // itself. That makes the wrapper taller than the box, and the row's
            // items-center then centres the *wrapper* — dropping the avatar a
            // couple of pixels below the caret. (The default variant's wrapper
            // is a flex container, which blockifies its children already.)
            'custom-scrollbar block w-full resize-none border-0 bg-transparent text-sm leading-5 placeholder:text-muted-foreground/50 focus:outline-none focus:ring-0 disabled:cursor-not-allowed disabled:opacity-50',
            inline ? 'py-1' : 'px-1 py-2',
          )}
        />
      </div>
      <div className={cn('flex items-center justify-end', !inline && 'mt-0')}>
        <Button
          onClick={() => void send()}
          aria-label={inline ? 'Post reply' : 'Post comment'}
          disabled={disabled || sending || empty}
          variant="default"
          size="icon"
          className={cn(
            'shrink-0 rounded-full border-0 p-0 focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0',
            // Ghosted until there is something to send, so an idle thread ends
            // in an invitation rather than in a row of dead buttons.
            inline ? 'h-6 w-6 transition-opacity' : 'h-7 w-7',
            inline && empty && !sending && 'pointer-events-none opacity-30',
          )}
        >
          {sending ? (
            <RefreshCw className={cn('animate-spin', inline ? 'h-3 w-3' : 'h-3.5 w-3.5')} />
          ) : (
            <ArrowUp className={cn(inline ? 'h-3 w-3' : 'h-3.5 w-3.5')} />
          )}
        </Button>
      </div>
    </div>
  );
}
