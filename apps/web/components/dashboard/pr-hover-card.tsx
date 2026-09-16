'use client';

import { useState } from 'react';
import { Check, Copy, ExternalLink } from 'lucide-react';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';
import { cn } from '@/lib/utils';
import { openExternalUrl } from '@/lib/open-external';
import {
  checksDotClassName,
  checksLabel,
  prPresentation,
  type PrInfo,
} from '@/components/dashboard/pr-status';

/**
 * Hover panel for a branch's pull request, opened from the branch icon.
 *
 * Renders `children` untouched when there is no PR, so a row without one keeps
 * exactly its previous markup and gains no hover behaviour.
 *
 * Opens to the side rather than below: these triggers sit in a dense list of
 * rows, and a panel dropping downward would cover the very sibling branches the
 * user is scanning.
 */
export function PrHoverCard({
  pr,
  branch,
  children,
}: {
  pr: PrInfo | null | undefined;
  branch: string;
  children: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);

  if (!pr) return <>{children}</>;

  const { icon: StateIcon, className: stateClassName, label: stateLabel } =
    prPresentation(pr);
  const dot = checksDotClassName(pr);
  const checks = checksLabel(pr);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(pr.url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be denied (insecure origin, browser policy). The link is
      // still reachable through "Open", so a failure needs no error surface.
    }
  };

  return (
    <HoverCard openDelay={300} closeDelay={150}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent
        side="right"
        align="start"
        sideOffset={8}
        className="w-72 p-3"
        // The trigger lives inside the row's collapse button; without this a
        // click landing on the panel would toggle the group behind it.
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-1.5">
          <StateIcon className={cn('h-3.5 w-3.5 shrink-0', stateClassName)} />
          <span className={cn('text-xs font-medium', stateClassName)}>{stateLabel}</span>
          <span className="text-xs text-muted-foreground">#{pr.number}</span>
          {dot && checks && (
            <span className="ml-auto flex items-center gap-1">
              <span className={cn('h-1.5 w-1.5 rounded-full', dot)} />
              <span className="text-[11px] text-muted-foreground">{checks}</span>
            </span>
          )}
        </div>

        <p className="mt-2 line-clamp-3 text-xs leading-snug text-foreground">
          {pr.title}
        </p>

        <p className="mt-1.5 truncate font-mono text-[11px] text-muted-foreground">
          {branch}
        </p>

        <div className="mt-3 flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => openExternalUrl(pr.url)}
            className="flex flex-1 cursor-pointer items-center justify-center gap-1.5 rounded border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ExternalLink className="h-3 w-3" />
            Open
          </button>
          <button
            type="button"
            onClick={copyLink}
            aria-label="Copy pull request link"
            className="flex flex-1 cursor-pointer items-center justify-center gap-1.5 rounded border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            {copied ? 'Copied' : 'Copy link'}
          </button>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
