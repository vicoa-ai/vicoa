'use client';

import { useState } from 'react';
import { Check, Copy, ExternalLink } from 'lucide-react';
import { Slot as SlotPrimitive } from 'radix-ui';
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

/** Space between the sidebar's right border and the panel. */
const EDGE_GAP = 6;

/**
 * How far right of the *row* the panel must sit to clear the *sidebar*.
 *
 * The row ends short of the sidebar's border — list padding, the scrollbar
 * (only while the list overflows), the border itself — so a fixed offset
 * would leave the panel wandering by a few pixels from one list to the next.
 * Both sidebar shells are an `<aside>`; without one, fall back to the row.
 */
function offsetToSidebarEdge(row: HTMLElement): number {
  const sidebar = row.closest('aside');
  if (!sidebar) return EDGE_GAP;
  const gap = sidebar.getBoundingClientRect().right - row.getBoundingClientRect().right;
  return Math.max(0, Math.round(gap)) + EDGE_GAP;
}

type TriggerProps = Omit<
  React.ComponentPropsWithRef<typeof SlotPrimitive.Slot>,
  'children'
>;

/**
 * Hover panel for a branch's pull request, opened by hovering its row.
 *
 * `children` is the row. With no PR it is rendered untouched — through a Slot,
 * so props an enclosing trigger merges in (the row's context menu) still land
 * on it — and the row keeps exactly its previous markup and gains no hover
 * behaviour.
 *
 * The panel opens beside the *sidebar*, not beside the row: it overlays the
 * content area to the right, so it never covers the sibling rows the user is
 * scanning, and every row's panel lands on the same vertical line.
 */
export function PrHoverCard({
  pr,
  branch,
  children,
  ...triggerProps
}: {
  pr: PrInfo | null | undefined;
  branch: string;
  children: React.ReactNode;
} & TriggerProps) {
  const [copied, setCopied] = useState(false);
  const [sideOffset, setSideOffset] = useState(EDGE_GAP);

  if (!pr) {
    return <SlotPrimitive.Slot {...triggerProps}>{children}</SlotPrimitive.Slot>;
  }

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
      <HoverCardTrigger asChild>
        <SlotPrimitive.Slot
          {...triggerProps}
          onPointerEnter={(event) => {
            triggerProps.onPointerEnter?.(event);
            setSideOffset(offsetToSidebarEdge(event.currentTarget));
          }}
          // The row holds buttons (collapse, "+", "⋯"), and Chromium focuses a
          // button on click. Left to Radix, focus would open the panel and blur
          // close it — so clicking the row and then a panel button would blur
          // the row and snap the panel shut under the cursor. preventDefault is
          // Radix's documented opt-out from its own handler; the panel stays
          // pointer-only, as it was when the icon alone was the trigger.
          onFocus={(event) => {
            triggerProps.onFocus?.(event);
            event.preventDefault();
          }}
          onBlur={(event) => {
            triggerProps.onBlur?.(event);
            event.preventDefault();
          }}
        >
          {children}
        </SlotPrimitive.Slot>
      </HoverCardTrigger>
      <HoverCardContent
        side="right"
        align="start"
        // Lifts the panel so its first line sits level with the row's text
        // instead of its top edge meeting the row's top edge.
        alignOffset={-11}
        sideOffset={sideOffset}
        collisionPadding={8}
        className="w-72 p-3"
        // Portaled, but React events still bubble up the component tree — into
        // the row's context-menu trigger. Without this, a right-click inside
        // the panel would open the worktree's Delete menu.
        onContextMenu={(event) => event.stopPropagation()}
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
