import { syntaxTree } from '@codemirror/language';
import { StateField } from '@codemirror/state';
import type { EditorState, Extension, Range, Text } from '@codemirror/state';
import {
  Decoration,
  type DecorationSet,
  EditorView,
  runScopeHandlers,
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

/**
 * Where each cell's text sits in a table row, as offsets into `line` — the one
 * splitter for table rows, so what the grid renders and what a click resolves
 * to can never drift apart. Outer pipes and surrounding space are excluded; an
 * escaped `\|` is part of the cell.
 */
export function cellRanges(line: string): Array<{ from: number; to: number }> {
  let start = line.length - line.trimStart().length;
  let end = line.trimEnd().length;
  if (line[start] === '|') start += 1;
  if (end - 1 > start && line[end - 1] === '|' && line[end - 2] !== '\\') end -= 1;

  const out: Array<{ from: number; to: number }> = [];
  let cell = start;
  for (let i = start; i <= end; i++) {
    if (i < end && !(line[i] === '|' && line[i - 1] !== '\\')) continue;
    let from = cell;
    let to = i;
    while (from < to && /\s/.test(line[from])) from += 1;
    while (to > from && /\s/.test(line[to - 1])) to -= 1;
    out.push({ from, to });
    cell = i + 1;
  }
  return out;
}

/** Split a markdown table row into trimmed cells, honoring escaped `\|`. */
function splitTableRow(line: string): string[] {
  return cellRanges(line).map(({ from, to }) => line.slice(from, to).replace(/\\\|/g, '|'));
}

/** A rendered row of a table: the line it occupies and its cells, all as
 *  offsets into the table's own source. */
export interface TableRowSource {
  /** The row's line, trailing whitespace excluded. */
  from: number;
  to: number;
  cells: Array<{ from: number; to: number }>;
}

/**
 * The source of every rendered row of `src`, in `[row]` order — row 0 is the
 * header and the delimiter row is skipped, so the indices line up with
 * {@link ParsedTable}.
 */
export function tableRowSources(src: string): TableRowSource[] {
  const out: TableRowSource[] = [];
  let offset = 0;
  let row = 0;
  for (const line of src.split('\n')) {
    if (line.trim() !== '') {
      // Row 1 is the `---|---` delimiter: rendered as the grid's shape, not a row.
      if (row !== 1) {
        out.push({
          from: offset + (line.length - line.trimStart().length),
          to: offset + line.trimEnd().length,
          cells: cellRanges(line).map(({ from, to }) => ({ from: from + offset, to: to + offset })),
        });
      }
      row += 1;
    }
    offset += line.length + 1; // the `\n`
  }
  return out;
}

/**
 * The source offsets of every rendered cell of `src`, as `[row][col]`.
 * Offsets are relative to the table's own text.
 */
export function tableCellOffsets(src: string): Array<Array<{ from: number; to: number }>> {
  return tableRowSources(src).map((row) => row.cells);
}

/** A cell's text as it must be written back: a typed `|` would split the cell
 *  in two, and a pasted newline would end the table. */
export function escapeCellText(value: string): string {
  return value.replace(/\r?\n/g, ' ').replace(/(?<!\\)\|/g, '\\|');
}

/**
 * The document change that sets cell `[row][col]` of a table to `value`, as
 * offsets into the table's own source — the one place that knows how an edit in
 * the grid becomes markdown.
 *
 * A row rendered with fewer cells than the header has empty ones padded in by
 * the grid; typing in one of those appends the cells it needs to the row rather
 * than refusing the edit.
 */
export function cellEdit(
  src: string,
  row: number,
  col: number,
  value: string,
): { from: number; to: number; insert: string } | null {
  const rows = tableRowSources(src);
  const line = rows[row];
  if (!line) return null;
  // Trimmed, because a cell's source range is its *text*: the spaces around it
  // are the author's padding, which an edit has no business rewriting (and
  // which a typed trailing space would otherwise pile up in, one per keystroke).
  const text = escapeCellText(value).trim();
  const cell = line.cells[col];
  if (cell) return { from: cell.from, to: cell.to, insert: text };

  // Past the end of the row: grow it, filling any gap with empty cells.
  const gap = '|  '.repeat(Math.max(0, col - line.cells.length));
  const endsWithPipe = src.slice(line.to - 1, line.to) === '|';
  const at = endsWithPipe ? line.to - 1 : line.to;
  const insert = endsWithPipe ? `${gap}| ${text} ` : ` ${gap}| ${text}`;
  return { from: at, to: at, insert };
}

/** A rendered character index inside a cell, as an offset into its source —
 *  they differ by the backslash of every `\|` before it. */
export function sourceOffsetInCell(cellSrc: string, rendered: number): number {
  let seen = 0;
  for (let i = 0; i < cellSrc.length; i++) {
    if (seen === rendered) return i;
    if (cellSrc[i] === '\\' && cellSrc[i + 1] === '|') i += 1;
    seen += 1;
  }
  return cellSrc.length;
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

/** The rendered grid a GFM table collapses to when the cursor isn't inside it.
 *
 *  Its cells are `<input>`s, so the grid is edited in place rather than turning
 *  back into pipes the moment it is touched. Inputs, not `contenteditable`:
 *  typing in one mutates no text node CodeMirror's DOM observer is watching and
 *  moves no document selection, so the editor and the grid never fight over the
 *  DOM. Every keystroke is written straight back into the table's markdown
 *  through {@link cellEdit} — the buffer stays the file's exact source. */
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
    // The handlers below read the *current* source from here: the widget they
    // were created with is replaced on every edit, but this DOM lives on.
    wrap.dataset.src = this.src;

    const table = document.createElement('table');
    table.className = 'cm-md-table';
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    parsed.header.forEach((cell, col) => {
      headRow.appendChild(buildCell('th', cell, 0, col, parsed.align[col]));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    parsed.rows.forEach((row, r) => {
      const tr = document.createElement('tr');
      for (let col = 0; col < parsed.header.length; col++) {
        tr.appendChild(buildCell('td', row[col] ?? '', r + 1, col, parsed.align[col]));
      }
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);

    wrap.addEventListener('input', (event) => this.onInput(wrap, view, event));
    wrap.addEventListener('keydown', (event) => this.onKeyDown(wrap, view, event));
    wrap.addEventListener('mousedown', (event) => {
      // A click on the input itself belongs to the browser: it focuses the
      // cell and puts the caret under the pointer. A click elsewhere in the
      // same cell (its padding, past the end of a short value) still means
      // that cell, so it takes the caret to the end of the text.
      if (event.target instanceof HTMLInputElement) return;
      const cell = event.target instanceof Element ? event.target.closest('th,td') : null;
      event.preventDefault();
      const input = cell?.querySelector('input');
      if (input) {
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
        return;
      }
      // Outside the cells — the grid's own padding. Drop the caret into the
      // markdown, which reveals it for the edits the grid cannot express:
      // adding a column, changing the alignment row.
      view.dispatch({ selection: { anchor: view.posAtDOM(wrap) } });
      view.focus();
    });
    return wrap;
  }

  /** Update the grid in place for a new source — called by CodeMirror instead
   *  of redrawing, which is what keeps the caret inside the cell being typed
   *  in. A shape change (a column added in the source) redraws. */
  updateDOM(dom: HTMLElement, _view: EditorView, _old: WidgetType): boolean {
    const parsed = parseTableCached(this.src);
    const inputs = dom.querySelectorAll('input');
    if (!parsed || !dom.dataset.src) return false;
    const cells = [parsed.header, ...parsed.rows.map((r) => padRow(r, parsed.header.length))];
    if (cells.reduce((n, row) => n + row.length, 0) !== inputs.length) return false;

    dom.dataset.src = this.src;
    let i = 0;
    for (const row of cells) {
      for (const text of row) {
        const input = inputs[i++];
        // Typing into a cell leaves its input already holding the new text, so
        // this is a no-op for the cell being edited. It is not skipped, though:
        // an undo, or the file changing under the editor, must reach the
        // focused cell too — with the caret kept where it was.
        if (input.value !== text) {
          const caret = input.selectionStart;
          setCellValue(input, text);
          if (input === input.ownerDocument.activeElement && caret !== null) {
            const at = Math.min(caret, text.length);
            input.setSelectionRange(at, at);
          }
        }
      }
    }
    return true;
  }

  /** A keystroke in a cell, written back into the table's markdown. */
  private onInput(wrap: HTMLElement, view: EditorView, event: Event): void {
    const input = event.target;
    const cell = input instanceof HTMLInputElement ? input.parentElement : null;
    if (!(input instanceof HTMLInputElement) || !(cell instanceof HTMLElement)) return;
    const src = wrap.dataset.src;
    if (src == null) return;
    const edit = cellEdit(src, Number(cell.dataset.row), Number(cell.dataset.col), input.value);
    if (!edit) return;
    cell.dataset.value = input.value; // keeps the cell as wide as its text
    const base = view.posAtDOM(wrap);
    view.dispatch({
      changes: { from: base + edit.from, to: base + edit.to, insert: edit.insert },
      userEvent: 'input.type',
    });
  }

  private onKeyDown(wrap: HTMLElement, view: EditorView, event: KeyboardEvent): void {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    if (event.key === 'Tab') {
      event.preventDefault();
      focusSibling(wrap, input, event.shiftKey ? -1 : 1, 'all');
      return;
    }
    if (event.key === 'Enter' || event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      const columns = wrap.querySelectorAll('thead th').length;
      const step = event.key === 'ArrowUp' ? -columns : columns;
      if (focusSibling(wrap, input, step, 'all')) event.preventDefault();
      return;
    }
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      // Walking off the end of a cell's text continues into the next cell,
      // as it would if the row were one line of prose. Anywhere else in the
      // text (or with a selection to collapse) the arrow is the input's.
      const forward = event.key === 'ArrowRight';
      const caret = input.selectionStart ?? 0;
      const leaving =
        input.selectionEnd === caret && (forward ? caret === input.value.length : caret === 0);
      if (leaving && focusSibling(wrap, input, forward ? 1 : -1, forward ? 'start' : 'end')) {
        event.preventDefault();
      }
      return;
    }
    if (event.key === 'Escape') {
      // Out of the grid and into the markdown, at the same character.
      event.preventDefault();
      const cell = input.parentElement;
      const src = wrap.dataset.src;
      const offsets =
        cell instanceof HTMLElement && src != null
          ? tableCellOffsets(src)[Number(cell.dataset.row)]?.[Number(cell.dataset.col)]
          : undefined;
      const inCell = offsets
        ? sourceOffsetInCell(src!.slice(offsets.from, offsets.to), input.selectionStart ?? 0)
        : 0;
      view.dispatch({
        selection: { anchor: view.posAtDOM(wrap) + (offsets ? offsets.from + inCell : 0) },
      });
      view.focus();
      return;
    }
    // Editor shortcuts still work from inside a cell (save, undo, find…), while
    // the clipboard and select-all keep their meaning for the input's own text.
    // Undo is deliberately the document's, not the input's: they are the same
    // edits, and only one of the two histories knows about the rest of the file.
    if ((event.metaKey || event.ctrlKey) && !'acvx'.includes(event.key.toLowerCase())) {
      if (runScopeHandlers(view, event, 'editor')) event.preventDefault();
    }
  }

  ignoreEvent(): boolean {
    // Every event inside the grid is the grid's own: CodeMirror must not read a
    // keystroke in a cell as a keystroke in the document.
    return true;
  }
}

/** `row` padded out to the header's width, so every rendered cell has a slot. */
function padRow(row: string[], columns: number): string[] {
  return Array.from({ length: columns }, (_, i) => row[i] ?? '');
}

/** Set a cell input's text, keeping the sizing shadow in step. */
function setCellValue(input: HTMLInputElement, text: string): void {
  input.value = text;
  if (input.parentElement) input.parentElement.dataset.value = text;
}

/** One cell: an input for the text inside a box that carries the same text in a
 *  `data-value` the CSS draws invisibly behind it. That shadow is what gives
 *  the column its natural width — an input has none of its own — and it is why
 *  the box, not the `th`/`td`, is the element with `display: grid` (a table
 *  cell that stops being a table cell takes the grid's alignment with it). */
function buildCell(
  tag: 'th' | 'td',
  text: string,
  row: number,
  col: number,
  align: 'left' | 'right' | 'center' | null,
): HTMLElement {
  const cell = document.createElement(tag);
  if (align) cell.style.textAlign = align;
  const box = document.createElement('span');
  box.className = 'cm-md-tcell';
  box.dataset.row = String(row);
  box.dataset.col = String(col);
  box.dataset.value = text;
  const input = document.createElement('input');
  input.type = 'text';
  input.value = text;
  // An input's natural width is 20 characters; left at that, every column would
  // be 20 wide. One character, and the `data-value` shadow sets the width.
  input.size = 1;
  input.spellcheck = false;
  input.setAttribute('aria-label', `row ${row + 1}, column ${col + 1}`);
  box.appendChild(input);
  cell.appendChild(box);
  return cell;
}

/** Move the caret `step` cells along, if there is one: `all` selects the cell's
 *  text (tabbing into a cell means replacing it), `start`/`end` put the caret
 *  at the edge the caret arrived from. */
function focusSibling(
  wrap: HTMLElement,
  input: HTMLInputElement,
  step: number,
  caret: 'all' | 'start' | 'end',
): boolean {
  const inputs = Array.from(wrap.querySelectorAll('input'));
  const next = inputs[inputs.indexOf(input) + step];
  if (!next) return false;
  next.focus();
  if (caret === 'all') next.select();
  else {
    const at = caret === 'end' ? next.value.length : 0;
    next.setSelectionRange(at, at);
  }
  return true;
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
  // An editable cell: the input and the invisible copy of its text share one
  // grid area, so the column is as wide as the text however it is edited.
  '.cm-md-tcell': { display: 'inline-grid', verticalAlign: 'top' },
  '.cm-md-tcell::after': {
    content: 'attr(data-value) " "',
    gridArea: '1 / 1',
    visibility: 'hidden',
    whiteSpace: 'pre',
    font: 'inherit',
  },
  '.cm-md-tcell input': {
    gridArea: '1 / 1',
    width: '100%',
    minWidth: '1.5em',
    margin: '0',
    padding: '0',
    border: 'none',
    outline: 'none',
    background: 'transparent',
    color: 'inherit',
    font: 'inherit',
    textAlign: 'inherit',
  },
  '.cm-md-tcell input:focus': { outline: 'none' },
  '.cm-md-tcell input::selection': { backgroundColor: 'hsl(var(--info) / 0.3)' },
});

/** The live-preview layer: pair with the GFM `markdownLanguage` base in an
 *  editable markdown view (see markdown-live-editor). */
export function markdownLivePreview(): Extension {
  return [markdownLivePlugin, tableField, markdownLiveTheme];
}
