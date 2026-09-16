/**
 * Two Blink quirks that break drag-selecting transcript text, and their
 * work-arounds. Both are attached to the transcript scroller by
 * `attachSelectionDragFix`.
 *
 * 1. A drag dies on fractional pointer coordinates (Retina / trackpad).
 *
 *    On mousedown Blink hit-tests at the *rounded* pointer position and places
 *    a caret there (`event_handling_util::ContentPointFromRootFrame` →
 *    `PhysicalOffset::FromPointFRound`). When the drag starts it re-hit-tests
 *    at the stored `mouse_down_pos_`, which was *floored*
 *    (`MouseEventManager::HandleMousePressEvent` → `gfx::ToFlooredPoint`). If
 *    a character boundary falls between those two integer x's the re-hit-test
 *    yields a different caret, `FrameSelection::SetSelection` sees a change,
 *    and `SelectionController::NotifySelectionChanged` drops the drag state
 *    back to "placed caret" — so every later mousemove just collapses the
 *    caret at the pointer instead of extending from the anchor. Nothing ever
 *    highlights. In 14px monospace prose that is roughly one drag in fifteen;
 *    the user reads it as "I can't select this", retries within the
 *    double-click interval, and the retry is then a word- or
 *    paragraph-granularity drag that grabs far more than they wanted.
 *
 *    Fix: right after Blink has placed its caret, move it to the caret the
 *    drag will re-hit-test to (`caretRangeFromPoint` at the floored point).
 *    The re-hit-test then finds the selection already there, `SetSelection`
 *    is a no-op, the drag state survives, and the selection extends normally.
 *    Only ever touches a collapsed selection, so word/paragraph selection
 *    (double/triple click), shift-click extension and drag-of-selected-text
 *    are untouched.
 *
 * 2. A drag that leaves a <table> box jumps to the table's start or end.
 *
 *    `PhysicalBoxFragment::PositionForPointInTable` maps every pointer
 *    position outside the <table> box to "before the table" when x is in the
 *    left half, else "after the table" — there is no per-row hit-test outside
 *    the box. Overshoot a row's left edge by the cell padding and the whole
 *    selection flips backward to the table start (plus the previous block's
 *    trailing newline); overshoot the right edge, or drift into the gap
 *    above, and the rest of the table is selected in one go.
 *
 *    Fix: while the primary button is down, after each Blink selection update
 *    re-aim the focus at the row the pointer is level with (its first/last
 *    cell), or at the first cell when the pointer is in the gap above. The
 *    anchor is never touched, so Blink's own drag keeps extending from it.
 */

const TEXT_CONTROL_SELECTOR = 'input, textarea, select, [contenteditable=""], [contenteditable="true"]';

/** How far above a table's top edge still counts as "aiming at the table". */
const ABOVE_TABLE_SLACK_PX = 24;

/** Attach to a transcript container. Returns the detach function. */
export function attachSelectionDragFix(container: HTMLElement): () => void {
  let dragging = false;
  let pointerX = 0;
  let pointerY = 0;

  const onMouseDown = (event: MouseEvent) => {
    // Plain left button only: modifiers and multi-clicks have their own
    // selection semantics that must not be disturbed.
    if (event.button !== 0 || event.detail > 1 || event.shiftKey || event.metaKey || event.ctrlKey) return;
    if (typeof document.caretRangeFromPoint !== 'function') return;
    const target = event.target instanceof Element ? event.target : null;
    // Never move the document selection out from under a focused text control.
    if (target?.closest(TEXT_CONTROL_SELECTOR)) return;
    dragging = true;
    pointerX = event.clientX;
    pointerY = event.clientY;
    const x = Math.floor(event.clientX);
    const y = Math.floor(event.clientY);
    // Blink places its caret as the default action, after listeners have run,
    // so defer to the next task. A drag's first mousemove is a later input
    // task, so this lands in between.
    setTimeout(() => {
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0 || !selection.isCollapsed) return;
      if (document.activeElement?.closest(TEXT_CONTROL_SELECTOR)) return;
      const range = document.caretRangeFromPoint(x, y);
      if (!range || !container.contains(range.startContainer)) return;
      selection.collapse(range.startContainer, range.startOffset);
    }, 0);
  };

  // The pointer may leave the container mid-drag, so track it on the document.
  const onMouseMove = (event: MouseEvent) => {
    if (!dragging) return;
    pointerX = event.clientX;
    pointerY = event.clientY;
  };
  const endDrag = () => {
    dragging = false;
  };

  const onSelectionChange = () => {
    if (!dragging) return;
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return;
    if (!selection.anchorNode || !container.contains(selection.anchorNode)) return;
    const table = tableAimedAt(container, pointerX, pointerY);
    if (!table) return;
    const target = targetCell(table, pointerX, pointerY);
    if (!target || !selection.focusNode || target.cell.contains(selection.focusNode)) return;
    selection.extend(target.cell, target.atEnd ? target.cell.childNodes.length : 0);
  };

  container.addEventListener('mousedown', onMouseDown, { passive: true });
  document.addEventListener('mousemove', onMouseMove, { passive: true });
  document.addEventListener('mouseup', endDrag, { passive: true });
  window.addEventListener('blur', endDrag);
  document.addEventListener('selectionchange', onSelectionChange);
  return () => {
    container.removeEventListener('mousedown', onMouseDown);
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', endDrag);
    window.removeEventListener('blur', endDrag);
    document.removeEventListener('selectionchange', onSelectionChange);
  };
}

/**
 * The table whose box the pointer is level with but outside of (or in the gap
 * just above), i.e. a position Blink resolves to before/after the whole table.
 */
function tableAimedAt(container: HTMLElement, x: number, y: number): HTMLTableElement | null {
  for (const table of container.querySelectorAll('table')) {
    const rect = table.getBoundingClientRect();
    if (rect.height === 0) continue;
    const beside = y >= rect.top && y <= rect.bottom && (x < rect.left || x > rect.right);
    const above = y < rect.top && y >= rect.top - ABOVE_TABLE_SLACK_PX;
    if (beside || above) return table;
  }
  return null;
}

/**
 * Where the drag should be aimed: the end of the last cell of the row the
 * pointer is level with when it is off the right edge, otherwise the start of
 * that row's first cell (off the left edge, or in the gap above → first row).
 */
function targetCell(
  table: HTMLTableElement,
  x: number,
  y: number,
): { cell: HTMLTableCellElement; atEnd: boolean } | null {
  const rect = table.getBoundingClientRect();
  const rows = Array.from(table.rows);
  if (rows.length === 0) return null;
  const above = y < rect.top;
  const row = above
    ? rows[0]
    : rows.find((r) => {
        const rr = r.getBoundingClientRect();
        return y >= rr.top && y <= rr.bottom;
      });
  if (!row || row.cells.length === 0) return null;
  const atEnd = !above && x > rect.right;
  return { cell: atEnd ? row.cells[row.cells.length - 1] : row.cells[0], atEnd };
}
