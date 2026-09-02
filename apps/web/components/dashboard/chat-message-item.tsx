'use client';

import { memo, useState } from 'react';
import { MessageResponse } from '@/lib/backend-api';
import { MessageMarkdown } from '@/components/ui/message-markdown';
import { extractMessageOptions, formatTaskNotifications } from '@/components/ui/message-markdown-utils';
import { hasAnsiCodes, parseAnsiToHtml } from '@/components/ui/ansi-render';
import { ToolUseLine, isToolUseContent } from '@/components/dashboard/tool-use-display';
import { AskUserQuestionPanel, type AskUserQuestionSubmitPayload, parseAskUserQuestionPayload } from '@/components/dashboard/ask-user-question-panel';
import { ChatAttachments, extractChatAttachments } from '@/components/chat-attachments';
import { StandaloneThinkingCard, parseThinkingPayload } from '@/components/dashboard/thinking-card';
import { CollapsibleUserMessage } from '@/components/dashboard/collapsible-user-message';
import { stripPermissionModeCommandTokens } from '@/lib/session-control-messages';
import { CONTROL_COMMAND_JSON_REGEX, isControlEnvelope } from '@/lib/control-messages';
import { HighlightedText, useFindHighlight } from '@/components/dashboard/chat-find-context';

export type UiAgentType = 'claude' | 'codex' | 'opencode';

const USER_SENDER_TYPES = new Set(['user', 'human', 'USER', 'HUMAN']);

/**
 * The user-visible text of a message, after the same stripping/formatting
 * MessageItem applies. Shared with the find feature so the match set and the
 * highlighted text stay in lockstep.
 */
export function getMessageVisibleText(message: MessageResponse): string {
  const { content } = extractMessageOptions(message.content);
  if (USER_SENDER_TYPES.has(message.sender_type)) {
    return formatTaskNotifications(stripPermissionModeCommandTokens(content) || content);
  }
  return isControlEnvelope(content)
    ? content.replace(CONTROL_COMMAND_JSON_REGEX, '').trim() || content
    : content;
}

/** Fallback for a tool message rendered outside a tool-group chat item —
    local expansion state is fine here (not a virtualized group row). */
function StandaloneToolUse({
  content,
  agentType,
  projectPath,
}: {
  content: string;
  agentType: UiAgentType;
  projectPath?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <ToolUseLine
      content={content}
      agentType={agentType}
      expanded={expanded}
      onToggle={() => setExpanded((current) => !current)}
      projectPath={projectPath}
    />
  );
}

export function resolveAgentType(agentTypeName?: string): UiAgentType {
  const normalized = (agentTypeName ?? '').toLowerCase().replace(/[^a-z0-9]/g, '');
  if (normalized.includes('opencode')) {
    return 'opencode';
  }
  if (normalized.includes('codex')) {
    return 'codex';
  }
  return 'claude';
}

