'use client';

import { useCallback, useState } from 'react';
import { Check, Copy } from 'lucide-react';

/**
 * A shell one-liner with a copy button. Vicoa never runs installers itself —
 * this is the install affordance everywhere one is offered (onboarding's agent
 * scan, the Providers and Machines settings tabs).
 */
export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard can be blocked; the command stays selectable on screen.
    }
  }, [command]);

  return (
    <div className="flex items-center gap-2">
      <code className="min-w-0 flex-1 truncate rounded-md border border-border/60 bg-background px-2.5 py-1.5 font-mono text-[11px] text-muted-foreground">
        {command}
      </code>
      <button
        type="button"
        onClick={copy}
        aria-label={copied ? 'Copied' : 'Copy install command'}
        className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-border/70 px-2.5 py-1.5 text-[11px] font-medium text-foreground/80 transition-colors hover:border-foreground/40 hover:text-foreground"
      >
        {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
}
