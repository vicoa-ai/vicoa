/**
 * Mentions in task comments, and who a comment would wake.
 *
 * A mention is the markdown link the comment box's `@` picker inserts:
 * `[@Name](vicoa://agent/<profile id>)` for an agent, `[@Name](vicoa://user/<user
 * id>)` for a person. Plain typed "@name" is not one: an agent mention starts a
 * run on someone's computer, and a person mention sends a push, so either has
 * to be a deliberate pick. A person mention only tells them; it wakes no agent.
 *
 * `agentsToWake` mirrors the server's routing (`shared/task_dispatch.py`,
 * `route_comment`) so the hint under the box says what sending will do:
 *
 * 1. a comment starting with `/note` wakes nobody;
 * 2. any other comment wakes the agents with an open question to the person
 *    writing it (their comment answers it), wherever on the task it is;
 * 3. explicit agent mentions wake those agents, and nothing else (on a Done or
 *    Cancelled task, a mention is the only thing that wakes anyone);
 * 4. a reply in a thread an agent wrote in wakes that agent;
 * 5. a top-level comment on a task assigned to an agent wakes that agent,
 *    unless an agent is waiting on the person writing it: then the comment
 *    is that agent's answer, and the assignee is not woken beside it.
 *
 * The server stays the authority: this only predicts it for the hint.
 */

const UUID = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
const HREF_RE = new RegExp(`^vicoa://agent/(${UUID})$`);
const BODY_RE = new RegExp(`\\(vicoa://agent/(${UUID})\\)`, 'g');
const USER_HREF_RE = new RegExp(`^vicoa://user/(${UUID})$`);
const NOTE_PREFIX = '/note';

/** Who a mention names. */
export type MentionKind = 'agent' | 'user';

export function agentMentionHref(profileId: string): string {
  return `vicoa://agent/${profileId}`;
}

export function userMentionHref(userId: string): string {
  return `vicoa://user/${userId}`;
}

/** The link the `@` picker writes. Brackets in a name would end the link text early. */
export function agentMentionMarkdown(name: string, profileId: string): string {
  return mentionMarkdown('agent', name, profileId);
}

export function mentionMarkdown(kind: MentionKind, name: string, id: string): string {
  const safe = name.replace(/[[\]]/g, '');
  const href = kind === 'user' ? userMentionHref(id) : agentMentionHref(id);
  return `[@${safe}](${href})`;
}

/** The profile id an href names, or null when it is not an agent mention. */
export function parseAgentMentionHref(href: string | null | undefined): string | null {
  const match = HREF_RE.exec((href ?? '').trim());
  return match ? match[1].toLowerCase() : null;
}

/** The user id an href names, or null when it is not a person mention. */
export function parseUserMentionHref(href: string | null | undefined): string | null {
  const match = USER_HREF_RE.exec((href ?? '').trim());
  return match ? match[1].toLowerCase() : null;
}

/** Profiles a body mentions, in order, each once. */
export function mentionedAgentIds(body: string): string[] {
  const out: string[] = [];
  for (const match of body.matchAll(BODY_RE)) {
    const id = match[1].toLowerCase();
    if (!out.includes(id)) out.push(id);
  }
  return out;
}

/** `/note` as a word at the very start ("/notebook" is not a note); mirrors the server's `is_note`. */
const NOTE_RE = /^\/note(?:\s|:|$)/i;

export function isNoteComment(body: string): boolean {
  return NOTE_RE.test(body.trimStart());
}

/** An agent waiting on the viewer: it asked them a question on this task. */
export interface WaitingAgent {
  id: string;
  name: string;
}

export interface WakeContext {
  /** The box replies inside a thread (vs. starting a new one). */
  inThread: boolean;
  /** In a thread: the agent that wrote in it most recently. */
  threadAgentId: string | null;
  /** The task's assignee, when it is an agent. */
  assigneeAgentId: string | null;
  /** The task is Done or Cancelled: only an explicit mention wakes an agent. */
  taskClosed?: boolean;
  /** Agents with an open question to the viewer on this task: whatever the
   *  viewer writes next (but a `/note`) answers them. */
  askers?: WaitingAgent[];
}

