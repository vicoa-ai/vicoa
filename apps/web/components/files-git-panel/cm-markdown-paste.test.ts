import { describe, test, expect } from 'vitest';
import { EditorState } from '@codemirror/state';
import { ensureSyntaxTree } from '@codemirror/language';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import {
  htmlToMarkdown,
  isStructuralHtml,
  isVerbatimContext,
  markdownForPaste,
} from './cm-markdown-paste';

/** A parsed state over `doc` with the caret at `caret`. */
function stateFor(doc: string, caret = doc.length): EditorState {
  const state = EditorState.create({
    doc,
    selection: { anchor: caret },
    extensions: [markdown({ base: markdownLanguage })],
  });
  ensureSyntaxTree(state, doc.length, 5000);
  return state;
}

describe('isStructuralHtml', () => {
  test('markup a markdown document can express', () => {
    expect(isStructuralHtml('<p>see <a href="https://example.com">docs</a></p>')).toBe(true);
    expect(isStructuralHtml('<ul><li>one</li></ul>')).toBe(true);
    expect(isStructuralHtml('<table><tr><td>a</td></tr></table>')).toBe(true);
    expect(isStructuralHtml('<h2>Title</h2>')).toBe(true);
    expect(isStructuralHtml('<img src="a.png">')).toBe(true);
  });

  test('styled plain text is not', () => {
    // What a code editor or a terminal puts on the clipboard: the markdown of
    // this is its own plain text, and converting it would mangle the code.
    const fromEditor =
      '<div style="color:#d4d4d4;background:#1f1f1f"><div><span style="color:#569cd6">const</span>' +
      '<span style="color:#9cdcfe"> x</span></div></div>';
    expect(isStructuralHtml(fromEditor)).toBe(false);
    expect(isStructuralHtml('<p>just a sentence</p>')).toBe(false);
    expect(isStructuralHtml('plain text, no tags')).toBe(false);
  });

  test('a leading <style> block does not count as structure', () => {
    // Word and Google Docs prepend CSS that names every tag there is.
    const fromWord = '<style>table { border: 0 } a { color: blue }</style><span>hello</span>';
    expect(isStructuralHtml(fromWord)).toBe(false);
  });
});

describe('htmlToMarkdown', () => {
  test('headings, links, emphasis and lists', () => {
    const md = htmlToMarkdown(
      '<h2>Setup</h2><p>Run <strong>this</strong> and see ' +
        '<a href="https://example.com/docs">the docs</a>.</p><ul><li>one</li><li>two</li></ul>',
    );
    expect(md).toContain('## Setup');
    expect(md).toContain('**this**');
    expect(md).toContain('[the docs](https://example.com/docs)');
    // `- item`, not turndown's default `-   item` — the repo's own style.
    expect(md).toContain('- one\n- two');
  });

  test('GFM: tables, strikethrough and task lists', () => {
    const md = htmlToMarkdown(
      '<table><thead><tr><th>k</th><th>v</th></tr></thead>' +
        '<tbody><tr><td>a</td><td>1</td></tr></tbody></table><p><del>gone</del></p>',
    );
    // The GFM plugin pads cells to an even width, so compare unpadded.
    const tight = md.replace(/ +/g, ' ');
    expect(tight).toContain('| k | v |');
    expect(tight).toContain('| a | 1 |');
    expect(md).toContain('~~gone~~');
  });

  test('nested and ordered lists keep their shape', () => {
    const md = htmlToMarkdown('<ol><li>one<ul><li>deep</li></ul></li><li>two</li></ol>');
    expect(md).toBe('1. one\n   - deep\n2. two');
  });

  test('code blocks come back fenced', () => {
    const md = htmlToMarkdown('<pre><code class="language-ts">const x = 1;</code></pre>');
    expect(md).toContain('```');
    expect(md).toContain('const x = 1;');
  });

  test('empty in, empty out; unclosed tags do not throw', () => {
    expect(htmlToMarkdown('')).toBe('');
    expect(htmlToMarkdown('<ul><li>one<li>two')).toBe('- one\n- two');
  });
});

describe('isVerbatimContext', () => {
  test('inside code, and inside front matter', () => {
    const fenced = '# Doc\n\n```ts\nconst x = 1;\n```\n';
    expect(isVerbatimContext(stateFor(fenced), fenced.indexOf('const') + 2)).toBe(true);
    const inline = 'text `code here` more';
    expect(isVerbatimContext(stateFor(inline), inline.indexOf('code') + 1)).toBe(true);
    const indented = 'text\n\n    indented code\n';
    expect(isVerbatimContext(stateFor(indented), indented.indexOf('indented') + 1)).toBe(true);
    const fm = '---\ntitle: x\n---\n\nbody';
    expect(isVerbatimContext(stateFor(fm), fm.indexOf('title'))).toBe(true);
  });

  test('ordinary prose is not', () => {
    const doc = '# Doc\n\nsome prose here\n';
    expect(isVerbatimContext(stateFor(doc), doc.indexOf('prose'))).toBe(false);
  });
});

describe('markdownForPaste', () => {
  const HTML = '<p>see <a href="https://example.com">docs</a></p>';
  const PLAIN = 'see docs';

  test('converts structural HTML into markdown', () => {
    expect(markdownForPaste(stateFor('body'), HTML, PLAIN)).toBe(
      'see [docs](https://example.com)',
    );
  });

  test('stays out of the way with nothing to gain', () => {
    expect(markdownForPaste(stateFor('body'), '', PLAIN)).toBe(null);
    expect(markdownForPaste(stateFor('body'), undefined, PLAIN)).toBe(null);
    expect(markdownForPaste(stateFor('body'), '<span style="color:red">x</span>', 'x')).toBe(null);
    // Conversion that lands on the plain text anyway.
    expect(markdownForPaste(stateFor('body'), '<p><code>x</code></p>', '`x`')).toBe(null);
  });

  test('pasting into code or front matter keeps the plain flavour', () => {
    const doc = '```\n\n```\n';
    expect(markdownForPaste(stateFor(doc, 4), HTML, PLAIN)).toBe(null);
    const fm = '---\ntitle: x\n---\n\nbody';
    expect(markdownForPaste(stateFor(fm, fm.indexOf('x')), HTML, PLAIN)).toBe(null);
  });
});
