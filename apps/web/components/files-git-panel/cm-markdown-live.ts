import { syntaxTree } from '@codemirror/language';
import { StateField } from '@codemirror/state';
import type { EditorState, Extension, Range, Text } from '@codemirror/state';
import {
  Decoration,
  type DecorationSet,
  EditorView,
  ViewPlugin,
  type ViewUpdate,
  WidgetType,
} from '@codemirror/view';
import { inlineDestination } from './cm-markdown-links';

/**
 * Live-preview markdown for CodeMirror — Obsidian/Typora style, editing on the
 * rendered document instead of toggling to a raw-source view.
 *
 * The document buffer stays the file's *exact* markdown text, so saves are
 * byte-identical and the panel's save/conflict/poll/diff engine is untouched —
 * this only decorates the buffer: syntax marks (`#`, `**`, `` ` ``, `[..](..)`,
 * `>`, `---`) are hidden and their content styled, and GFM tables are rendered
 * as a real grid — EXCEPT on the construct the cursor/selection currently sits
 * in, which reveals its raw source so it stays editable in place. No
 * serialization, no round-trip: the reason Path B carries none of the
 * ProseMirror fidelity risk.
 *
 * Requires the editor's markdown language to be the GFM `markdownLanguage` base
 * (see markdown-live-editor); commonmark alone doesn't emit `Table`/
 * `Strikethrough` nodes.
 */

/** A zero-width hide — collapses a syntax-mark range out of view. */
const HIDE = Decoration.replace({});

/** True when any selection range overlaps `[from, to]`. Boundaries are
 *  inclusive, so a cursor resting right against a construct reveals it too —
 *  which also keeps arrow-key navigation from getting stuck on hidden marks. */
function selectionTouches(state: EditorState, from: number, to: number): boolean {
  for (const r of state.selection.ranges) {
    if (r.from <= to && r.to >= from) return true;
  }
  return false;
}

/** A front-matter block longer than this is not front matter — and the probe
 *  runs on every decoration build, so it needs a bound. */
const FRONT_MATTER_MAX_LINES = 200;

/** `---` alone on a line opens a front-matter block; either fence closes it. */
const FENCE_OPEN = /^---[ \t]*$/;
const FENCE_CLOSE = /^(?:---|\.\.\.)[ \t]*$/;

/**
 * The `---` … `---` block at the very top of a file, or null.
 *
 * Read from the text rather than the syntax tree, because the markdown parser
 * has no concept of front matter: it sees a thematic break, and then whatever
 * the YAML happens to look like — `title: x\n---` parses as a *setext heading*
 * whose `---` is a header mark, so the live layer used to render the opening
 * fence as a divider and hide the closing one, leaving the user staring at an
 * unterminated block. A blank line inside the YAML changes that shape again.
 *
 * Mounting `yamlFrontmatter` from @codemirror/lang-yaml would parse it properly
 * but swallows the entire file as YAML while the block is still unterminated —
 * i.e. every moment between typing the opening `---` and the closing one.
 */
export function frontMatterRange(doc: Text): { from: number; to: number } | null {
  if (!FENCE_OPEN.test(doc.line(1).text)) return null;
  const last = Math.min(doc.lines, FRONT_MATTER_MAX_LINES);
  for (let i = 2; i <= last; i++) {
    const line = doc.line(i);
    if (FENCE_CLOSE.test(line.text)) return { from: 0, to: line.to };
  }
  return null;
}

/** The rendered divider a `---`/`***` line collapses to when not being edited. */
class HrWidget extends WidgetType {
  toDOM(): HTMLElement {
    const el = document.createElement('span');
    el.className = 'cm-md-hr';
    return el;
  }
  eq(): boolean {
    return true;
  }
  ignoreEvent(): boolean {
    return false;
  }
}

/** Inline nodes whose whole span gets a styling class (the marks inside are
 *  hidden separately via {@link HIDDEN_MARKS}). */
const INLINE_STYLE_CLASS: Record<string, string> = {
  StrongEmphasis: 'cm-md-strong',
  Emphasis: 'cm-md-em',
  Strikethrough: 'cm-md-strike',
  InlineCode: 'cm-md-code',
};

/** Syntax-mark tokens that get hidden unless their construct is being edited.
 *  Link brackets are handled in the `Link` branch (so image marks stay put). */
const HIDDEN_MARKS = new Set([
  'HeaderMark',
  'EmphasisMark',
  'StrikethroughMark',
  'CodeMark',
  'QuoteMark',
]);

/**
 * Build the inline live-preview decorations for `ranges` (the viewport, in the
 * live editor; the whole doc, in tests). Pure over `state` — exported for tests.
 * Block-level tables are handled separately by {@link tableField}.
 */
