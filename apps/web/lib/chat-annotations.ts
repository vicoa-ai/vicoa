/**
 * Chat annotations: a passage selected in the transcript, with an optional
 * comment, carried in the composer until the next send.
 *
 * Like `#` references (lib/composer-references.ts) they are composer state the
 * textarea never sees, and they reach the agent as text: at send time the list
 * becomes a numbered block of quotes and comments under the typed message.
 * Nothing is stored server-side, so the agent, the transcript and the mobile
 * app all read the same plain text.
 *
 * Two surfaces hold them. The chat composer keeps a list per session in
 * sessionStorage, so switching sessions and coming back keeps them, like the
 * draft. "Continue in new session" hands one quote to the new-session page
 * through a sessionStorage handoff, the way a fork hands over its history
 * (lib/fork-session.ts): a reload of `?annotations=1` restores the chip, and
 * the handoff is dropped once the session spawns or the chip is removed.
 *
 * Lives outside the components so it can be unit-tested — the vitest setup
 * runs in the `node` environment and cannot render components.
 */

export interface ChatAnnotation {
  id: string;
  /** The selected text, normalised by `normalizeSelectedText`. */
  quote: string;
  /** The user's note on it; empty when they added none. */
  comment: string;
}

/** Longest quote kept; a longer selection is cut with a marker. */
export const MAX_QUOTE_CHARS = 4000;

/**
 * A DOM selection as a quote: CRLF folded, trailing spaces stripped per line,
 * runs of blank lines (block boundaries in `Selection.toString()`) squeezed to
 * one, the whole trimmed, then clamped.
 */
export function normalizeSelectedText(text: string): string {
  const cleaned = text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((line) => line.replace(/[ \t ]+$/, ''))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  if (cleaned.length <= MAX_QUOTE_CHARS) return cleaned;
  return `${cleaned.slice(0, MAX_QUOTE_CHARS).trimEnd()}\n… (truncated)`;
}

export function createAnnotation(quote: string, comment = ''): ChatAnnotation {
  const id =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  return { id, quote: normalizeSelectedText(quote), comment: comment.trim() };
}

/**
 * One list item: the quote as `>` lines, then the comment. The continuation
 * lines are indented under the number so the block reads as a list both raw
 * (the user bubble renders plain text) and to an agent parsing markdown.
 */
function formatAnnotation(annotation: ChatAnnotation, index: number): string {
  const marker = `${index + 1}. `;
  const indent = ' '.repeat(marker.length);
  const quoteLines = annotation.quote
    .split('\n')
    .map((line, i) => `${i === 0 ? marker : indent}>${line ? ` ${line}` : ''}`);
  const comment = annotation.comment.trim();
  if (!comment) return quoteLines.join('\n');
  const commentLines = comment
    .split('\n')
    .map((line, i) => `${indent}${i === 0 ? 'Comment: ' : ''}${line}`);
  return [...quoteLines, ...commentLines].join('\n');
}

/**
 * The numbered quotes, with no header line: the block is read by the agent,
 * and the `>` quotes already say what they are.
 */
export function buildAnnotationBlock(annotations: ChatAnnotation[]): string {
  return annotations
    .filter((a) => a.quote.trim())
    .map(formatAnnotation)
    .join('\n\n');
}

/** Typed text first, then the annotations under a rule, as `#` references do. */
export function appendAnnotations(body: string, annotations: ChatAnnotation[]): string {
  const block = buildAnnotationBlock(annotations);
  if (!block) return body;
  return body ? `${body}\n\n---\n${block}` : block;
}

/** A stored list, keeping only well-formed entries. */
export function parseAnnotations(raw: unknown): ChatAnnotation[] {
  if (!Array.isArray(raw)) return [];
  const out: ChatAnnotation[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const { id, quote, comment } = item as Record<string, unknown>;
    if (typeof id !== 'string' || typeof quote !== 'string' || !quote.trim()) continue;
    out.push({ id, quote, comment: typeof comment === 'string' ? comment : '' });
  }
  return out;
}

function readJson(key: string): unknown {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as unknown) : null;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore quota errors — the annotations just don't survive a reload */
  }
}

const sessionKey = (instanceId: string) => `vicoa:chat-annotations:${instanceId}`;

export function loadSessionAnnotations(instanceId: string): ChatAnnotation[] {
  return parseAnnotations(readJson(sessionKey(instanceId)));
}

export function saveSessionAnnotations(instanceId: string, annotations: ChatAnnotation[]): void {
  writeJson(sessionKey(instanceId), annotations.length > 0 ? annotations : null);
}

/** What "Continue in new session" leaves for the new-session page. */
const HANDOFF_KEY = 'vicoa:annotation-handoff';

export function saveAnnotationHandoff(annotations: ChatAnnotation[]): void {
  writeJson(HANDOFF_KEY, annotations.length > 0 ? annotations : null);
}

export function loadAnnotationHandoff(): ChatAnnotation[] {
  return parseAnnotations(readJson(HANDOFF_KEY));
}

export function clearAnnotationHandoff(): void {
  writeJson(HANDOFF_KEY, null);
}
