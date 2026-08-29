'use client';

import type { ReactNode } from 'react';
import { Bot, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { MessageResponse } from '@/lib/backend-api';

/**
 * A sub-agent (Task tool) activity group: a collapsible "Sub-agent: <type>"
 * header wrapping the messages the sub-agent produced while it ran, indented
 * beneath it. Mirrors `ToolUseGroup`'s collapse mechanics and indent classes
 * (tool-use-display.tsx) exactly, but delegates rendering each child message
 * to the caller via `renderMessage` — a sub-agent's children are arbitrary
 * chat messages (text, tool-use, options, ...) that need the full
 * `MessageItem` treatment, not a single-purpose `ToolUseLine`. `MessageItem`
 * lives in the instance page (it needs page-level callbacks/state), so this
 * component stays decoupled from it to avoid a circular import.
 */
export function SubagentGroup({
  messages,
  subagentType,
  description,
  expanded,
  onToggle,
  renderMessage,
}: {
  messages: MessageResponse[];
  subagentType: string;
  description: string;
  expanded: boolean;
  onToggle: () => void;
  renderMessage: (message: MessageResponse) => ReactNode;
}) {
  const headerLabel = `Sub-agent: ${subagentType}`;

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full min-w-0 items-center gap-1.5 rounded -mx-0.5 px-0.5 py-0.5 text-left cursor-pointer hover:bg-muted/40"
      >
        <Bot className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" aria-hidden="true" />
        <span className="min-w-0 shrink-0 text-muted-foreground">{headerLabel}</span>
        {description && (
          <span className="min-w-0 truncate text-muted-foreground" title={description}>
            {description}
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
        <div className="ml-1.5 mt-1.5 space-y-1 border-l border-border/40 pl-2.5">
          {messages.map((message) => (
            <div key={message.id}>{renderMessage(message)}</div>
          ))}
        </div>
      )}
    </div>
  );
}
