'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { Check, Copy, Split } from 'lucide-react';
import { formatDateGroup, parseUTCTimestamp } from '@/lib/message-grouping';

/**
 * Local time for the message footer — bare "10:30 AM" today, and widening to
 * "Yesterday …" / "Jan 15, …" / "Jan 15, 2024, …" as the message ages. Shares
 * the date separators' formatter so both read alike.
 */
export function formatMessageTime(timestamp: string): string {
  if (!timestamp) return '';
  const date = parseUTCTimestamp(timestamp);
  if (Number.isNaN(date.getTime())) return '';
  return formatDateGroup(date);
}

const ACTION_BUTTON_CLASS =
  'cursor-pointer rounded p-1 text-muted-foreground/70 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring';

/**
 * Hover-revealed footer under a chat bubble: copy, fork (agent turns only) and
 * the message's time.
 *
 * Absolutely positioned, so it costs the transcript no vertical space at all —
 * reserving a row for it pushed every message 24px apart, and letting it into
 * the flow only on hover would make Virtuoso re-measure and shift rows under
 * the cursor. The trade-off is that it floats over the top of the next row
 * while visible, hence the toolbar chrome (surface + hairline + shadow) and the
 * z-index. Requires a `relative` parent carrying `group/message`.
 */
export const MessageActions = memo(function MessageActions({
  timestamp,
  text,
  onFork,
  align,
}: {
  timestamp: string;
  /** Text put on the clipboard — the message as rendered, not the raw payload. */
  text: string;
  /** Omitted for user messages: a fork always resumes from an agent turn. */
  onFork?: () => void;
  align: 'left' | 'right';
}) {
  const [copied, setCopied] = useState(false);
  const resetRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (resetRef.current) clearTimeout(resetRef.current);
  }, []);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (resetRef.current) clearTimeout(resetRef.current);
      resetRef.current = setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard can be blocked (insecure context / denied permission); the
      // message stays selectable on screen.
    }
  }, [text]);

  // An image-only message has no text to copy — it still gets a time.
  const copyButton = text.trim() ? (
    <button
      type="button"
      onClick={handleCopy}
      title={copied ? 'Copied' : 'Copy message'}
      aria-label={copied ? 'Copied' : 'Copy message'}
      className={ACTION_BUTTON_CLASS}
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  ) : null;

  const forkButton = onFork ? (
    <button
      type="button"
      onClick={onFork}
      title="Fork into a new session from here"
      aria-label="Fork into a new session from here"
      className={ACTION_BUTTON_CLASS}
    >
      <Split className="h-3.5 w-3.5" />
    </button>
  ) : null;

  const time = (
    <span className="px-1 font-mono text-[11px] text-muted-foreground/60">
      {formatMessageTime(timestamp)}
    </span>
  );

  return (
    <div
      className={`absolute top-full z-10 mt-0.5 flex items-center gap-0.5 rounded-md border border-border/60 bg-background px-0.5 shadow-sm pointer-events-none opacity-0 transition-opacity duration-150 group-hover/message:pointer-events-auto group-hover/message:opacity-100 focus-within:pointer-events-auto focus-within:opacity-100 ${
        align === 'right' ? 'right-2' : 'left-2'
      }`}
    >
      {/* Mirrored around the bubble's edge: the icons sit outermost either way,
          so a user row reads "time, copy" and an agent row "copy, fork, time". */}
      {align === 'right' ? (
        <>
          {time}
          {copyButton}
          {forkButton}
        </>
      ) : (
        <>
          {copyButton}
          {forkButton}
          {time}
        </>
      )}
    </div>
  );
});
