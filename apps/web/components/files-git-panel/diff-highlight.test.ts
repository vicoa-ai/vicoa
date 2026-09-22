import { describe, test, expect } from 'vitest';
import { escapeHtml, overlaySegments } from './diff-highlight';

const seg = (text: string, changed = false) => ({ text, changed });

describe('overlaySegments', () => {
  test('wraps a changed run inside plain text', () => {
    expect(overlaySegments('const a = 1', [seg('const a = '), seg('1', true)], 'c')).toBe(
      'const a = <span class="c">1</span>',
    );
  });

  test('passes syntax tags through and splits a box that crosses one', () => {
    // hljs: `<span class="hljs-keyword">const</span> a = 1`
    const html = '<span class="hljs-keyword">const</span> a = 1';
    const out = overlaySegments(html, [seg('con'), seg('st a', true), seg(' = 1')], 'c');
    expect(out).toBe(
      '<span class="hljs-keyword">con<span class="c">st</span></span><span class="c"> a</span> = 1',
    );
  });

  test('counts entities as one source character and re-escapes', () => {
    // Source `a<b && c` → hljs escapes it; the box covers `<b &`.
    const html = 'a&lt;b &amp;&amp; c';
    const out = overlaySegments(html, [seg('a'), seg('<b &', true), seg('& c')], 'c');
    expect(out).toBe('a<span class="c">&lt;b &amp;</span>&amp; c');
  });

  test('no changed runs returns the html untouched', () => {
    const html = '<span class="x">foo</span> bar';
    expect(overlaySegments(html, [seg('foo bar')], 'c')).toBe(html);
  });

  test('adjacent changed runs each get their own box', () => {
    const out = overlaySegments('ab', [seg('a', true), seg('b', true)], 'c');
    expect(out).toBe('<span class="c">a</span><span class="c">b</span>');
  });
});

describe('escapeHtml', () => {
  test('escapes the hljs set', () => {
    expect(escapeHtml(`<a href="x">&'</a>`)).toBe('&lt;a href=&quot;x&quot;&gt;&amp;&#x27;&lt;/a&gt;');
  });
});
