import { describe, test, expect } from 'vitest';
import { EditorState, Text } from '@codemirror/state';
import { ensureSyntaxTree } from '@codemirror/language';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import {
  buildTableDecorations,
  computeMarkdownDecorations,
  frontMatterRange,
  parseTable,
} from './cm-markdown-live';

interface Deco {
  from: number;
  to: number;
  cls?: string;
  title?: string;
  /** A zero-spec replace — a hidden syntax mark. */
  hide: boolean;
  widget: boolean;
}

/** Compute the live-preview decorations for `doc` with the selection at
 *  `caret` (default: end of doc, i.e. away from the markup under test). */
function decorate(doc: string, caret = doc.length): Deco[] {
  const state = EditorState.create({
    doc,
    selection: { anchor: caret },
    // GFM base — same as the live editor — so strikethrough/tables are parsed.
    extensions: [markdown({ base: markdownLanguage })],
  });
  // Force a full parse so `syntaxTree` inside the builder is complete.
  ensureSyntaxTree(state, doc.length, 5000);
  const set = computeMarkdownDecorations(state, [{ from: 0, to: doc.length }]);
  const out: Deco[] = [];
  const it = set.iter();
  while (it.value) {
    // `spec` is public on Decoration but untyped; read it defensively.
    const spec =
      (
        it.value as unknown as {
          spec?: { class?: string; widget?: unknown; attributes?: Record<string, string> };
        }
      ).spec ?? {};
    out.push({
      from: it.from,
      to: it.to,
      cls: spec.class,
      title: spec.attributes?.title,
      hide: !spec.class && !spec.widget,
      widget: !!spec.widget,
    });
    it.next();
  }
  return out;
}

/** The block decorations `buildTableDecorations` produces for `doc`. */
function tableBlocks(doc: string, caret = doc.length): Array<{ from: number; to: number }> {
  const state = EditorState.create({
    doc,
    selection: { anchor: caret },
    extensions: [markdown({ base: markdownLanguage })],
  });
  ensureSyntaxTree(state, doc.length, 5000);
  const out: Array<{ from: number; to: number }> = [];
  const it = buildTableDecorations(state).iter();
  while (it.value) {
    out.push({ from: it.from, to: it.to });
    it.next();
  }
  return out;
}

const hasClass = (d: Deco[], cls: string, from: number, to: number) =>
  d.some((x) => x.cls === cls && x.from === from && x.to === to);
const hasHide = (d: Deco[], from: number, to: number) =>
  d.some((x) => x.hide && x.from === from && x.to === to);

describe('computeMarkdownDecorations', () => {
  test('plain text gets no decorations', () => {
    expect(decorate('just some words')).toEqual([]);
  });

  test('heading: sizes the line and hides the `# ` marker', () => {
    // "# Title\n\nbody" — caret in the body, so the heading is not revealed.
    const d = decorate('# Title\n\nbody');
    expect(hasClass(d, 'cm-md-h1', 0, 0)).toBe(true); // line decoration at line start
    expect(hasHide(d, 0, 2)).toBe(true); // hides `#` + the trailing space
  });

  test('heading levels map to their class', () => {
    const d = decorate('### Deep\n\nx');
    expect(hasClass(d, 'cm-md-h3', 0, 0)).toBe(true);
    expect(hasHide(d, 0, 4)).toBe(true); // `###` + space
  });

  test('bold: styles the span and hides both `**` marks', () => {
    const d = decorate('a **bold** b', 0); // caret at start, outside the bold
    expect(hasClass(d, 'cm-md-strong', 2, 10)).toBe(true);
    expect(hasHide(d, 2, 4)).toBe(true); // opening **
    expect(hasHide(d, 8, 10)).toBe(true); // closing **
  });

  test('cursor inside a construct reveals its marks (still styled)', () => {
    const doc = 'a **bold** b';
    const d = decorate(doc, 5); // caret inside "bold"
    expect(hasClass(d, 'cm-md-strong', 2, 10)).toBe(true); // styling stays
    expect(d.some((x) => x.hide)).toBe(false); // nothing hidden while editing it
  });

  test('inline code is styled and its backticks hidden', () => {
    const d = decorate('run `npm i` now', 0);
    expect(hasClass(d, 'cm-md-code', 4, 11)).toBe(true); // includes both backticks
    expect(hasHide(d, 4, 5)).toBe(true); // opening `
    expect(hasHide(d, 10, 11)).toBe(true); // closing `
  });

  test('link: keeps the text, hides `[` and `](url)`', () => {
    const doc = 'see [Vicoa](https://vicoa.ai) here';
    const d = decorate(doc, 0);
    expect(hasClass(d, 'cm-md-link', 5, 10)).toBe(true); // "Vicoa"
    expect(hasHide(d, 4, 5)).toBe(true); // `[`
    expect(hasHide(d, 10, 29)).toBe(true); // `](https://vicoa.ai)`
  });

  test('link: hover shows the destination the preview hides', () => {
    const d = decorate('see [Vicoa](https://vicoa.ai) here', 0);
    expect(d.find((x) => x.cls === 'cm-md-link')?.title).toBe('https://vicoa.ai');
  });

  test('link: empty text (`[](url)`) still decorates the rest of the doc', () => {
    // An empty mark decoration throws in CodeMirror, which would take the whole
    // live-preview layer down for the file.
    const d = decorate('see [](https://vicoa.ai) and **bold**', 0);
    expect(d.some((x) => x.cls === 'cm-md-link')).toBe(false);
    expect(d.some((x) => x.cls === 'cm-md-strong')).toBe(true);
  });

  test('front matter is left as source and styled as metadata', () => {
    // `title: Plan\n---` parses as a setext heading, so the closing `---` used
    // to be hidden as its header mark and the opening one drawn as a divider.
    // Caret in the trailing paragraph, i.e. away from every construct here.
    const doc = '---\ntitle: Plan\n---\n\n# Body\n\ntail';
    const d = decorate(doc);
    expect(d.some((x) => x.widget)).toBe(false); // no divider
    expect(hasHide(d, 16, 19)).toBe(false); // closing `---` stays visible
    expect(hasClass(d, 'cm-md-frontmatter', 0, 0)).toBe(true); // opening fence line
    expect(hasClass(d, 'cm-md-frontmatter', 4, 4)).toBe(true); // `title: Plan`
    expect(hasClass(d, 'cm-md-frontmatter', 16, 16)).toBe(true); // closing fence
    // The body past it is decorated as usual.
    expect(hasClass(d, 'cm-md-h1', 21, 21)).toBe(true);
    expect(hasHide(d, 21, 23)).toBe(true);
  });

  test('front matter: nothing inside it is hidden or restyled', () => {
    // A YAML list is a markdown link to the parser, and it used to lose its
    // brackets; `*` and backticks are just as legal in YAML.
    const doc = '---\ntags: [a, b]\nnote: **x** `y`\n---\n\nbody';
    const fm = 44; // end of the closing fence
    const inside = decorate(doc).filter((x) => x.to <= fm);
    expect(inside.every((x) => x.cls === 'cm-md-frontmatter')).toBe(true);
  });

  test('front matter: a blank line inside it, and a `...` close', () => {
    const doc = '---\ntitle: Plan\n\ntags: []\n...\n\nbody';
    const d = decorate(doc);
    expect(d.some((x) => x.widget)).toBe(false);
    expect(hasClass(d, 'cm-md-frontmatter', 17, 17)).toBe(true); // past the blank line
    expect(hasClass(d, 'cm-md-frontmatter', 26, 26)).toBe(true); // the `...` fence
  });

  test('a `---` that is not front matter is still a divider', () => {
    // Mid-document, and an unterminated opening fence (which is what a file
    // looks like while the block is being typed).
    const midDoc = '# Title\n\n---\n\nbody';
    expect(decorate(midDoc).some((x) => x.widget)).toBe(true);
    expect(decorate(midDoc).some((x) => x.cls === 'cm-md-frontmatter')).toBe(false);
    const openDoc = '---\n\n# Title\n\nbody';
    expect(decorate(openDoc).some((x) => x.widget)).toBe(true);
    expect(decorate(openDoc).some((x) => x.cls === 'cm-md-frontmatter')).toBe(false);
  });

  test('strikethrough (GFM) is styled and its `~~` marks hidden', () => {
    const doc = 'a ~~gone~~ b';
    const d = decorate(doc, 0);
    expect(hasClass(d, 'cm-md-strike', 2, 10)).toBe(true);
    expect(hasHide(d, 2, 4)).toBe(true); // opening ~~
    expect(hasHide(d, 8, 10)).toBe(true); // closing ~~
  });

  test('horizontal rule collapses to a widget when not on the line', () => {
    const d = decorate('a\n\n---\n\nb', 0); // caret on the first line
    expect(d.some((x) => x.widget)).toBe(true);
  });
});