/** The agent profile ids sending `body` would wake (see the module header). */
export function agentsToWake(body: string, ctx: WakeContext): string[] {
  if (!body.trim() || isNoteComment(body)) return [];
  const out = (ctx.askers ?? []).map((a) => a.id.toLowerCase());
  const add = (ids: string[]) => {
    for (const id of ids) if (!out.includes(id)) out.push(id);
    return out;
  };
  const mentioned = mentionedAgentIds(body);
  if (mentioned.length > 0) return add(mentioned);
  if (ctx.taskClosed) return out;
  if (ctx.inThread) return add(ctx.threadAgentId ? [ctx.threadAgentId.toLowerCase()] : []);
  if (out.length > 0) return out;
  return add(ctx.assigneeAgentId ? [ctx.assigneeAgentId.toLowerCase()] : []);
}

// --- The composer's side: `@Name` text plus the picks behind it -----------------
//
// The same split as `#` references (lib/composer-references): the box shows
// plain `@Name`, which the user edits like any text, and the pick (name + id)
// is composer state. A pick counts only while its `@Name` is still in the text,
// so deleting the name drops the mention. Only on send does each picked
// `@Name` become the `[@Name](vicoa://agent/<id>)` (or `vicoa://user/<id>`)
// link the server routes on.

/** An agent or person picked from the `@` list, carried beside the draft until sent. */
export interface PickedMention {
  id: string;
  name: string;
  /** Default `agent`. */
  kind?: MentionKind;
}

/** What the box shows for a pick. Brackets would break the link on send. */
export function mentionToken(name: string): string {
  return `@${name.replace(/[[\]]/g, '')}`;
}

export interface MentionRange {
  start: number;
  end: number;
  id: string;
}

const isBoundaryBefore = (text: string, index: number) =>
  index === 0 || /\s|[(]/.test(text[index - 1]);
const isBoundaryAfter = (text: string, index: number) =>
  index >= text.length || /[\s.,;:!?)]/.test(text[index]);

/**
 * Where each picked `@Name` sits in `text`, left to right, never overlapping.
 * Longer names are tried first at a position, so `@bot2` is not read as
 * `@bot` followed by "2".
 */
export function mentionRanges(text: string, picks: PickedMention[]): MentionRange[] {
  const tokens = [...new Map(picks.map((p) => [mentionToken(p.name), p.id])).entries()].sort(
    (a, b) => b[0].length - a[0].length,
  );
  const ranges: MentionRange[] = [];
  let index = 0;
  while (index < text.length) {
    const at = text.indexOf('@', index);
    if (at === -1) break;
    let matched: MentionRange | null = null;
    if (isBoundaryBefore(text, at)) {
      for (const [token, id] of tokens) {
        const end = at + token.length;
        if (text.startsWith(token, at) && isBoundaryAfter(text, end)) {
          matched = { start: at, end, id };
          break;
        }
      }
    }
    if (matched) {
      ranges.push(matched);
      index = matched.end;
    } else {
      index = at + 1;
    }
  }
  return ranges;
}

/** The picks whose `@Name` is still in the text. */
export function activeMentions(picks: PickedMention[], text: string): PickedMention[] {
  const present = new Set(mentionRanges(text, picks).map((r) => r.id));
  return picks.filter((p) => present.has(p.id));
}

/** The body to post: each picked `@Name` written as its mention link. */
export function serializeMentions(text: string, picks: PickedMention[]): string {
  const ranges = mentionRanges(text, picks);
  if (ranges.length === 0) return text;
  const byId = new Map(picks.map((p) => [p.id, p]));
  let out = '';
  let cursor = 0;
  for (const range of ranges) {
    out += text.slice(cursor, range.start);
    const pick = byId.get(range.id);
    out += mentionMarkdown(pick?.kind ?? 'agent', pick?.name ?? '', range.id);
    cursor = range.end;
  }
  return out + text.slice(cursor);
}

/** The note body without its `/note` prefix, for display. */
export function stripNotePrefix(body: string): string {
  const trimmed = body.trimStart();
  return trimmed.slice(NOTE_PREFIX.length).replace(/^[\s:]+/, '');
}
