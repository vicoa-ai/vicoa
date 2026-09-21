'use client';

import { useMemo, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react';
import {
  ChevronRight,
  Terminal,
  Pencil,
  Eye,
  Bot,
  Search,
  List as ListIcon,
  ListTodo,
  Globe,
  MessageCircleQuestion,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { isTextSelectionClick } from '@/lib/text-selection';
import { classifyWorkspacePath } from '@/lib/message-links';
import { MessageMarkdown } from '@/components/ui/message-markdown';
import { HighlightedText, useFindHighlight } from '@/components/dashboard/chat-find-context';
import { useFileLinks } from '@/components/dashboard/file-link-context';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { MessageResponse } from '@/lib/backend-api';
import {
  describeToolRun,
  editedFilesInRun,
  isFileEditToolName,
  parseToolUse,
  relativizeFilePath,
  summarizeToolUse,
  toolNamesInRun,
  type ToolUseAgentType,
} from './tool-use-parsing';

export { describeToolRun, isToolUseContent, parseToolUse, summarizeToolUse } from './tool-use-parsing';
export type { ParsedToolUse, ToolUseAgentType, ToolUseSummary } from './tool-use-parsing';

/**
 * Compact, expandable rendering for agent tool-use messages.
 *
 * - A lone tool use renders as a single truncated line; a chevron expands the
 *   hidden detail (code blocks, command output) inline.
 * - A consecutive run of tool uses renders as one "N tool uses" row that
 *   expands to the individual lines.
 * - File-based tools (Edit/Read/Write…) show `Tool basename` (+N -M when the
 *   agent reports it); the full path appears in the tooltip and above the
 *   code block when expanded.
 *
 * Find-in-conversation aware: a row whose hidden detail matches the active
 * find query reveals that detail on its own (the transcript-level search
 * counts it as a hit, so it has to be visible), and every label / body it
 * renders highlights the term.
 */

function DiffStat({ stat }: { stat: string }) {
  const [plus, minus] = stat.split(/\s+/);
  return (
    <span className="flex shrink-0 items-center gap-1 text-xs">
      {plus && <span className="text-success">{plus}</span>}
      {minus && <span className="text-red-400">{minus}</span>}
    </span>
  );
}

/**
 * A file chip: `basename (+N -M)`. When the edit has a diff, hovering the name
 * previews it in a tooltip (the code block, rendered like the inline diff);
 * otherwise the full path shows as a plain native title. Reused for the
 * single-line summary and for each edited file on a collapsed group.
 *
 * In a session with a machine to read from, the name is also a click that
 * opens the file in the files panel — resolved exactly like a file link in
 * prose (file-link-context.tsx), so a path outside the workspace, or a surface
 * with no panel (task timeline, share viewer), leaves it plain. The click stops
 * at the chip: the row it sits in is itself a button that toggles its detail,
 * and opening a file must not also fold or unfold the row.
 */
function FileChip({
  fileName,
  fullPath,
  diffStat,
  diffContent,
  agentType,
  projectPath,
  inline = false,
  nameOnly = false,
}: {
  fileName: string;
  fullPath: string | null;
  diffStat: string | null;
  /** Fenced diff/code to preview on hover ('' disables the preview). */
  diffContent: string;
  agentType: ToolUseAgentType;
  /** Project root; when the file is under it, the chip shows the relative path. */
  projectPath?: string | null;
  /** Render as a bordered pill (group row). */
  inline?: boolean;
  /** Show just the basename; the relative path moves to the hover title. A
   *  collapsed group lists several files side by side and has no room for
   *  their directories. */
  nameOnly?: boolean;
}) {
  const { query: findQuery } = useFindHighlight();
  const fileLinks = useFileLinks();
  const hasPreview = diffContent.trim().length > 0;
  const relativeLabel = relativizeFilePath(fullPath, fileName, projectPath);
  const label = nameOnly ? fileName : relativeLabel;
  const labelNode = <HighlightedText text={label} query={findQuery} />;

  const openFile = fileLinks.openFile;
  const target = openFile && fullPath ? classifyWorkspacePath(fullPath, fileLinks) : null;
  const file = target?.kind === 'file' ? target.file : null;
  const open = openFile && file ? () => openFile(file) : null;
  const onClick = open
    ? (e: MouseEvent<HTMLElement>) => {
        e.stopPropagation();
        if (!isTextSelectionClick(e)) open();
      }
    : undefined;
  const onKeyDown = open
    ? (e: KeyboardEvent<HTMLElement>) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        e.stopPropagation();
        open();
      }
    : undefined;
  // Hover text: a basename chip reveals its relative path; a plain name its
  // absolute one; a chip with a diff preview leaves that to the tooltip.
  const title = open
    ? `Open ${relativeLabel}`
    : nameOnly
      ? relativeLabel
      : hasPreview
        ? undefined
        : (fullPath ?? undefined);
  // The chip's row is a <button>, which can't nest another; the name is a
  // span that behaves as one.
  const nameProps = open ? { role: 'button', tabIndex: 0, onClick, onKeyDown, title } : { title };
  const nameClass = cn(
    'min-w-0 text-muted-foreground',
    open && 'cursor-pointer underline-offset-2 decoration-dotted hover:text-foreground hover:underline',
  );

  const inner = inline ? (
    // Bordered pill; the border separates files so no "·" is needed. No
    // vertical padding: the line box has room already, and a pill one text
    // line tall keeps a row of chips as tall as a row of text, so the header's
    // icon and chevron (pinned to the first line) sit centred on it.
    <span
      className={cn(
        'inline-flex min-w-0 items-center gap-1 rounded border border-border px-1.5',
        // A basename is never clipped or wrapped: a pill that doesn't fit its
        // row moves whole to the next one (the group row wraps its chips).
        nameOnly && 'shrink-0 whitespace-nowrap',
      )}
    >
      {nameOnly ? (
        <span className={nameClass} {...nameProps}>
          {labelNode}
        </span>
      ) : (
        // A relative path uses a CSS start-ellipsis (rtl base direction +
        // native text-overflow): it shows in full whenever it fits and only
        // clips the head (keeping the basename) when actually squeezed —
        // unlike a measured/JS ellipsis, which mis-sized inside this
        // shrink-to-fit pill and clipped even with room.
        <span className={cn(nameClass, 'truncate')} style={{ direction: 'rtl' }} {...nameProps}>
          <span dir="ltr">{labelNode}</span>
        </span>
      )}
      {diffStat && <DiffStat stat={diffStat} />}
    </span>
  ) : (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className={cn(nameClass, 'truncate')} {...nameProps}>
        {labelNode}
      </span>
      {diffStat && <DiffStat stat={diffStat} />}
    </span>
  );

  if (!hasPreview) return inner;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{inner}</TooltipTrigger>
        <TooltipContent
          side="bottom"
          align="start"
          sideOffset={6}
          className="max-w-[min(90vw,560px)] p-0 text-foreground"
        >
          {fullPath && (
            <div
              className="border-b border-border px-2.5 py-1.5 text-xs text-muted-foreground break-all"
              title={fullPath}
            >
              {relativeLabel}
            </div>
          )}
          {/* Strip the code block's card chrome (border/bg/padding) so the diff
              blends into the tooltip; the per-line +/- colors carry it. Wrap long
              diff lines instead of scrolling horizontally (overriding the inline
              renderer's whitespace-pre / overflow-x-auto, scoped to this preview). */}
          <div className="markdown-content custom-scrollbar max-h-[340px] overflow-y-auto px-2.5 py-2 [&_pre]:mb-0 [&_pre]:border-0 [&_pre]:bg-transparent [&_pre]:p-0 [&_code]:overflow-x-hidden [&_code_span]:whitespace-pre-wrap [&_code_span]:[overflow-wrap:anywhere]">
            <MessageMarkdown agentType={agentType}>{diffContent}</MessageMarkdown>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/**
 * Priority for the icon that represents a collapsed group: the highest-signal
 * tool wins, so Agent > Edit > Read > Bash. A run that reads a file and runs a
 * command shows the eye; add an edit and it shows the pencil. Lower rank wins.
 */
const TOOL_RANK: Record<string, number> = {
  task: 0,
  agent: 0,
  subagent: 0,
  askuserquestion: 0,
  edit: 1,
  edited: 1,
  write: 1,
  multiedit: 1,
  read: 2,
  search: 3,
  grep: 3,
  glob: 3,
  bash: 4,
  exec: 4,
  list: 5,
  todos: 6,
};

function normalizeToolName(name: string): string {
  return name.toLowerCase().replace(/[^a-z]/g, '');
}

/** Map a tool name to its glyph; Wrench is the catch-all for unknown tools. */
function iconForToolName(name: string): LucideIcon {
  const normalized = normalizeToolName(name);
  if (normalized === 'bash' || normalized === 'exec') return Terminal;
  if (normalized === 'edit' || normalized === 'edited' || normalized === 'write' || normalized === 'multiedit') {
    return Pencil;
  }
  if (normalized === 'read') return Eye;
  if (normalized === 'askuserquestion') return MessageCircleQuestion;
  if (normalized === 'task' || normalized.includes('agent')) return Bot;
  if (normalized === 'search' || normalized === 'grep' || normalized === 'glob') return Search;
  if (normalized === 'list') return ListIcon;
  if (normalized === 'todos') return ListTodo;
  if (normalized === 'webfetch' || normalized === 'websearch' || normalized === 'fetch') return Globe;
  return Wrench;
}

/** Highest-priority tool name in a run — drives the collapsed-group icon. */
function representativeToolName(names: string[]): string {
  let best = '';
  let bestRank = Infinity;
  for (const name of names) {
    const rank = TOOL_RANK[normalizeToolName(name)] ?? 40;
    if (rank < bestRank) {
      bestRank = rank;
      best = name;
    }
  }
  return best;
}

/** The small, dimmed glyph shown at the start of every tool-use row. */
function ToolIcon({ name, className }: { name: string; className?: string }) {
  const Icon = iconForToolName(name);
  return <Icon className={cn('h-3.5 w-3.5 shrink-0 text-muted-foreground/70', className)} aria-hidden="true" />;
}

/**
 * The text of a group header (label, description, file chips…), laid out as a
 * wrapping flex line between the header's icon and chevron. It takes only the
 * width its content needs — the chevron follows a short header directly — and
 * wraps once the row runs out, each item moving whole to the next line.
 */
export function HeaderRow({ children }: { children: ReactNode }) {
  return <span className="flex min-w-0 flex-wrap items-center gap-1.5">{children}</span>;
}

/**
 * Pins a header's icon or chevron to its first line. A collapsed group's chips
 * may wrap the header onto several rows; the glyphs belong beside the label on
 * the first, not floating at the block's middle. `1lh` is the row's own line
 * height, so a one-line header renders exactly as before.
 */
export function HeaderGlyph({ children }: { children: ReactNode }) {
  return <span className="flex h-[1lh] shrink-0 items-center">{children}</span>;
}

/** Description long enough that the collapsed line is almost surely truncated. */
const LONG_DESCRIPTION_CHARS = 80;

/** Cap on edited-file chips shown on a collapsed group before "+N more" —
 *  about two rows' worth, so the summary stays a summary. */
const MAX_INLINE_FILE_CHIPS = 8;

/**
 * What a collapsed run of tool uses says about itself: the aggregate action
 * label, and — when the run edited files — a chip per file carrying its
 * `+N -M` and a hover diff preview, so the changed files are visible without
 * expanding anything.
 *
 * Shared by `ToolUseGroup` and `SubagentGroup` so a sub-agent's collapsed
 * header reads in exactly the same vocabulary as a top-level tool run; before
 * this, a sub-agent that rewrote three files announced itself as one line of
 * text naming neither the work nor the files.
 *
 * Renders as a fragment (no wrapper): a plain label when there are no chips,
 * otherwise the label and one item per file. The caller owns the row — a
 * wrapping flex line (see [HeaderRow]) — so chips move whole onto further rows
 * instead of squeezing into one, and a name is never clipped or split.
 */
export function ToolRunSummary({
  contents,
  agentType,
  projectPath,
  showFileChips,
}: {
  /** The run's tool-use message contents, in chat order. */
  contents: string[];
  agentType: ToolUseAgentType;
  projectPath?: string | null;
  /** Chips are for the collapsed state; expanded rows show their own diffs. */
  showFileChips: boolean;
}) {
  const { query: findQuery } = useFindHighlight();

  // "Run 2 commands, edit 2 files, read a file" — distinct tools, first-use order.
  const runLabel = useMemo(() => describeToolRun(contents, agentType), [contents, agentType]);

  // Same label minus the edit segments — edits are shown inline as file chips,
  // so the collapsed row reads "Run a command · foo.ts +3 -1 · …" ('' if only
  // edits). Only used when the run has edits and is collapsed.
  const nonEditLabel = useMemo(
    () => describeToolRun(contents, agentType, { excludeFileEdits: true }),
    [contents, agentType],
  );

  // One chip per distinct file, in first-edit order (repeated edits to a file
  // fold into one — see editedFilesInRun).
  const editedFiles = useMemo(() => editedFilesInRun(contents, agentType), [contents, agentType]);

  if (!showFileChips || editedFiles.length === 0) {
    if (!runLabel) return null;
    return (
      <span className="min-w-0 truncate text-muted-foreground" title={runLabel}>
        <HighlightedText text={runLabel} query={findQuery} />
      </span>
    );
  }

  const inlineFiles = editedFiles.slice(0, MAX_INLINE_FILE_CHIPS);
  const overflowCount = editedFiles.length - inlineFiles.length;

  return (
    <>
      {nonEditLabel && <span className="shrink-0 text-muted-foreground">{nonEditLabel},</span>}
      {inlineFiles.map((edit, index) => {
        // Prefix the file with its tool name ("Edit"/"Write"/…), but only
        // when it changes — a run of same-tool files shares one label:
        // "Edit foo.ts bar.ts", "Edit foo.ts Write baz.ts". The label rides in
        // the same flex item as its first chip so a wrap can't strand it at
        // the end of a row.
        const showToolLabel = index === 0 || edit.toolName !== inlineFiles[index - 1].toolName;
        return (
          <span key={edit.fullPath ?? edit.fileName} className="flex shrink-0 items-center gap-1.5">
            {showToolLabel && <span className="text-muted-foreground">{edit.toolName}</span>}
            <FileChip
              inline
              nameOnly
              fileName={edit.fileName}
              fullPath={edit.fullPath}
              diffStat={edit.diffStat}
              diffContent={edit.diffContent}
              agentType={agentType}
              projectPath={projectPath}
            />
          </span>
        );
      })}
      {overflowCount > 0 && (
        <span className="shrink-0 text-muted-foreground/70">+{overflowCount} more</span>
      )}
    </>
  );
}

/** One tool use: a single-line summary row, expandable when there's detail. */
export function ToolUseLine({
  content,
  agentType,
  expanded,
  onToggle,
  projectPath,
}: {
  content: string;
  agentType: ToolUseAgentType;
  expanded: boolean;
  onToggle: () => void;
  projectPath?: string | null;
}) {
  const parsed = useMemo(() => parseToolUse(content, agentType), [content, agentType]);
  const { query: findQuery } = useFindHighlight();
  // Only hand the query to bodies that actually contain it — a non-matching
  // MessageMarkdown keeps `highlightQuery` undefined and so keeps its memo.
  const highlightIn = (text: string) =>
    findQuery !== '' && text.toLowerCase().includes(findQuery.toLowerCase()) ? findQuery : undefined;
  if (!parsed) {
    // Unparseable tool-ish content — fall back to plain markdown.
    return (
      <div className="markdown-content">
        <MessageMarkdown agentType={agentType} highlightQuery={highlightIn(content)}>
          {content}
        </MessageMarkdown>
      </div>
    );
  }

  const summary = summarizeToolUse(parsed);
  const expandable = summary.hasDetail || summary.description.length > LONG_DESCRIPTION_CHARS;
  // Find counts this row's hidden detail as a hit (lib/chat-search.ts), so a
  // matching term forces the detail open — otherwise stepping onto the match
  // would land on a collapsed row with nothing highlighted. Reverts when the
  // query is cleared; the user's own toggle is untouched.
  const findDetailText = [parsed.toolDescription, parsed.remainingContent, summary.fullPath ?? ''].join('\n');
  const findRevealsDetail =
    findQuery !== '' && findDetailText.toLowerCase().includes(findQuery.toLowerCase());
  const showDetail = expandable && (expanded || findRevealsDetail);
  // Edit/Write/MultiEdit that carry a diff (or a new-file body) render as a
  // bordered file pill — same as the group row — and preview on hover while
  // collapsed. Read/etc. and content-less writes keep the plain filename.
  const editDiffContent = isFileEditToolName(summary.name) ? parsed.remainingContent : '';
  const hasEditDiff = editDiffContent.trim().length > 0;

  return (
    <div className="using-tool-message">
      <button
        type="button"
        // A drag-select across the row must not also toggle it; `select-text`
        // is what lets the drag select at all (lib/text-selection.ts).
        onClick={
          expandable
            ? (e) => {
                if (!isTextSelectionClick(e)) onToggle();
              }
            : undefined
        }
        aria-expanded={expandable ? expanded : undefined}
        className={cn(
          // -mx cancels the hover padding so the text lines up with normal
          // markdown content (no visual indent).
          'flex w-full min-w-0 items-center gap-1.5 rounded -mx-0.5 px-0.5 py-0.5 text-left select-text',
          expandable ? 'cursor-pointer hover:bg-muted/40' : 'cursor-default',
        )}
      >
        <ToolIcon name={summary.name} />
        <span className="shrink-0 font-normal text-muted-foreground">{summary.name}</span>
        {/* The filename chip stays in the header even when expanded (the
            detail adds the full path); a plain command/description collapses
            into the detail instead. */}
        {summary.fileName ? (
          <FileChip
            inline={hasEditDiff}
            fileName={summary.fileName}
            fullPath={summary.fullPath}
            diffStat={summary.diffStat}
            // Hover preview only while collapsed — the diff is shown inline
            // below once expanded (the border stays either way).
            diffContent={showDetail ? '' : editDiffContent}
            agentType={agentType}
            projectPath={projectPath}
          />
        ) : (
          !showDetail && (
            <>
              {summary.description && (
                <span className="min-w-0 truncate text-muted-foreground">
                  <HighlightedText text={summary.description} query={findQuery} />
                </span>
              )}
              {summary.diffStat && <DiffStat stat={summary.diffStat} />}
            </>
          )
        )}
        {expandable && (
          <ChevronRight
            className={cn(
              'h-3.5 w-3.5 shrink-0 text-muted-foreground/60 transition-transform',
              showDetail && 'rotate-90',
            )}
          />
        )}
      </button>

      {showDetail && (
        <div className="mt-1.5 space-y-1.5">
          {summary.fullPath && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {/* Project-relative path here too; hover for the absolute path. */}
              <span className="break-all" title={summary.fullPath}>
                <HighlightedText
                  text={relativizeFilePath(summary.fullPath, summary.fileName ?? '', projectPath)}
                  query={findQuery}
                />
              </span>
              {summary.diffStat && <DiffStat stat={summary.diffStat} />}
            </div>
          )}
          {!summary.fullPath && !parsed.isMultilineDescription && summary.description && (
            <code className="block w-fit max-w-full break-all rounded bg-muted px-1.5 py-1 text-xs text-muted-foreground">
              <HighlightedText text={summary.description} query={findQuery} />
            </code>
          )}
          {parsed.isMultilineDescription && parsed.toolDescription && (
            <div className="markdown-content">
              <MessageMarkdown agentType={agentType} highlightQuery={highlightIn(parsed.toolDescription)}>
                {'```\n' + parsed.toolDescription.replace(/^`|`$/g, '').trim() + '\n```'}
              </MessageMarkdown>
            </div>
          )}
          {parsed.remainingContent && (
            <div className="markdown-content">
              <MessageMarkdown agentType={agentType} highlightQuery={highlightIn(parsed.remainingContent)}>
                {parsed.remainingContent}
              </MessageMarkdown>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** A run of consecutive tool uses: "N tool uses" that expands to the lines.
    A run of one renders the line directly (the parent's expanded state then
    drives the line itself). */
export function ToolUseGroup({
  messages,
  agentType,
  expanded,
  onToggle,
  projectPath,
}: {
  messages: MessageResponse[];
  agentType: ToolUseAgentType;
  expanded: boolean;
  onToggle: () => void;
  projectPath?: string | null;
}) {
  // Per-tool expansion inside an expanded group. Local state: it resets if
  // the row is recycled offscreen by the virtual list, which is acceptable.
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());

  const contents = useMemo(() => messages.map((message) => message.content), [messages]);

  // The single icon that stands in for the whole collapsed run.
  const groupIconName = useMemo(
    () => representativeToolName(toolNamesInRun(contents, agentType)),
    [contents, agentType],
  );

  if (messages.length === 1) {
    return (
      <ToolUseLine
        content={messages[0].content}
        agentType={agentType}
        expanded={expanded}
        onToggle={onToggle}
        projectPath={projectPath}
      />
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={(e) => {
          if (!isTextSelectionClick(e)) onToggle();
        }}
        aria-expanded={expanded}
        className="flex w-full min-w-0 items-start gap-1.5 rounded -mx-0.5 px-0.5 py-0.5 text-left cursor-pointer hover:bg-muted/40 select-text"
      >
        <HeaderGlyph>
          <ToolIcon name={groupIconName} />
        </HeaderGlyph>
        <HeaderRow>
          <ToolRunSummary
            contents={contents}
            agentType={agentType}
            projectPath={projectPath}
            showFileChips={!expanded}
          />
        </HeaderRow>
        <HeaderGlyph>
          <ChevronRight
            className={cn(
              'h-3.5 w-3.5 shrink-0 text-muted-foreground/60 transition-transform',
              expanded && 'rotate-90',
            )}
          />
        </HeaderGlyph>
      </button>
      {expanded && (
        <div className="ml-1.5 mt-1.5 space-y-1 border-l border-border/40 pl-2.5">
          {messages.map((message) => (
            <ToolUseLine
              key={message.id}
              content={message.content}
              agentType={agentType}
              expanded={expandedTools.has(message.id)}
              onToggle={() =>
                setExpandedTools((prev) => {
                  const next = new Set(prev);
                  if (next.has(message.id)) next.delete(message.id);
                  else next.add(message.id);
                  return next;
                })
              }
              projectPath={projectPath}
            />
          ))}
        </div>
      )}
    </div>
  );
}
