'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageSquareQuote, Pencil, Trash2, X } from 'lucide-react';
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover';
import { AnnotationCommentField } from '@/components/dashboard/annotation-comment-field';
import type { ChatAnnotation } from '@/lib/chat-annotations';

/** Grace period for the pointer to cross the gap between pill and list. */
const HOVER_CLOSE_DELAY_MS = 150;

const ICON_BUTTON_CLASS =
  'cursor-pointer rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring';

/**
 * Annotations waiting in the composer: a compact "N annotations" pill whose
 * list opens on hover (or on click, for touch and keyboard). Each row shows the
 * selected text and the comment; the pill's × drops them all.
 *
 * A comment is edited in place: the pencil, or a click on the comment itself
 * (or on "Add comment" when there is none), turns that one line into the same
 * rounded field the selection menu adds comments with. ⏎ or ✓ saves, Esc
 * cancels, and clicking away, or starting another row's edit, keeps what was
 * typed.
 *
 * The list is a Popover driven by hover rather than a HoverCard so it can hold
 * a text field: it stays open while a comment is being edited even when the
 * pointer wanders off, and it never takes focus on open, so passing the
 * pointer over the pill doesn't pull the caret out of the composer.
 */
export function AnnotationsChip({
  annotations,
  onUpdateComment,
  onRemove,
  onClear,
}: {
  annotations: ChatAnnotation[];
  onUpdateComment: (id: string, comment: string) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const editingIdRef = useRef<string | null>(null);
  editingIdRef.current = editingId;
  const pillRef = useRef<HTMLDivElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Whether the pointer is over the pill or the list. An edit can end with the
  // pointer already elsewhere, and then no pointerleave is coming to close it.
  const hoveringRef = useRef(false);

  const cancelClose = useCallback(() => {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    closeTimerRef.current = null;
  }, []);
  useEffect(() => cancelClose, [cancelClose]);

  const show = useCallback(() => {
    cancelClose();
    setOpen(true);
  }, [cancelClose]);

  const handlePointerEnter = useCallback(
    (e: React.PointerEvent) => {
      if (e.pointerType !== 'mouse') return;
      hoveringRef.current = true;
      show();
    },
    [show],
  );

  const scheduleClose = useCallback(() => {
    cancelClose();
    if (editingIdRef.current) return;
    closeTimerRef.current = setTimeout(() => setOpen(false), HOVER_CLOSE_DELAY_MS);
  }, [cancelClose]);

  const handlePointerLeave = useCallback(
    (e: React.PointerEvent) => {
      if (e.pointerType !== 'mouse') return;
      hoveringRef.current = false;
      scheduleClose();
    },
    [scheduleClose],
  );

  const endEdit = useCallback(() => {
    editingIdRef.current = null;
    setEditingId(null);
    if (!hoveringRef.current) scheduleClose();
  }, [scheduleClose]);

  const startEdit = useCallback(
    (annotation: ChatAnnotation) => {
      const current = editingIdRef.current;
      if (current === annotation.id) return;
      if (current) onUpdateComment(current, draft);
      editingIdRef.current = annotation.id;
      setEditingId(annotation.id);
      setDraft(annotation.comment);
    },
    [draft, onUpdateComment],
  );

  const commitEdit = useCallback(() => {
    const id = editingIdRef.current;
    if (id) onUpdateComment(id, draft);
    endEdit();
  }, [draft, onUpdateComment, endEdit]);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      // Clicking away keeps what was typed; only Esc throws an edit away.
      if (!next) commitEdit();
      setOpen(next);
    },
    [commitEdit],
  );

  const handleRemove = useCallback(
    (id: string) => {
      if (editingIdRef.current === id) setEditingId(null);
      onRemove(id);
    },
    [onRemove],
  );

  const count = annotations.length;
  const label = `${count} annotation${count === 1 ? '' : 's'}`;

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverAnchor asChild>
        <div
          ref={pillRef}
          onPointerEnter={handlePointerEnter}
          onPointerLeave={handlePointerLeave}
          className="flex h-7 items-center gap-0.5 rounded-full border border-border bg-muted-foreground/5 pl-2.5 pr-1 text-xs"
        >
          <button
            type="button"
            onClick={show}
            aria-expanded={open}
            aria-label={`Show ${label}`}
            className="flex cursor-pointer items-center gap-1.5 pr-1 focus-visible:outline-none"
          >
            <MessageSquareQuote className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
            <span className="whitespace-nowrap">{label}</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setEditingId(null);
              setOpen(false);
              onClear();
            }}
            title="Remove all annotations"
            aria-label="Remove all annotations"
            className="flex h-5 w-5 cursor-pointer items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      </PopoverAnchor>
      <PopoverContent
        side="top"
        align="start"
        sideOffset={6}
        className="w-96 max-w-[calc(100vw-2rem)] p-0"
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onCloseAutoFocus={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => {
          if (!editingIdRef.current) return;
          e.preventDefault();
          endEdit();
        }}
        onInteractOutside={(e) => {
          // The pill is the list's own handle, not "outside".
          if (pillRef.current?.contains(e.target as Node)) e.preventDefault();
        }}
      >
        <ol className="custom-scrollbar max-h-80 divide-y divide-border overflow-y-auto">
          {annotations.map((annotation, index) => {
            const editing = editingId === annotation.id;
            return (
              <li
                key={annotation.id}
                className="grid grid-cols-[1rem_minmax(0,1fr)_auto] gap-x-2 px-3 py-2.5 text-xs"
              >
                <span className="pt-px text-muted-foreground tabular-nums">{index + 1}.</span>
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="text-[11px] text-muted-foreground">Selected text:</span>
                  <p className="line-clamp-3 whitespace-pre-wrap break-words">{annotation.quote}</p>
                  {editing ? (
                    <span className="mt-1 text-[11px] text-muted-foreground">User comment:</span>
                  ) : annotation.comment ? (
                    <>
                      <span className="mt-1 text-[11px] text-muted-foreground">User comment:</span>
                      <button
                        type="button"
                        onClick={() => startEdit(annotation)}
                        className="-mx-1 cursor-pointer rounded px-1 text-left whitespace-pre-wrap break-words hover:bg-muted"
                      >
                        {annotation.comment}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => startEdit(annotation)}
                      className="mt-1 cursor-pointer self-start text-[11px] text-muted-foreground/60 hover:text-foreground"
                    >
                      Add comment
                    </button>
                  )}
                </div>
                <div className="flex items-start gap-0.5">
                  <button
                    type="button"
                    onClick={() => startEdit(annotation)}
                    title={annotation.comment ? 'Edit comment' : 'Add comment'}
                    aria-label={annotation.comment ? 'Edit comment' : 'Add comment'}
                    className={ICON_BUTTON_CLASS}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleRemove(annotation.id)}
                    title="Delete annotation"
                    aria-label="Delete annotation"
                    className={ICON_BUTTON_CLASS}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                {editing && (
                  // Runs under the icons too, out to the row's right padding.
                  <AnnotationCommentField
                    value={draft}
                    onChange={setDraft}
                    onSubmit={commitEdit}
                    submitLabel="Save"
                    compact
                    className="col-span-2 col-start-2 mt-1"
                  />
                )}
              </li>
            );
          })}
        </ol>
      </PopoverContent>
    </Popover>
  );
}