export function computeMarkdownDecorations(
  state: EditorState,
  ranges: readonly { from: number; to: number }[],
): DecorationSet {
  const deco: Range<Decoration>[] = [];
  const tree = syntaxTree(state);
  // Metadata, not content: the block is left as source (nothing hidden inside
  // it) and styled apart, and the two branches below step around it.
  const frontMatter = frontMatterRange(state.doc);
  /** Wholly inside the front-matter block (a construct crossing out of it is
   *  left to the normal branches). */
  const inFrontMatter = (from: number, to: number): boolean =>
    frontMatter !== null && from >= frontMatter.from && to <= frontMatter.to;

  if (frontMatter) {
    for (const { from, to } of ranges) {
      if (from > frontMatter.to) continue;
      let pos = Math.max(from, frontMatter.from);
      while (pos <= Math.min(to, frontMatter.to)) {
        const line = state.doc.lineAt(pos);
        deco.push(Decoration.line({ class: 'cm-md-frontmatter' }).range(line.from));
        pos = line.to + 1;
      }
    }
  }

  for (const { from, to } of ranges) {
    tree.iterate({
      from,
      to,
      enter: (node) => {
        // Front matter is metadata, kept exactly as written — whatever the
        // markdown parser made of it. To it, the fences are thematic breaks or
        // a setext heading's marks, and a YAML list `[a, b]` is a link whose
        // brackets it would hide.
        if (inFrontMatter(node.from, node.to)) return false;
        const name = node.name;

        // Headings: size the whole line via a line decoration; the `#` run is
        // hidden by the HeaderMark branch below.
        const heading = /^ATXHeading([1-6])$/.exec(name);
        if (heading) {
          const line = state.doc.lineAt(node.from);
          deco.push(Decoration.line({ class: `cm-md-h${heading[1]}` }).range(line.from));
          return;
        }

        // Inline styling: bold / italic / strikethrough / inline-code.
        const styleClass = INLINE_STYLE_CLASS[name];
        if (styleClass) {
          deco.push(Decoration.mark({ class: styleClass }).range(node.from, node.to));
          return;
        }

        // Blockquote: tint + left border on every line it spans.
        if (name === 'Blockquote') {
          let pos = node.from;
          while (pos <= node.to) {
            const line = state.doc.lineAt(pos);
            deco.push(Decoration.line({ class: 'cm-md-quote' }).range(line.from));
            if (line.to + 1 > node.to) break;
            pos = line.to + 1;
          }
          return;
        }

        // Links: keep the text, hide `[` and `](url)` (reveal-aware). Images are
        // deliberately left as source in v1 — rendering remote images inline is
        // out of scope and the `!` disambiguates them for the reader.
        if (name === 'Link') {
          const marks = node.node.getChildren('LinkMark');
          if (marks.length >= 2) {
            const open = marks[0]; // `[`
            const close = marks[1]; // `]`
            // `[](url)` has no text to style, and an empty mark decoration is a
            // hard error in CodeMirror — which would take the whole preview
            // layer down with it.
            if (close.from > open.to) {
              // The destination is hidden in the rendered document, so hover
              // reveals it: the status bar a browser would give a link.
              const dest = inlineDestination(state, node.node);
              const spec = dest
                ? { class: 'cm-md-link', attributes: { title: dest } }
                : { class: 'cm-md-link' };
              deco.push(Decoration.mark(spec).range(open.to, close.from));
            }
            if (!selectionTouches(state, node.from, node.to)) {
              if (open.to > node.from) deco.push(HIDE.range(node.from, open.to));
              if (node.to > close.from) deco.push(HIDE.range(close.from, node.to));
            }
          }
          return;
        }

        // Horizontal rule: collapse the `---` line to a divider unless edited.
        if (name === 'HorizontalRule') {
          const line = state.doc.lineAt(node.from);
          if (!selectionTouches(state, line.from, line.to) && line.to > line.from) {
            deco.push(Decoration.replace({ widget: new HrWidget() }).range(line.from, line.to));
          }
          return;
        }

        // Syntax marks: hidden unless their enclosing construct is being edited.
        if (HIDDEN_MARKS.has(name)) {
          const parent = node.node.parent;
          if (!parent) return;
          if (selectionTouches(state, parent.from, parent.to)) return;
          let hideTo = node.to;
          // Swallow the single space that trails a `#`/`>` marker.
          if (
            (name === 'HeaderMark' || name === 'QuoteMark') &&
            state.doc.sliceString(node.to, node.to + 1) === ' '
          ) {
            hideTo += 1;
          }
          if (hideTo > node.from) deco.push(HIDE.range(node.from, hideTo));
          return;
        }
      },
    });
  }

  return Decoration.set(deco, true);
}

