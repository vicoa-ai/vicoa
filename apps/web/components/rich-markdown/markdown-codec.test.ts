import { Editor, type JSONContent } from '@tiptap/core';
import { afterEach, describe, expect, it } from 'vitest';
import { markdownExtensions } from './extensions';
import { prepareMarkdown, serializeMarkdown } from './markdown-codec';

// Headless (`element: null`): the codec needs the schema and the markdown
// manager, not a view, so this runs in vitest's node environment.
const editors: Editor[] = [];
function load(content: string | JSONContent): Editor {
  const editor = new Editor({
    element: null,
    extensions: markdownExtensions(),
    ...(typeof content === 'string'
      ? { content: prepareMarkdown(content), contentType: 'markdown' as const }
      : { content }),
  });
  editors.push(editor);
  return editor;
}
afterEach(() => {
  while (editors.length) editors.pop()?.destroy();
});

const roundTrip = (markdown: string) => serializeMarkdown(load(markdown));

describe('serializeMarkdown keeps what was typed', () => {
  const unchanged: Record<string, string> = {
    'soft line breaks': 'line one\nline two\nline three',
    'a hard break': 'line one  \nline two',
    'underscores in paths and identifiers': 'Read @src/my_file.ts and fix snake_case_name.',
    'ampersands and angle brackets': 'R&D, a > b and a < b',
    'unrecognized raw HTML': 'before <br> after\n\n<details><summary>x</summary>body</details>',
    'nested bullets': '- parent\n  - child\n    - grandchild\n- second',
    'an ordered list from 3': '3. three\n4. four',
    'task items': '- [ ] todo\n- [x] done\n  - [ ] nested',
    'a fenced block': '```ts\nconst snake_case = a * b;\n```\n\nand `inline_code`',
    headings: '# Title\n\nSome text\n\n## Sub\n\ntext',
    'a quote': '> quoted\n> lines',
    'a rule': 'above\n\n---\n\nbelow',
    'slash commands': '/review the PR then run /compact',
    'extra blank lines': 'para one\n\n\n\npara two',
    'an image': '![alt](https://example.com/x.png)',
    'a bare URL': 'See [docs](https://example.com) and https://a.example.com/a_b.',
    'a bold URL glued to CJK text': '**https://x.dev/pull/54**（rebase）',
    'an escaped heading marker': '\\# not a heading',
  };
  for (const [name, markdown] of Object.entries(unchanged)) {
    it(name, () => expect(roundTrip(markdown)).toBe(markdown));
  }

  // The serializer hook is internal @tiptap/markdown API. If an upgrade stops
  // it taking effect, the library escapes again and this is what breaks.
  it('does not escape the way @tiptap/markdown does on its own', () => {
    const editor = load('a_b & c');
    expect(editor.getMarkdown()).toBe('a\\_b &amp; c');
    expect(serializeMarkdown(editor)).toBe('a_b & c');
  });
});

describe('serializeMarkdown normalizes only where it must', () => {
  it('ends a URL followed by CJK punctuation with <…>', () => {
    expect(roundTrip('看 https://a.com/x_y，然后 继续')).toBe('看 <https://a.com/x_y>，然后 继续');
  });

  it('writes one list marker and one emphasis style', () => {
    expect(roundTrip('* star\n* two')).toBe('- star\n- two');
    expect(roundTrip('say _this_ now')).toBe('say *this* now');
  });

  it('keeps a table a table, one blank line either side', () => {
    expect(roundTrip('| a | b |\n|---|---|\n| 1 | 2 |')).toBe('| a   | b   |\n| --- | --- |\n| 1   | 2   |');
    expect(roundTrip('before\n\n| a |\n|---|\n| 1 |\n\nafter')).toBe('before\n\n| a   |\n| --- |\n| 1   |\n\nafter');
  });
});

describe('serializeMarkdown escapes literal block markers', () => {
  const paragraph = (text: string): JSONContent => ({
    type: 'doc',
    content: [{ type: 'paragraph', content: [{ type: 'text', text }] }],
  });

  // Text a person typed literally (an input rule undone, a plain paste) that
  // markdown would otherwise read back as structure.
  const cases: Record<string, [string, string]> = {
    heading: ['# not a heading', '\\# not a heading'],
    bullet: ['- not a list', '\\- not a list'],
    'ordered marker': ['1. not a list', '1\\. not a list'],
    quote: ['> not a quote', '\\> not a quote'],
    'a marker after a soft break': ['first\n# second', 'first\n\\# second'],
  };
  for (const [name, [text, expected]] of Object.entries(cases)) {
    it(name, () => {
      const editor = load(paragraph(text));
      const markdown = serializeMarkdown(editor);
      expect(markdown).toBe(expected);
      // And it does read back as the same plain paragraph.
      expect(serializeMarkdown(load(markdown))).toBe(expected);
    });
  }

  it('leaves the same characters alone mid-line', () => {
    expect(serializeMarkdown(load(paragraph('issue #12 - see 1. above')))).toBe('issue #12 - see 1. above');
  });

  it('falls back to escaping when plain text would change meaning', () => {
    const markdown = serializeMarkdown(load(paragraph('**not bold**')));
    expect(markdown).not.toBe('**not bold**');
    expect(load(markdown).getText()).toBe('**not bold**');
  });
});

describe('prepareMarkdown', () => {
  it('leaves URLs inside fenced code alone', () => {
    const markdown = '```\nhttps://a.com，x\n```';
    expect(prepareMarkdown(markdown)).toBe(markdown);
  });

  it('delimits a bare URL outside code', () => {
    expect(prepareMarkdown('看 https://a.com，x')).toBe('看 <https://a.com>，x');
  });
});
