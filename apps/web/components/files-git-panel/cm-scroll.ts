import { EditorView } from '@codemirror/view';

/**
 * Scroll-position memory for the file surfaces, expressed as a *line number plus
 * a sub-line pixel offset* rather than a raw `scrollTop`. The line keeps the
 * anchor meaningful when the same file is re-shown at a different width, with
 * word-wrap toggled, or after switching between the editor, the diff and the
 * read-only view; the offset restores the exact fraction of that line the user
 * was scrolled into, so returning to a file lands pixel-close, not a line off.
 * See {@link topAnchor}/{@link scrollToAnchor}.
 */
export interface ScrollAnchor {
  /** 1-based document line at the top of the viewport. */
  line: number;
  /** Pixels of that line scrolled above the viewport's top edge (>= 0). */
  offset: number;
}

/** How long scrolling must settle before the anchor is persisted. */
export const SCROLL_PERSIST_MS = 200;

/** The anchor for the line currently at the top of the viewport (`line: 1,
 *  offset: 0` when it can't be determined — i.e. scrolled to the top). */
export function topAnchor(view: EditorView): ScrollAnchor {
  const rect = view.scrollDOM.getBoundingClientRect();
  // Sample just below the top edge to catch the truly-topmost visible line even
  // when it's only partly in view, and at the horizontal centre so we land on
  // text rather than the line-number gutter. `false` → nearest pos, not null.
  const pos = view.posAtCoords({ x: rect.left + rect.width / 2, y: rect.top + 1 }, false);
  if (pos == null) return { line: 1, offset: 0 };
  const line = view.state.doc.lineAt(pos);
  const coords = view.coordsAtPos(line.from);
  const offset = coords ? Math.max(0, Math.round(rect.top - coords.top)) : 0;
  return { line: line.number, offset };
}

/** Scroll so `anchor.line` (1-based, clamped) sits at the top of the viewport
 *  with `anchor.offset` px of it hidden above — reproducing where the user was.
 *
 *  With `y: 'start'` CodeMirror places the line's top `yMargin` px below the
 *  container top, so a *negative* `yMargin` pulls it up by that many px, hiding
 *  exactly `offset` px of it. (The API default is `yMargin: 5`, which is why an
 *  explicit `0` is needed to land flush.) CodeMirror applies this in its own
 *  measure cycle, so it works even on the freshly-created view. */
export function scrollToAnchor(view: EditorView, anchor: ScrollAnchor): void {
  const total = view.state.doc.lines;
  const line = Math.max(1, Math.min(anchor.line, total));
  const pos = view.state.doc.line(line).from;
  view.dispatch({
    effects: EditorView.scrollIntoView(pos, { y: 'start', yMargin: -Math.max(0, anchor.offset) }),
  });
}
