import { Node } from '@tiptap/core';
import type { ReferenceKind } from '@/lib/backend-api';
import { parseReferenceHref, referenceHref, referenceLinkMarkdown } from '@/lib/reference-links';

// A `#` reference in the editor: one inline atom, drawn as a chip with the
// item's current title (the editor attaches the view). Atomic so it is
// selected and deleted whole; a link mark would let a caret wander into
// `#VIC-42` and leave half a token behind.
//
// The markdown doesn't change: it is still `[#VIC-42](/dashboard/tasks/<id>)`
// (lib/reference-links), so the title is looked up when shown rather than
// frozen into the text.

export interface ReferenceAttrs {
  kind: ReferenceKind;
  id: string;
  /** The link's stored text, `#VIC-42`: written back as is, and what the chip
   *  shows until (or unless) the item itself can be read. */
  label: string;
}

interface MarkedToken {
  type?: string;
  text?: string;
  raw?: string;
  href?: string;
  title?: string | null;
  tokens?: MarkedToken[];
}

/** The link text as written, escapes undone (`#a\]b` → `#a]b`). */
function plainText(tokens: MarkedToken[] | undefined, fallback: string): string {
  if (!tokens?.length) return fallback;
  return tokens.map((t) => (t.tokens?.length ? plainText(t.tokens, t.text ?? '') : (t.text ?? t.raw ?? ''))).join('');
}

export const ReferenceNode = Node.create({
  name: 'reference',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,
  // Link (priority 1000) reads markdown `link` tokens too, and an inline token
  // only ever reaches the FIRST handler registered for it (@tiptap/markdown's
  // parseInlineTokens has no fall-through). So this one goes first and does
  // Link's job for every link that isn't a reference; see parseMarkdown.
  priority: 1001,

  addAttributes() {
    return {
      kind: { default: 'task' },
      id: { default: '' },
      label: { default: '' },
    };
  },

  // Copy and paste between editors: the HTML flavour is an anchor that says
  // what it is.
  parseHTML() {
    return [
      {
        tag: 'a[data-reference]',
        priority: 100,
        getAttrs: (el) => {
          const target = parseReferenceHref((el as HTMLElement).getAttribute('href') ?? '');
          return target ? { ...target, label: (el as HTMLElement).textContent ?? '' } : false;
        },
      },
    ];
  },

  renderHTML({ node }) {
    const { kind, id, label } = node.attrs as ReferenceAttrs;
    return ['a', { href: referenceHref(kind, id), 'data-reference': kind }, label];
  },

  renderText({ node }) {
    return (node.attrs as ReferenceAttrs).label;
  },

  markdownTokenName: 'link',

  parseMarkdown: (token: MarkedToken, helpers) => {
    const target = parseReferenceHref(token.href ?? '');
    if (target) {
      return helpers.createNode('reference', { ...target, label: plainText(token.tokens, token.text ?? '') });
    }
    // An ordinary link: exactly what @tiptap/extension-link's own handler
    // returns (markdown-codec.test.ts pins that ordinary links survive).
    return helpers.applyMark('link', helpers.parseInline((token.tokens ?? []) as never), {
      href: token.href,
      title: token.title || null,
    });
  },

  renderMarkdown: (node) => {
    const { kind, id, label } = node.attrs as ReferenceAttrs;
    return referenceLinkMarkdown(kind, id, label);
  },
});
