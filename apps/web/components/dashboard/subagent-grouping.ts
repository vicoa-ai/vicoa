import type { MessageResponse } from '@/lib/backend-api';

/**
 * Pure parsing/bucketing for sub-agent (Task tool) activity.
 *
 * The backend tags every child message a sub-agent produces with
 * `message_metadata.subagent = { tool_use_id, subagent_type, description, role }`
 * (see `integrations/headless/subagent.py`). `tool_use_id` is the id of the
 * launching `Task` block, so it's the group key: every message stamped with
 * the same `tool_use_id` belongs to the same sub-agent run, however it's
 * interleaved with other messages (including a second, parallel sub-agent's
 * messages) in the flat stream.
 *
 * Kept JSX-free so it's unit-testable without a DOM (mirrors
 * `tool-use-parsing.ts` / `session-grouping.ts`).
 */

export interface SubagentPayload {
  toolUseId: string;
  subagentType: string;
  description: string;
}

/** Read a message's `message_metadata.subagent` payload, or null when absent
    / malformed. Mirrors `parseAskUserQuestionPayload` (ask-user-question-panel.tsx). */
export function parseSubagentPayload(message: MessageResponse): SubagentPayload | null {
  const metadata = message.message_metadata as Record<string, unknown> | null | undefined;
  const raw = metadata?.subagent as Record<string, unknown> | undefined;
  if (!raw || typeof raw !== 'object') {
    return null;
  }

  const toolUseId = typeof raw.tool_use_id === 'string' ? raw.tool_use_id : '';
  if (!toolUseId) {
    return null;
  }

  const subagentTypeRaw = typeof raw.subagent_type === 'string' ? raw.subagent_type.trim() : '';
  const descriptionRaw = typeof raw.description === 'string' ? raw.description : '';

  return {
    toolUseId,
    subagentType: subagentTypeRaw || 'agent',
    description: descriptionRaw,
  };
}

export type SubagentBucketItem =
  | { type: 'message'; message: MessageResponse; key: string }
  | {
      type: 'subagent-group';
      messages: MessageResponse[];
      subagentType: string;
      description: string;
      key: string;
    };

/**
 * Bucket messages by `subagent.tool_use_id`, anchored at each group's FIRST
 * occurrence — not a consecutive-run grouping. This is what makes interleaved
 * parallel sub-agents (messages with different `tool_use_id`s interspersed)
 * form separate groups, each positioned where its first message appeared,
 * rather than one being swallowed into the other or the ordering breaking.
 *
 * Non-subagent messages pass through untouched, in place, as `{type:'message'}`
 * items — callers that also need tool-use-run collapsing (page.tsx's
 * `chatItems`) run that as a second pass over this function's output, since a
 * subagent-group is an opaque boundary for that collapsing (like an
 * interactive message), not a message to fold into a flat tool run.
 */
export function groupSubagents(messages: MessageResponse[]): SubagentBucketItem[] {
  const items: SubagentBucketItem[] = [];
  const groupIndexByToolUseId = new Map<string, number>();

  for (const message of messages) {
    const payload = parseSubagentPayload(message);
    if (!payload) {
      items.push({ type: 'message', message, key: message.id });
      continue;
    }

    const { toolUseId, subagentType, description } = payload;
    const existingIndex = groupIndexByToolUseId.get(toolUseId);
    if (existingIndex === undefined) {
      groupIndexByToolUseId.set(toolUseId, items.length);
      items.push({
        type: 'subagent-group',
        messages: [message],
        subagentType,
        description,
        key: `subagent-${toolUseId}`,
      });
      continue;
    }

    const existing = items[existingIndex];
    // Always true (we only ever record subagent-group indexes above), but
    // narrow for TS.
    if (existing.type === 'subagent-group') {
      existing.messages.push(message);
      // The launching Task block's `description` — read from the very first
      // step message we saw for this id — is treated as canonical; later
      // steps carry the same label. Fall back to a later non-empty value only
      // if the anchor message happened to have none.
      if (!existing.description && description) {
        existing.description = description;
      }
    }
  }

  return items;
}