export const MessageItem = memo(function MessageItem({ message, onOptionClick, onAskUserQuestionSubmit, onAskUserQuestionCancel, agentTypeName, projectPath, compact = false }: {
  message: MessageResponse;
  onOptionClick?: (option: string) => void;
  onAskUserQuestionSubmit?: (payload: AskUserQuestionSubmitPayload) => void;
  onAskUserQuestionCancel?: (messageId: string) => void;
  agentTypeName?: string;
  /** Project root, so tool-use file paths render relative to it. */
  projectPath?: string | null;
  // Sub-agent children render inside SubagentGroup's already-indented,
  // space-y-1 container. Drop the top-level chat-bubble chrome (outer margins,
  // bubble padding/shadow) so the rows sit as tight as a tool-group's lines
  // instead of stacking mb-2 + py-2 into a big gap between each.
  compact?: boolean;
}) {
  // More robust user detection - check for various possible user sender types
  const isUser = message.sender_type === 'user' ||
                 message.sender_type === 'human' ||
                 message.sender_type === 'USER' ||
                 message.sender_type === 'HUMAN';

  const agentType = resolveAgentType(agentTypeName);
  const askUserQuestion = parseAskUserQuestionPayload(message);
  const attachments = extractChatAttachments(message.message_metadata);

  const { options } = extractMessageOptions(message.content);

  const userVisibleContent = getMessageVisibleText(message);

  // Find-in-conversation: the active term (or '') + whether this row is the
  // focused match. Consuming context re-renders this (memoized) row on every
  // keystroke, but MessageMarkdown only re-parses when it actually matches —
  // non-matches keep `highlightQuery` undefined, so their memo holds.
  const { query: findQuery, activeKey } = useFindHighlight();
  const findHit = !!findQuery && userVisibleContent.toLowerCase().includes(findQuery.toLowerCase());
  const isFindActive = findHit && activeKey === message.id;

  const hasAnsi = isUser && hasAnsiCodes(userVisibleContent);
  const shouldUseMonospace = hasAnsi;

  // Model reasoning (Claude ThinkingBlock / Codex reasoning) renders as a
  // collapsed "Thinking" card instead of a plain agent bubble — same wrapper
  // chrome as a tool-group line, works both top-level and (compact) nested in
  // a SubagentGroup. Detected via message_metadata.thinking; agent-only.
  const thinking = !isUser ? parseThinkingPayload(message) : null;
  if (thinking) {
    return (
      <div className={compact ? 'flex justify-start' : 'flex justify-start mb-1'}>
        <div className="rounded-xl px-4 py-0.5 flex-1 min-w-0 text-sm leading-relaxed font-mono">
          <StandaloneThinkingCard content={userVisibleContent} agentType={agentType} />
        </div>
      </div>
    );
  }

  // Shared bubble chrome, now applied to the image bubble and the text bubble
  // independently (they used to be one element).
  // Agent messages are flat (no bg / border / shadow) so they read as plain
  // prose; only the user bubble carries a (reduced) fill + hairline border.
  const bubbleShell = `rounded-xl ${compact && !isUser ? '' : 'px-4 py-2'} ${
    isUser
      ? 'bg-user-bubble border border-border text-foreground rounded-tr-sm shadow-sm'
      : 'text-foreground rounded-tl-sm'
  }`;
  // An image-only user message has no text body — skip the empty text bubble.
  const hasTextBody =
    !isUser || attachments.length === 0 ||
    !!userVisibleContent.trim() || !!askUserQuestion || options.length > 0;

  return (
    <div
      className={`flex gap-3 ${
        isUser
          ? compact ? 'justify-end' : 'justify-end mt-6 mb-6'
          : compact ? 'justify-start' : 'justify-start mb-1'
      }`}
    >
      <div className={`flex gap-3 ${isUser ? 'max-w-[85%] flex-row-reverse' : 'flex-row w-full'}`}>
        {/* <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
          isUser ? 'bg-blue-100 dark:bg-blue-900' : requiresAction ? 'bg-muted' : 'bg-muted'
        }`}>
          {isUser ? (
            <User className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          ) : requiresAction ? (
            <Bot className="w-5 h-5 text-muted-foreground" />
          ) : (
            <Bot className="w-5 h-5 text-muted-foreground" />
          )}
        </div> */}
        <div className={`flex min-w-0 flex-1 flex-col gap-1.5 ${isUser ? 'items-end' : 'items-stretch'}`}>
          {/* Images get their OWN bubble stacked above the text bubble, so an
              image + caption reads as two user messages rather than one. */}
          {attachments.length > 0 && (
            <div className={`${bubbleShell} max-w-full`}>
              <ChatAttachments attachments={attachments} />
            </div>
          )}
          {hasTextBody && (
            <div
              className={`${bubbleShell} w-full min-w-0 ${
                isFindActive ? 'find-active-message ring-2 ring-amber-400 dark:ring-amber-500' : ''
              }`}
            >
              <div className="text-sm leading-relaxed font-mono">
                {isUser ? (
                  <CollapsibleUserMessage>
                    <div className="whitespace-pre-wrap break-words overflow-wrap-anywhere">
                      {hasAnsi ? (
                        parseAnsiToHtml(userVisibleContent)
                      ) : (
                        <HighlightedText text={userVisibleContent} query={findHit ? findQuery : ''} />
                      )}
                    </div>
                  </CollapsibleUserMessage>
                ) : isToolUseContent(userVisibleContent) ? (
                  // Normally tool messages are grouped into 'tool-group' chat
                  // items before they reach MessageItem; this is the fallback
                  // (ToolUseLine renders plain markdown if parsing fails).
                  <StandaloneToolUse content={userVisibleContent} agentType={agentType} projectPath={projectPath} />
                ) : (
                  <div className="markdown-content">
                    <MessageMarkdown agentType={agentType} highlightQuery={findHit ? findQuery : undefined}>
                      {userVisibleContent}
                    </MessageMarkdown>
                  </div>
                )}
              </div>

              {askUserQuestion && (
                <AskUserQuestionPanel
                  message={message}
                  onSubmit={onAskUserQuestionSubmit}
                  onCancel={onAskUserQuestionCancel}
                />
              )}

              {/* Render clickable options */}
              {!askUserQuestion && options.length > 0 && (
                <div className="mt-3 space-y-2">
                  <div className="text-xs font-medium text-muted-foreground mb-2 font-mono">Choose an option:</div>
                  {options.map((option, index) => (
                    <button
                      key={index}
                      onClick={() => onOptionClick?.(option)}
                      className="group block w-full text-left px-3 py-2 text-xs bg-card border-2 border-border/50 rounded-lg cursor-pointer hover:border-muted-foreground/40 hover:bg-muted hover:shadow-sm transition-colors duration-150 focus:outline-none focus:ring-1"
                    >
                      <span className="font-medium text-muted-foreground font-mono text-xs group-hover:text-foreground transition-colors duration-150">{index + 1}.</span>{' '}
                      <span className="text-foreground font-mono text-xs">{option}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

// Date separator component
export const DateSeparator = memo(function DateSeparator({ date }: { date: string }) {
  return (
    <div className="flex items-center justify-center my-6">
      <div className="text-xs font-medium text-muted-foreground px-3 py-1 bg-muted rounded-full">
        {date}
      </div>
    </div>
  );
});

// "Agent is thinking" indicator with the wavy "vibing" animation.
export const ThinkingIndicator = memo(function ThinkingIndicator({ vibingMessage }: { vibingMessage: string }) {
  return (
    <div className="flex gap-3 justify-start mt-3 mb-3">
      <div className="flex gap-3 w-full">
        <div className="rounded-xl px-4 py-3 text-foreground rounded-tl-sm">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <style>{`
              @keyframes blink-wave {
                0% { opacity: 0.3; }
                50% { opacity: 0.8; }
                100% { opacity: 0.3; }
              }
              .vibing-text span {
                display: inline-block;
                animation: blink-wave 6s ease-in-out infinite;
              }
            `}</style>
            <span className="vibing-text font-mono">
              {vibingMessage.split('').map((char, index) => (
                <span key={index} style={{ animationDelay: `${index * 0.15}s` }}>
                  {char}
                </span>
              ))}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
});

// Vibing messages for the thinking indicator
export const vibingMessages = ["Accomplishing", "Actioning", "Actualizing", "Architecting", "Baking", "Beaming", "Beboppin'", "Befuddling", "Billowing", "Blanching", "Bloviating", "Boogieing", "Boondoggling", "Booping", "Bootstrapping", "Brewing", "Bunning", "Burrowing", "Calculating", "Canoodling", "Caramelizing", "Cascading", "Catapulting", "Cerebrating", "Channeling", "Channelling", "Choreographing", "Churning", "Clauding", "Coalescing", "Cogitating", "Combobulating", "Composing", "Computing", "Concocting", "Considering", "Contemplating", "Cooking", "Crafting", "Creating", "Crunching", "Crystallizing", "Cultivating", "Deciphering", "Deliberating", "Determining", "Dilly-dallying", "Discombobulating", "Doing", "Doodling", "Drizzling", "Ebbing", "Effecting", "Elucidating", "Embellishing", "Enchanting", "Envisioning", "Evaporating", "Fermenting", "Fiddle-faddling", "Finagling", "Flambéing", "Flibbertigibbeting", "Flowing", "Flummoxing", "Fluttering", "Forging", "Forming", "Frolicking", "Frosting", "Gallivanting", "Galloping", "Garnishing", "Generating", "Gesticulating", "Germinating", "Gitifying", "Grooving", "Gusting", "Harmonizing", "Hashing", "Hatching", "Herding", "Honking", "Hullaballooing", "Hyperspacing", "Ideating", "Imagining", "Improvising", "Incubating", "Inferring", "Infusing", "Ionizing", "Jitterbugging", "Julienning", "Kneading", "Leavening", "Levitating", "Lollygagging", "Manifesting", "Marinating", "Meandering", "Metamorphosing", "Misting", "Moonwalking", "Moseying", "Mulling", "Mustering", "Musing", "Nebulizing", "Nesting", "Newspapering", "Noodling", "Nucleating", "Orbiting", "Orchestrating", "Osmosing", "Perambulating", "Percolating", "Perusing", "Philosophising", "Photosynthesizing", "Pollinating", "Pondering", "Pontificating", "Pouncing", "Precipitating", "Prestidigitating", "Processing", "Proofing", "Propagating", "Puttering", "Puzzling", "Quantumizing", "Razzle-dazzling", "Razzmatazzing", "Recombobulating", "Reticulating", "Roosting", "Ruminating", "Sautéing", "Scampering", "Schlepping", "Scurrying", "Seasoning", "Shenaniganing", "Shimmying", "Simmering", "Skedaddling", "Sketching", "Slithering", "Smooshing", "Sock-hopping", "Spelunking", "Spinning", "Sprouting", "Stewing", "Sublimating", "Swirling", "Swooping", "Symbioting", "Synthesizing", "Tempering", "Thinking", "Thundering", "Tinkering", "Tomfoolering", "Topsy-turvying", "Transfiguring", "Transmuting", "Twisting", "Undulating", "Unfurling", "Unravelling", "Vibing", "Waddling", "Wandering", "Warping", "Whatchamacalliting", "Whirlpooling", "Whirring", "Whisking", "Wibbling", "Working", "Wrangling", "Zesting", "Zigzagging"];
