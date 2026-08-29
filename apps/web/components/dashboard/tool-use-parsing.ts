/**
 * Pure parsing/summarizing of agent tool-use message content.
 * Ported from the instance page's former inline formatUsingToolMessage /
 * formatToolPattern helpers; kept JSX-free so it is unit-testable.
 */

export type ToolUseAgentType = 'claude' | 'codex' | 'opencode';

export interface ParsedToolUse {
  toolName: string;
  toolDescription: string;
  remainingContent: string;
  isMultilineDescription: boolean;
}

/** Cheap first-line screen for "is this a tool-use message at all". */
export function isToolUseContent(content: string): boolean {
  const trimmed = content.trim();
  return (
    trimmed.startsWith('Using tool:') ||
    trimmed.startsWith('🔧 Using tool:') ||
    trimmed.startsWith('🔧') ||
    trimmed.startsWith('**Exec:**') ||
    (content.includes('✏️ Applying patch to') && content.includes('file (+'))
  );
}

/** Full parse; null when the content isn't a recognizable tool-use message. */
export function parseToolUse(content: string, agentType: ToolUseAgentType): ParsedToolUse | null {
  let processedContent = content;

  // Codex appends status lines; keep only the part before them.
  if (agentType === 'codex') {
    const lines = processedContent.split('\n');
    const statusIndex = lines.findIndex((line) => /\*\*Status:\*\*/.test(line.trim()));
    if (statusIndex !== -1) {
      processedContent = lines.slice(0, statusIndex).join('\n');
    }
  }

  if (!isToolUseContent(processedContent)) return null;
  return formatToolPattern(processedContent);
}

function formatToolPattern(content: string): ParsedToolUse | null {
  const lines = content.split('\n');
  const firstLine = lines[0].trim();

  let toolName = '';
  let toolDescription = '';
  let isMultilineDescription = false;
  let remainingContent = lines.length > 1 ? lines.slice(1).join('\n').trim() : '';

  // Parse codex pattern like "**Exec:** `command`"
  const codexMatch = firstLine.match(/\*\*Exec:\*\*\s*(.*)/);
  if (codexMatch) {
    toolName = 'Exec';
    toolDescription = codexMatch[1]?.replace(/bash -lc |zsh -lc /, '') || '';

    if (toolDescription.startsWith('`') && !toolDescription.endsWith('`')) {
      // Opening backtick but not closing on the same line — multiline command.
      isMultilineDescription = true;
      const fullMatch = content.match(/\*\*Exec:\*\*\s*([\s\S]*)/);
      if (fullMatch) {
        toolDescription = fullMatch[1].replace(/bash -lc |zsh -lc /, '');
        remainingContent = '';
      }
    }

    if (toolDescription.startsWith('`ls')) {
      toolName = 'List';
    } else if (
      toolDescription.startsWith('`rg') ||
      toolDescription.startsWith('`ripgrep') ||
      toolDescription.startsWith('`grep')
    ) {
      toolName = 'Search';
    } else if (/sed\s+-n\s+'(\d+),(\d+)p'/.test(toolDescription)) {
      toolName = 'Read';
    } else if (/<<\s*'([^']+)'/.test(toolDescription)) {
      // Heredoc command like `python - <<'PY'`
      if (!isMultilineDescription) {
        toolDescription += '`';
        remainingContent = formatHeredocInContent(content);
      }
    }

    return { toolName, toolDescription, remainingContent, isMultilineDescription };
  }

  // Codex git-patch output: "✏️ Applying patch to 1 file (+12 -3)"
  if (firstLine.includes('✏️ Applying patch to') && firstLine.includes('file (+')) {
    toolName = 'Edited';
    const patchMatch = firstLine.match(/✏️ Applying patch to \d+ file \(([^)]+)\)/);
    if (patchMatch) {
      toolDescription = patchMatch[1] || '';
      if (lines.length > 2) {
        const fileName = lines[1].trim().replace('└ ', '');
        toolDescription = `\`${fileName}\` ${toolDescription}`;
        remainingContent = lines
          .slice(2)
          .filter((line) => !line.startsWith(`**${fileName}`))
          .join('\n')
          .trim();
      }
    }
    return { toolName, toolDescription, remainingContent, isMultilineDescription };
  }

  // Standard patterns: "Using tool: **Edit** - `/path`", "🔧 Using tool: Bash - `cmd`"
  const match = firstLine.match(/(?:🔧\s*)?Using tool:\s*(?:\*\*)?([^*-]+?)(?:\*\*)?\s*(?:-\s*(.+))?$/);
  if (!match) return null;

  toolName = match[1]?.trim() || '';
  toolDescription = match[2]?.trim() || '';

  if (toolDescription.startsWith('`') && !toolDescription.endsWith('`')) {
    isMultilineDescription = true;
    const fullContentMatch = content.match(
      /(?:🔧\s*)?Using tool:\s*(?:\*\*)?[^*-]+?(?:\*\*)?\s*(?:-\s*([\s\S]*))?$/,
    );
    if (fullContentMatch && fullContentMatch[1]) {
      toolDescription = fullContentMatch[1].trim();
      remainingContent = '';
    }
  }

  if (toolName === 'TodoWrite') {
    toolName = 'Todos';
  }

  return { toolName, toolDescription, remainingContent, isMultilineDescription };
}

