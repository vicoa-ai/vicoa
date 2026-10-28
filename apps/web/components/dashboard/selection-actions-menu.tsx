'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Copy, MessageCirclePlus, MessageSquareQuote } from 'lucide-react';
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover';
import { AnnotationCommentField } from '@/components/dashboard/annotation-comment-field';
import { normalizeSelectedText } from '@/lib/chat-annotations';

/** CSS Custom Highlight name for the passage a comment is being written for. */
const SOURCE_HIGHLIGHT = 'vicoa-annotation-source';

/**
 * Its style ships with the component rather than in app/globals.css: the CSS
 * parser Next runs over stylesheets rejects `::highlight()` and fails the whole
 * file. A React 19 `<style href precedence>` is hoisted into <head> once and
 * never goes through that parser.
 */
const SOURCE_HIGHLIGHT_CSS = `::highlight(${SOURCE_HIGHLIGHT}) { background-color: hsl(var(--primary) / 0.18); }`;

/** Quiet period after the last `selectionchange` before a keyboard or touch selection opens the menu. */
const SELECTION_SETTLE_MS = 200;

const EDITABLE_SELECTOR = 'input, textarea, select, [contenteditable=""], [contenteditable="true"]';

const ITEM_CLASS =
  'flex w-full cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-foreground/[0.06] focus-visible:bg-foreground/[0.06] dark:hover:bg-foreground/10 dark:focus-visible:bg-foreground/10 [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground';

interface VirtualAnchor {
  getBoundingClientRect: () => DOMRect;
  /** Lets floating-ui follow the scroller this element sits in. */
  contextElement?: Element;
}

interface SelectionSnapshot {
  /** Exactly what was selected, for Copy. */
  raw: string;
  /** Normalised and clamped, for the annotation. */
  quote: string;
  range: Range;
  backward: boolean;
}

function isBackward(selection: Selection): boolean {
  const { anchorNode, focusNode } = selection;
  if (!anchorNode || !focusNode) return false;
  if (anchorNode === focusNode) return selection.focusOffset < selection.anchorOffset;
  return !!(anchorNode.compareDocumentPosition(focusNode) & Node.DOCUMENT_POSITION_PRECEDING);
}

function elementOf(node: Node): Element | null {
  return node instanceof Element ? node : node.parentElement;
}

/**
 * A zero-width rect at the end the pointer finished on, so the menu opens
 * where the drag stopped: under the last line of a forward drag, above the
 * first line of a backward one. Null once the range has nothing on screen.
 */
function focusEdgeRect(range: Range, backward: boolean): DOMRect | null {
  if (range.collapsed || !range.startContainer.isConnected) return null;
  const rects = Array.from(range.getClientRects()).filter((r) => r.width > 0 || r.height > 0);
  if (rects.length === 0) return null;
  const edge = backward ? rects[0] : rects[rects.length - 1];
  return new DOMRect(backward ? edge.left : edge.right, edge.top, 0, edge.height);
}

function setSourceHighlight(range: Range | null): void {
  if (typeof CSS === 'undefined' || !('highlights' in CSS) || typeof Highlight === 'undefined') return;
  if (range) CSS.highlights.set(SOURCE_HIGHLIGHT, new Highlight(range));
  else CSS.highlights.delete(SOURCE_HIGHLIGHT);
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Clipboard API blocked (insecure context, denied permission): the
    // selection is still live in the document, so the legacy path copies it.
    document.execCommand('copy');
  }
}

/**
 * The menu that opens on a text selection in the transcript: Copy, Add to
 * chat and Continue in new session.
 *
 * Add to chat puts the passage in the composer at once, then turns the menu
 * into the one-line comment field (annotation-comment-field.tsx): ⏎ adds the
 * comment, ⌘⏎ (Ctrl⏎) adds it and sends the message. Leaving the field
 * another way keeps the annotation; a click elsewhere keeps the typed
 * comment, Esc drops it.
 *
 * It reads the selection, never steers it: the transcript already patches two
 * Blink drag-selection quirks (lib/selection-drag-fix.ts), so this only
 * listens, after the gesture has finished. The text and range are captured
 * when the menu opens because Virtuoso unmounts rows that scroll far enough
 * away, and a click on a menu row must not collapse the selection first. While
 * the comment field has focus the native selection is gone, so the passage
 * stays marked with a CSS Custom Highlight instead.
 *
 * Omit `onAddToChat` / `onContinueInNewSession` to hide those rows.
 */
