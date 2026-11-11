'use client';

/**
 * The host's right-hand peek panel: a task or a session, next to the page
 * that asked for it, without leaving that page.
 *
 * It pushes the page narrower rather than covering it, and its width is the
 * user's: drag the separator (min 360px, max 60% of the space), double-click
 * it to reset. When opened with siblings (the list it came from), it shows
 * "n of N", J/K step through them, and handing a task back moves on to the
 * next one. Esc closes.
 *
 * Generic: plugin pages drive it through `vicoa.open.*`, and a host page can
 * use it the same way through `usePeekPanel`.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { TaskDetail } from '@/app/dashboard/tasks/[taskId]/task-detail';
import { SessionPeek } from './session-peek';

export type PeekKind = 'task' | 'session';

export interface PeekItem {
  kind: PeekKind;
  id: string;
  /** The list it was opened from, in order; J/K move through it. */
  siblings: string[];
}

export const PEEK_MIN_WIDTH = 360;
export const PEEK_DEFAULT_WIDTH = 460;
const PEEK_MAX_FRACTION = 0.6;
const WIDTH_KEY = 'vicoa.peek-panel-width';

export function clampPeekWidth(width: number, containerWidth: number): number {
  const max = Math.max(PEEK_MIN_WIDTH, Math.floor(containerWidth * PEEK_MAX_FRACTION));
  return Math.min(max, Math.max(PEEK_MIN_WIDTH, Math.round(width)));
}

/** Panel state for a page: what is open, plus J/K over its siblings. */
export function usePeekPanel(onChange?: (item: PeekItem | null) => void) {
  const [item, setItem] = useState<PeekItem | null>(null);
  const itemRef = useRef<PeekItem | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const set = useCallback((next: PeekItem | null) => {
    itemRef.current = next;
    setItem(next);
    onChangeRef.current?.(next);
  }, []);

  const open = useCallback(
    (kind: PeekKind, id: string, siblings: string[] = []) =>
      set({ kind, id, siblings: siblings.includes(id) ? siblings : [] }),
    [set],
  );

  const step = useCallback(
    (delta: 1 | -1) => {
      const cur = itemRef.current;
      if (!cur || cur.siblings.length < 2) return;
      const nextId = cur.siblings[cur.siblings.indexOf(cur.id) + delta];
      if (nextId) set({ ...cur, id: nextId });
    },
    [set],
  );

  return { item, open, close: useCallback(() => set(null), [set]), step };
}

const isTyping = (el: Element | null) =>
  !!el &&
  (el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement ||
    (el as HTMLElement).isContentEditable ||
    el.tagName === 'IFRAME');

/**
 * Lays out `children` (the page) with the panel to its right when an item is
 * open. The page keeps its own scrolling; the panel scrolls on its own.
 */
