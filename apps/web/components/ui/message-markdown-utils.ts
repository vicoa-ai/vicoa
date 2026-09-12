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

const URL_SCHEME = /https?:\/\//gi;
/** Ends a bare URL: whitespace, markdown's own `<`/`>`/backtick, a table `|`,
 *  or any non-ASCII punctuation or symbol (`（），。：`, `…`, `—`, emoji…). */
const URL_END = /[\s<>|`]|(?![\x00-\x7f])[\p{P}\p{S}]/u;
/** GFM's trailing marks: never part of a URL when nothing but marks follow. */
const URL_TRAIL_MARKS = '!"\'*,.:;?_~]';

/** Split a line into code spans and the prose between them. A backtick run
 *  with no closing run of the same length is prose, as in CommonMark. */
function splitCodeSpans(line: string): { text: string; code: boolean }[] {
  const parts: { text: string; code: boolean }[] = [];
  let i = 0;
  let proseStart = 0;
  while (i < line.length) {
    if (line[i] !== '`') {
      i += 1;
      continue;
    }
    let runEnd = i;
    while (runEnd < line.length && line[runEnd] === '`') runEnd += 1;
    const size = runEnd - i;
    let close = -1;
    for (let j = runEnd; j < line.length; ) {
      if (line[j] !== '`') {
        j += 1;
        continue;
      }
      let k = j;
      while (k < line.length && line[k] === '`') k += 1;
      if (k - j === size) {
        close = j;
        break;
      }
      j = k;
    }
    if (close === -1) {
      i = runEnd;
      continue;
    }
    if (i > proseStart) parts.push({ text: line.slice(proseStart, i), code: false });
    parts.push({ text: line.slice(i, close + size), code: true });
    i = proseStart = close + size;
  }
  if (proseStart < line.length) parts.push({ text: line.slice(proseStart), code: false });
  return parts;
}

/** Drop the trailing marks GFM would not count as part of the URL: the
 *  {@link URL_TRAIL_MARKS}, a `)` with no `(` to balance it, and an `&name;`
 *  that reads as a character reference. */
function trimUrlTrail(url: string): string {
  let end = url.length;
  while (end > 0) {
    const ch = url[end - 1];
    if (ch === ';') {
      const ref = /&[a-z]+;$/i.exec(url.slice(0, end));
      end -= ref ? ref[0].length : 1;
    } else if (URL_TRAIL_MARKS.includes(ch)) {
      end -= 1;
    } else if (ch === ')') {
      const head = url.slice(0, end);
      const opens = head.split('(').length;
      const closes = head.split(')').length;
      if (closes <= opens) break;
      end -= 1;
    } else {
      break;
    }
  }
  return url.slice(0, end);
}

/** The `*`/`~` run an emphasis or strikethrough would have opened with right
 *  before `at`, or `''`. A lone `~` is left alone: it's common in URLs
 *  (`/~user`) and rare as a delimiter. `_` is never treated as one — it is far
 *  more often part of the URL (`__init__.py`) than emphasis around it. */
function emphasisOpener(text: string, at: number): string {
  const ch = text[at - 1];
  if (ch !== '*' && ch !== '~') return '';
  let from = at - 1;
  while (from > 0 && text[from - 1] === ch) from -= 1;
  const run = text.slice(from, at);
  return ch === '~' && run.length < 2 ? '' : run;
}

/** Index of the last `(` with no `)` after it, or `body.length` if every
 *  paren is closed. */
function unclosedParen(body: string): number {
  let cut = body.length;
  let depth = 0;
  for (let i = body.length - 1; i >= 0; i -= 1) {
    if (body[i] === ')') depth += 1;
    else if (body[i] === '(') {
      if (depth === 0) cut = i;
      else depth -= 1;
    }
  }
  return cut;
}

/** Net unclosed `[` in a run of prose (escaped brackets don't count). */
function countOpenLabels(prose: string, depth: number): number {
  let open = depth;
  for (let i = 0; i < prose.length; i += 1) {
    if (prose[i] === '\\') {
      i += 1;
    } else if (prose[i] === '[') {
      open += 1;
    } else if (prose[i] === ']' && open > 0) {
      open -= 1;
    }
  }
  return open;
}

/**
 * Rewrite every bare `http(s)://` URL on one line of markdown as an explicit
 * `<url>` autolink.
 *
 * GFM's autolink literal runs a bare URL up to the next ASCII whitespace or
 * `<`, only ever forgiving a few *trailing* ASCII marks. CJK prose puts
 * full-width punctuation straight after a URL, and a bold URL glues its
 * closing `**` on as well, so `**https://x/pull/54**（rebase …` links the text
 * `https://x/pull/54**（rebase` and leaves the opening `**` dangling. An
 * angle-bracketed autolink ends exactly where we say it ends, so the same
 * source renders as a bold link followed by plain text.
 *
 * The URL is cut at {@link URL_END} and trimmed like GFM trims it, plus two
 * rules GFM lacks, for prose that glues ASCII punctuation on too
 * (`**https://x/pull/54**(rebase …)`): a URL opened by an emphasis run
 * (`**`, `*`, `~~`) ends at the matching run, and an unclosed `(` is never part
 * of it (a closed one still is: `wiki/Foo_(bar)`). Untouched: code spans;
 * anything GFM wouldn't link either (a URL glued to a preceding letter, inside
 * an unclosed `[…` label, or with no domain); and URLs that already have a
 * delimiter — `<…>`, an inline-link destination `](…)`, an HTML attribute
 * value. Fenced code is the caller's job; indented code blocks are not
 * detected. `www.` and e-mail literals are left to GFM.
 */
export function delimitBareUrls(line: string): string {
  if (!/https?:\/\//i.test(line)) return line;
  let out = '';
  // Unclosed `[` seen so far: links can't nest, and GFM won't autolink inside
  // a label either, so leave those alone.
  let openLabels = 0;
  for (const { text, code } of splitCodeSpans(line)) {
    if (code) {
      out += text;
      continue;
    }
    let from = 0;
    URL_SCHEME.lastIndex = 0;
    for (let m = URL_SCHEME.exec(text); m; m = URL_SCHEME.exec(text)) {
      const start = m.index;
      openLabels = countOpenLabels(text.slice(from, start), openLabels);
      out += text.slice(from, start);
      from = start;
      const before = text.slice(Math.max(0, start - 2), start);
      const prev = before.slice(-1);
      const skip =
        openLabels > 0 ||
        /[a-z<]/i.test(prev) ||
        before === '](' ||
        ((prev === '"' || prev === "'") && before[0] === '=');
      if (skip) continue;

      let end = start + m[0].length;
      while (end < text.length) {
        const ch = String.fromCodePoint(text.codePointAt(end) as number);
        if (URL_END.test(ch)) break;
        end += ch.length;
      }
      let body = text.slice(start + m[0].length, end);
      const opener = emphasisOpener(text, start);
      if (opener) {
        const close = body.indexOf(opener);
        if (close !== -1) body = body.slice(0, close);
      }
      body = body.slice(0, unclosedParen(body));
      const url = trimUrlTrail(m[0] + body);
      // Something GFM would call a domain has to follow the scheme.
      if (!/^[\p{L}\p{N}]/u.test(url.slice(m[0].length))) continue;

      out += `<${url}>`;
      from = start + url.length;
      URL_SCHEME.lastIndex = from;
    }
    openLabels = countOpenLabels(text.slice(from), openLabels);
    out += text.slice(from);
  }
  return out;
}
