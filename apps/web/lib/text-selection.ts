/**
 * Text selection inside clickable chat elements.
 *
 * Chromium never starts a text selection from a mousedown inside a `<button>`
 * (`HTMLButtonElement::CanStartSelection()` is hard-wired to false) or inside
 * an `<a href>` (a drag there is a link drag-and-drop instead). Most of a
 * transcript is exactly that — tool rows, thinking cards, sub-agent headers,
 * file citations, bare URLs — so dragging over it selected nothing, and the
 * mouseup then fired `click` and toggled the row you were trying to copy.
 *
 * Two things fix it, and both are needed:
 *   - `user-select: text` set explicitly on the element (`select-text`). The
 *     text-node check in `Node::CanStartSelection()` returns early on an
 *     explicit `text`, before it walks up to the button/anchor that would
 *     refuse. A link also needs `draggable={false}` so the drag is not claimed
 *     by DnD first.
 *   - a click guard: a drag that starts and ends inside the same element still
 *     dispatches `click`, so the handler has to skip its action when the
 *     gesture left a selection behind.
 */

/**
 * True when a pointer click should be treated as "the user was selecting text"
 * rather than "the user activated the control": the click came from a pointer
 * (`detail > 0`; keyboard activation reports 0) and the document holds a
 * non-empty selection at click time. A plain click collapses any earlier
 * selection to a caret on mousedown, so only a drag-select gets here.
 */
export function isTextSelectionClick(event: { detail: number }): boolean {
  if (event.detail <= 0) return false;
  if (typeof window === 'undefined') return false;
  const selection = window.getSelection();
  return !!selection && !selection.isCollapsed && selection.toString().length > 0;
}
