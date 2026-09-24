import { syntaxTree } from '@codemirror/language';
import type { EditorState, Extension } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import TurndownService from 'turndown';
import { gfm } from '@joplin/turndown-plugin-gfm';
import { frontMatterRange } from './cm-markdown-live';

/**
 * Paste rich text into the markdown editor as markdown.
 *
 * A copy from a browser (or from any editor) puts two flavours on the
 * clipboard: `text/plain` and `text/html`. Pasting the plain flavour into a
 * markdown document throws away every link, heading and table — you get the
 * words and then retype the markup. So when the HTML flavour carries structure
 * worth keeping, it is converted and inserted instead.
 *
 * The buffer still receives plain markdown text, like any other edit: this is a
 * paste transform, not a second document model.
 */

/**
 * Tags that make an HTML payload worth converting.
 *
 * Deliberately *not* `div`/`span`/`p`/`br`: copying from a code editor or a
 * terminal puts a wall of styled `span`s on the clipboard, and converting that
 * mangles the code the user meant to paste, to no benefit — its markdown is its
 * plain text. Anything below, on the other hand, is markup a markdown document
 * can express and would otherwise lose.
 */
const STRUCTURAL_TAG =
  /<(?:a|strong|b|em|i|h[1-6]|ul|ol|li|table|thead|tbody|tr|th|td|blockquote|pre|code|img|hr|del|s)[\s>/]/i;

/** Is this clipboard HTML worth converting, rather than pasting as text? */
export function isStructuralHtml(html: string): boolean {
  // Word and Google Docs prepend a `<style>` block whose CSS mentions every tag
  // under the sun; the content itself starts after it.
  return STRUCTURAL_TAG.test(html.replace(/<style[\s\S]*?<\/style>/gi, ''));
}

let service: TurndownService | null = null;

/** The converter, built once. Its options are the markdown this repo writes:
 *  `#` headings, `-` bullets, fenced code, inline links. */
function converter(): TurndownService {
  if (service) return service;
  service = new TurndownService({
    headingStyle: 'atx',
    bulletListMarker: '-',
    codeBlockStyle: 'fenced',
    emDelimiter: '*',
    strongDelimiter: '**',
    linkStyle: 'inlined',
    hr: '---',
  });
  // Tables, strikethrough and task lists — the GFM the live preview renders.
  service.use(gfm);
  service.remove(['style', 'script', 'head', 'meta', 'title', 'link']);
  // Turndown writes list items as `-   item` / `1.  item`, padded out to four
  // columns. Every markdown file this editor opens writes `- item` / `1. item`,
  // and a pasted list should not read as a different document — so its rule is
  // replaced by the same logic at the narrower indent (continuation lines line
  // up under the text, which is what makes nesting parse).
  service.addRule('tightListItem', {
    filter: 'li',
    replacement: (content, node, options) => {
      const parent = node.parentNode as Element | null;
      let prefix = `${options.bulletListMarker} `;
      if (parent?.nodeName === 'OL') {
        const start = parent.getAttribute('start');
        const index = Array.prototype.indexOf.call(parent.children, node);
        prefix = `${start ? Number(start) + index : index + 1}. `;
      }
      const body = content
        .replace(/^\n+/, '')
        .replace(/\n+$/, '\n')
        .replace(/\n/g, `\n${' '.repeat(prefix.length)}`);
      return prefix + body + (node.nextSibling && !/\n$/.test(body) ? '\n' : '');
    },
  });
  return service;
}

/** Clipboard HTML as markdown text. Empty when it carried no text at all. */
export function htmlToMarkdown(html: string): string {
  try {
    return converter().turndown(html);
  } catch {
    // A malformed fragment must not cost the user their paste — the caller
    // falls back to the plain-text flavour.
    return '';
  }
}

/** The `@lezer/common` node type, reached through the tree (as in
 *  cm-markdown-links.ts) rather than imported from a transitive dependency. */
type SyntaxNode = ReturnType<ReturnType<typeof syntaxTree>['resolveInner']>;

/** Code (fenced, indented or inline) and front matter take the plain flavour:
 *  pasting into them means pasting *source*, which conversion would rewrite. */
export function isVerbatimContext(state: EditorState, pos: number): boolean {
  const frontMatter = frontMatterRange(state.doc);
  if (frontMatter && pos <= frontMatter.to) return true;
  let node: SyntaxNode | null = syntaxTree(state).resolveInner(pos, -1);
  for (; node; node = node.parent) {
    if (node.name === 'FencedCode' || node.name === 'CodeBlock' || node.name === 'InlineCode') {
      return true;
    }
  }
  return false;
}

/** The markdown a paste should insert, or null to let CodeMirror paste the
 *  plain-text flavour as usual. Pure, so the decision is testable without a
 *  clipboard. */
export function markdownForPaste(
  state: EditorState,
  html: string | null | undefined,
  plain: string,
): string | null {
  if (!html || !isStructuralHtml(html)) return null;
  if (isVerbatimContext(state, state.selection.main.head)) return null;
  const markdown = htmlToMarkdown(html);
  // No gain, no surprise: if the conversion comes back as the text that would
  // have been pasted anyway, stay out of the way.
  if (!markdown.trim() || markdown === plain) return null;
  return markdown;
}

/** Paste rich text as markdown. See {@link markdownForPaste} for the rules. */
export function markdownPaste(): Extension {
  return EditorView.domEventHandlers({
    paste(event, view) {
      const clipboard = event.clipboardData;
      if (!clipboard) return false;
      const markdown = markdownForPaste(
        view.state,
        clipboard.getData('text/html'),
        clipboard.getData('text/plain'),
      );
      if (markdown === null) return false;
      event.preventDefault();
      view.dispatch(view.state.replaceSelection(markdown), {
        scrollIntoView: true,
        userEvent: 'input.paste',
      });
      return true;
    },
  });
}
