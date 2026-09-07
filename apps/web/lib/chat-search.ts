/**
 * Searchable text for find-in-conversation.
 *
 * The find bar searches the in-memory transcript rather than the DOM, so it
 * must look at everything a row would show once fully expanded — otherwise
 * text that only appears after expanding a collapsed tool use / sub-agent /
 * thinking row is unfindable. `getMessageVisibleText` alone covers only the
 * prose of a plain message; these helpers add the tool-use detail (command,
 * output, diff) and the grouped rows' children.
 */

import type { MessageResponse } from '@/lib/backend-api';
import { getMessageVisibleText } from '@/components/dashboard/chat-message-item';
import {
  isToolUseContent,
  parseToolUse,
  type ToolUseAgentType,
} from '@/components/dashboard/tool-use-parsing';

/**
 * Structural shape of the instance page's `ChatItem` union — only the fields
 * that carry text. Kept minimal so the page's richer items (which also carry
 * `key`/`date`) assign to it without importing page-level types here.
 */
export type SearchableChatItem =
  | { type: 'separator' }
  | { type: 'thinking' }
  | { type: 'message'; message: MessageResponse }
  | { type: 'tool-group'; messages: MessageResponse[] }
  | { type: 'subagent-group'; messages: MessageResponse[]; subagentType: string; description: string };

/**
 * Everything one message contributes to find: its visible prose, plus — for a
 * tool use — the tool name, the full command/path and the detail hidden behind
 * the collapsed row.
 */
export function getMessageSearchText(message: MessageResponse, agentType: ToolUseAgentType): string {
  const visible = getMessageVisibleText(message);
  if (!isToolUseContent(visible)) return visible;
  const parsed = parseToolUse(visible, agentType);
  // Unparseable tool-ish content renders as raw markdown, so search it as-is.
  if (!parsed) return visible;
  return [parsed.toolName, parsed.toolDescription, parsed.remainingContent]
    .filter((part) => part.trim() !== '')
    .join('\n');
}

/** The same, for a whole chat item — groups fold in every child they hide. */
export function getChatItemSearchText(item: SearchableChatItem, agentType: ToolUseAgentType): string {
  switch (item.type) {
    case 'message':
      return getMessageSearchText(item.message, agentType);
    case 'tool-group':
      return item.messages.map((message) => getMessageSearchText(message, agentType)).join('\n');
    case 'subagent-group':
      return [
        item.subagentType,
        item.description,
        ...item.messages.map((message) => getMessageSearchText(message, agentType)),
      ]
        .filter((part) => part.trim() !== '')
        .join('\n');
    default:
      // Separators and the "thinking" indicator carry no searchable text.
      return '';
  }
}

/** True when `text` contains `needle` (already lowercased, non-empty). */
export function matchesNeedle(text: string, needle: string): boolean {
  return needle !== '' && text.toLowerCase().includes(needle);
}