export function SelectionActionsMenu({
  getContainer,
  onAddToChat,
  onCommentAnnotation,
  onContinueInNewSession,
}: {
  /** The transcript scroller; selections outside it are ignored. */
  getContainer: () => HTMLElement | null;
  /** Add the passage to the composer; returns the annotation's id, or null if it couldn't. */
  onAddToChat?: (quote: string) => string | null;
  /** Comment on the annotation just added; `send` sends the message too. */
  onCommentAnnotation?: (id: string, comment: string, send: boolean) => void;
  onContinueInNewSession?: (quote: string) => void;
}) {
  const [snapshot, setSnapshot] = useState<SelectionSnapshot | null>(null);
  // Set once the passage is in the composer: the menu is the comment field.
  const [annotationId, setAnnotationId] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const annotationIdRef = useRef(annotationId);
  annotationIdRef.current = annotationId;
  const commentRef = useRef(comment);
  commentRef.current = comment;
  const snapshotRef = useRef(snapshot);
  snapshotRef.current = snapshot;
  const contentRef = useRef<HTMLDivElement>(null);
  const lastRectRef = useRef<DOMRect>(new DOMRect());
  const anchorRef = useRef<VirtualAnchor>({ getBoundingClientRect: () => lastRectRef.current });

  const close = useCallback(() => {
    setSnapshot(null);
    setAnnotationId(null);
    setComment('');
    setSourceHighlight(null);
  }, []);

  // Open on (or follow) the current selection if it is transcript text;
  // otherwise drop a menu that is only offering actions.
  const evaluate = useCallback(() => {
    if (annotationIdRef.current) return;
    const container = getContainer();
    const selection = window.getSelection();
    const range = selection && selection.rangeCount > 0 && !selection.isCollapsed ? selection.getRangeAt(0) : null;
    const host = range ? elementOf(range.commonAncestorContainer) : null;
    // A selection inside a text field reports the field's parent as its host,
    // so the focused element is what tells the two apart.
    const active = document.activeElement;
    const inField = !!host?.closest(EDITABLE_SELECTOR) || (active instanceof Element && active.matches(EDITABLE_SELECTOR));
    const raw = selection?.toString() ?? '';
    const quote = normalizeSelectedText(raw);
    if (!selection || !range || !container || !host || !container.contains(host) || inField || !quote) {
      if (snapshotRef.current) close();
      return;
    }
    const backward = isBackward(selection);
    const kept = range.cloneRange();
    lastRectRef.current = focusEdgeRect(kept, backward) ?? lastRectRef.current;
    anchorRef.current = {
      getBoundingClientRect: () => {
        const live = focusEdgeRect(kept, backward);
        if (live) lastRectRef.current = live;
        return lastRectRef.current;
      },
      contextElement: elementOf(kept.startContainer) ?? undefined,
    };
    setSourceHighlight(null);
    setSnapshot({ raw, quote, range: kept, backward });
  }, [getContainer, close]);

  useEffect(() => {
    let pointerDown = false;
    let settleTimer: ReturnType<typeof setTimeout> | null = null;
    const insideMenu = (target: EventTarget | null) =>
      target instanceof Node && !!contentRef.current?.contains(target);

    const onPointerDown = (event: PointerEvent) => {
      if (!insideMenu(event.target)) pointerDown = true;
    };
    const onPointerUp = (event: PointerEvent) => {
      if (!pointerDown) return;
      pointerDown = false;
      if (insideMenu(event.target)) return;
      // The selection settles after the gesture's own handlers have run.
      setTimeout(evaluate, 0);
    };
    // Keyboard extension (shift+arrows) and touch selection handles move the
    // selection with no pointer gesture to end on; wait for them to settle.
    const onSelectionChange = () => {
      if (pointerDown) return;
      if (settleTimer) clearTimeout(settleTimer);
      settleTimer = setTimeout(evaluate, SELECTION_SETTLE_MS);
    };

    document.addEventListener('pointerdown', onPointerDown, true);
    document.addEventListener('pointerup', onPointerUp, true);
    document.addEventListener('pointercancel', onPointerUp, true);
    document.addEventListener('selectionchange', onSelectionChange);
    return () => {
      if (settleTimer) clearTimeout(settleTimer);
      document.removeEventListener('pointerdown', onPointerDown, true);
      document.removeEventListener('pointerup', onPointerUp, true);
      document.removeEventListener('pointercancel', onPointerUp, true);
      document.removeEventListener('selectionchange', onSelectionChange);
    };
  }, [evaluate]);

  useEffect(() => () => setSourceHighlight(null), []);

  const handleCopy = useCallback(() => {
    const current = snapshotRef.current;
    if (!current) return;
    void copyText(current.raw);
    close();
  }, [close]);

  const handleAddToChat = useCallback(() => {
    const current = snapshotRef.current;
    if (!current || !onAddToChat) return;
    const id = onAddToChat(current.quote);
    if (!id) {
      close();
      return;
    }
    setSourceHighlight(current.range);
    setAnnotationId(id);
  }, [onAddToChat, close]);

  const submitComment = useCallback(
    (send: boolean) => {
      const id = annotationIdRef.current;
      if (id && (send || commentRef.current.trim())) onCommentAnnotation?.(id, commentRef.current, send);
      window.getSelection()?.removeAllRanges();
      close();
    },
    [onCommentAnnotation, close],
  );

  const handleContinue = useCallback(() => {
    const current = snapshotRef.current;
    if (!current || !onContinueInNewSession) return;
    close();
    onContinueInNewSession(current.quote);
  }, [onContinueInNewSession, close]);

  return (
    <Popover
      open={!!snapshot}
      onOpenChange={(open) => {
        if (open) return;
        // A click elsewhere: the annotation is already in, keep what was typed.
        // The selection is left alone, since that click may be starting a new one.
        const id = annotationIdRef.current;
        if (id && commentRef.current.trim()) onCommentAnnotation?.(id, commentRef.current, false);
        close();
      }}
    >
      <style href="vicoa-annotation-source-highlight" precedence="default">
        {SOURCE_HIGHLIGHT_CSS}
      </style>
      <PopoverAnchor virtualRef={anchorRef} />
      {/* Unmounted, not animated out: after Copy or Continue the menu has to
          be gone at once, not fade over the text it just acted on. */}
      {snapshot && (
        <PopoverContent
          ref={contentRef}
          side={snapshot.backward ? 'top' : 'bottom'}
          align="start"
          sideOffset={6}
          collisionPadding={8}
          hideWhenDetached
          // Focus stays in the transcript so the selection stays painted; the
          // comment field takes focus itself when it mounts.
          onOpenAutoFocus={(e) => e.preventDefault()}
          onCloseAutoFocus={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => {
            // Esc drops the comment; the annotation stays in the composer.
            if (!annotationIdRef.current) return;
            e.preventDefault();
            close();
          }}
          className={
            annotationId
              ? 'w-80 rounded-full border-0 bg-transparent p-0 shadow-none'
              : 'w-auto min-w-[12rem] bg-menu p-1 text-menu-foreground'
          }
        >
          {annotationId ? (
            <AnnotationCommentField
              value={comment}
              onChange={setComment}
              onSubmit={submitComment}
              submitLabel="Add"
              sendable
              className="shadow-lg"
            />
          ) : (
            // A press on a row must not collapse the selection before the click
            // lands (and the legacy copy fallback needs it live).
            <div role="menu" aria-label="Selection actions" onMouseDown={(e) => e.preventDefault()}>
              <button type="button" role="menuitem" onClick={handleCopy} className={ITEM_CLASS}>
                <Copy />
                Copy
              </button>
              {onAddToChat && (
                <button type="button" role="menuitem" onClick={handleAddToChat} className={ITEM_CLASS}>
                  <MessageSquareQuote />
                  Add to chat
                </button>
              )}
              {onContinueInNewSession && (
                <button type="button" role="menuitem" onClick={handleContinue} className={ITEM_CLASS}>
                  <MessageCirclePlus />
                  Continue in new session
                </button>
              )}
            </div>
          )}
        </PopoverContent>
      )}
    </Popover>
  );
}
