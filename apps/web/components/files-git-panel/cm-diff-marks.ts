import { RangeSetBuilder, StateField, type EditorState, type Extension, type Text } from '@codemirror/state';
import {
  Decoration,
  EditorView,
  ViewPlugin,
  WidgetType,
  type DecorationSet,
  type ViewUpdate,
} from '@codemirror/view';
import { highlightingFor, language } from '@codemirror/language';
import { highlightTree } from '@lezer/highlight';
import {
  getChunks,
  getOriginalDoc,
  mergeViewSiblings,
  type Change,
  type Chunk,
} from '@codemirror/merge';

/**
 * Word-level change marks for the @codemirror/merge surfaces, replacing the
 * package's own (`highlightChanges`), which box every changed character: a
 * wholly inserted block gets a box over each line on top of its tint, and a
 * re-wrapped paragraph lights up every moved line break. These read as VS
 * Code's inner-change highlights instead:
 *
 * - a pure insertion / deletion chunk gets no boxes — its line tint says it;
 * - a change that only moves whitespace across a line break (re-wrap) is not
 *   boxed;
 * - a box never spans a whole line (the tint already covers that);
 * - a chunk where too little text survives is a rewrite, not an edit — plain
 *   tinted lines, no boxes around the few tokens that happen to coincide.
 *
 * `diffChangeMarks` decorates a pane's own document (either MergeView pane, or
 * the editable side of a unified view). The unified view renders deleted lines
 * inside a widget the package builds, whose marks can't be filtered, so
 * `unifiedDeletedChunks` draws that widget itself with the same rules; the
 * package's widget is hidden by the theme.
 */

/** Box over inserted text (the `b` side). */
export const CHANGED_TEXT_CLASS = 'cm-vicoa-changedText';
/** Box over deleted text (the `a` pane, or the unified view's deleted widget). */
export const DELETED_TEXT_CLASS = 'cm-vicoa-deletedText';
/** Our replacement for the package's `.cm-deletedChunk` in the unified view. */
export const DELETED_CHUNK_CLASS = 'cm-vicoa-deletedChunk';

// Below this share of surviving text (non-whitespace chars outside any change,
// over the smaller side) a chunk is a rewrite: no boxes. Mirrors diff-align's
// MIN_COVERAGE so both diff surfaces make the same call.
const MIN_COVERAGE = 0.3;
// Deleted text longer than this isn't syntax-highlighted (package default).
const SYNTAX_MAX_LENGTH = 3000;

const WS_ONLY = /^\s*$/;
const WS_RE = /\s/g;

function nonWsLength(s: string): number {
  return s.replace(WS_RE, '').length;
}

type Side = 'a' | 'b';

/** The character ranges to box on `side` of `chunk`, in that side's document
 *  positions, clipped to lines; empty when the chunk reads better as plain
 *  tinted lines. */
export function chunkMarkRanges(chunk: Chunk, docA: Text, docB: Text, side: Side): [number, number][] {
  // Pure insertion/deletion: the line tint says it all.
  if (chunk.fromA === chunk.toA || chunk.fromB === chunk.toB) return [];
  const endA = Math.min(chunk.toA, docA.length);
  const endB = Math.min(chunk.toB, docB.length);
  const textA = docA.sliceString(chunk.fromA, endA);
  const textB = docB.sliceString(chunk.fromB, endB);

  let changedChars = 0;
  const kept: Change[] = [];
  for (const ch of chunk.changes) {
    const a = textA.slice(ch.fromA, ch.toA);
    const b = textB.slice(ch.fromB, ch.toB);
    changedChars += nonWsLength(a);
    // A re-wrap: whitespace on both sides, with a line break on one.
    if (WS_ONLY.test(a) && WS_ONLY.test(b) && (a.includes('\n') || b.includes('\n'))) continue;
    kept.push(ch);
  }
  // Text outside the changes is identical on both sides, so what survives can
  // be counted on either.
  const aChars = nonWsLength(textA);
  const shared = aChars - changedChars;
  const smaller = Math.min(aChars, nonWsLength(textB));
  if (smaller === 0 || shared < MIN_COVERAGE * smaller) return [];

  const doc = side === 'a' ? docA : docB;
  const base = side === 'a' ? chunk.fromA : chunk.fromB;
  const end = side === 'a' ? endA : endB;
  const out: [number, number][] = [];
  for (const ch of kept) {
    const from = base + (side === 'a' ? ch.fromA : ch.fromB);
    const to = Math.min(end, base + (side === 'a' ? ch.toA : ch.toB));
    if (from >= to) continue;
    const text = doc.sliceString(from, to);
    const wsOnly = WS_ONLY.test(text);
    // Whitespace with a line break on this side is a moved break, and the
    // words that moved are boxed on the other side.
    if (wsOnly && text.includes('\n')) continue;
    // Whitespace at the ends of a box is trimmed off — the indent of a wrapped
    // line, the space after an inserted word — unless the change is nothing
    // but whitespace on this side, in which case that is the change.
    const trim = !wsOnly;
    for (let line = doc.lineAt(from); ; line = doc.lineAt(line.to + 1)) {
      let f = Math.max(from, line.from);
      let t = Math.min(to, line.to);
      if (trim) {
        const frag = doc.sliceString(f, t);
        f += frag.length - frag.trimStart().length;
        t -= frag.length - frag.trimEnd().length;
      }
      // A box across the whole line adds nothing to the tint.
      if (f < t && !(f === line.from && t === line.to)) out.push([f, t]);
      if (line.to >= to) break;
    }
  }
  return out;
}

