import type { Editor, JSONContent } from '@tiptap/core';
import type { MarkdownManager } from '@tiptap/markdown';
import type { Node as ProseMirrorNode, Schema } from '@tiptap/pm/model';
import { delimitBareUrls } from '@/components/ui/message-markdown-utils';

// Markdown in, markdown out, for a column agents read raw.
//
// @tiptap/markdown is built to never be misread: every `_ * [ ] ~ \` in a text
// node is backslash-escaped and every `& < >` becomes an entity. That turns
// `@src/my_file.ts` into `@src/my\_file.ts`, "R&D" into "R&amp;D" and a pasted
// `<details>` block into `&lt;details&gt;`, so the prompt an agent gets from
// the task would differ from what the person typed. It also misses the one
// escape that matters: a paragraph that starts with a literal `# ` is written
// out as a heading.
//
// So serialization writes text as typed, escaping only a block marker at the
// start of a line, and keeps that only if it reads back as the document on
// screen. The check is a real re-parse, not a guess about which characters
// are dangerous: a lone `*`, an intraword `_` or a `[x]` with no `(…)` after it
// are literal to the parser, and whether they are is the parser's call.

type TextEncoder = (text: string, node: JSONContent, parent: JSONContent | undefined) => string;

/** The one MarkdownManager method this module swaps out while serializing.
 *  Internal API: pinned by the exact @tiptap/markdown version in package.json
 *  and by markdown-codec.test.ts, which fails if the swap stops taking effect. */
interface ManagerTextHook {
  encodeTextForMarkdown: TextEncoder;
}

// What turns the start of a line into a block, and so needs a backslash when
// the text there is meant literally: ATX headings, quotes, bullets, ordered
// markers, fences, and lines made only of rule/setext characters.
const BLOCK_START: [RegExp, string][] = [
  [/^(\s{0,3})(#{1,6})(?=\s|$)/, '$1\\$2'],
  [/^(\s{0,3})>/, '$1\\>'],
  [/^(\s{0,3})([-+*])(?=\s)/, '$1\\$2'],
  [/^(\s{0,3})(\d{1,9})([.)])(?=\s|$)/, '$1$2\\$3'],
  [/^(\s{0,3})(`{3,}|~{3,})/, '$1\\$2'],
  [/^(\s{0,3})([-*_=])(?=[-*_=\s]*$)/, '$1\\$2'],
];

function escapeBlockStart(line: string): string {
  for (const [pattern, replacement] of BLOCK_START) {
    if (pattern.test(line)) return line.replace(pattern, replacement);
  }
  return line;
}

/** Text as typed, with a block marker escaped wherever the text opens a line
 *  of a paragraph. Marked text never needs it: its own `**`/`[` comes first. */
const verbatim: TextEncoder = (text, node, parent) => {
  if (parent?.type !== 'paragraph' || (node.marks?.length ?? 0) > 0) return text;
  const siblings = parent.content ?? [];
  const at = siblings.indexOf(node);
  const opensLine = at === 0 || siblings[at - 1]?.type === 'hardBreak';
  return text
    .split('\n')
    .map((line, i) => (i > 0 || opensLine ? escapeBlockStart(line) : line))
    .join('\n');
};

// A bare URL parses as a link whose text is its own href, which the serializer
// writes out as `[url](url)` (with any emphasis inside the label). Bare or
// angle-bracketed, it reads the same.
const SELF_LINK = /\[(\*\*|\*|~~|)(https?:\/\/[^\s\]*~]+)\1\]\(\2\)/g;

// The table serializer pads itself with a blank line on each side, on top of
// the one between blocks; one is all markdown needs.
function tidyTables(markdown: string): string {
  return markdown.replace(/\n\n\n(?=\|)/g, '\n\n').replace(/(\|[^\n]*)\n\n\n/g, '$1\n\n');
}

const FENCE = /^\s{0,3}(`{3,}|~{3,})/;

/**
 * Prepare stored markdown for the editor: give each bare URL an explicit end,
 * exactly as MessageMarkdown does before rendering, so a URL followed by CJK
 * punctuation links the same span in the editor as everywhere else.
 */
export function prepareMarkdown(markdown: string): string {
  if (!/https?:\/\//i.test(markdown)) return markdown;
  let fence: string | null = null;
  return markdown
    .split('\n')
    .map((line) => {
      const m = line.match(FENCE);
      if (m) {
        const run = m[1];
        if (fence === null) fence = run;
        else if (run[0] === fence[0] && run.length >= fence.length) fence = null;
        return line;
      }
      return fence === null ? delimitBareUrls(line) : line;
    })
    .join('\n');
}

function serializeVerbatim(manager: MarkdownManager, json: JSONContent): string {
  const hook = manager as unknown as ManagerTextHook;
  const original = hook.encodeTextForMarkdown;
  hook.encodeTextForMarkdown = verbatim;
  try {
    return manager.serialize(json);
  } finally {
    hook.encodeTextForMarkdown = original;
  }
}

/** A document in comparable form. Trailing empty paragraphs are dropped: the
 *  editor keeps one after a final table or code block for the caret to land
 *  in, and it serializes to nothing. */
function fingerprint(doc: JSONContent): string {
  const content = [...(doc.content ?? [])];
  while (content.length > 0) {
    const last = content[content.length - 1];
    if (last.type !== 'paragraph' || (last.content?.length ?? 0) > 0) break;
    content.pop();
  }
  return JSON.stringify({ ...doc, content });
}

/** How `markdown` reads back, through the schema so adjacent text runs merge
 *  and attributes get their defaults, just as they did in the editor. */
function readBack(schema: Schema, manager: MarkdownManager, markdown: string): string | null {
  try {
    return fingerprint(schema.nodeFromJSON(manager.parse(markdown)).toJSON() as JSONContent);
  } catch {
    return null;
  }
}

/**
 * A document as markdown, trimmed, with the least escaping that still reads
 * back as the same document. See the module comment. Defaults to the editor's
 * own document; the clipboard passes the copied slice.
 */
export function serializeMarkdown(editor: Editor, doc: ProseMirrorNode = editor.state.doc): string {
  const manager = editor.markdown;
  if (!manager) throw new Error('serializeMarkdown: the Markdown extension is not installed');
  const json = doc.toJSON() as JSONContent;
  const escaped = manager.serialize(json).trim();
  const plain = serializeVerbatim(manager, json).trim();
  const read = (markdown: string) => readBack(editor.schema, manager, markdown);

  // Bare URLs first; then `<url>`, which also ends a URL glued to CJK text that
  // a bare one would run into; then plain with `[url](url)` left alone. Each
  // with tables tidied first, and as written if that changes the reading.
  const candidates = [
    ...new Set(
      [tidyTables(plain), plain].flatMap((base) => [
        base.replace(SELF_LINK, '$1$2$1'),
        base.replace(SELF_LINK, '$1<$2>$1'),
        base,
      ]),
    ),
  ];

  const onScreen = fingerprint(json);
  for (const candidate of [...candidates, escaped]) {
    if (read(candidate) === onScreen) return candidate;
  }
  // Nothing reads back exactly: the document holds something markdown can't
  // say (two adjacent lists merge, leading spaces drop). Then the bar is the
  // escaped form's own reading, and the least-escaped text that meets it.
  const fallback = read(escaped);
  if (fallback !== null) {
    for (const candidate of candidates) {
      if (read(candidate) === fallback) return candidate;
    }
  }
  return escaped;
}
