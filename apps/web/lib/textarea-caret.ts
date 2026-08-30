/**
 * Viewport coordinates of the caret inside a `<textarea>`.
 *
 * Used to anchor the `@`-mention and `/`-command suggestion panels next to the
 * caret rather than to the field's edges. In a tall, expanded field the field
 * bottom can be far below the line being typed, so anchoring to the container
 * dropped the panel "way below the cursor" — this fixes that by measuring where
 * the caret actually is.
 *
 * Standard mirror-`<div>` technique: clone the textarea's text-affecting
 * styles into an off-screen div, place the text up to the caret in it with a
 * marker span, and read the span's offset. No dependency, ~one layout pass.
 */

// Text-affecting properties that change where a glyph lands. Anything omitted
// here (colors, cursor, etc.) can't move the caret, so it's skipped.
const MIRRORED_PROPERTIES = [
  'boxSizing',
  'width',
  'borderTopWidth',
  'borderRightWidth',
  'borderBottomWidth',
  'borderLeftWidth',
  'borderStyle',
  'paddingTop',
  'paddingRight',
  'paddingBottom',
  'paddingLeft',
  'fontStyle',
  'fontVariant',
  'fontWeight',
  'fontStretch',
  'fontSize',
  'fontSizeAdjust',
  'lineHeight',
  'fontFamily',
  'textAlign',
  'textTransform',
  'textIndent',
  'letterSpacing',
  'wordSpacing',
  'tabSize',
] as const;

export interface CaretRect {
  /** Viewport y of the caret line's top. */
  top: number;
  /** Viewport y of the caret line's bottom. */
  bottom: number;
  /** Viewport x of the caret. */
  left: number;
}

export function getCaretViewportRect(el: HTMLTextAreaElement): CaretRect {
  const rect = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  const div = document.createElement('div');
  const ds = div.style;

  ds.position = 'absolute';
  ds.top = '0';
  ds.left = '0';
  ds.visibility = 'hidden';
  ds.whiteSpace = 'pre-wrap';
  ds.wordWrap = 'break-word';
  ds.overflow = 'hidden';
  for (const prop of MIRRORED_PROPERTIES) {
    // The div mirrors the textarea's own border-box width, so copying `width`
    // plus the paddings/borders reproduces the exact wrapping.
    ds[prop as never] = style[prop as never];
  }

  const caretIndex = el.selectionEnd ?? el.value.length;
  div.textContent = el.value.substring(0, caretIndex);
  // A marker whose top/height report the caret line. Non-empty so it has a box
  // even at end-of-text or on a blank final line.
  const span = document.createElement('span');
  span.textContent = el.value.substring(caretIndex) || '.';
  div.appendChild(span);

  document.body.appendChild(div);
  const spanTop = span.offsetTop;
  const lineHeight = span.offsetHeight || parseFloat(style.lineHeight) || parseFloat(style.fontSize) || 16;
  const spanLeft = span.offsetLeft;
  document.body.removeChild(div);

  // `offsetTop`/`offsetLeft` are measured from the mirror's padding edge (inside
  // the border), so add the textarea's border to reach its border-box origin,
  // then anchor to the textarea's viewport rect and undo its own scroll.
  const borderTop = parseFloat(style.borderTopWidth) || 0;
  const borderLeft = parseFloat(style.borderLeftWidth) || 0;
  const caretTop = rect.top + borderTop + spanTop - el.scrollTop;
  return {
    top: caretTop,
    bottom: caretTop + lineHeight,
    left: rect.left + borderLeft + spanLeft - el.scrollLeft,
  };
}