/** Both documents as seen from this pane, or `null` while a MergeView is still
 *  constructing: pane `a` is built (and runs its plugins) before pane `b`
 *  exists, so the first build there has nothing to compare against. */
function sideDocs(view: EditorView, side: Side): { a: Text; b: Text } | null {
  const siblings = mergeViewSiblings(view);
  if (siblings) {
    // Typed non-null, but undefined until the merge view has built both panes.
    const other = (side === 'a' ? siblings.b : siblings.a) as EditorView | undefined;
    if (!other) return null;
    return side === 'a'
      ? { a: view.state.doc, b: other.state.doc }
      : { a: other.state.doc, b: view.state.doc };
  }
  return { a: getOriginalDoc(view.state), b: view.state.doc };
}

const changedMark = Decoration.mark({ class: CHANGED_TEXT_CLASS });
const deletedMark = Decoration.mark({ class: DELETED_TEXT_CLASS });

function chunksOf(state: EditorState): readonly Chunk[] | null {
  return getChunks(state)?.chunks ?? null;
}

class ChangeMarksPlugin {
  deco: DecorationSet = Decoration.none;
  /** Set when a build ran before the sibling pane existed; retried on the next
   *  update (the merge view's first measure pass dispatches one). */
  private pending = false;

  constructor(view: EditorView) {
    this.build(view);
  }

  update(u: ViewUpdate) {
    if (
      this.pending ||
      u.docChanged ||
      u.viewportChanged ||
      chunksOf(u.startState) !== chunksOf(u.state)
    ) {
      this.build(u.view);
    }
  }

  private build(view: EditorView) {
    const info = getChunks(view.state);
    const side = info?.side;
    if (!info || !side) {
      this.deco = Decoration.none;
      this.pending = false;
      return;
    }
    const docs = sideDocs(view, side);
    if (!docs) {
      this.deco = Decoration.none;
      this.pending = true;
      return;
    }
    this.pending = false;
    const mark = side === 'a' ? deletedMark : changedMark;
    const builder = new RangeSetBuilder<Decoration>();
    const { from: viewFrom, to: viewTo } = view.viewport;
    for (const chunk of info.chunks) {
      const from = side === 'a' ? chunk.fromA : chunk.fromB;
      const to = side === 'a' ? chunk.toA : chunk.toB;
      if (from >= viewTo) break;
      if (to <= viewFrom) continue;
      for (const [f, t] of chunkMarkRanges(chunk, docs.a, docs.b, side)) builder.add(f, t, mark);
    }
    this.deco = builder.finish();
  }
}

/** Word-level boxes on this pane's changed lines. Add to each MergeView pane
 *  and to the unified view's editor (which is its `b` side). */
export const diffChangeMarks: Extension = ViewPlugin.fromClass(ChangeMarksPlugin, {
  decorations: (p) => p.deco,
});

// ── Unified view: deleted-chunk widget ───────────────────────────────────────

function sameRanges(x: [number, number][], y: [number, number][]): boolean {
  if (x.length !== y.length) return false;
  for (let i = 0; i < x.length; i++) if (x[i][0] !== y[i][0] || x[i][1] !== y[i][1]) return false;
  return true;
}

/** Deleted lines of one chunk, rendered like the package's `.cm-deletedChunk`
 *  (one `<div><del>` per line, syntax-highlighted with the editor's language)
 *  with the filtered boxes from `chunkMarkRanges`. `marks` are offsets into
 *  `text`. `dark` is part of the identity: the syntax classes baked into the
 *  DOM belong to one palette, so a theme flip must rebuild it. */
class DeletedChunkWidget extends WidgetType {
  private dom: HTMLElement | null = null;

  constructor(
    readonly text: string,
    readonly marks: [number, number][],
    readonly dark: boolean,
  ) {
    super();
  }

  eq(other: DeletedChunkWidget): boolean {
    return other.text === this.text && other.dark === this.dark && sameRanges(other.marks, this.marks);
  }

  toDOM(view: EditorView): HTMLElement {
    return this.dom ?? (this.dom = buildDeletedDOM(view.state, this.text, this.marks));
  }
}