describe('parseTable', () => {
  test('parses header, alignment, and rows', () => {
    const src = '| Name | Age |\n|:-----|----:|\n| Bob  | 30  |\n| Ann  | 7   |';
    expect(parseTable(src)).toEqual({
      header: ['Name', 'Age'],
      align: ['left', 'right'],
      rows: [
        ['Bob', '30'],
        ['Ann', '7'],
      ],
    });
  });

  test('center alignment via `:---:`', () => {
    const src = '| A |\n|:-:|\n| x |';
    expect(parseTable(src)?.align).toEqual(['center']);
  });

  test('honors escaped pipes inside cells', () => {
    const src = 'a \\| b | c\n---|---\n1 | 2';
    expect(parseTable(src)?.header).toEqual(['a | b', 'c']);
  });

  test('rejects a block without a delimiter row', () => {
    expect(parseTable('| just | text |\n| more | rows |')).toBeNull();
    expect(parseTable('not a table at all')).toBeNull();
  });
});

describe('frontMatterRange', () => {
  const range = (doc: string) => frontMatterRange(Text.of(doc.split('\n')));

  test('spans the block, fence to fence', () => {
    expect(range('---\ntitle: x\n---\n\nbody')).toEqual({ from: 0, to: 16 });
  });

  test('null without an opening fence on line 1, or without a close', () => {
    expect(range('# Title\n\n---\n')).toBe(null);
    expect(range('---\ntitle: x\n')).toBe(null);
    expect(range('...\ntitle: x\n...\n')).toBe(null); // `...` cannot open one
  });

  test('gives up past the line bound rather than scanning a whole file', () => {
    const doc = ['---', ...Array.from({ length: 400 }, (_, i) => `k${i}: v`), '---'].join('\n');
    expect(range(doc)).toBe(null);
  });
});

describe('buildTableDecorations', () => {
  const TABLE = '| a | b |\n| --- | --- |\n| 1 | 2 |';

  test('renders a table as one block widget', () => {
    expect(tableBlocks(`x\n\n${TABLE}\n\ny`)).toEqual([{ from: 3, to: 3 + TABLE.length }]);
  });

  test('a table inside a list item still renders', () => {
    // The walk only descends into the block nodes that can hold a table, so
    // this pins the container list.
    const doc = `- item\n\n  ${TABLE.split('\n').join('\n  ')}\n`;
    expect(tableBlocks(doc)).toHaveLength(1);
  });

  test('a table with the cursor inside it stays raw markdown', () => {
    const doc = `x\n\n${TABLE}\n`;
    expect(tableBlocks(doc, 5)).toEqual([]);
  });
});
