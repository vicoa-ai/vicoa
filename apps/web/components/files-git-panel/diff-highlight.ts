import type { DiffSegment } from './diff-lines';

// The five characters highlight.js escapes in its output — decoding exactly
// these (and no more) recovers the source text run for run.
const ENTITY_RE = /&(amp|lt|gt|quot|#x27);/g;
const ENTITIES: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', '#x27': "'" };
const ESCAPE_RE = /[&<>"']/g;
const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#x27;',
};

function decodeHljs(s: string): string {
  return s.replace(ENTITY_RE, (_, name: string) => ENTITIES[name]);
}

export function escapeHtml(s: string): string {
  return s.replace(ESCAPE_RE, (c) => ESCAPES[c]);
}

const TAG_RE = /<[^>]*>/g;

/** Layer the word-level diff boxes over a syntax-highlighted line. `html` is
 *  highlight.js output for the line whose text `segments` concatenate to; the
 *  `changed` runs come back wrapped in `<span class={cls}>`, split wherever
 *  they cross a syntax span so the markup stays properly nested. The tags
 *  themselves pass through untouched. */
export function overlaySegments(html: string, segments: DiffSegment[], cls: string): string {
  const ranges: [number, number][] = [];
  let off = 0;
  for (const seg of segments) {
    if (seg.changed) ranges.push([off, off + seg.text.length]);
    off += seg.text.length;
  }
  if (ranges.length === 0) return html;

  let out = '';
  let pos = 0; // text offset of the next character to emit
  let ri = 0;
  const emitText = (escaped: string) => {
    const text = decodeHljs(escaped);
    let at = 0;
    while (at < text.length) {
      while (ri < ranges.length && ranges[ri][1] <= pos + at) ri++;
      let stop = text.length;
      let inChange = false;
      if (ri < ranges.length) {
        const [from, to] = ranges[ri];
        if (from <= pos + at) {
          inChange = true;
          stop = Math.min(stop, to - pos);
        } else {
          stop = Math.min(stop, from - pos);
        }
      }
      const piece = escapeHtml(text.slice(at, stop));
      out += inChange ? `<span class="${cls}">${piece}</span>` : piece;
      at = stop;
    }
    pos += text.length;
  };

  let last = 0;
  for (const m of html.matchAll(TAG_RE)) {
    emitText(html.slice(last, m.index));
    out += m[0];
    last = m.index + m[0].length;
  }
  emitText(html.slice(last));
  return out;
}