/** Wrap heredoc bodies (`cmd <<'PY' … PY`) in a code fence. */
function formatHeredocInContent(content: string): string {
  if (content.includes('<<') && /<<\s*'([^']+)'/.test(content)) {
    const heredocMatch = content.match(/<<\s*'([^']+)'/);
    if (heredocMatch) {
      const delimiter = heredocMatch[1] || '';
      const lines = content.split('\n');
      let startIndex = -1;
      let endIndex = -1;
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes(`<<'${delimiter}'`)) {
          startIndex = i + 1;
        } else if (lines[i].trim().startsWith(delimiter) && startIndex !== -1) {
          endIndex = i;
          break;
        }
      }
      if (startIndex !== -1 && endIndex !== -1) {
        const newLines = [...lines];
        newLines.splice(startIndex, 0, '```');
        newLines.splice(endIndex + 1, 0, '```');
        return newLines.join('\n');
      }
    }
  }
  return content;
}

export interface ToolUseSummary {
  name: string;
  /** One-line description with backticks stripped ('' when hidden, e.g. Todos). */
  description: string;
  /** Basename when the description is a single path-like token. */
  fileName: string | null;
  fullPath: string | null;
  /** "+N -M" when the agent reported line counts. */
  diffStat: string | null;
  /** There is hidden content (code block / output) beyond the summary line. */
  hasDetail: boolean;
}

/**
 * Derive "+N -M" from fenced code blocks in the detail content (diff-style
 * lines starting with a single +/-). Null when the blocks don't look like a
 * diff at all — e.g. a Write tool dumping raw file content.
 */
export function computeDiffStatFromContent(content: string): string | null {
  if (!content.includes('```')) return null;
  let additions = 0;
  let deletions = 0;
  let inFence = false;
  for (const line of content.split('\n')) {
    if (line.trimStart().startsWith('```')) {
      inFence = !inFence;
      continue;
    }
    if (!inFence) continue;
    if (line.startsWith('+') && !line.startsWith('+++')) additions += 1;
    else if (line.startsWith('-') && !line.startsWith('---')) deletions += 1;
  }
  if (additions === 0 && deletions === 0) return null;
  return `+${additions} -${deletions}`;
}

/**
 * Header label for a run of tool uses: distinct tool actions in first-use
 * order, deduped, each with its count — commands run, or distinct files
 * touched ("a file"/"N files"). The whole label is sentence-cased: only the
 * very first letter is capitalized, later segments stay lowercase.
 * e.g. "Run 2 commands, edit 2 files, read a file". Falls back to
 * "N tool uses" when nothing parses.
 */
export function describeToolRun(
  contents: string[],
  agentType: ToolUseAgentType,
  options?: { excludeFileEdits?: boolean },
): string {
  interface ToolAggregate {
    name: string;
    count: number;
    files: Set<string>;
    hasFile: boolean;
  }
  const order: ToolAggregate[] = [];
  const byName = new Map<string, ToolAggregate>();
  for (const content of contents) {
    const parsed = parseToolUse(content, agentType);
    if (!parsed) continue;
    const summary = summarizeToolUse(parsed);
    // Edits are surfaced as their own file chips, so callers can drop them from
    // the run label and keep only the other actions ("Run a command", …).
    if (options?.excludeFileEdits && isFileEditToolName(summary.name)) continue;
    let aggregate = byName.get(summary.name);
    if (!aggregate) {
      aggregate = { name: summary.name, count: 0, files: new Set(), hasFile: false };
      byName.set(summary.name, aggregate);
      order.push(aggregate);
    }
    aggregate.count += 1;
    if (summary.fullPath) {
      aggregate.hasFile = true;
      aggregate.files.add(summary.fullPath);
    }
  }
  if (order.length === 0) {
    // Excluding edits from an all-edit run leaves nothing to label.
    return options?.excludeFileEdits ? '' : `${contents.length} tool uses`;
  }
  const segments = order.map((aggregate) => {
    // Shell tools read better as an action than a name; count the commands run.
    if (aggregate.name === 'Bash' || aggregate.name === 'Exec') {
      return aggregate.count > 1 ? `Run ${aggregate.count} commands` : 'Run a command';
    }
    // File tools count the distinct files they touched.
    if (aggregate.hasFile) {
      return aggregate.files.size > 1
        ? `${aggregate.name} ${aggregate.files.size} files`
        : `${aggregate.name} a file`;
    }
    return aggregate.name;
  });
  // Sentence case: keep the first segment as-is, lowercase the rest's leads.
  return segments
    .map((segment, index) => (index === 0 ? segment : lowerFirst(segment)))
    .join(', ');
}

