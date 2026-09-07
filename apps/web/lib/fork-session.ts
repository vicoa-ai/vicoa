/**
 * Forking a session: capture the transcript up to a chosen agent message and
 * hand it to the new-session page as a chat-history attachment, so a new
 * session starts with the old conversation as context instead of a blank slate.
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

const FORK_KEY = 'vicoa:fork-context';

/** Longest a single transcript entry may be before it is elided. */
const MAX_ENTRY_CHARS = 4000;
/** Overall budget; older entries are dropped first so the fork keeps the tail. */
const MAX_TOTAL_CHARS = 120_000;

const USER_SENDER_TYPES = new Set(['user', 'human', 'USER', 'HUMAN']);

export interface ForkContext {
  /** The `<chat-history>` block prepended to the new session's first message. */
  text: string;
  /** Transcript entries the block covers — the composer chip's "N messages". */
  messageCount: number;
  /** Session the fork came from, for the chip's label/tooltip. */
  sourceInstanceId: string;
  sourceTitle: string;
}

function clampEntry(text: string): string {
  if (text.length <= MAX_ENTRY_CHARS) return text;
  return `${text.slice(0, MAX_ENTRY_CHARS)}\n… (truncated)`;
}

/** One line for a tool-use message: the action, never its output. */
function formatToolEntry(message: MessageResponse, agentType: ToolUseAgentType): string | null {
  const parsed = parseToolUse(message.content, agentType);
  if (!parsed) return null;
  const description = parsed.toolDescription.split('\n')[0].replace(/`/g, '').trim();
  const label = [parsed.toolName, description].filter(Boolean).join(' ').trim();
  return label ? `Agent (tool): ${label}` : null;
}

function formatEntry(message: MessageResponse, agentType: ToolUseAgentType): string | null {
  // Reasoning blocks are the model's scratchpad, not conversation — a fresh
  // agent has its own, so carrying them over is noise.
  if (parseThinkingPayload(message)) return null;
  if (shouldHideControlMessage(message)) return null;

  const isUser = USER_SENDER_TYPES.has(message.sender_type);
  if (!isUser) {
    const tool = formatToolEntry(message, agentType);
    if (tool) return tool;
  }
  const text = getMessageVisibleText(message).trim();
  if (!text || text === 'Waiting for your input...') return null;
  return `${isUser ? 'User' : 'Agent'}: ${clampEntry(text)}`;
}

/**
 * Render the transcript up to and including `boundaryMessageId` as the text
 * block a forked session opens with. An unknown boundary id (the message was
 * pruned mid-click) falls back to the whole timeline rather than failing.
 */
export function buildForkTranscript(input: {
  messages: MessageResponse[];
  boundaryMessageId: string;
  agentType: ToolUseAgentType;
  sourceTitle?: string | null;
  sourceDirectory?: string | null;
}): { text: string; messageCount: number } {
  const boundaryIndex = input.messages.findIndex((m) => m.id === input.boundaryMessageId);
  const selected = input.messages.slice(0, boundaryIndex >= 0 ? boundaryIndex + 1 : undefined);

  const entries: string[] = [];
  for (const message of selected) {
    const entry = formatEntry(message, input.agentType);
    if (entry) entries.push(entry);
  }

  // Trim from the front — the messages nearest the fork point are the ones the
  // new session actually needs.
  let total = entries.reduce((sum, entry) => sum + entry.length + 1, 0);
  let dropped = 0;
  while (entries.length > 1 && total > MAX_TOTAL_CHARS) {
    total -= entries[0].length + 1;
    entries.shift();
    dropped += 1;
  }
  if (dropped > 0) {
    entries.unshift(`… ${dropped} earlier message${dropped === 1 ? '' : 's'} omitted …`);
  }

  const header = ['Chat history from an earlier Vicoa session, for context.'];
  const title = input.sourceTitle?.trim();
  const directory = input.sourceDirectory?.trim();
  if (title) header.push(`Source session: ${title}`);
  if (directory) header.push(`Source directory: ${directory}`);

  const body = entries.length > 0 ? entries.join('\n') : 'No chat history to display.';
  return {
    text: `<chat-history>\n${header.join('\n')}\n\n${body}\n</chat-history>`,
    messageCount: entries.length - (dropped > 0 ? 1 : 0),
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