function buildDeletedDOM(state: EditorState, text: string, marks: [number, number][]): HTMLElement {
  const dom = document.createElement('div');
  dom.className = DELETED_CHUNK_CLASS;

  // Syntax runs covering the whole text (unstyled gaps as empty class).
  const runs: [number, number, string][] = [];
  const lang = state.facet(language);
  if (lang && text.length <= SYNTAX_MAX_LENGTH) {
    let pos = 0;
    highlightTree(
      lang.parser.parse(text),
      { style: (tags) => highlightingFor(state, tags) },
      (from, to, cls) => {
        if (from > pos) runs.push([pos, from, '']);
        runs.push([from, to, cls]);
        pos = to;
      },
    );
    if (pos < text.length) runs.push([pos, text.length, '']);
  } else {
    runs.push([0, text.length, '']);
  }

  let line = newLine(dom);
  let mi = 0;
  for (const [from, to, cls] of runs) {
    let at = from;
    while (at < to) {
      // Next line break inside this run, if any (one that ends the run belongs
      // to the following run, which starts on it).
      const found = text.indexOf('\n', at);
      const nl = found >= 0 && found < to ? found : -1;
      let stop = nl >= 0 ? nl : to;
      while (mi < marks.length && marks[mi][1] <= at) mi++;
      let inMark = false;
      if (mi < marks.length) {
        const [mFrom, mTo] = marks[mi];
        if (mFrom <= at) {
          inMark = true;
          stop = Math.min(stop, mTo);
        } else {
          stop = Math.min(stop, mFrom);
        }
      }
      if (stop > at) {
        const node = document.createTextNode(text.slice(at, stop));
        const spanCls = inMark ? `${cls} ${DELETED_TEXT_CLASS}`.trim() : cls;
        if (spanCls) {
          const span = line.appendChild(document.createElement('span'));
          span.className = spanCls;
          span.appendChild(node);
        } else {
          line.appendChild(node);
        }
        at = stop;
      }
      if (at === nl) {
        line = newLine(dom);
        at++;
      }
    }
  }
  if (!line.firstChild) line.appendChild(document.createElement('br'));
  return dom;
}

/** Append a deleted line row; an empty previous row gets a `<br>` so it keeps
 *  its height. Returns the `<del>` the text goes into. */
function newLine(dom: HTMLElement): HTMLElement {
  const prev = dom.lastElementChild?.firstElementChild;
  if (prev && !prev.firstChild) prev.appendChild(document.createElement('br'));
  const row = dom.appendChild(document.createElement('div'));
  row.className = 'cm-deletedLine';
  return row.appendChild(document.createElement('del'));
}

// One decoration per chunk (and palette), so an edit elsewhere in the file
// doesn't rebuild every deleted block. Chunks are immutable; the merge view
// replaces the ones an edit touches.
const widgetCache = new WeakMap<Chunk, { dark: boolean; deco: Decoration }>();

function deletedWidget(chunk: Chunk, docA: Text, docB: Text, dark: boolean): Decoration {
  const known = widgetCache.get(chunk);
  if (known && known.dark === dark) return known.deco;
  const text = docA.sliceString(chunk.fromA, chunk.endA);
  const marks = chunkMarkRanges(chunk, docA, docB, 'a').map(
    ([f, t]): [number, number] => [f - chunk.fromA, t - chunk.fromA],
  );
  const deco = Decoration.widget({
    block: true,
    side: -1,
    widget: new DeletedChunkWidget(text, marks, dark),
  });
  widgetCache.set(chunk, { dark, deco });
  return deco;
}

function buildDeletedChunks(state: EditorState): DecorationSet {
  const chunks = chunksOf(state);
  if (!chunks) return Decoration.none;
  const docA = getOriginalDoc(state);
  const dark = state.facet(EditorView.darkTheme);
  const builder = new RangeSetBuilder<Decoration>();
  for (const chunk of chunks) {
    if (chunk.fromA >= chunk.toA) continue; // nothing deleted
    builder.add(chunk.fromB, chunk.fromB, deletedWidget(chunk, docA, state.doc, dark));
  }
  return builder.finish();
}

/** The unified view's deleted-lines widgets, one above each chunk that removed
 *  something. Pair with `unifiedMergeView({ highlightChanges: false })` and a
 *  theme that hides `.cm-deletedChunk`. */
export const unifiedDeletedChunks: Extension = StateField.define<DecorationSet>({
  create: buildDeletedChunks,
  update(deco, tr) {
    // A reconfigure is how the theme (and with it the syntax palette) flips.
    if (tr.reconfigured || chunksOf(tr.startState) !== chunksOf(tr.state)) {
      return buildDeletedChunks(tr.state);
    }
    return tr.docChanged ? deco.map(tr.changes) : deco;
  },
  provide: (f) => EditorView.decorations.from(f),
});
