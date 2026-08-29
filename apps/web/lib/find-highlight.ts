/**
 * Shared primitives for the in-conversation find feature.
 *
 * `splitOnQuery` powers plain-text highlighting; `makeFindHighlightPlugin` is a
 * dependency-free rehype plugin that wraps matched substrings in
 * `<mark class="find-hit">` inside the markdown HAST — so the same term lights
 * up whether a message rendered as plain text or as Markdown.
 */

export interface FindSegment {
  text: string;
  /** True when this segment is a case-insensitive match of the query. */
  hit: boolean;
}

/**
 * Split `text` into alternating non-match / match segments for `query`
 * (case-insensitive). Original casing is preserved in every segment.
 */
export function splitOnQuery(text: string, query: string): FindSegment[] {
  const needle = query.toLowerCase();
  if (!needle) return [{ text, hit: false }];

  const hay = text.toLowerCase();
  const segments: FindSegment[] = [];
  let cursor = 0;

  while (cursor < text.length) {
    const idx = hay.indexOf(needle, cursor);
    if (idx === -1) {
      segments.push({ text: text.slice(cursor), hit: false });
      break;
    }
    if (idx > cursor) segments.push({ text: text.slice(cursor, idx), hit: false });
    segments.push({ text: text.slice(idx, idx + needle.length), hit: true });
    cursor = idx + needle.length;
  }

  return segments;
}

// Minimal HAST shapes — we only touch text nodes and rebuild children arrays.
interface HastNode {
  type: string;
  value?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

function highlightHast(node: HastNode, needle: string): void {
  if (!Array.isArray(node.children)) return;

  const next: HastNode[] = [];
  for (const child of node.children) {
    if (child.type === 'text' && typeof child.value === 'string' && child.value) {
      const segments = splitOnQuery(child.value, needle);
      if (segments.length === 1 && !segments[0].hit) {
        next.push(child);
        continue;
      }
      for (const segment of segments) {
        if (!segment.text) continue;
        if (segment.hit) {
          next.push({
            type: 'element',
            tagName: 'mark',
            properties: { className: ['find-hit'] },
            children: [{ type: 'text', value: segment.text }],
          });
        } else {
          next.push({ type: 'text', value: segment.text });
        }
      }
    } else {
      // Recurse into element children (including hljs-produced code spans), but
      // never into the <mark>s we just created — their children are fresh text.
      highlightHast(child, needle);
      next.push(child);
    }
  }

  node.children = next;
}

/**
 * A rehype plugin (attacher factory) that highlights `query` matches in the
 * tree. Returns a no-op transformer when the query is empty. Run it AFTER
 * rehype-highlight so prose text nodes are still intact when we split them.
 */
export function makeFindHighlightPlugin(query: string | undefined) {
  const needle = (query ?? '').toLowerCase();
  return function attacher() {
    return function transformer(tree: unknown) {
      if (!needle) return;
      highlightHast(tree as HastNode, needle);
    };
  };
}
