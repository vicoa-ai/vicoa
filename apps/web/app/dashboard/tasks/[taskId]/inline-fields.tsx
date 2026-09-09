'use client';

// Click-to-edit title and description for the task page.
//
// The rule both fields follow: **the edit surface sits in exactly the same box
// as the read surface**. Same size, weight, leading and offset; the textarea
// only swaps the background. If clicking a title made it jump a pixel or change
// leading, the page would flinch on every edit — which is what makes inline
// editing feel worse than a dialog rather than better. (The description is the
// honest exception: rendered markdown and its source can't occupy identical
// space, so it matches on box and type size and accepts reflow on lists and
// headings, the same as GitHub and Linear.)
//
// Saving is on blur, not on a button. A Save button in a properties column is a
// second thing to aim at for a change the user has already finished making;
// Linear, Notion and GitHub's title field all commit on blur. Escape reverts,
// so the destructive-feeling case still has an undo that doesn't need a dialog.

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';

import { MessageMarkdown } from '@/components/ui/message-markdown';
import { cn } from '@/lib/utils';

// How tall a collapsed description is allowed to be — roughly fourteen lines at
// this leading. Anything under it renders whole and grows no affordance; the
// point is to stop a spec-length description from pushing the timeline off the
// screen, not to make people expand an ordinary paragraph. A clamp that fires
// on a normal-sized description just adds a click to reading the task.
const COLLAPSED_MAX_PX = 320;

/** Grow a textarea to fit its content, coalesced into one reflow per frame. */
function useAutoResize(value: string, enabled: boolean) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value, enabled]);
  return ref;
}

export function EditableTitle({
  value,
  onSave,
}: {
  value: string;
  onSave: (next: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const ref = useAutoResize(draft, editing);

  // A background refresh can land while the field is closed; don't clobber a
  // draft the user is in the middle of typing.
  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  const commit = useCallback(() => {
    setEditing(false);
    const next = draft.trim();
    // A task must have a title (the API enforces min_length 1), so an empty
    // field reverts rather than erroring after the fact.
    if (!next || next === value) {
      setDraft(value);
      return;
    }
    onSave(next);
  }, [draft, value, onSave]);

  const shared =
    'w-full text-2xl font-semibold leading-tight tracking-[-0.01em]';

  if (!editing) {
    return (
      <h1
        role="textbox"
        tabIndex={0}
        onClick={() => setEditing(true)}
        // Enter/Space, not focus: opening an editor merely because Tab passed
        // through would ambush anyone navigating by keyboard.
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setEditing(true);
          }
        }}
        className={cn(
          shared,
          'cursor-text rounded-md px-1 py-0.5 -mx-1 transition-colors hover:bg-accent/40',
        )}
      >
        {value}
      </h1>
    );
  }

  return (
    <textarea
      ref={ref}
      autoFocus
      value={draft}
      rows={1}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        // A title has no line breaks, so Enter is unambiguous: commit.
        if (e.key === 'Enter') {
          e.preventDefault();
          commit();
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setDraft(value);
          setEditing(false);
        }
      }}
      className={cn(
        shared,
        'resize-none overflow-hidden rounded-md border-0 bg-accent/40 px-1 py-0.5 -mx-1',
        'focus:outline-none focus:ring-0',
      )}
    />
  );
}

export function EditableDescription({
  value,
  onSave,
}: {
  value: string | null;
  onSave: (next: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? '');
  const [expanded, setExpanded] = useState(false);
  // Whether the rendered body is actually taller than the clamp. Measured, not
  // guessed from length: markdown expands unpredictably — 200 characters with a
  // code block is tall, 600 characters of prose is four lines.
  const [overflowing, setOverflowing] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const ref = useAutoResize(draft, editing);

  useEffect(() => {
    if (!editing) setDraft(value ?? '');
  }, [value, editing]);

  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    const measure = () => setOverflowing(el.scrollHeight > COLLAPSED_MAX_PX + 8);
    measure();
    // Markdown can reflow after mount (fonts, code highlighting, a container
    // resize), so a single measurement at render time would be wrong as often
    // as it was right.
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [value, editing]);

  const commit = useCallback(() => {
    setEditing(false);
    const next = draft.trim();
    if (next === (value ?? '').trim()) return;
    // Unlike the title, empty is a legitimate value — clearing a description
    // sends null so the column goes back to NULL rather than storing "".
    onSave(next || null);
  }, [draft, value, onSave]);

  if (!editing) {
    const clamped = overflowing && !expanded;
    return (
      // The toggle sits OUTSIDE the click-to-edit region rather than inside it
      // with a stopPropagation: "show me the rest" and "let me rewrite it" are
      // different intents, and one shouldn't have to defuse the other.
      <div className="space-y-1">
        <div
          role="textbox"
          tabIndex={0}
          onClick={() => setEditing(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setEditing(true);
            }
          }}
          className="relative -mx-2 cursor-text overflow-hidden rounded-md px-2 py-1.5 text-sm leading-relaxed transition-colors hover:bg-accent/40"
          style={clamped ? { maxHeight: COLLAPSED_MAX_PX } : undefined}
        >
          <div ref={bodyRef}>
            {value ? (
              <MessageMarkdown>{value}</MessageMarkdown>
            ) : (
              <span className="text-muted-foreground/60">Add a description…</span>
            )}
          </div>
          {/* A hard cut mid-sentence looks like a rendering bug; the fade says
              "there is more" without needing to be read. */}
          {clamped && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-b from-transparent to-background" />
          )}
        </div>
        {overflowing && (
          // Centred, and full-width rather than a floating link. The page holds
          // a strict left column — avatars, comment bodies and rail rows all
          // share one edge — so a left-aligned link here would read as another
          // item in that column. This isn't an item; it's the seam of the block
          // above it, which is also what the full-width fade is drawing. Making
          // the control span the same width and centring its label says "the
          // block continues" instead of "here is one more thing to read".
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="-mx-2 flex w-[calc(100%+1rem)] cursor-pointer items-center justify-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent/40 hover:text-foreground"
          >
            <ChevronDown
              className={cn('size-3 transition-transform', expanded && 'rotate-180')}
            />
            {expanded ? 'Show less' : 'Show more'}
          </button>
        )}
      </div>
    );
  }

  return (
    <textarea
      ref={ref}
      autoFocus
      value={draft}
      rows={3}
      placeholder="Add a description…"
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        // Enter breaks the line — this is markdown, and a description that
        // couldn't hold a list would be a worse editor than the dialog's.
        // ⌘/Ctrl+Enter is the explicit commit for anyone who doesn't want to
        // click away.
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          e.currentTarget.blur();
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setDraft(value ?? '');
          setEditing(false);
        }
      }}
      className={cn(
        '-mx-2 w-[calc(100%+1rem)] resize-none overflow-hidden rounded-md border-0 bg-accent/40 px-2 py-1.5',
        'text-sm leading-relaxed focus:outline-none focus:ring-0',
        'placeholder:text-muted-foreground/60',
      )}
    />
  );
}
