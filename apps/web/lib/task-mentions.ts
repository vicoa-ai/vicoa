/**
 * Agent mentions in task comments, and who a comment would wake.
 *
 * A mention is the markdown link the comment box's `@` picker inserts,
 * `[@Name](vicoa://agent/<profile id>)`. Plain typed "@name" is not one: a
 * mention starts a run on someone's computer, so it has to be a deliberate pick.
 *
 * `agentsToWake` mirrors the server's routing (`shared/task_dispatch.py`,
 * `route_comment`) so the hint under the box says what sending will do:
 *
 * 1. a comment starting with `/note` wakes nobody;
 * 2. explicit mentions wake those agents, and nothing else (on a Done or
 *    Cancelled task, a mention is the only thing that wakes anyone);
 * 3. a reply in a thread an agent wrote in wakes that agent;
 * 4. a top-level comment on a task assigned to an agent wakes that agent.
 *
 * The server stays the authority: this only predicts it for the hint.
 */

const UUID = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
const HREF_RE = new RegExp(`^vicoa://agent/(${UUID})$`);
const BODY_RE = new RegExp(`\\(vicoa://agent/(${UUID})\\)`, 'g');
const NOTE_PREFIX = '/note';

export function agentMentionHref(profileId: string): string {
  return `vicoa://agent/${profileId}`;
}

/** The link the `@` picker writes. Brackets in a name would end the link text early. */
export function agentMentionMarkdown(name: string, profileId: string): string {
  const safe = name.replace(/[[\]]/g, '');
  return `[@${safe}](${agentMentionHref(profileId)})`;
}

/** The profile id an href names, or null when it is not an agent mention. */
export function parseAgentMentionHref(href: string | null | undefined): string | null {
  const match = HREF_RE.exec((href ?? '').trim());
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

export interface WakeContext {
  /** The box replies inside a thread (vs. starting a new one). */
  inThread: boolean;
  /** In a thread: the agent that wrote in it most recently. */
  threadAgentId: string | null;
  /** The task's assignee, when it is an agent. */
  assigneeAgentId: string | null;
  /** The task is Done or Cancelled: only an explicit mention wakes an agent. */
  taskClosed?: boolean;
}

/** The agent profile ids sending `body` would wake (see the module header). */
export function agentsToWake(body: string, ctx: WakeContext): string[] {
  if (!body.trim() || isNoteComment(body)) return [];
  const mentioned = mentionedAgentIds(body);
  if (mentioned.length > 0) return mentioned;
  if (ctx.taskClosed) return [];
  if (ctx.inThread) return ctx.threadAgentId ? [ctx.threadAgentId.toLowerCase()] : [];
  return ctx.assigneeAgentId ? [ctx.assigneeAgentId.toLowerCase()] : [];
}

// --- The composer's side: `@Name` text plus the picks behind it -----------------
//
// The same split as `#` references (lib/composer-references): the box shows
// plain `@Name`, which the user edits like any text, and the pick (name + id)
// is composer state. A pick counts only while its `@Name` is still in the text,
// so deleting the name drops the mention. Only on send does each picked
// `@Name` become the `[@Name](vicoa://agent/<id>)` link the server routes on.

/** An agent picked from the `@` list, carried beside the draft until sent. */
export interface PickedMention {
  id: string;
  name: string;
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
  const byId = new Map(picks.map((p) => [p.id, p.name]));
  let out = '';
  let cursor = 0;
  for (const range of ranges) {
    out += text.slice(cursor, range.start);
    out += agentMentionMarkdown(byId.get(range.id) ?? '', range.id);
    cursor = range.end;
  }
  return out + text.slice(cursor);
}

/** The note body without its `/note` prefix, for display. */
export function stripNotePrefix(body: string): string {
  const trimmed = body.trimStart();
  return trimmed.slice(NOTE_PREFIX.length).replace(/^[\s:]+/, '');
}
