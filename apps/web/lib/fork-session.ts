/**
 * Forking a session: capture the transcript up to a chosen agent message and
 * hand it to the new-session page as a chat-history attachment, so a new
 * session starts with the old conversation as context instead of a blank slate.
 *
 * The block carries the *conversation* — user and agent prose — and, per turn,
 * one line naming the files the agent edited. The tool trail itself (Bash,
 * Read, Grep, sub-agents …) is left out: measured on real sessions it is
 * 92–99 % of the transcript by volume and says nothing the agent's prose does
 * not, and a bare "Read x" line tempts the new agent into believing it has
 * seen the file. The header tells it to re-read instead.
 *
 * The payload rides sessionStorage rather than the URL — a transcript is orders
 * of magnitude too big for a query string — and is consumed on the first
 * successful spawn (a reload of `?fork=1` re-reads it, so the chip survives).
 */

import { MessageResponse } from '@/lib/backend-api';
import { getMessageVisibleText } from '@/components/dashboard/chat-message-item';
import { parseToolUse, type ToolUseAgentType } from '@/components/dashboard/tool-use-parsing';
import { parseThinkingPayload } from '@/components/dashboard/thinking-card';
import { shouldHideControlMessage } from '@/lib/session-control-messages';
import { groupTurns, type TurnMessageKind } from '@/lib/agent-turns';

const FORK_KEY = 'vicoa:fork-context';

/** Longest a single transcript entry may be before it is elided. */
export const MAX_ENTRY_CHARS = 8000;
/** Overall budget; older entries are dropped first so the fork keeps the tail. */
export const MAX_TOTAL_CHARS = 120_000;
/** Paths listed on a turn's `[edited: …]` line before it says `+N more`. */
export const MAX_EDITED_PATHS = 20;

const USER_SENDER_TYPES = new Set(['user', 'human', 'USER', 'HUMAN']);

/**
 * Tool names whose row means "the agent changed this file", lower-cased. Only
 * these feed the `[edited: …]` line; every other tool is dropped, and an
 * unknown name is never guessed at — a missed path costs nothing, a wrong one
 * misleads. Sources: Claude Code (and Antigravity, whose cards reuse the same
 * formatter), Codex `fileChange` items (Write/Edit; multi-file → ApplyPatch;
 * the older `✏️ Applying patch` row → Edited), ACP `edit` kind, pi-family
 * `write`/`edit`, and the lower-case spellings other ACP agents use.
 */
const EDIT_TOOL_NAMES = new Set([
  'edit',
  'multiedit',
  'write',
  'notebookedit',
  'applypatch',
  'edited',
  'edit_file',
  'write_file',
  'create_file',
  'apply_patch',
]);

export interface ForkContext {
  /** The `<chat-history>` block prepended to the new session's first message. */
  text: string;
  /** Transcript entries the block covers — the composer chip's "N messages". */
  messageCount: number;
  /** Entries dropped from the front to fit the budget, for the chip's tooltip. */
  omittedCount?: number;
  /** Session the fork came from, for the chip's label/tooltip. */
  sourceInstanceId: string;
  sourceTitle: string;
}

function clampEntry(text: string): string {
  if (text.length <= MAX_ENTRY_CHARS) return text;
  return `${text.slice(0, MAX_ENTRY_CHARS)}\n… (truncated)`;
}

function looksLikePath(token: string): boolean {
  return token.includes('/') || token.includes('\\') || /\.[A-Za-z0-9]{1,8}$/.test(token);
}

/**
 * File paths named by an edit-class tool row's description. The formatters put
 * the path in backticks, so a whitespace-free span is taken as-is (Codex's
 * multi-file ApplyPatch lists several). A span with spaces — an ACP title like
 * `Writing to src/a.ts`, or a pi `intent` with no backticks at all — yields
 * its first path-looking token, or nothing.
 */