const markdownLivePlugin = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;
    constructor(view: EditorView) {
      this.decorations = computeMarkdownDecorations(view.state, view.visibleRanges);
    }
    update(u: ViewUpdate) {
      // Selection moves matter as much as edits: they drive reveal/hide.
      if (u.docChanged || u.selectionSet || u.viewportChanged) {
        this.decorations = computeMarkdownDecorations(u.view.state, u.view.visibleRanges);
      }
    }
  },
  { decorations: (v) => v.decorations },
);

// ── GFM tables ───────────────────────────────────────────────────────────────

export interface ParsedTable {
  header: string[];
  align: Array<'left' | 'right' | 'center' | null>;
  rows: string[][];
}

/** Split a markdown table row into trimmed cells, honoring escaped `\|`. */
function splitTableRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1);
  return s.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'));
}

/** Parse a GFM table's source into header/alignment/rows, or `null` when the
 *  block isn't a real table (needs a header row + a `---`/`:--:` delimiter). */
export function parseTable(src: string): ParsedTable | null {
  const lines = src.split('\n').map((l) => l.trim()).filter((l) => l !== '');
  if (lines.length < 2) return null;
  const header = splitTableRow(lines[0]);
  const delim = splitTableRow(lines[1]);
  if (delim.length === 0 || !delim.every((c) => /^:?-+:?$/.test(c))) return null;
  const align = delim.map<'left' | 'right' | 'center' | null>((c) => {
    const l = c.startsWith(':');
    const r = c.endsWith(':');
    return l && r ? 'center' : r ? 'right' : l ? 'left' : null;
  });
  const rows = lines.slice(2).map(splitTableRow);
  return { header, align, rows };
}

/** How many parsed tables to remember. A plain bound, cleared wholesale rather
 *  than evicted one by one — the set in play is the tables of one file. */
const PARSED_TABLE_CACHE_MAX = 64;
const parsedTables = new Map<string, ParsedTable | null>();

/** {@link parseTable}, memoised on the source text. The field below rebuilds on
 *  every keystroke and every cursor move, and re-splitting each table in the
 *  file every time is the other half of that cost — as is the widget parsing
 *  the same source again in `toDOM`. */
function parseTableCached(src: string): ParsedTable | null {
  const cached = parsedTables.get(src);
  if (cached !== undefined) return cached;
  const parsed = parseTable(src);
  if (parsedTables.size >= PARSED_TABLE_CACHE_MAX) parsedTables.clear();
  parsedTables.set(src, parsed);
  return parsed;
}

