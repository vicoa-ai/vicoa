import { describe, test, expect } from 'vitest';
import { chunkPtyInput, isLineEditorReady, PTY_INPUT_CHUNK_BYTES } from './initial-input';

const utf8Bytes = (text: string): number => new TextEncoder().encode(text).length;
const bytes = (text: string): Uint8Array => new TextEncoder().encode(text);

describe('chunkPtyInput', () => {
  test('short input stays a single write', () => {
    expect(chunkPtyInput('ls -la\r')).toEqual(['ls -la\r']);
  });

  test('empty input produces no writes', () => {
    expect(chunkPtyInput('')).toEqual([]);
  });

  test('a real setup chain is split under the tty input queue and rejoins', () => {
    const chain = `export VICOA_ROOT_PATH='/Users/x/vicoa' && ${Array.from(
      { length: 12 },
      (_, i) => `echo 'step ${i} ---------------------------------------------'`,
    ).join(' && ')}\r`;
    const chunks = chunkPtyInput(chain);
    expect(chunks.length).toBeGreaterThan(1);
    for (const chunk of chunks) expect(utf8Bytes(chunk)).toBeLessThanOrEqual(PTY_INPUT_CHUNK_BYTES);
    expect(chunks.join('')).toBe(chain);
    // The CR that runs the chain must be the last thing written.
    expect(chunks[chunks.length - 1].endsWith('\r')).toBe(true);
  });

  test('chunks are measured in UTF-8 bytes, not UTF-16 units', () => {
    const chunks = chunkPtyInput('方'.repeat(300), 12);
    for (const chunk of chunks) expect(utf8Bytes(chunk)).toBeLessThanOrEqual(12);
    expect(chunks[0]).toBe('方'.repeat(4));
  });

  test('never splits a surrogate pair', () => {
    const text = '👩‍💻'.repeat(20);
    const chunks = chunkPtyInput(text, 5);
    for (const chunk of chunks) {
      expect(chunk).toBe(new TextDecoder().decode(new TextEncoder().encode(chunk)));
    }
    expect(chunks.join('')).toBe(text);
  });

  test('a code point wider than the budget still gets written', () => {
    expect(chunkPtyInput('👩', 2)).toEqual(['👩']);
  });
});

describe('isLineEditorReady', () => {
  test('detects bracketed-paste-on in a prompt burst', () => {
    expect(isLineEditorReady(bytes('nick@mac vicoa % \x1b[?2004h'))).toBe(true);
  });

  test('a plain prompt with no bracketed paste is not ready', () => {
    expect(isLineEditorReady(bytes('bash-3.2$ '))).toBe(false);
  });

  test('bracketed-paste-off is not a ready signal', () => {
    expect(isLineEditorReady(bytes('\x1b[?2004l'))).toBe(false);
  });

  test('a truncated sequence at the end of a chunk does not match', () => {
    expect(isLineEditorReady(bytes('\x1b[?2004'))).toBe(false);
  });

  test('empty output is not ready', () => {
    expect(isLineEditorReady(new Uint8Array(0))).toBe(false);
  });
});
