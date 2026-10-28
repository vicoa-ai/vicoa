import { describe, expect, test } from 'vitest';
import {
  appendAnnotations,
  buildAnnotationBlock,
  createAnnotation,
  MAX_QUOTE_CHARS,
  normalizeSelectedText,
  parseAnnotations,
  type ChatAnnotation,
} from './chat-annotations';

function annotation(quote: string, comment = '', id = quote): ChatAnnotation {
  return { id, quote, comment };
}

describe('normalizeSelectedText', () => {
  test('folds CRLF, strips trailing spaces and squeezes blank-line runs', () => {
    expect(normalizeSelectedText('  first  \r\n\r\n\r\n\nsecond\t\n')).toBe('first\n\nsecond');
  });

  test('clamps an over-long selection with a marker', () => {
    const out = normalizeSelectedText('a'.repeat(MAX_QUOTE_CHARS + 50));
    expect(out.startsWith('a'.repeat(MAX_QUOTE_CHARS))).toBe(true);
    expect(out.endsWith('\n… (truncated)')).toBe(true);
  });
});

describe('createAnnotation', () => {
  test('normalises the quote, trims the comment and assigns an id', () => {
    const a = createAnnotation('  quoted \n', '  why?  ');
    expect(a.quote).toBe('quoted');
    expect(a.comment).toBe('why?');
    expect(a.id).toBeTruthy();
  });
});

describe('buildAnnotationBlock', () => {
  test('numbers the quotes and indents comments under them, with no header line', () => {
    const block = buildAnnotationBlock([annotation('line one\n\nline two', 'Hi ?'), annotation('second')]);
    expect(block).toBe(
      [
        '1. > line one',
        '   >',
        '   > line two',
        '   Comment: Hi ?',
        '',
        '2. > second',
      ].join('\n'),
    );
  });

  test('keeps a multi-line comment under its number', () => {
    const block = buildAnnotationBlock([annotation('q', 'a\nb')]);
    expect(block).toBe(['1. > q', '   Comment: a', '   b'].join('\n'));
  });

  test('widens the indent past nine items', () => {
    const many = Array.from({ length: 10 }, (_, i) => annotation(`q${i}`, 'c', `${i}`));
    expect(buildAnnotationBlock(many).split('\n').slice(-2)).toEqual(['10. > q9', '    Comment: c']);
  });

  test('is empty when nothing has a quote', () => {
    expect(buildAnnotationBlock([annotation('  ')])).toBe('');
    expect(buildAnnotationBlock([])).toBe('');
  });
});

describe('appendAnnotations', () => {
  test('puts the block under the typed text after a rule', () => {
    expect(appendAnnotations('fix this', [annotation('q')])).toBe('fix this\n\n---\n1. > q');
  });

  test('sends the block alone when nothing was typed', () => {
    expect(appendAnnotations('', [annotation('q')])).toBe('1. > q');
  });

  test('leaves the body untouched without annotations', () => {
    expect(appendAnnotations('hello', [])).toBe('hello');
  });
});

describe('parseAnnotations', () => {
  test('keeps well-formed entries and drops the rest', () => {
    expect(
      parseAnnotations([
        { id: 'a', quote: 'q', comment: 'c' },
        { id: 'b', quote: 'q2' },
        { id: 'c', quote: '   ' },
        { quote: 'no id' },
        null,
        'text',
      ]),
    ).toEqual([
      { id: 'a', quote: 'q', comment: 'c' },
      { id: 'b', quote: 'q2', comment: '' },
    ]);
  });

  test('treats anything but an array as empty', () => {
    expect(parseAnnotations({ id: 'a' })).toEqual([]);
    expect(parseAnnotations(null)).toEqual([]);
  });
});
