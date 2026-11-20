'use client';

// The task-detail comment box. Deliberately the same object as the session
// composer (`components/chat-input.tsx`): same `bg-composer` surface, same
// `border-border/50`, same auto-growing textarea, same round 28px send button
// with an ArrowUp. Two boxes that take typed text and send it should not be two
// different-looking controls in one product.
//
// It corners tighter than the chat composer (`rounded-xl`, not `rounded-3xl`).
// The chat box is that page's primary affordance and sits alone above the
// fold; this one ends a column of square-ish cards, where a pill silhouette
// reads as a different kind of object than the things it is answering.
//
// What it deliberately does NOT inherit: attachments, slash commands, the
// config chips and the usage ring. Those address an agent session; a comment
// has no model, no permission mode and no rate limit.
//
// Two variants. `default` is the box at the foot of the page that starts a new
// thread. `inline` is the "Leave a reply…" row that ends every thread card:
// borderless, one line tall, and it takes an avatar — inside a thread the
// avatar is not decoration, it holds the row on the same column as the comments
// above it and marks the box as part of that conversation rather than a control
// floating under it.
//
// Both variants take `agents` (and `people`) for an `@` picker. A pick writes
// plain `@Name` into the box, drawn as a chip by a highlight layer behind the
// textarea, and only becomes the mention link when the comment is sent
// (lib/task-mentions, the same token/state split as `#` references). Deleting
// the name drops the mention. Mentioning an agent asks it to answer; mentioning
// a person only tells them. `wake` says what sending would do: a one-line hint
// under the box names the agents the comment would wake, mirroring the
// server's routing, so a comment never starts a run by surprise. That includes
// an agent waiting on the viewer's answer to its question (`wake.askers`). A
// comment starting with `/note` wakes nobody; the box tints and the hint says
// so.
//
// Passages selected in the thread above ("Add to reply" in its selection menu,
// lib/chat-annotations.ts) wait in the box as the chat composer's annotation
// pill, and go out under the typed text when the comment is sent. Like the
// draft they live in memory: a reload drops them. The parent reaches the box
// through the `ref` handle (`CommentComposerHandle`).
//
// `CommentEditor` at the foot of the file is the same textarea opened in place
// over a comment you wrote, for editing it.

import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { ArrowUp, RefreshCw } from 'lucide-react';

import { AnnotationsChip } from '@/components/dashboard/annotations-chip';
import { Button } from '@/components/ui/button';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import type { AgentProfile, PrincipalResponse } from '@/lib/backend-api';
import { appendAnnotations, createAnnotation, type ChatAnnotation } from '@/lib/chat-annotations';
import { detectTriggerToken, replaceTokenWith, type TriggerToken } from '@/lib/composer-references';
import { isImeComposing } from '@/lib/ime';
import {
  activeMentions,
  agentsToWake,
  isNoteComment,
  mentionRanges,
  mentionToken,
  serializeMentions,
  type PickedMention,
  type WakeContext,
} from '@/lib/task-mentions';
import { principalFromResponse, type Principal } from '@/lib/principals';
import { agentPrincipal } from '@/lib/use-agent-profiles';
import { cn } from '@/lib/utils';

const MENTION_LIMIT = 6;

/** One row of the `@` picker: an agent the viewer can start, or a person. */
interface MentionCandidate {
  kind: 'agent' | 'user';
  id: string;
  name: string;
  principal: Principal;
}

/** What a thread's selection menu drives the reply box with. */
export interface CommentComposerHandle {
  /** Add a passage as an annotation; returns its id. */
  addAnnotation: (quote: string) => string;
  /** Set the comment on an annotation added above; with `send`, post the comment too. */
  commentAnnotation: (id: string, comment: string, options?: { send?: boolean }) => void;
}

const MIN_HEIGHT = 36;
// The inline reply row is one line tall at rest so a thread ends in a hint, not
// in a second composer competing with the page's own.
const INLINE_HEIGHT = 28;
const MAX_HEIGHT = 200;

