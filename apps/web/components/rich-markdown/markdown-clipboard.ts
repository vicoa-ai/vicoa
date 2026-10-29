import { Extension } from '@tiptap/core';
import { Slice } from '@tiptap/pm/model';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { prepareMarkdown, serializeMarkdown } from './markdown-codec';

// Clipboard in markdown, both ways.
//
// Paste: ProseMirror reads text/html whenever it is there and text/plain only
// when it is not, so markdown copied from a terminal, an agent's reply or a
// .md file lands as literal `**` and `##`, and is then saved escaped. Here
// plain text is read as markdown, unless the HTML beside it carries real
// structure (a web page, another editor's rich content), which ProseMirror
// already maps well. A code editor's clipboard is HTML too, but only styled
// `<div>`/`<span>` runs around the source, so it counts as plain text.
//
// Copy: the text/plain flavour is the selection as markdown instead of its
// bare text, so a copied checklist pastes into a prompt as a checklist.

// Elements that mean the HTML is the content, not a wrapper around it.
const STRUCTURAL_HTML = [
  'a[href]', 'b', 'strong', 'em', 'i', 's', 'del', 'blockquote', 'h1', 'h2', 'h3',
  'h4', 'h5', 'h6', 'hr', 'img', 'li', 'ol', 'ul', 'table', 'tr', 'td', 'th',
].join(',');

function isStructuralHtml(html: string): boolean {
  // ProseMirror's own clipboard (this editor, or another one): its HTML is the
  // exact document, so let it through.
  if (html.includes('data-pm-slice')) return true;
  const doc = new DOMParser().parseFromString(html, 'text/html');
  return doc.body.querySelector(STRUCTURAL_HTML) !== null;
}

export const MarkdownClipboard = Extension.create({
  name: 'markdownClipboard',
  addProseMirrorPlugins() {
    const editor = this.editor;
    return [
      new Plugin({
        key: new PluginKey('markdownClipboard'),
        props: {
          handlePaste(view, event) {
            const data = event.clipboardData;
            if (!data || !editor.markdown) return false;
            // Inside a code block, text is code: ProseMirror inserts it as is.
            if (view.state.selection.$from.parent.type.spec.code) return false;
            const text = data.getData('text/plain');
            if (!text) return false;
            const html = data.getData('text/html');
            if (html && isStructuralHtml(html)) return false;
            const doc = view.state.schema.nodeFromJSON(editor.markdown.parse(prepareMarkdown(text)));
            // Open only where the paste starts or ends with plain text: a
            // pasted line joins the line the caret is on, while a heading,
            // list or code block at either end stays one instead of being
            // flattened into that line (ProseMirror opens every edge).
            const openAt = (node: typeof doc.firstChild) => (node?.type.name === 'paragraph' ? 1 : 0);
            const slice = new Slice(doc.content, openAt(doc.firstChild), openAt(doc.lastChild));
            view.dispatch(view.state.tr.replaceSelection(slice).scrollIntoView().setMeta('uiEvent', 'paste'));
            return true;
          },
          clipboardTextSerializer(slice) {
            try {
              return serializeMarkdown(editor, editor.schema.topNodeType.create(null, slice.content));
            } catch {
              return slice.content.textBetween(0, slice.content.size, '\n\n');
            }
          },
        },
      }),
    ];
  },
});

