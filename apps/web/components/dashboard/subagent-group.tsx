'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { Bot, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { MessageResponse } from '@/lib/backend-api';
import { ToolRunSummary, ToolUseLine, parseToolUse, type ToolUseAgentType } from '@/components/dashboard/tool-use-display';
import { parseAskUserQuestionPayload } from '@/components/dashboard/ask-user-question-panel';
import { parseThinkingPayload } from '@/components/dashboard/thinking-card';
import { subagentGroupStatus } from '@/components/dashboard/subagent-grouping';

/**
 * A sub-agent (Task tool) activity group: a collapsible "Sub-agent: <type>"
 * header wrapping what the sub-agent did while it ran.
 *
 * The header is deliberately the same row a collapsed `ToolUseGroup` draws —
 * icon, aggregate action label ("Run 2 commands, edit 2 files"), then a chip
 * per edited file carrying its `+N -M` and a hover diff preview. A sub-agent
 * that rewrote three files used to announce itself as one line of text naming
 * neither the work nor the files, so its edits were invisible until you
 * expanded the group and then expanded a row inside it.
 *
 * Collapsed, it is that one row and nothing else — the same affordance a tool
 * group has. Expanded, its children render in chat order, ending with the
 * sub-agent's settled report.
 *
 * Rendering each child is delegated to the caller via `renderMessage` — a
 * sub-agent's children are arbitrary chat messages (text, thinking cards,
 * options, ...) that need the full `MessageItem` treatment. `MessageItem`
 * lives in the instance page (it needs page-level callbacks/state), so this
 * component stays decoupled from it to avoid a circular import. Runs of
 * consecutive tool uses are the exception: they render here as fused
 * `ToolUseLine`s, exactly like an expanded `ToolUseGroup`, so a sub-agent's
 * work reads the same as the main agent's.
 */
export function SubagentGroup({
  messages,
  subagentType,
  description,
  expanded,
  onToggle,
  renderMessage,
  agentType,
  projectPath,
}: {
  messages: MessageResponse[];
  subagentType: string;
  description: string;
  expanded: boolean;
  onToggle: () => void;
  renderMessage: (message: MessageResponse) => ReactNode;
  agentType: ToolUseAgentType;
  /** Project root, so tool-use file paths render relative to it. */
  projectPath?: string | null;
}) {
  // Per-row detail expansion for the fused tool runs. Local state: it resets
  // if the row is recycled offscreen by the virtual list, which is acceptable
  // (mirrors `ToolUseGroup`).
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const toggleTool = (id: string) =>
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const status = useMemo(() => subagentGroupStatus(messages), [messages]);

  // Only the tool uses feed the header summary — prose (the report), thinking
  // cards and question panels aren't actions, and counting them would turn
  // "2 tool uses" into "5".
  const summaryItems = useMemo(
    () =>
      messages
        .filter((message) => isFusableToolUse(message, agentType))
        .map((message) => ({ id: message.id, content: message.content })),
    [messages, agentType],
  );

  const headerLabel = `Sub-agent: ${subagentType}`;
  // 'completed' is the normal ending and needs no marker; anything else does.
  const failure = status && status !== 'completed' ? status : null;

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
        {summaryItems.length > 0 && (
          <>
            <span className="shrink-0 text-muted-foreground/40" aria-hidden="true">
              ·
            </span>
            <ToolRunSummary
              items={summaryItems}
              agentType={agentType}
              projectPath={projectPath}
              showFileChips={!expanded}
            />
          </>
        )}
        {failure && <span className="shrink-0 text-red-400">{failure}</span>}
        <ChevronRight
          className={cn(
            'h-3.5 w-3.5 shrink-0 text-muted-foreground/60 transition-transform',
            expanded && 'rotate-90',
          )}
        />
      </button>
      {expanded && (
        <div className="ml-1.5 mt-1.5 space-y-1 border-l border-border/40 pl-2.5">
          {renderChildren(messages, agentType, projectPath, expandedTools, toggleTool, renderMessage)}
        </div>
      )}
    </div>
  );
}

/**
 * A child that belongs in a fused tool run. Interactive rows (a question
 * panel, a permission prompt) and thinking cards look like tool uses but must
 * render through `MessageItem` to keep their own affordance — the same guard
 * the instance page applies before collapsing a top-level tool run.
 */
function isFusableToolUse(message: MessageResponse, agentType: ToolUseAgentType): boolean {
  if (message.requires_user_input) return false;
  if (parseAskUserQuestionPayload(message) !== null) return false;
  if (parseThinkingPayload(message) !== null) return false;
  return parseToolUse(message.content, agentType) !== null;
}

/** Children in chat order, with consecutive tool uses fused into one run. */
function renderChildren(
  children: MessageResponse[],
  agentType: ToolUseAgentType,
  projectPath: string | null | undefined,
  expandedTools: Set<string>,
  toggleTool: (id: string) => void,
  renderMessage: (message: MessageResponse) => ReactNode,
): ReactNode[] {
  const rows: ReactNode[] = [];
  let run: MessageResponse[] = [];

  const flush = () => {
    if (run.length === 0) return;
    rows.push(
      <div key={`run-${run[0].id}`} className="space-y-1">
        {run.map((message) => (
          <ToolUseLine
            key={message.id}
            content={message.content}
            agentType={agentType}
            expanded={expandedTools.has(message.id)}
            onToggle={() => toggleTool(message.id)}
            projectPath={projectPath}
          />
        ))}
      </div>,
    );
    run = [];
  };

  for (const message of children) {
    if (isFusableToolUse(message, agentType)) {
      run.push(message);
      continue;
    }
    flush();
    rows.push(<div key={message.id}>{renderMessage(message)}</div>);
  }
  flush();
  return rows;
}