/** The rendered grid a GFM table collapses to when the cursor isn't inside it. */
class TableWidget extends WidgetType {
  constructor(readonly src: string) {
    super();
  }
  eq(other: TableWidget): boolean {
    return other.src === this.src;
  }
  toDOM(view: EditorView): HTMLElement {
    const wrap = document.createElement('div');
    wrap.className = 'cm-md-table-wrap';
    const parsed = parseTableCached(this.src);
    if (!parsed) {
      wrap.textContent = this.src;
      return wrap;
    }
    const table = document.createElement('table');
    table.className = 'cm-md-table';

    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    parsed.header.forEach((cell, i) => {
      const th = document.createElement('th');
      th.textContent = cell; // textContent, not innerHTML — no injection.
      const a = parsed.align[i];
      if (a) th.style.textAlign = a;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    for (const row of parsed.rows) {
      const tr = document.createElement('tr');
      for (let i = 0; i < parsed.header.length; i++) {
        const td = document.createElement('td');
        td.textContent = row[i] ?? '';
        const a = parsed.align[i];
        if (a) td.style.textAlign = a;
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);

    // Click the rendered grid to drop the cursor into its source (posAtDOM keeps
    // this correct across edits above the table), which reveals the raw markdown
    // via the selection-touch check so it can be edited.
    wrap.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const pos = view.posAtDOM(wrap);
      view.dispatch({ selection: { anchor: pos } });
      view.focus();
    });
    return wrap;
  }
  ignoreEvent(): boolean {
    return true;
  }
}

/** The only block nodes a GFM table can sit inside — everything else is skipped
 *  without descending. The walk used to enter *every* node in the document,
 *  down to each inline mark, and it reruns on every keystroke and cursor move. */
const TABLE_CONTAINERS = new Set([
  'Document',
  'Blockquote',
  'BulletList',
  'OrderedList',
  'ListItem',
]);

/** The block-level table decorations for `state`. Exported for tests; the field
 *  below is what the editor actually uses. */
export function buildTableDecorations(state: EditorState): DecorationSet {
  const deco: Range<Decoration>[] = [];
  syntaxTree(state).iterate({
    enter: (node) => {
      if (node.name !== 'Table') return TABLE_CONTAINERS.has(node.name);
      const first = state.doc.lineAt(node.from);
      const last = state.doc.lineAt(node.to);
      // Cursor/selection inside → leave the raw markdown visible for editing.
      if (selectionTouches(state, first.from, last.to)) return false;
      const src = state.doc.sliceString(first.from, last.to);
      if (!parseTableCached(src)) return false;
      deco.push(
        Decoration.replace({ widget: new TableWidget(src), block: true }).range(first.from, last.to),
      );
      return false; // a rendered table has nothing inside it to decorate
    },
  });
  return Decoration.set(deco, true);
}

/** Block-level table rendering lives in a StateField (not the ViewPlugin):
 *  CodeMirror only accepts block / cross-line-replacing decorations from a
 *  field. Rebuilds on edits, selection moves (reveal/hide), and — so a table
 *  far down a large file still renders — background parse progress. */
const tableField = StateField.define<DecorationSet>({
  create: (state) => buildTableDecorations(state),
  update: (deco, tr) => {
    if (tr.docChanged || tr.selection) return buildTableDecorations(tr.state);
    if (syntaxTree(tr.startState) !== syntaxTree(tr.state)) return buildTableDecorations(tr.state);
    return deco;
  },
  provide: (f) => EditorView.decorations.from(f),
});

// ── Theme ────────────────────────────────────────────────────────────────────

const markdownLiveTheme = EditorView.theme({
  // Headings: distinguished by size + weight only. The `span` rules override the
  // syntax theme's heading color so heading text reads as normal body color.
  //
  // Every surface below is keyed off `--foreground` rather than a literal white
  // so the rendered document follows the site theme along with the panel.
  '.cm-md-h1': { fontSize: '1.3em', fontWeight: '700', lineHeight: '1.35' },
  '.cm-md-h2': { fontSize: '1.18em', fontWeight: '700', lineHeight: '1.35' },
  '.cm-md-h3': { fontSize: '1.08em', fontWeight: '600', lineHeight: '1.35' },
  '.cm-md-h4': { fontSize: '1em', fontWeight: '600' },
  '.cm-md-h5': { fontSize: '0.95em', fontWeight: '600' },
  '.cm-md-h6': { fontSize: '0.9em', fontWeight: '600' },
  '.cm-md-h1 span, .cm-md-h2 span, .cm-md-h3 span, .cm-md-h4 span, .cm-md-h5 span, .cm-md-h6 span':
    { color: 'inherit' },
  '.cm-md-strong': { fontWeight: '700' },
  '.cm-md-em': { fontStyle: 'italic' },
  '.cm-md-strike': { textDecoration: 'line-through', opacity: '0.7' },
  '.cm-md-code': {
    fontFamily: 'var(--font-geist-mono), ui-monospace, SFMono-Regular, Menlo, monospace',
    backgroundColor: 'hsl(var(--foreground) / 0.08)',
    borderRadius: '3px',
    padding: '0.05em 0.3em',
    fontSize: '0.9em',
  },
  '.cm-md-link': { color: 'hsl(var(--info))', textDecoration: 'underline', textUnderlineOffset: '2px' },
  // Front matter reads as a quiet metadata header: real monospace, dimmed, on a
  // faint block. `span` overrides the syntax theme, which colours the YAML as
  // whatever markdown construct it mistook it for.
  '.cm-md-frontmatter': {
    fontFamily: 'var(--font-geist-mono), ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize: '0.85em',
    backgroundColor: 'hsl(var(--foreground) / 0.04)',
    color: 'hsl(var(--foreground) / 0.6)',
  },
  // The light-theme highlight style underlines headings, and the parser reads
  // this block as one — hence `textDecoration` in the reset.
  '.cm-md-frontmatter span': {
    color: 'inherit',
    fontWeight: 'inherit',
    fontStyle: 'inherit',
    textDecoration: 'none',
  },
  '.cm-md-quote': {
    borderLeft: '3px solid hsl(var(--foreground) / 0.2)',
    paddingLeft: '0.75em',
    color: 'hsl(var(--foreground) / 0.7)',
  },
  '.cm-md-hr': {
    display: 'inline-block',
    width: '100%',
    borderTop: '1px solid hsl(var(--foreground) / 0.25)',
    verticalAlign: 'middle',
  },
  '.cm-md-table-wrap': { padding: '6px 0', overflowX: 'auto' },
  '.cm-md-table': { borderCollapse: 'collapse', fontSize: '0.9em', lineHeight: '1.4' },
  '.cm-md-table th, .cm-md-table td': {
    border: '1px solid hsl(var(--foreground) / 0.15)',
    padding: '4px 10px',
    textAlign: 'left',
  },
  '.cm-md-table th': { fontWeight: '600', backgroundColor: 'hsl(var(--foreground) / 0.06)' },
});

/** The live-preview layer: pair with the GFM `markdownLanguage` base in an
 *  editable markdown view (see markdown-live-editor). */
export function markdownLivePreview(): Extension {
  return [markdownLivePlugin, tableField, markdownLiveTheme];
}
