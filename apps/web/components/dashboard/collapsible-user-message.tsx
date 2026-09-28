'use client';

import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronsDown, ChevronsUp } from 'lucide-react';

// User messages can be arbitrarily long (pasted logs, specs, stack traces).
// Collapse ones taller than COLLAPSED_MAX_HEIGHT_PX behind a bottom fade + a
// chevron toggle — the web port of the mobile app's _CollapsibleUserMessage.
// Only the text body collapses; the fade blends into the user bubble's
// `bg-muted` background. ~250px ≈ 10 lines at text-sm/leading-relaxed.
const COLLAPSED_MAX_HEIGHT_PX = 250;

export function CollapsibleUserMessage({ children }: { children: ReactNode }) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [isOverflow, setIsOverflow] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  // A layout effect, not a passive one: the first measurement must collapse
  // the bubble before the browser lays it out for paint. Measured after paint,
  // the row mounts at full height and shrinks a frame later — and the
  // transcript's Virtuoso list reacts to that resize. When the bubble sits at
  // the edge of Virtuoso's overscan band, the shrink scrolls it back out of the
  // band (unmount), it re-enters at full height (remount), and the list flips
  // between two scroll positions every frame.
  useLayoutEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    // The inner div is never height-constrained (the parent clips), so its
    // scrollHeight is always the content's natural height.
    const measure = () => setIsOverflow(el.scrollHeight > COLLAPSED_MAX_HEIGHT_PX + 1);
    measure();
    // Re-measure on reflow (panel resize changing bubble width, late content).
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [children]);

  const collapsed = isOverflow && !isExpanded;

  return (
    <div>
      <div
        className="relative overflow-hidden"
        style={collapsed ? { maxHeight: COLLAPSED_MAX_HEIGHT_PX } : undefined}
      >
        <div ref={contentRef}>{children}</div>
        {collapsed && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-b from-transparent to-muted" />
        )}
      </div>
      {isOverflow && (
        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex w-full items-center justify-center py-1 text-muted-foreground transition-colors hover:text-foreground"
          aria-label={isExpanded ? 'Collapse message' : 'Expand message'}
        >
          {isExpanded ? <ChevronsUp className="h-4 w-4" /> : <ChevronsDown className="h-4 w-4" />}
        </button>
      )}
    </div>
  );
}