export function CommentComposer({
  ref,
  onSubmit,
  disabled = false,
  placeholder = 'Leave a comment…',
  autoFocus = false,
  variant = 'default',
  leading,
  className,
  agents,
  people,
  viewerId = null,
  wake,
}: {
  /** Annotations from the thread's selection menu come in through this. */
  ref?: React.Ref<CommentComposerHandle>;
  onSubmit: (body: string) => Promise<void>;
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  /** `inline` is the reply row inside a thread card; see the header comment. */
  variant?: 'default' | 'inline';
  /** Rendered left of the textarea — the viewer's avatar, on `inline`. */
  leading?: React.ReactNode;
  className?: string;
  /** The agents an `@` can mention (the viewer's own). Omitted: no picker. */
  agents?: AgentProfile[];
  /** The people an `@` can mention: who can see the task. The viewer is left out. */
  people?: PrincipalResponse[];
  /** The signed-in user, to leave them out of `people`. */
  viewerId?: string | null;
  /** Where the box sits, for the "… will work on this" hint. Omitted: no hint. */
  wake?: WakeContext;
}) {
  const [value, setValue] = useState('');
  // Agents picked from the `@` list; each counts while its `@Name` is in the text.
  const [picks, setPicks] = useState<PickedMention[]>([]);
  // The `@` token the caret is in, while the agent picker is open.
  const [mention, setMention] = useState<TriggerToken | null>(null);
  const [highlight, setHighlight] = useState(0);
  // The wake hint is for the person typing: shown only while the box has focus.
  const [focused, setFocused] = useState(false);
  // A send in flight locks the button.
  const [sending, setSending] = useState(false);
  // Passages picked with "Add to reply", sent under the typed text.
  const [annotations, setAnnotations] = useState<ChatAnnotation[]>([]);
  const annotationsRef = useRef(annotations);
  annotationsRef.current = annotations;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);

  // Same rAF-coalesced auto-resize as the chat composer: reading scrollHeight
  // after writing height='auto' forces a synchronous layout, so collapse a
  // burst of keystrokes into one reflow per frame.
  const frameRef = useRef<number | null>(null);
  const autoResize = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = 'auto';
      const floor = variant === 'inline' ? INLINE_HEIGHT : MIN_HEIGHT;
      el.style.height = `${Math.max(floor, Math.min(el.scrollHeight, MAX_HEIGHT))}px`;
    });
  }, [variant]);

  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  // Only agents a comment can actually start: the viewer's own, live ones.
  const mentionable = useMemo(
    () => (agents ?? []).filter((a) => !a.is_archived && !a.team_id),
    [agents],
  );
  // Agents first (a mention there starts work), then the people on the board.
  const candidates = useMemo<MentionCandidate[]>(() => {
    const out: MentionCandidate[] = mentionable.map((a) => ({
      kind: 'agent',
      id: a.id,
      name: a.name,
      principal: agentPrincipal(a),
    }));
    for (const person of people ?? []) {
      const name = person.name?.trim();
      if (!person.id || !name || person.id === viewerId) continue;
      const principal = principalFromResponse(person);
      if (principal) out.push({ kind: 'user', id: person.id, name, principal });
    }
    return out;
  }, [mentionable, people, viewerId]);
  const matches = useMemo(() => {
    if (!mention) return [];
    const q = mention.query.toLowerCase();
    return candidates.filter((c) => c.name.toLowerCase().includes(q)).slice(0, MENTION_LIMIT);
  }, [mention, candidates]);
  const pickerOpen = mention !== null && matches.length > 0;

  const trackMention = useCallback(
    (text: string, cursor: number) => {
      if (candidates.length === 0) return;
      const token = detectTriggerToken(text, cursor, '@');
      setMention(token);
      setHighlight(0);
    },
    [candidates.length],
  );

  const chooseMention = useCallback(
    (picked: MentionCandidate) => {
      if (!mention) return;
      const next = replaceTokenWith(value, mention, mentionToken(picked.name));
      setValue(next.text);
      setPicks((prev) => [
        ...prev.filter((p) => p.id !== picked.id),
        { id: picked.id, name: picked.name, kind: picked.kind },
      ]);
      setMention(null);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.focus();
        el.setSelectionRange(next.cursor, next.cursor);
      });
      autoResize();
    },
    [mention, value, autoResize],
  );

  // The picks still in the text, and the body as it would be posted.
  const livePicks = useMemo(() => activeMentions(picks, value), [picks, value]);
  const outgoing = useCallback(
    (text: string) => serializeMentions(text, livePicks),
    [livePicks],
  );
  const isNote = isNoteComment(value);

  // "… will work on this": the server's routing, predicted. With nothing typed
  // yet it shows what a plain comment here would do.
  const wakeNames = useMemo(() => {
    if (!wake) return [];
    const ids = agentsToWake(value.trim() ? outgoing(value) : '.', wake);
    // An agent asking the viewer may be someone else's (a teammate's agent).
    const byId = new Map([
      ...(wake.askers ?? []).map((a) => [a.id.toLowerCase(), a.name] as const),
      ...mentionable.map((a) => [a.id.toLowerCase(), a.name] as const),
    ]);
    return ids.map((id) => byId.get(id)).filter((name): name is string => !!name);
  }, [wake, value, outgoing, mentionable]);

  // The chip layer: the text with each live `@Name` marked, laid out exactly
  // like the textarea above it. A trailing newline needs a character after it
  // or the layer ends a line short.
  const highlighted = useMemo(() => {
    const ranges = mentionRanges(value, livePicks);
    if (ranges.length === 0) return null;
    const parts: React.ReactNode[] = [];
    let cursor = 0;
    ranges.forEach((range, index) => {
      parts.push(value.slice(cursor, range.start));
      // The posted chip's look (message-markdown): its padding is a ring, which
      // takes no layout space, so every glyph stays over its textarea twin.
      parts.push(
        <mark
          key={index}
          className="rounded bg-primary/10 text-primary ring-[3px] ring-primary/10"
        >
          {value.slice(range.start, range.end)}
        </mark>,
      );
      cursor = range.end;
    });
    parts.push(`${value.slice(cursor)}\u200b`);
    return parts;
  }, [value, livePicks]);

  const clear = useCallback(() => {
    setValue('');
    setPicks([]);
    setMention(null);
    setAnnotations([]);
    const el = textareaRef.current;
    if (el) el.style.height = `${variant === 'inline' ? INLINE_HEIGHT : MIN_HEIGHT}px`;
  }, [variant]);

  // `pending` is passed in by the selection menu's ⌘⏎, so a comment set in the
  // same tick as the send is in the posted text.
  const send = useCallback(
    async (pending: ChatAnnotation[] = annotationsRef.current) => {
      // A comment is rendered, so the quotes go out in the markdown format.
      const body = appendAnnotations(outgoing(value).trim(), pending, 'markdown');
      if (!body || sending || disabled) return;
      setSending(true);
      try {
        await onSubmit(body);
        clear();
      } finally {
        setSending(false);
      }
    },
    [value, outgoing, sending, disabled, onSubmit, clear],
  );

  const updateAnnotationComment = useCallback((id: string, comment: string) => {
    setAnnotations((items) => items.map((a) => (a.id === id ? { ...a, comment: comment.trim() } : a)));
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      addAnnotation: (quote: string) => {
        const annotation = createAnnotation(quote);
        setAnnotations((items) => [...items, annotation]);
        return annotation.id;
      },
      commentAnnotation: (id: string, comment: string, options?: { send?: boolean }) => {
        const trimmed = comment.trim();
        if (trimmed) updateAnnotationComment(id, trimmed);
        if (!options?.send) return;
        void send(annotationsRef.current.map((a) => (a.id === id ? { ...a, comment: trimmed } : a)));
      },
    }),
    [updateAnnotationComment, send],
  );

  const inline = variant === 'inline';
  const hasAnnotations = annotations.length > 0;
  // Nothing to send: no text, and no annotation to send on its own.
  const empty = value.trim().length === 0 && !hasAnnotations;
  // Hint copy is secondary (apps/web/AGENTS.md → "Hint text"): dimmer than
  // body text, only while typing here, whole sentences. An empty box says who
  // it is for in its placeholder instead.
  const hintClass = cn(
    'font-sans text-[11px] text-muted-foreground/60',
    inline ? 'pb-0.5' : 'mt-1 px-1',
  );
  const wakeHint =
    !focused || empty ? null : isNote ? (
      <p className={hintClass}>Just a note. No agent will act on it.</p>
    ) : wakeNames.length > 0 ? (
      <p className={hintClass}>
        {formatNames(wakeNames)} will work on this. Start with /note to just leave a note.
      </p>
    ) : null;
  // An agent waiting on the viewer's answer: the box is a reply to it, wherever
  // it sits.
  const answering = (wake?.askers ?? []).length > 0;
  const shownPlaceholder =
    wake && wakeNames.length > 0
      ? `${wake.inThread || answering ? 'Reply to' : 'Comment for'} ${formatNames(wakeNames)}…`
      : placeholder;

  return (
    <div
      className={cn(
        'relative w-full font-mono',
        // The inline row has no edge of its own: the thread card is already a
        // surface, and a second border inside it reads as a nested object.
        // The inline row wraps only to put the annotation pill on a line of
        // its own above the avatar, the text and the button.
        inline
          ? 'flex flex-wrap items-center gap-x-2 gap-y-1'
          : 'rounded-xl border border-border/50 bg-composer px-3 py-2.5 shadow-sm transition-colors',
        // A note reads as an aside before it is even sent.
        isNote && (inline ? 'rounded-md bg-muted/50 px-1' : 'border-dashed bg-muted/40'),
        className,
      )}
    >
      {hasAnnotations && (
        // Over the text column: past the avatar (16px + the row's 8px gap) on
        // the inline row, and on the textarea's 4px inset in the box.
        <div className={cn('flex', inline ? cn('basis-full pt-1', leading && 'pl-6') : 'mb-1.5 px-1')}>
          <AnnotationsChip
            annotations={annotations}
            onUpdateComment={updateAnnotationComment}
            onRemove={(id) => setAnnotations((items) => items.filter((a) => a.id !== id))}
            onClear={() => setAnnotations([])}
          />
        </div>
      )}
      {/* The page-bottom variant carries no avatar: only one person can be
          typing there, and their own face is not information — it was just an
          indent. Inside a thread it earns its place (see the header). */}
      {inline && leading}
      {pickerOpen && (
        <div
          role="listbox"
          aria-label="Mention an agent or a person"
          className="absolute bottom-full left-0 z-20 mb-1 w-56 overflow-hidden rounded-md border bg-popover p-1 font-sans shadow-md"
        >
          {matches.map((candidate, index) => (
            <button
              key={`${candidate.kind}:${candidate.id}`}
              type="button"
              role="option"
              aria-selected={index === highlight}
              // mousedown, not click: the textarea's blur would close the list first.
              onMouseDown={(e) => {
                e.preventDefault();
                chooseMention(candidate);
              }}
              onMouseEnter={() => setHighlight(index)}
              className={cn(
                'flex w-full cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm',
                index === highlight && 'bg-accent text-accent-foreground',
              )}
            >
              <PrincipalAvatar principal={candidate.principal} size="xs" />
              <span className="truncate">{candidate.name}</span>
              {candidate.kind === 'agent' && (
                <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">agent</span>
              )}
            </button>
          ))}
        </div>
      )}
      <div className={cn(inline ? 'min-w-0 flex-1' : 'flex items-start gap-2')}>
        <div className="relative w-full min-w-0">
        {highlighted && (
          <div
            ref={highlightRef}
            aria-hidden
            className={cn(
              // Same box and type as the textarea so every glyph lands on top
              // of its mark; only the marks are visible.
              // The layer draws the text (the textarea's own is transparent
              // while it shows) so a mention can be coloured like a chip.
              'pointer-events-none absolute inset-0 overflow-hidden whitespace-pre-wrap break-words text-sm leading-5 text-foreground',
              inline ? 'py-1' : 'px-1 py-2',
            )}
          >
            {highlighted}
          </div>
        )}
        <textarea
          ref={textareaRef}
          onScroll={(e) => {
            if (highlightRef.current) highlightRef.current.scrollTop = e.currentTarget.scrollTop;
          }}
          value={value}
          autoFocus={autoFocus}
          onChange={(e) => {
            setValue(e.target.value);
            trackMention(e.target.value, e.target.selectionStart ?? e.target.value.length);
            autoResize();
          }}
          onKeyDown={(e) => {
            // An IME's Enter picks a candidate, it doesn't send.
            if (isImeComposing(e)) return;
            if (pickerOpen) {
              if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                const step = e.key === 'ArrowDown' ? 1 : -1;
                setHighlight((i) => (i + step + matches.length) % matches.length);
                return;
              }
              if (e.key === 'Enter' || e.key === 'Tab') {
                e.preventDefault();
                chooseMention(matches[Math.min(highlight, matches.length - 1)]);
                return;
              }
              if (e.key === 'Escape') {
                // Closes the picker only; a dialog around the box stays open.
                e.preventDefault();
                setMention(null);
                return;
              }
            }
            // Enter sends, Shift+Enter breaks the line — the same contract the
            // session composer teaches.
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
            if (e.key === 'Escape') {
              e.preventDefault();
              textareaRef.current?.blur();
            }
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false);
            setMention(null);
          }}
          placeholder={shownPlaceholder}
          disabled={disabled}
          rows={1}
          style={{
            height: inline ? INLINE_HEIGHT : MIN_HEIGHT,
            minHeight: inline ? INLINE_HEIGHT : MIN_HEIGHT,
            maxHeight: MAX_HEIGHT,
          }}
          className={cn(
            // `block` is load-bearing, not tidiness: a textarea is inline-block
            // by default, so inside the inline variant's plain wrapper it sits
            // on a text baseline and leaves ~4px of descender space beneath
            // itself. That makes the wrapper taller than the box, and the row's
            // items-center then centres the *wrapper* — dropping the avatar a
            // couple of pixels below the caret. (The default variant's wrapper
            // is a flex container, which blockifies its children already.)
            'custom-scrollbar relative block w-full resize-none border-0 bg-transparent text-sm leading-5 placeholder:text-muted-foreground/50 focus:outline-none focus:ring-0 disabled:cursor-not-allowed disabled:opacity-50',
            inline ? 'py-1' : 'px-1 py-2',
            highlighted && 'text-transparent caret-foreground',
          )}
        />
        </div>
        {inline && wakeHint}
      </div>
      <div className={cn('flex items-center justify-end', !inline && 'mt-0')}>
        <Button
          onClick={() => void send()}
          aria-label={inline ? 'Post reply' : 'Post comment'}
          disabled={disabled || !!sending || empty}
          variant="default"
          size="icon"
          className={cn(
            'shrink-0 rounded-full border-0 p-0 focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0',
            // Ghosted until there is something to send, so an idle thread ends
            // in an invitation rather than in a row of dead buttons.
            inline ? 'h-6 w-6 transition-opacity' : 'h-7 w-7',
            inline && empty && !sending && 'pointer-events-none opacity-30',
          )}
        >
          {sending ? (
            <RefreshCw className={cn('animate-spin', inline ? 'h-3 w-3' : 'h-3.5 w-3.5')} />
          ) : (
            <ArrowUp className={cn(inline ? 'h-3 w-3' : 'h-3.5 w-3.5')} />
          )}
        </Button>
      </div>
      {!inline && wakeHint}
    </div>
  );
}

function formatNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? '';
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/**
 * A comment's own text, reopened for editing where it was. Enter saves and
 * Escape cancels, so editing keeps the keys typing it taught; Save and Cancel
 * are there for whoever reaches for the mouse. Saving unchanged text just
 * closes it: an "(edited)" mark on a comment nobody changed is a false record.
 */
export function CommentEditor({
  initialValue,
  onSave,
  onCancel,
}: {
  initialValue: string;
  onSave: (body: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initialValue);
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.max(MIN_HEIGHT, Math.min(el.scrollHeight, MAX_HEIGHT))}px`;
  }, []);

  // Open at the text's full height with the caret at its end, where an edit
  // usually starts.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    resize();
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, [resize]);

  const body = value.trim();
  const save = useCallback(async () => {
    if (!body || saving) return;
    if (body === initialValue.trim()) {
      onCancel();
      return;
    }
    setSaving(true);
    try {
      await onSave(body);
    } catch (err) {
      // Stay open with the draft intact, so a failed save loses nothing.
      console.error('Failed to save comment:', err);
    } finally {
      setSaving(false);
    }
  }, [body, saving, initialValue, onSave, onCancel]);

  return (
    <div className="mt-1.5 rounded-lg border border-border/50 bg-composer px-2 py-1.5 font-mono">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          resize();
        }}
        onKeyDown={(e) => {
          if (isImeComposing(e)) return;
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            void save();
          }
          if (e.key === 'Escape') {
            e.preventDefault();
            onCancel();
          }
        }}
        disabled={saving}
        rows={1}
        aria-label="Edit comment"
        style={{ minHeight: MIN_HEIGHT, maxHeight: MAX_HEIGHT }}
        className="custom-scrollbar block w-full resize-none border-0 bg-transparent px-1 py-2 text-sm leading-5 focus:outline-none focus:ring-0 disabled:opacity-50"
      />
      <div className="flex items-center justify-end gap-1.5">
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={saving}
          className="h-7 px-2.5 text-xs"
        >
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={() => void save()}
          disabled={saving || !body}
          className="h-7 px-2.5 text-xs"
        >
          {saving && <RefreshCw className="size-3 animate-spin" />}
          Save
        </Button>
      </div>
    </div>
  );
}
