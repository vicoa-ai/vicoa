'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowUp, Check } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { comboKeycaps, isMacPlatform, type ShortcutCombo } from '@/lib/desktop-shortcuts';
import { cn } from '@/lib/utils';

const SUBMIT_COMBO: ShortcutCombo = { code: 'Enter', meta: false, shift: false, alt: false };
const SEND_COMBO: ShortcutCombo = { ...SUBMIT_COMBO, meta: true };

/** The field grows with its text up to this many lines, then scrolls. */
const MAX_LINES = 6;

let measureCanvas: HTMLCanvasElement | null = null;

/** Rendered width of one line of `text` in `font` (a computed CSS font shorthand). */
function textWidth(text: string, font: string): number {
  measureCanvas ??= document.createElement('canvas');
  const context = measureCanvas.getContext('2d');
  if (!context) return 0;
  context.font = font;
  return context.measureText(text).width;
}

/** ⌘ on macOS, Ctrl elsewhere: the modifier that turns the submit into Send. */
function primaryModifierHeld(event: { metaKey: boolean; ctrlKey: boolean }): boolean {
  return isMacPlatform() ? event.metaKey : event.ctrlKey;
}

function Keycaps({ keys }: { keys: string[] }) {
  return (
    <span className="flex justify-end gap-0.5">
      {keys.map((key) => (
        <kbd key={key} className="rounded border bg-muted px-1 py-0.5 text-[10px] leading-none text-muted-foreground">
          {key}
        </kbd>
      ))}
    </span>
  );
}

/**
 * The rounded comment field an annotation is written in: in the transcript's
 * selection menu when it is added, and in place in the composer pill's list
 * when it is edited. ⏎ or the round ✓ button submits; ⇧⏎ breaks the line.
 *
 * Short text sits on one line in a pill, the button at its end. Once the text
 * no longer fits that line the field becomes a rounded box: the text wraps
 * across the full width, growing to MAX_LINES lines before it scrolls, and the
 * button moves to a row of its own underneath. Whether it fits is measured
 * against the one-line width, not the current one, so text that would fit
 * only once the button has moved away can't flip the layout back and forth.
 *
 * With `sendable`, ⌘⏎ (Ctrl⏎) or a ⌘-click submits and sends the message
 * too, and the button's tick turns into the send arrow while the modifier is
 * held. Esc and clicking away are the host's to handle (each sits in its own
 * popover), so the field takes no part in them.
 */
export function AnnotationCommentField({
  value,
  onChange,
  onSubmit,
  submitLabel,
  sendable = false,
  compact = false,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  /** `send` is true only when `sendable` and the modifier was held. */
  onSubmit: (send: boolean) => void;
  /** What ⏎ does, e.g. "Add" or "Save"; names the button and its tooltip row. */
  submitLabel: string;
  sendable?: boolean;
  /** The smaller size used inside the annotation list. */
  compact?: boolean;
  className?: string;
}) {
  const [sendMode, setSendMode] = useState(false);
  const [multiline, setMultiline] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const singleLineWidthRef = useRef(0);

  // Before paint, so neither the layout switch nor the height change flickers.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const style = getComputedStyle(el);
    if (!multiline) singleLineWidthRef.current = el.clientWidth;
    const wraps = value.includes('\n') || textWidth(value, style.font) > singleLineWidthRef.current;
    if (wraps !== multiline) {
      setMultiline(wraps);
      return;
    }
    const maxHeight = parseFloat(style.lineHeight) * MAX_LINES;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, [value, multiline]);
  const [keycaps, setKeycaps] = useState<{ submit: string[]; send: string[] } | null>(null);

  // Platform keycaps read `navigator`, so they're computed after mount.
  useEffect(() => {
    setKeycaps({ submit: comboKeycaps(SUBMIT_COMBO), send: comboKeycaps(SEND_COMBO) });
  }, []);

  useEffect(() => {
    if (!sendable) return;
    const sync = (event: KeyboardEvent) => setSendMode(primaryModifierHeld(event));
    const reset = () => setSendMode(false);
    window.addEventListener('keydown', sync);
    window.addEventListener('keyup', sync);
    window.addEventListener('blur', reset);
    return () => {
      window.removeEventListener('keydown', sync);
      window.removeEventListener('keyup', sync);
      window.removeEventListener('blur', reset);
    };
  }, [sendable]);

  const submit = (event: { metaKey: boolean; ctrlKey: boolean }) =>
    onSubmit(sendable && primaryModifierHeld(event));
  const showSend = sendable && sendMode;

  return (
    <div
      className={cn(
        'flex border border-border bg-composer',
        multiline
          ? cn('flex-col gap-1', compact ? 'rounded-xl pt-1.5 pb-0.5 pl-3 pr-0.5' : 'rounded-2xl pt-2.5 pb-1 pl-4 pr-1')
          : cn('items-center gap-2 rounded-full', compact ? 'py-0.5 pl-3 pr-0.5' : 'py-1 pl-4 pr-1'),
        className,
      )}
    >
      <textarea
        ref={textareaRef}
        autoFocus
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return;
          e.preventDefault();
          submit(e);
        }}
        placeholder="Add optional comment ..."
        aria-label="Comment on the selected text"
        className={cn(
          'custom-scrollbar resize-none bg-transparent outline-none placeholder:text-muted-foreground/60',
          compact ? 'text-xs' : 'text-sm',
          // In the column a flex-1 basis of 0 would override the measured height.
          multiline ? 'w-full flex-none pr-3' : 'min-w-0 flex-1',
        )}
      />
      {/* `contents` on one line, its own right-aligned row once wrapped: the
          button keeps its place in the tree, so switching never remounts it. */}
      <div className={multiline ? 'flex justify-end' : 'contents'}>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={submit}
                aria-label={showSend ? 'Send' : submitLabel}
                className={cn(
                  'flex flex-shrink-0 cursor-pointer items-center justify-center rounded-full bg-primary text-primary-foreground transition-colors hover:bg-primary/90',
                  compact ? 'h-6 w-6' : 'h-7 w-7',
                )}
              >
                {showSend ? <ArrowUp className="h-3.5 w-3.5" /> : <Check className="h-3.5 w-3.5" />}
              </button>
            </TooltipTrigger>
            {keycaps && (
              <TooltipContent side="top" align="end" className="bg-menu px-2 py-1.5 text-menu-foreground">
                <div className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1">
                  <span>{submitLabel}</span>
                  <Keycaps keys={keycaps.submit} />
                  {sendable && (
                    <>
                      <span>Send</span>
                      <Keycaps keys={keycaps.send} />
                    </>
                  )}
                </div>
              </TooltipContent>
            )}
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  );
}
