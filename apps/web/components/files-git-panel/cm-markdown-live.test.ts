import { describe, test, expect } from 'vitest';
import { EditorState } from '@codemirror/state';
import { ensureSyntaxTree } from '@codemirror/language';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { computeMarkdownDecorations, parseTable } from './cm-markdown-live';

interface Deco {
  from: number;
  to: number;
  cls?: string;
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
    const spec = (it.value as unknown as { spec?: { class?: string; widget?: unknown } }).spec ?? {};
    out.push({
      from: it.from,
      to: it.to,
      cls: spec.class,
      hide: !spec.class && !spec.widget,
      widget: !!spec.widget,
    });
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
