'use client';

// The transcript, extracted from the session page (collaboration §8.4, P4).
//
// Two layers, so the session page and the public share viewer render the SAME
// rows without the viewer inheriting the page's composer, terminal, dashboard
// context or scroll-follow machinery:
//
// 1. `buildTranscriptItems` + `TranscriptRow` — the pure pipeline from
//    date-grouped messages to Virtuoso rows (tool-run collapsing, sub-agent
//    bucketing, the thinking indicator) and the renderer for one row. The
//    session page uses these directly inside its own Virtuoso, keeping every
//    piece of its bottom-following logic; the interactive handlers are all
//    optional so a read-only surface simply leaves them off.
// 2. `<SessionTranscript>` — a self-contained read-only list: give it messages
//    and an agent type and it renders. No context requirements: the file-link
//    and find-highlight contexts both have safe defaults, and this component
//    pins the file-link one to "no panel to open into" so paths render as text.

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { ArrowDown, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { MessageResponse } from '@/lib/backend-api';
import { groupMessagesByDate, messageSortKey } from '@/lib/message-grouping';
import { computeTurnEnds, type TurnMessageEntry } from '@/lib/agent-turns';
import { shouldHideControlMessage } from '@/lib/session-control-messages';
import { isInterruptControlMessage } from '@/lib/control-messages';
import { ToolUseGroup, isToolUseContent, parseToolUse } from '@/components/dashboard/tool-use-display';
import { SubagentGroup } from '@/components/dashboard/subagent-group';
import { groupSubagents } from '@/components/dashboard/subagent-grouping';
import {
  DateSeparator,
  MessageItem,
  ThinkingIndicator,
  getMessageVisibleText,
  resolveAgentType,
} from '@/components/dashboard/chat-message-item';
import { parseAskUserQuestionPayload, type AskUserQuestionSubmitPayload } from '@/components/dashboard/ask-user-question-panel';
import { parseThinkingPayload } from '@/components/dashboard/thinking-card';
import { isPendingQueueStatus, parseQueuePayload } from '@/components/dashboard/queue-status';
import { FileLinkProvider } from '@/components/dashboard/file-link-context';

export type TranscriptItem =
  | { type: 'separator'; date: string; key: string }
  | { type: 'message'; message: MessageResponse; key: string }
  | { type: 'tool-group'; messages: MessageResponse[]; key: string }
  | {
      type: 'subagent-group';
      messages: MessageResponse[];
      subagentType: string;
      description: string;
      key: string;
    }
  | { type: 'thinking'; key: string };

const USER_SENDER_TYPES = new Set(['user', 'human', 'USER', 'HUMAN']);

export function isUserMessage(message: MessageResponse): boolean {
  return USER_SENDER_TYPES.has(message.sender_type);
}

/**
 * Flatten date groups into Virtuoso rows. Keys are stable per item (separators
 * use the date + first id, messages their id, tool runs their first id) so
 * Virtuoso preserves scroll position when older history is prepended and a
 * streaming run keeps its expansion state as it grows.
 */
export function buildTranscriptItems(
  groupedMessages: { date: string; messages: MessageResponse[] }[],
  options: { agentTypeName?: string | null; showThinking?: boolean },
): TranscriptItem[] {
  const itemsAgentType = resolveAgentType(options.agentTypeName || undefined);
  const items: TranscriptItem[] = [];
  for (const group of groupedMessages) {
    const filtered = group.messages.filter(
      (msg) => msg.content.trim() !== 'Waiting for your input...' && !shouldHideControlMessage(msg),
    );
    if (filtered.length === 0) continue;
    const firstId = filtered[0].id;
    items.push({ type: 'separator', date: group.date, key: `sep-${group.date}-${firstId}` });
    // Sub-agent (Task tool) child messages are bucketed by tool_use_id,
    // anchored at each group's first occurrence, BEFORE tool-run collapsing
    // runs below — so interleaved parallel sub-agents form separate groups
    // instead of their messages getting folded into the flat tool-group
    // stream. Non-subagent messages pass through untouched, in place.
    const subagentBucketed = groupSubagents(filtered);

    // Consecutive agent tool-use messages collapse into one 'tool-group'
    // item ("N tool uses"); a run of one renders as a single tool line.
    let toolRun: MessageResponse[] = [];
    const flushToolRun = () => {
      if (toolRun.length === 0) return;
      items.push({ type: 'tool-group', messages: toolRun, key: `tools-${toolRun[0].id}` });
      toolRun = [];
    };
    for (const bucketed of subagentBucketed) {
      // A subagent-group is an opaque boundary for tool-run collapsing —
      // like an interactive message, it flushes whatever run preceded it
      // and is pushed as-is (its children render as full messages inside).
      if (bucketed.type === 'subagent-group') {
        flushToolRun();
        items.push(bucketed);
        continue;
      }
      const msg = bucketed.message;
      // Interactive messages (AskUserQuestion, permission prompts) look like
      // tool uses but must render through MessageItem so their panels show;
      // reasoning rows render as their own collapsed "Thinking" card.
      const isInteractive =
        msg.requires_user_input ||
        parseAskUserQuestionPayload(msg) !== null ||
        parseThinkingPayload(msg) !== null;
      const isToolUse =
        !isInteractive &&
        !USER_SENDER_TYPES.has(msg.sender_type) &&
        parseToolUse(msg.content, itemsAgentType) !== null;
      if (isToolUse) {
        toolRun.push(msg);
      } else {
        flushToolRun();
        items.push({ type: 'message', message: msg, key: msg.id });
      }
    }
    flushToolRun();
  }
  if (options.showThinking) {
    items.push({ type: 'thinking', key: 'thinking' });
  }
  return items;
}

/**
 * Turn-end lookup for the hover footer: only the last agent message of each
 * run since the previous user message carries copy/fork, and copying it yields
 * that whole turn. Derived from the built items so it sees exactly what
 * renders — anything folded into a tool-group or thinking card is inside the
 * turn but never anchors it.
 */
export function computeTranscriptTurns(items: TranscriptItem[]): Map<string, string> {
  const entries: TurnMessageEntry[] = [];
  for (const item of items) {
    if (item.type !== 'message') continue;
    const text = getMessageVisibleText(item.message);
    const kind: TurnMessageEntry['kind'] = USER_SENDER_TYPES.has(item.message.sender_type)
      ? 'user'
      : parseThinkingPayload(item.message) || isToolUseContent(text)
        ? 'other'
        : 'agent';
    entries.push({ id: item.message.id, kind, text });
  }
  return computeTurnEnds(entries);
}

/** Whether a list has any real message rows (a lone thinking item doesn't count). */
export function hasTranscriptMessages(items: TranscriptItem[]): boolean {
  return items.some(
    (it) => it.type === 'message' || it.type === 'tool-group' || it.type === 'subagent-group',
  );
}

export interface TranscriptRowProps {
  item: TranscriptItem;
  agentTypeName?: string | null;
  /** Project root, so tool-use file paths render relative to it. */
  projectPath?: string | null;
  /** Chat-item keys currently expanded (tool groups / sub-agent groups). */
  expandedKeys: ReadonlySet<string>;
  onToggleExpanded: (key: string) => void;
  /** The focused find match, if any — highlights the row. */
  findActiveKey?: string | null;
  vibingMessage?: string;
  /** Interactive handlers — all optional; a read-only surface omits them. */
  onOptionClick?: (option: string) => void;
  onAskUserQuestionSubmit?: (payload: AskUserQuestionSubmitPayload) => void;
  onAskUserQuestionCancel?: (messageId: string) => void;
  onFork?: (message: MessageResponse) => void;
  /** Turn-end copy text by message id (see `computeTranscriptTurns`). */
  turnCopyText?: ReadonlyMap<string, string>;
}

const ROW_SHELL = 'max-w-4xl mx-auto px-6';

/** One Virtuoso row: separator, thinking, a tool run, a sub-agent group, or a message. */
export function TranscriptRow({
  item,
  agentTypeName,
  projectPath,
  expandedKeys,
  onToggleExpanded,
  findActiveKey = null,
  vibingMessage = 'Working',
  onOptionClick,
  onAskUserQuestionSubmit,
  onAskUserQuestionCancel,
  onFork,
  turnCopyText,
}: TranscriptRowProps) {
  const agentType = resolveAgentType(agentTypeName || undefined);
  if (item.type === 'separator') {
    return (
      <div className={ROW_SHELL}>
        <DateSeparator date={item.date} />
      </div>
    );
  }
  if (item.type === 'thinking') {
    return (
      <div className={ROW_SHELL}>
        <ThinkingIndicator vibingMessage={vibingMessage} />
      </div>
    );
  }
  const groupShell = `rounded-xl px-4 py-0.5 flex-1 min-w-0 text-sm leading-relaxed font-mono ${
    findActiveKey === item.key ? 'find-active-message ring-2 ring-amber-400 dark:ring-amber-500' : ''
  }`;
  if (item.type === 'tool-group') {
    return (
      <div className={ROW_SHELL}>
        <div className="flex justify-start mb-1">
          <div className={groupShell}>
            <ToolUseGroup
              messages={item.messages}
              agentType={agentType}
              expanded={expandedKeys.has(item.key)}
              onToggle={() => onToggleExpanded(item.key)}
              projectPath={projectPath}
            />
          </div>
        </div>
      </div>
    );
  }
  if (item.type === 'subagent-group') {
    return (
      <div className={ROW_SHELL}>
        <div className="flex justify-start mb-1">
          <div className={groupShell}>
            <SubagentGroup
              messages={item.messages}
              subagentType={item.subagentType}
              description={item.description}
              expanded={expandedKeys.has(item.key)}
              onToggle={() => onToggleExpanded(item.key)}
              agentType={agentType}
              projectPath={projectPath}
              renderMessage={(message) => (
                <MessageItem
                  message={message}
                  onOptionClick={onOptionClick}
                  onAskUserQuestionSubmit={onAskUserQuestionSubmit}
                  onAskUserQuestionCancel={onAskUserQuestionCancel}
                  agentTypeName={agentTypeName ?? undefined}
                  projectPath={projectPath}
                  compact
                />
              )}
            />
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className={ROW_SHELL}>
      <MessageItem
        message={item.message}
        onOptionClick={onOptionClick}
        onAskUserQuestionSubmit={onAskUserQuestionSubmit}
        onAskUserQuestionCancel={onAskUserQuestionCancel}
        onFork={onFork}
        turnCopyText={turnCopyText?.get(item.message.id)}
        agentTypeName={agentTypeName ?? undefined}
        projectPath={projectPath}
      />
    </div>
  );
}

/** Expansion state for tool/sub-agent groups, held above Virtuoso since it recycles rows. */
export function useExpandedTranscriptKeys(): [Set<string>, (key: string) => void] {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);
  return [expanded, toggle];
}

/**
 * The transcript's own view of the message list: drop user rows still sitting
 * in the queue (pending ones live in the owner's queue bar, cancelled ones were
 * unsent) and order consumed-queued messages at their consumption point.
 */
export function orderTranscriptMessages(messages: MessageResponse[]): MessageResponse[] {
  const visible = messages.filter((m) => {
    if (!USER_SENDER_TYPES.has(m.sender_type)) return true;
    const status = parseQueuePayload(m)?.status;
    if (status === 'cancelled') return false;
    if (isInterruptControlMessage(m.content || '')) return true;
    if (isPendingQueueStatus(status)) return false;
    return true;
  });
  return visible.sort((a, b) => {
    const ka = messageSortKey(a);
    const kb = messageSortKey(b);
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  });
}

interface ListContext {
  loadingOlder: boolean;
}

// Module-level: Virtuoso treats each entry as a component type, and an inline
// object would remount the header/footer on every render.
const LIST_COMPONENTS = {
  Header: ({ context }: { context?: ListContext }) =>
    context?.loadingOlder ? (
      <div className="flex items-center justify-center py-3 text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      </div>
    ) : (
      <div className="h-6" />
    ),
  Footer: () => <div className="h-24" />,
};

// A large virtual index so prepended history can decrement it without ever
// going negative (the react-virtuoso "firstItemIndex" idiom).
const FIRST_ITEM_INDEX_BASE = 1_000_000;

function itemMessageIds(item: TranscriptItem): string[] {
  switch (item.type) {
    case 'message':
      return [item.message.id];
    case 'tool-group':
    case 'subagent-group':
      return item.messages.map((m) => m.id);
    default:
      return [];
  }
}

function firstMessageId(items: TranscriptItem[]): string | null {
  for (const item of items) {
    const ids = itemMessageIds(item);
    if (ids.length) return ids[0];
  }
  return null;
}

/** Row index of the item that carries `messageId`, or -1. */
function indexOfMessage(items: TranscriptItem[], messageId: string): number {
  return items.findIndex((item) => itemMessageIds(item).includes(messageId));
}

export interface SessionTranscriptProps {
  messages: MessageResponse[];
  agentTypeName?: string | null;
  /** The session's working directory, for relative tool paths; null on public surfaces. */
  projectPath?: string | null;
  /** Show the "working…" indicator at the tail (the session is mid-turn). */
  thinking?: boolean;
  /** Where the list opens: a document reads from the top, a live session from the tail. */
  startAt?: 'top' | 'bottom';
  /** Older-history paging. `onLoadOlder` fires when the reader reaches the top. */
  hasOlder?: boolean;
  loadingOlder?: boolean;
  onLoadOlder?: () => void;
  /** Rendered when there is nothing to show yet. */
  empty?: ReactNode;
  className?: string;
}

/**
 * A read-only, virtualized transcript. Follows the tail while the reader is at
 * the bottom (a live share keeps streaming — §10.3) and offers a jump-to-latest
 * button once they scroll up.
 */
export function SessionTranscript({
  messages,
  agentTypeName,
  projectPath = null,
  thinking = false,
  startAt = 'top',
  hasOlder = false,
  loadingOlder = false,
  onLoadOlder,
  empty,
  className,
}: SessionTranscriptProps) {
  const ordered = useMemo(() => orderTranscriptMessages(messages), [messages]);
  const grouped = useMemo(() => groupMessagesByDate(ordered), [ordered]);
  const items = useMemo(
    () => buildTranscriptItems(grouped, { agentTypeName, showThinking: thinking }),
    [grouped, agentTypeName, thinking],
  );
  const turnCopyText = useMemo(() => computeTranscriptTurns(items), [items]);
  const [expandedKeys, toggleExpanded] = useExpandedTranscriptKeys();
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const [atBottom, setAtBottom] = useState(startAt === 'bottom');

  // Keep scroll position stable when older rows are prepended: Virtuoso's
  // firstItemIndex must drop by exactly the number of new leading rows. The
  // anchor is the first *message* rather than the first row's key — a date
  // separator or a tool run is re-keyed by whichever message now leads it, so
  // a prepend that lands inside the same day (or the same run) would lose a
  // key-based anchor and jump.
  const [firstItemIndex, setFirstItemIndex] = useState(FIRST_ITEM_INDEX_BASE);
  const prevFirstMessageIdRef = useRef<string | null>(firstMessageId(items));
  useEffect(() => {
    const previous = prevFirstMessageIdRef.current;
    const current = firstMessageId(items);
    if (previous !== null && current !== null && previous !== current) {
      const oldIndex = indexOfMessage(items, previous);
      if (oldIndex > 0) setFirstItemIndex((idx) => idx - oldIndex);
    }
    prevFirstMessageIdRef.current = current;
  }, [items]);

  const context = useMemo<ListContext>(() => ({ loadingOlder: hasOlder || loadingOlder }), [hasOlder, loadingOlder]);
  const hasRows = hasTranscriptMessages(items);
  const scrollToBottom = useCallback(() => {
    virtuosoRef.current?.scrollToIndex({ index: 'LAST', align: 'end', behavior: 'smooth' });
  }, []);

  return (
    <FileLinkProvider cwd={projectPath} homeDir={null} openFile={null}>
      <div className={className ?? 'relative flex-1 min-h-0'}>
        {!hasRows ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {empty ?? 'No messages yet.'}
          </div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={items}
            firstItemIndex={firstItemIndex}
            className="absolute inset-0 overscroll-none [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-corner]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full dark:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/20"
            initialTopMostItemIndex={
              startAt === 'bottom' ? { index: Math.max(0, items.length - 1), align: 'end' } : 0
            }
            defaultItemHeight={120}
            followOutput={(isAtBottom) => (isAtBottom ? 'auto' : false)}
            atBottomThreshold={100}
            atBottomStateChange={setAtBottom}
            startReached={() => {
              if (hasOlder && !loadingOlder) onLoadOlder?.();
            }}
            increaseViewportBy={{ top: 1200, bottom: 800 }}
            computeItemKey={(_, item) => item.key}
            itemContent={(_, item) => (
              <TranscriptRow
                item={item}
                agentTypeName={agentTypeName}
                projectPath={projectPath}
                expandedKeys={expandedKeys}
                onToggleExpanded={toggleExpanded}
                turnCopyText={turnCopyText}
              />
            )}
            context={context}
            components={LIST_COMPONENTS}
          />
        )}
        {hasRows && !atBottom && (
          <Button
            type="button"
            variant="secondary"
            size="icon"
            onClick={scrollToBottom}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 h-9 w-9 rounded-full border border-border/70 shadow-lg bg-background text-foreground"
            aria-label="Scroll to latest message"
          >
            <ArrowDown className="w-3 h-3" />
          </Button>
        )}
      </div>
    </FileLinkProvider>
  );
}
