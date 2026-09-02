'use client';

import { useState } from 'react';
import { Brain, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MessageMarkdown } from '@/components/ui/message-markdown';
import type { MessageResponse } from '@/lib/backend-api';

/**
 * A collapsed "Thinking" card for a model-reasoning message.
 *
 * The backend tags a reasoning row with
 * `message_metadata.thinking = { source }` (see
 * `integrations/headless/thinking.py`) — Claude `ThinkingBlock`s and Codex
 * `reasoning` items both land here. The reasoning text rides in the row
 * `content`; this card wraps it in a collapse (mirroring `SubagentGroup`'s
 * chrome) so reasoning is available but never floods the transcript.
 */

// Kept structural (not imported from chat-message-item) to avoid a circular
// import — chat-message-item imports this module.
type UiAgentType = 'claude' | 'codex' | 'opencode';

export interface ThinkingPayload {
  source: string;
}

/** Read a message's `message_metadata.thinking` payload, or null when absent /
    malformed. Mirrors `parseSubagentPayload` (subagent-grouping.ts). */
export function parseThinkingPayload(message: MessageResponse): ThinkingPayload | null {
  const metadata = message.message_metadata as Record<string, unknown> | null | undefined;
  const raw = metadata?.thinking as Record<string, unknown> | undefined;
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const source = typeof raw.source === 'string' ? raw.source : '';
  return { source };
}

// Codex prefixes reasoning with a "Reasoning:" label (kept in `content` so
// pre-card clients still show it inline). Inside the card the header already
// says "Thinking", so strip the redundant prefix for display. The optional
// "🧠 " covers older daemons that still emit the emoji label.
function displayBody(content: string): string {
  return content.replace(/^\s*(?:🧠\s*)?Reasoning:\s*\n?/, '').trim() || content;
}

/** Controlled collapse — expansion state owned by the caller. */
export function ThinkingCard({
  content,
  agentType,
  expanded,
  onToggle,
}: {
  content: string;
  agentType: UiAgentType;
  expanded: boolean;
  onToggle: () => void;
}) {
  const body = displayBody(content);
  const preview = body.split('\n').find((line) => line.trim())?.trim() ?? '';

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full min-w-0 items-center gap-1.5 rounded -mx-0.5 px-0.5 py-0.5 text-left cursor-pointer hover:bg-muted/40"
      >
        <Brain className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" aria-hidden="true" />
        <span className="min-w-0 shrink-0 text-muted-foreground">Thinking</span>
        {!expanded && preview && (
          <span className="min-w-0 truncate italic text-muted-foreground/70" title={preview}>
            {preview}
          </span>
        )}
        <ChevronRight
          className={cn(
            'h-3.5 w-3.5 shrink-0 text-muted-foreground/60 transition-transform',
            expanded && 'rotate-90',
          )}
        />
      </button>
      {expanded && (
        <div className="ml-1.5 mt-1.5 border-l border-border/40 pl-2.5 italic text-muted-foreground">
          <div className="markdown-content">
            <MessageMarkdown agentType={agentType}>{body}</MessageMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

/** Self-contained variant with local expansion state — for use in `MessageItem`,
    which owns no page-level expansion set. Collapsed by default; a Virtuoso
    recycle re-collapses (acceptable for secondary reasoning content, matching
    `StandaloneToolUse`). */
export function StandaloneThinkingCard({
  content,
  agentType,
}: {
  content: string;
  agentType: UiAgentType;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <ThinkingCard
      content={content}
      agentType={agentType}
      expanded={expanded}
      onToggle={() => setExpanded((current) => !current)}
    />
  );
}