export function PeekLayout({
  item,
  onOpen,
  onClose,
  onStep,
  children,
}: {
  item: PeekItem | null;
  /** Open something else in the panel (a session linked from a task). */
  onOpen: (kind: PeekKind, id: string) => void;
  onClose: () => void;
  onStep: (delta: 1 | -1) => void;
  children: ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const [width, setWidth] = useState(PEEK_DEFAULT_WIDTH);
  const liveWidth = useRef(width);
  const [title, setTitle] = useState<string | null>(null);

  useEffect(() => {
    const saved = Number.parseInt(window.localStorage.getItem(WIDTH_KEY) ?? '', 10);
    if (Number.isFinite(saved)) {
      const w = clampPeekWidth(saved, containerRef.current?.clientWidth ?? window.innerWidth);
      liveWidth.current = w;
      setWidth(w);
    }
  }, []);

  // A newly opened item takes keyboard focus, so J/K/Esc work at once even
  // when the click that opened it landed inside a plugin's iframe.
  const itemKey = item ? `${item.kind}:${item.id}` : null;
  useEffect(() => {
    setTitle(null);
    if (itemKey) panelRef.current?.focus({ preventScroll: true });
  }, [itemKey]);

  useEffect(() => {
    if (!item) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
      if (e.key === 'Escape') {
        // Leave Esc to an open dialog or popover first.
        if (document.querySelector('[role="dialog"], [data-radix-popper-content-wrapper]')) return;
        onClose();
        return;
      }
      if (isTyping(document.activeElement)) return;
      if (e.key === 'j' || e.key === 'J') onStep(1);
      if (e.key === 'k' || e.key === 'K') onStep(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [item, onClose, onStep]);

  const startResize = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = liveWidth.current;
    const containerWidth = containerRef.current?.clientWidth ?? window.innerWidth;
    // An iframe under the pointer (a plugin page) would swallow the mouse
    // events and stall the drag, so frames ignore the pointer until mouseup.
    // Nothing covers the separator, so a double-click still reaches it.
    const frames = Array.from(containerRef.current?.querySelectorAll('iframe') ?? []);
    for (const f of frames) f.style.pointerEvents = 'none';
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    let moved = false;
    const onMove = (ev: MouseEvent) => {
      if (!moved && Math.abs(ev.clientX - startX) < 3) return;
      moved = true;
      const next = clampPeekWidth(startWidth - (ev.clientX - startX), containerWidth);
      liveWidth.current = next;
      if (panelRef.current) panelRef.current.style.width = `${next}px`;
    };
    const onUp = () => {
      for (const f of frames) f.style.pointerEvents = '';
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      if (!moved) return;
      setWidth(liveWidth.current);
      window.localStorage.setItem(WIDTH_KEY, String(liveWidth.current));
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  const resetWidth = () => {
    const w = clampPeekWidth(PEEK_DEFAULT_WIDTH, containerRef.current?.clientWidth ?? window.innerWidth);
    liveWidth.current = w;
    if (panelRef.current) panelRef.current.style.width = `${w}px`;
    setWidth(w);
    window.localStorage.removeItem(WIDTH_KEY);
  };

  const index = item ? item.siblings.indexOf(item.id) : -1;
  const count = item?.siblings.length ?? 0;

  const handedBack = () => {
    if (item && index >= 0 && index < count - 1) onStep(1);
  };

  return (
    <div ref={containerRef} className="flex h-full min-w-0 flex-1 overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
      {item ? (
        <>
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize panel"
            title="Drag to resize, double-click to reset"
            onMouseDown={startResize}
            onDoubleClick={resetWidth}
            className="group relative z-10 w-1.5 shrink-0 cursor-col-resize"
          >
            <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors group-hover:bg-muted-foreground/60" />
          </div>
          <aside
            ref={panelRef}
            tabIndex={-1}
            aria-label={item.kind === 'task' ? 'Task' : 'Session'}
            style={{ width }}
            className="flex h-full shrink-0 flex-col bg-background outline-none"
          >
            <div className="flex h-11 shrink-0 items-center gap-1 border-b border-border/60 px-3">
              <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                {count > 1 && index >= 0 ? `${index + 1} of ${count}` : item.kind === 'task' ? 'Task' : 'Session'}
                {title ? ` · ${title}` : ''}
              </span>
              {count > 1 ? (
                <>
                  <PanelButton label="Previous (K)" disabled={index <= 0} onClick={() => onStep(-1)}>
                    <ChevronUp className="size-4" />
                  </PanelButton>
                  <PanelButton label="Next (J)" disabled={index < 0 || index >= count - 1} onClick={() => onStep(1)}>
                    <ChevronDown className="size-4" />
                  </PanelButton>
                </>
              ) : null}
              <PanelButton label="Close (Esc)" onClick={onClose}>
                <X className="size-4" />
              </PanelButton>
            </div>
            <div className={cn('custom-scrollbar min-h-0 flex-1 overflow-y-auto')}>
              {item.kind === 'task' ? (
                <TaskDetail
                  taskId={item.id}
                  variant="panel"
                  className="px-5 py-4"
                  onHandedBack={handedBack}
                  onOpenSession={(id) => onOpen('session', id)}
                  onLoaded={(t) => setTitle(t.identifier ?? null)}
                />
              ) : (
                <SessionPeek sessionId={item.id} />
              )}
            </div>
          </aside>
        </>
      ) : null}
    </div>
  );
}

function PanelButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-7 w-7 p-0 text-muted-foreground"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}
