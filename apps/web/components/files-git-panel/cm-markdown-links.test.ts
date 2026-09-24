import { describe, test, expect } from 'vitest';
import { EditorState } from '@codemirror/state';
import { ensureSyntaxTree } from '@codemirror/language';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { destinationAt, followableUrlAt, linkAt } from './cm-markdown-links';

/** A fully parsed state over `doc`, on the same GFM base as the live editor. */
function stateFor(doc: string): EditorState {
  const state = EditorState.create({
    doc,
    extensions: [markdown({ base: markdownLanguage })],
  });
  ensureSyntaxTree(state, doc.length, 5000);
  return state;
}

/** The destination of the link covering `needle`'s first character. */
function destAtText(doc: string, needle: string): string | null {
  const pos = doc.indexOf(needle);
  expect(pos).toBeGreaterThanOrEqual(0);
  return destinationAt(stateFor(doc), pos);
}

describe('destinationAt', () => {
  test('inline link: from anywhere in the rendered text', () => {
    const doc = 'see [the docs](https://example.com/docs) for more';
    expect(destAtText(doc, 'the docs')).toBe('https://example.com/docs');
    expect(destAtText(doc, 'docs](')).toBe('https://example.com/docs');
    // …and from the raw destination, which the cursor reveals for editing.
    expect(destAtText(doc, 'https://example.com/docs')).toBe('https://example.com/docs');
  });

  test('inline link: both edges of the link text resolve', () => {
    const doc = '[ab](https://example.com)';
    const state = stateFor(doc);
    expect(destinationAt(state, 1)).toBe('https://example.com'); // before `a`
    expect(destinationAt(state, 3)).toBe('https://example.com'); // after `b`
  });

  test('a link title is not part of the destination', () => {
    expect(destAtText('[x](https://example.com "Docs")', 'x]')).toBe('https://example.com');
  });

  test('angle-bracketed and escaped destinations are unwrapped', () => {
    expect(destAtText('[x](<https://example.com/a b>)', 'x]')).toBe('https://example.com/a b');
    expect(destAtText('[x](https://example.com/a\\_b)', 'x]')).toBe('https://example.com/a_b');
  });

  test('bare and angle-bracket autolinks', () => {
    expect(destAtText('go to https://example.com now', 'https://')).toBe('https://example.com');
    expect(destAtText('go to <https://example.com> now', 'https://')).toBe('https://example.com');
  });

  test('reference link: explicit, collapsed and shortcut forms', () => {
    const refs = '\n\n[docs]: https://example.com/docs';
    expect(destAtText(`[the docs][docs]${refs}`, 'the docs')).toBe('https://example.com/docs');
    expect(destAtText(`[docs][]${refs}`, 'docs][')).toBe('https://example.com/docs');
    expect(destAtText(`[docs]${refs}`, 'docs]')).toBe('https://example.com/docs');
  });

  test('reference labels match case- and whitespace-insensitively', () => {
    const doc = '[x][My  Ref]\n\n[my ref]: https://example.com';
    expect(destAtText(doc, 'x]')).toBe('https://example.com');
  });

  test('a reference with no definition has no destination', () => {
    expect(destAtText('[x][nope] text', 'x]')).toBe(null);
  });

  test('plain text, and an image’s alt text, are not links', () => {
    expect(destAtText('just some words', 'some')).toBe(null);
    expect(destAtText('![a diagram](https://example.com/a.png)', 'a diagram')).toBe(null);
  });

  test('a link inside a list item still resolves', () => {
    expect(destAtText('- [x](https://example.com) and more', 'x]')).toBe('https://example.com');
  });
});

describe('followableUrlAt', () => {
  const at = (doc: string, needle: string): string | null =>
    followableUrlAt(stateFor(doc), doc.indexOf(needle));

  test('http(s) and mailto links may be opened', () => {
    expect(at('[x](https://example.com)', 'x]')).toBe('https://example.com');
    expect(at('[x](http://example.com)', 'x]')).toBe('http://example.com');
    expect(at('[x](mailto:someone@example.com)', 'x]')).toBe('mailto:someone@example.com');
  });

  test('links into the repo are not handed to the browser', () => {
    // A README's own links: relative, absolute-local, anchor, and `file:` —
    // opening any of them in the browser leaves the app (vicoa-ai/vicoa#46).
    for (const href of ['./docs/setup.md', '/docs/setup.md', '#section', 'file:///tmp/a.md']) {
      const doc = `[x](${href})`;
      expect(destinationAt(stateFor(doc), doc.indexOf('x]'))).toBe(href);
      expect(at(doc, 'x]')).toBe(null);
    }
  });

  test('a javascript: destination is never followed', () => {
    expect(at('[x](javascript:alert(1))', 'x]')).toBe(null);
  });
});

describe('linkAt', () => {
  test('reports the range the \u2318-hover affordance underlines', () => {
    const doc = 'see [the docs](https://example.com) and https://example.com/bare here';
    const state = stateFor(doc);
    const inline = linkAt(state, doc.indexOf('the docs'));
    // The whole construct: the hidden `[` and `](url)` carry no visible text,
    // so the underline lands on the link text alone.
    expect(doc.slice(inline?.from ?? 0, inline?.to ?? 0)).toBe('[the docs](https://example.com)');
    const bare = linkAt(state, doc.indexOf('https://example.com/bare'));
    expect(doc.slice(bare?.from ?? 0, bare?.to ?? 0)).toBe('https://example.com/bare');
  });

  test('null where there is no link', () => {
    const doc = 'just some words';
    expect(linkAt(stateFor(doc), 5)).toBe(null);
  });
});