export function extractEditedPaths(description: string): string[] {
  const firstLine = description.split('\n')[0];
  const spans = [...firstLine.matchAll(/`([^`]+)`/g)].map((m) => m[1].trim());
  const candidates = spans.length > 0 ? spans : [firstLine.trim()];
  const paths: string[] = [];
  for (const candidate of candidates) {
    if (!candidate || candidate.startsWith('{') || candidate.startsWith('[')) continue;
    if (!/\s/.test(candidate)) {
      paths.push(candidate);
      continue;
    }
    for (const token of candidate.split(/\s+/)) {
      const cleaned = token.replace(/^[('"[]+/, '').replace(/[)'",;:.\]]+$/, '');
      if (cleaned && looksLikePath(cleaned)) {
        paths.push(cleaned);
        break;
      }
    }
  }
  return paths;
}

/** `/repo/src/a.ts` → `src/a.ts` when the path sits under the source directory. */
function relativeToSource(path: string, sourceDirectory: string | undefined): string {
  if (!sourceDirectory) return path;
  const base = sourceDirectory.replace(/\/+$/, '');
  if (!base) return path;
  if (path === base) return '.';
  return path.startsWith(`${base}/`) ? path.slice(base.length + 1) : path;
}

function formatEditedLine(paths: string[]): string {
  const shown = paths.slice(0, MAX_EDITED_PATHS);
  const more = paths.length - shown.length;
  return `  [edited: ${shown.join(', ')}${more > 0 ? `, … +${more} more` : ''}]`;
}

interface ForkEntry {
  kind: TurnMessageKind;
  message: MessageResponse;
  /** Set on tool rows: the files this row edited, if it is an edit-class tool. */
  edited: string[];
}

function classify(message: MessageResponse, agentType: ToolUseAgentType): ForkEntry | null {
  // Reasoning blocks are the model's scratchpad, not conversation — a fresh
  // agent has its own, so carrying them over is noise.
  if (parseThinkingPayload(message)) return null;
  if (shouldHideControlMessage(message)) return null;
  if (USER_SENDER_TYPES.has(message.sender_type)) {
    return { kind: 'user', message, edited: [] };
  }
  const tool = parseToolUse(message.content, agentType);
  if (tool) {
    const edited = EDIT_TOOL_NAMES.has(tool.toolName.trim().toLowerCase())
      ? extractEditedPaths(tool.toolDescription)
      : [];
    return { kind: 'other', message, edited };
  }
  return { kind: 'agent', message, edited: [] };
}

function proseText(message: MessageResponse): string | null {
  const text = getMessageVisibleText(message).trim();
  if (!text || text === 'Waiting for your input...') return null;
  return text;
}

interface TranscriptEntry {
  text: string;
  /** Counts toward the chip's "N messages" (a standalone edited line does not). */
  isMessage: boolean;
}

/**
 * Render the transcript up to and including `boundaryMessageId` as the text
 * block a forked session opens with. An unknown boundary id (the message was
 * pruned mid-click) falls back to the whole timeline rather than failing.
 *
 * Callers must hand in the *whole* history up to the boundary — the block is
 * trimmed to budget from the front here, and that trim is the only place
 * earlier messages should go missing.
 */
export function buildForkTranscript(input: {
  messages: MessageResponse[];
  boundaryMessageId: string;
  agentType: ToolUseAgentType;
  sourceTitle?: string | null;
  sourceDirectory?: string | null;
}): { text: string; messageCount: number; omittedCount: number } {
  const boundaryIndex = input.messages.findIndex((m) => m.id === input.boundaryMessageId);
  const selected = input.messages.slice(0, boundaryIndex >= 0 ? boundaryIndex + 1 : undefined);
  const directory = input.sourceDirectory?.trim() || undefined;

  const classified: ForkEntry[] = [];
  for (const message of selected) {
    const entry = classify(message, input.agentType);
    if (entry) classified.push(entry);
  }

  const entries: TranscriptEntry[] = [];
  for (const turn of groupTurns(classified)) {
    const userText = turn.user ? proseText(turn.user.message) : null;
    if (userText) entries.push({ text: `User: ${clampEntry(userText)}`, isMessage: true });

    const turnStart = entries.length;
    const edited: string[] = [];
    const seen = new Set<string>();
    for (const entry of turn.entries) {
      if (entry.kind === 'agent') {
        const text = proseText(entry.message);
        if (text) entries.push({ text: `Agent: ${clampEntry(text)}`, isMessage: true });
        continue;
      }
      for (const path of entry.edited) {
        const shown = relativeToSource(path, directory);
        if (seen.has(shown)) continue;
        seen.add(shown);
        edited.push(shown);
      }
    }
    if (edited.length === 0) continue;
    // The line rides on the turn's last prose entry so a budget trim never
    // separates the two; a turn that only edited (no prose) still gets it.
    const line = formatEditedLine(edited);
    if (entries.length > turnStart) {
      const last = entries[entries.length - 1];
      last.text = `${last.text}\n${line}`;
    } else {
      entries.push({ text: line, isMessage: false });
    }
  }

  // Trim from the front — the messages nearest the fork point are the ones the
  // new session actually needs.
  let total = entries.reduce((sum, entry) => sum + entry.text.length + 1, 0);
  let omitted = 0;
  while (entries.length > 1 && total > MAX_TOTAL_CHARS) {
    const [first] = entries.splice(0, 1);
    total -= first.text.length + 1;
    if (first.isMessage) omitted += 1;
  }
  const lines = entries.map((entry) => entry.text);
  if (omitted > 0) {
    lines.unshift(`… ${omitted} earlier message${omitted === 1 ? '' : 's'} omitted …`);
  }

  const header = [
    'Chat history from an earlier Vicoa session, for context.',
    'Tool outputs are not included; re-read any file you need.',
  ];
  const title = input.sourceTitle?.trim();
  if (title) header.push(`Source session: ${title}`);
  if (directory) header.push(`Source directory: ${directory}`);

  const body = lines.length > 0 ? lines.join('\n') : 'No chat history to display.';
  return {
    text: `<chat-history>\n${header.join('\n')}\n\n${body}\n</chat-history>`,
    messageCount: entries.filter((entry) => entry.isMessage).length,
    omittedCount: omitted,
  };
}

export function saveForkContext(context: ForkContext): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(FORK_KEY, JSON.stringify(context));
  } catch {
    /* ignore quota errors — the fork just starts without its history */
  }
}

export function loadForkContext(): ForkContext | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(FORK_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ForkContext>;
    if (typeof parsed?.text !== 'string' || !parsed.text) return null;
    return {
      text: parsed.text,
      messageCount: typeof parsed.messageCount === 'number' ? parsed.messageCount : 0,
      omittedCount: typeof parsed.omittedCount === 'number' ? parsed.omittedCount : 0,
      sourceInstanceId: typeof parsed.sourceInstanceId === 'string' ? parsed.sourceInstanceId : '',
      sourceTitle: typeof parsed.sourceTitle === 'string' ? parsed.sourceTitle : '',
    };
  } catch {
    return null;
  }
}

export function clearForkContext(): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(FORK_KEY);
  } catch {
    /* ignore */
  }
}
