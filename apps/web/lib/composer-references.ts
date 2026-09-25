/** `#` references — pointing the current session at another Vicoa thing.
 *
 * `@` mentions a file; `#` mentions a *session*, *task* or *automation*. The
 * two halves of the feature live apart on purpose:
 *
 *  * The **token** (`#VIC-42`) is what the user sees and edits. It is plain
 *    text in the message, so deleting it is just deleting text.
 *  * The **reference** (kind + id + the expanded context block) is composer
 *    state the textarea never sees, fetched once when the row is picked.
 *
 * Nothing re-parses the token to find the entity again — a title-derived slug
 * is not a stable key. `activeReferences` reconciles the two by presence
 * instead: a reference counts only while its token is still somewhere in the
 * text. That makes "select the token and hit backspace" drop the attachment,
 * which is the one interaction a user will reach for without being told.
 *
 * Lives outside `components/chat-input.tsx` so it can be unit-tested — the
 * vitest setup runs in the `node` environment and cannot render components.
 */

import type {
  ReferenceCandidate,
  ReferenceDetail,
  ReferenceKind,
} from '@/lib/backend-api';

/** A picked reference, carried alongside the draft until it is sent. */
export interface ComposerReference {
  kind: ReferenceKind;
  id: string;
  /** Text after "#", e.g. `VIC-42`. Whitespace-free by construction. */
  token: string;
  label: string;
  /** The rendered block; empty when the expansion fetch failed. */
  context: string;
}

export function toComposerReference(detail: ReferenceDetail): ComposerReference {
  return {
    kind: detail.kind,
    id: detail.id,
    token: detail.token,
    label: detail.label,
    context: detail.context,
  };
}

const KIND_NOUN: Record<ReferenceKind, string> = {
  session: 'Session',
  task: 'Task',
  automation: 'Automation',
};

/**
 * The one line a reference is worth before its expansion arrives.
 *
 * A pick inserts its token instantly and fetches the full block behind it, so
 * a send in that window — or after a failed fetch — would otherwise ship a
 * `#token` the agent has no way to resolve. This keeps the message honest
 * with what the picker already knew.
 */
export function fallbackReferenceContext(item: ReferenceCandidate): string {
  const noun = KIND_NOUN[item.kind];
  const facts = [item.meta, `id: ${item.id}`].filter(Boolean).join(' · ');
  return `${noun} "${item.label}"\n${facts}`;
}

export function candidateToComposerReference(
  item: ReferenceCandidate,
): ComposerReference {
  return {
    kind: item.kind,
    id: item.id,
    token: item.token,
    label: item.label,
    context: fallbackReferenceContext(item),
  };
}

/** The trigger token the caret currently sits in, or null. */
export interface TriggerToken {
  /** Index of the trigger character itself. */
  start: number;
  /** Index just past the token (exclusive) — the first whitespace, or EOL. */
  end: number;
  /** Everything between the trigger and `end`. */
  query: string;
}

/**
 * Find the `trigger`-led token the caret is inside.
 *
 * The rules match the `@` detection in `mention-textarea.tsx`, so `@` and `#`
 * can never both claim the caret: the trigger must start the text or follow
 * whitespace, and the caret must sit within the token it opens.
 */
export function detectTriggerToken(
  text: string,
  cursor: number,
  trigger: string,
): TriggerToken | null {
  const start = text.lastIndexOf(trigger, Math.max(0, cursor - 1));
  if (start === -1) return null;

  const after = text.slice(start + 1);
  const whitespaceIndex = after.search(/\s/);
  const end = whitespaceIndex === -1 ? text.length : start + 1 + whitespaceIndex;
  if (cursor < start || cursor > end) return null;
  if (start !== 0 && !/\s/.test(text[start - 1])) return null;

  return { start, end, query: text.slice(start + 1, end) };
}

/** Replace `token`'s slice with `#<value>`, leaving the caret after it. */
export function replaceTriggerToken(
  text: string,
  token: TriggerToken,
  trigger: string,
  value: string,
): { text: string; cursor: number } {
  const before = text.slice(0, token.start);
  const after = text.slice(token.end);
  const needsSpace = after === '' || !after.startsWith(' ');
  const inserted = `${trigger}${value}${needsSpace ? ' ' : ''}`;
  return {
    text: `${before}${inserted}${after}`,
    cursor: before.length + inserted.length,
  };
}

/**
 * Add a pick, replacing any earlier reference that produced the same token.
 *
 * Two entities can slugify alike ("Fix the bug" twice). Keeping both would
 * make `activeReferences` attach two blocks for one visible token, so the
 * newest pick wins — which is also what the user just pointed at.
 */
export function addReference(
  refs: ComposerReference[],
  next: ComposerReference,
): ComposerReference[] {
  return [...refs.filter((r) => r.token !== next.token), next];
}

/** The references whose token still appears in the draft. */
export function activeReferences(
  refs: ComposerReference[],
  text: string,
): ComposerReference[] {
  return refs.filter((ref) => text.includes(`#${ref.token}`));
}

const BLOCK_HEADER = 'Referenced with # in Vicoa:';

/**
 * The context block appended to the outgoing message.
 *
 * Sent as text rather than resolved by the agent on demand: the agent may have
 * no Vicoa CLI on its PATH, and even when it does, a reference the user typed
 * is context they have already decided is relevant — making the agent spend a
 * tool call to discover it is a worse trade than the tokens. Each block still
 * ends with the command to go deeper.
 */
export function buildReferenceBlock(refs: ComposerReference[]): string {
  const blocks = refs.map((ref) => ref.context.trim()).filter(Boolean);
  if (blocks.length === 0) return '';
  return [BLOCK_HEADER, '', blocks.join('\n\n')].join('\n');
}

/** Typed text + folder chips + reference blocks, in the order the agent reads. */
export function composeOutgoingMessage(
  body: string,
  refs: ComposerReference[],
): string {
  const block = buildReferenceBlock(refs);
  if (!block) return body;
  return body ? `${body}\n\n---\n${block}` : block;
}

/**
 * The task a send should file the session under, or null.
 *
 * One task, because `agent_instances.task_id` is a single column — referencing
 * a task is the same late link the Tasks board already draws, not a new
 * many-to-many. The *first* referenced task wins so the choice is the order
 * the user typed, and an existing link is never overwritten: a session that
 * already belongs to a task keeps it, and the extra reference still ships its
 * context. Silently re-filing someone's session is the one failure mode here
 * that loses data the UI doesn't show.
 */
export function taskLinkForSend(
  refs: ComposerReference[],
  currentTaskId: string | null | undefined,
): string | null {
  if (currentTaskId) return null;
  const task = refs.find((ref) => ref.kind === 'task');
  return task ? task.id : null;
}
