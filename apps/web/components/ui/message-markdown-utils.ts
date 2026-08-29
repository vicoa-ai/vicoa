export type DiffLine = { content: string; type: 'add' | 'remove' | 'context' | 'ellipsis' };
export type ParsedMessageOptions = { content: string; options: string[] };

export function diffLineBackgroundClass(kind: 'add' | 'remove' | string): string {
  if (kind === 'add') return 'bg-green-50 dark:bg-green-900/50';
  if (kind === 'remove') return 'bg-red-50 dark:bg-red-900/50';
  return '';
}

const CONTEXT_LINES = 3;
const BRACKET_OPTIONS_REGEX = /\[OPTIONS\](.*?)\[\/OPTIONS\]/is;
const SLASH_OPTIONS_REGEX = /(?:^|\n)options\/\s*\n?([\s\S]*?)\n?\\options(?:\n|$)/i;

const stripDiffPrefix = (line: string) => line.slice(1);

const isDiffHeaderLine = (line: string) => line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@');

const formatMergedLine = (prefix: '+' | '-' | ' ', content: string) => {
  const spacer = content.startsWith(' ') ? '' : ' ';
  return `${prefix}${spacer}${content}`;
};

const buildMergedDiffLines = (
  removedLines: string[],
  addedLines: string[],
  compactContext: boolean
): DiffLine[] => {
  const m = removedLines.length;
  const n = addedLines.length;
  const lcs: number[][] = Array(m + 1)
    .fill(null)
    .map(() => Array(n + 1).fill(0));

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (removedLines[i - 1] === addedLines[j - 1]) {
        lcs[i][j] = lcs[i - 1][j - 1] + 1;
      } else {
        lcs[i][j] = Math.max(lcs[i - 1][j], lcs[i][j - 1]);
      }
    }
  }

  const result: DiffLine[] = [];
  let i = m;
  let j = n;

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && removedLines[i - 1] === addedLines[j - 1]) {
      result.unshift({ content: formatMergedLine(' ', removedLines[i - 1]), type: 'context' });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || lcs[i][j - 1] >= lcs[i - 1][j])) {
      result.unshift({ content: formatMergedLine('+', addedLines[j - 1]), type: 'add' });
      j -= 1;
    } else if (i > 0) {
      result.unshift({ content: formatMergedLine('-', removedLines[i - 1]), type: 'remove' });
      i -= 1;
    }
  }

  if (!compactContext) {
    return result;
  }

  const compacted: DiffLine[] = [];
  let contextBuffer: DiffLine[] = [];

  for (const item of result) {
    if (item.type === 'context') {
      contextBuffer.push(item);
      continue;
    }

    if (contextBuffer.length > CONTEXT_LINES * 2 + 1) {
      compacted.push(...contextBuffer.slice(0, CONTEXT_LINES));
      compacted.push({ content: '...', type: 'ellipsis' });
      compacted.push(...contextBuffer.slice(-CONTEXT_LINES));
    } else {
      compacted.push(...contextBuffer);
    }

    contextBuffer = [];
    compacted.push(item);
  }

  if (contextBuffer.length > CONTEXT_LINES) {
    compacted.push(...contextBuffer.slice(0, CONTEXT_LINES));
    compacted.push({ content: '...', type: 'ellipsis' });
  } else {
    compacted.push(...contextBuffer);
  }

  return compacted;
};

type FormatDiffOptions = {
  compactContext?: boolean;
};

