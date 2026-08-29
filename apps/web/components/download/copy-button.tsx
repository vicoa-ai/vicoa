'use client';

import { useState } from 'react';
import posthog from 'posthog-js';
import { Check, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';

type CopyButtonProps = {
  value: string;
  /** posthog event label, e.g. "cli_install" */
  event?: string;
  className?: string;
  label?: string;
  /** Drop the text and render just the glyph — for use inside a command block. */
  iconOnly?: boolean;
};

/**
 * Small clipboard button used by the download-page install blocks. Shows a
 * transient check-mark on success and reports a posthog event so we can see
 * which install command people actually copy.
 */
export function CopyButton({
  value,
  event,
  className,
  label = 'Copy',
  iconOnly = false,
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      if (event) posthog.capture('download_copy', { target: event });
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard can be blocked (insecure context, permissions). Fail quietly;
      // the command text is still visible for a manual copy.
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? 'Copied' : label}
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 rounded-md text-xs font-medium text-foreground/80 transition-colors hover:text-foreground',
        iconOnly
          ? 'p-1'
          : 'border border-border/70 bg-background px-3 py-1.5 hover:border-foreground/40',
        className
      )}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
      {!iconOnly && (copied ? 'Copied' : label)}
    </button>
  );
}