/** Lowercase only the first character, leaving the rest untouched. */
function lowerFirst(text: string): string {
  return text ? text[0].toLowerCase() + text.slice(1) : text;
}

/**
 * Distinct tool names in a run, in first-use order — used to choose the single
 * icon that stands in for a collapsed tool-use group. Mirrors describeToolRun's
 * parse loop but returns the raw names instead of a human-readable label.
 */
export function toolNamesInRun(contents: string[], agentType: ToolUseAgentType): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const content of contents) {
    const parsed = parseToolUse(content, agentType);
    if (!parsed) continue;
    const { name } = summarizeToolUse(parsed);
    if (name && !seen.has(name)) {
      seen.add(name);
      names.push(name);
    }
  }
  return names;
}

/** True for the tools that create or modify a file (Edit/Write/MultiEdit,
 *  plus codex's "Edited" patch) — as opposed to Read/Search/Bash. */
export function isFileEditToolName(name: string): boolean {
  const normalized = name.toLowerCase().replace(/[^a-z]/g, '');
  return (
    normalized === 'edit' ||
    normalized === 'edited' ||
    normalized === 'write' ||
    normalized === 'multiedit'
  );
}

/**
 * The label to show for a file: the path relative to the project root when the
 * file lives under it, otherwise the basename. Handles absolute paths (strip
 * the root prefix) and paths the agent already reported relative to its cwd
 * (shown as-is, since the cwd is the project root). Falls back to the basename
 * for absolute paths outside the project or when the root is unknown.
 */
export function relativizeFilePath(
  fullPath: string | null,
  fileName: string,
  projectPath?: string | null,
): string {
  if (!fullPath) return fileName;
  const isAbsolute = fullPath.startsWith('/') || /^[A-Za-z]:[\\/]/.test(fullPath);
  if (projectPath) {
    const root = projectPath.replace(/\/+$/, '');
    if (fullPath === root) return fileName;
    if (fullPath.startsWith(`${root}/`)) return fullPath.slice(root.length + 1);
  }
  // Already relative to the agent's cwd (= project root) — keep it, drop "./".
  if (!isAbsolute) return fullPath.replace(/^\.\//, '');
  // Absolute path outside the project, or unknown project — just the basename.
  return fileName;
}

export interface EditedFileSummary {
  /** The editing tool's display name ("Edit", "Write", "MultiEdit", "Edited"). */
  toolName: string;
  fileName: string;
  fullPath: string | null;
  /** "+N -M" when known (reported or derived from the diff), else null. */
  diffStat: string | null;
  /** Fenced diff/code content to preview on hover ('' when there is none). */
  diffContent: string;
}

/**
 * Summarize a single message as a file edit — the basename, path, +/- stat and
 * the diff body to preview on hover. Null when the message isn't a file-editing
 * tool use with a resolvable file name. Used to surface an at-a-glance list of
 * edited files (with hover diffs) on a collapsed tool-use group.
 */
export function editedFileFromContent(
  content: string,
  agentType: ToolUseAgentType,
): EditedFileSummary | null {
  const parsed = parseToolUse(content, agentType);
  if (!parsed || !isFileEditToolName(parsed.toolName)) return null;
  const summary = summarizeToolUse(parsed);
  if (!summary.fileName) return null;
  return {
    toolName: summary.name,
    fileName: summary.fileName,
    fullPath: summary.fullPath,
    diffStat: summary.diffStat,
    diffContent: parsed.remainingContent,
  };
}

export function summarizeToolUse(parsed: ParsedToolUse): ToolUseSummary {
  const firstLine = parsed.isMultilineDescription
    ? parsed.toolDescription.replace(/^`/, '').trimStart().split('\n')[0]
    : parsed.toolDescription;
  let description = firstLine.replace(/`/g, '').trim();

  let diffStat: string | null = null;
  const diffMatch = description.match(/\+\d+\s+-\d+\s*$/);
  if (diffMatch) {
    diffStat = diffMatch[0].trim();
    description = description.slice(0, diffMatch.index).trim();
  }
  if (diffStat === null) {
    // Not reported by the agent — derive it from the diff code block.
    diffStat = computeDiffStatFromContent(parsed.remainingContent);
  }

  let fileName: string | null = null;
  let fullPath: string | null = null;
  if (description && !/\s/.test(description) && description.includes('/')) {
    fullPath = description;
    const parts = description.replace(/\/+$/, '').split('/');
    fileName = parts[parts.length - 1] || description;
  }

  if (parsed.toolName === 'Todos') {
    description = '';
  }

  return {
    name: parsed.toolName,
    description,
    fileName,
    fullPath,
    diffStat,
    hasDetail: Boolean(parsed.remainingContent) || parsed.isMultilineDescription,
  };
}