export const formatDiffLines = (
  text: string,
  shouldMergeDiff: boolean,
  options: FormatDiffOptions = {}
): DiffLine[] => {
  const lines = text.split('\n');
  const result: DiffLine[] = [];
  let removedLines: string[] = [];
  let addedLines: string[] = [];
  let rawLines: string[] = [];
  let isMergeable = true;
  let hasAddedLines = false;
  const compactContext = options.compactContext !== false;

  const flush = () => {
    if (rawLines.length === 0) {
      return;
    }

    if (shouldMergeDiff && isMergeable && removedLines.length > 0 && addedLines.length > 0) {
      result.push(...buildMergedDiffLines(removedLines, addedLines, compactContext));
    } else {
      rawLines.forEach((line) => {
        if (line.startsWith('+')) {
          result.push({ content: line, type: 'add' });
        } else if (line.startsWith('-')) {
          result.push({ content: line, type: 'remove' });
        } else {
          result.push({ content: line, type: 'context' });
        }
      });
    }

    removedLines = [];
    addedLines = [];
    rawLines = [];
    isMergeable = true;
    hasAddedLines = false;
  };

  for (const line of lines) {
    if (isDiffHeaderLine(line)) {
      flush();
      result.push({ content: line, type: 'context' });
      continue;
    }

    if (line.startsWith('+') || line.startsWith('-')) {
      rawLines.push(line);
      if (line.startsWith('+')) {
        addedLines.push(stripDiffPrefix(line));
        hasAddedLines = true;
      } else {
        if (hasAddedLines) {
          isMergeable = false;
        }
        removedLines.push(stripDiffPrefix(line));
      }
      continue;
    }

    flush();
    result.push({ content: line, type: 'context' });
  }

  flush();

  return result;
};

function parseOptionsBlock(optionsText: string): string[] {
  return optionsText
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => /^\d+\./.test(line))
    .map((line) => {
      const match = line.match(/^\d+\.\s*(.+)$/);
      return match ? match[1].trim() : line;
    })
    .filter(Boolean);
}

const TASK_NOTIFICATION_PATTERN = /<task-notification>([\s\S]*?)<\/task-notification>/gi;
const TASK_NOTIFICATION_STATUS = /<status>([\s\S]*?)<\/status>/i;
const TASK_NOTIFICATION_SUMMARY = /<summary>([\s\S]*?)<\/summary>/i;

// Collapse <task-notification> harness blocks to a two-line summary —
// `Task <status>  \n<summary>` — ignoring task-id / output-file / result /
// usage. The trailing two-space + newline forces a markdown hard break so
// the lines render adjacent rather than as separate paragraphs.
export function formatTaskNotifications(text: string): string {
  if (!text.includes('<task-notification>')) return text;
  return text.replace(TASK_NOTIFICATION_PATTERN, (_match, body: string) => {
    const status = body.match(TASK_NOTIFICATION_STATUS)?.[1]?.trim() ?? '';
    const summary = body.match(TASK_NOTIFICATION_SUMMARY)?.[1]?.trim() ?? '';
    return `Task ${status}  \n${summary}`;
  });
}

export function normalizeCommandOutput(text: string): string {
  return text
    .replace(/<local-command-stdout>([\s\S]*?)<\/local-command-stdout>/g, '$1')
    .replace(/<local-command-stderr>[\s\S]*?<\/local-command-stderr>/g, '')
    .replace(/\x1B?\[1m([\s\S]*?)\x1B?\[(?:22|0)m/g, '**$1**')
    .replace(/\x1B?\[\d+(?:;\d+)*m/g, '')
    .replace(/\x1B?\[\?\d+[hl]/g, '');
}

export function extractMessageOptions(content: string): ParsedMessageOptions {
  const bracketMatch = content.match(BRACKET_OPTIONS_REGEX);
  if (bracketMatch) {
    return {
      content: content.replace(BRACKET_OPTIONS_REGEX, '').trim(),
      options: parseOptionsBlock(bracketMatch[1] || ''),
    };
  }

  const slashMatch = content.match(SLASH_OPTIONS_REGEX);
  if (slashMatch) {
    return {
      content: content.replace(SLASH_OPTIONS_REGEX, '\n').trim(),
      options: parseOptionsBlock(slashMatch[1] || ''),
    };
  }

  return { content, options: [] };
}
