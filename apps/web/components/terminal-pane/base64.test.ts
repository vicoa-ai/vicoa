import { describe, test, expect } from 'vitest';
import { base64ToBytes, bytesToBase64, utf8ToBase64 } from './base64';

const decode = (bytes: Uint8Array): string => new TextDecoder().decode(bytes);

describe('utf8ToBase64 -> base64ToBytes round trip', () => {
  test('plain ASCII', () => {
    expect(decode(base64ToBytes(utf8ToBase64('ls -la\r')))).toBe('ls -la\r');
  });

  test('CJK, accents, and ZWJ emoji survive', () => {
    const text = '方寸万象 héllo 👩‍💻 ~/プロジェクト';
    expect(decode(base64ToBytes(utf8ToBase64(text)))).toBe(text);
  });

  test('empty string', () => {
    expect(utf8ToBase64('')).toBe('');
    expect(base64ToBytes('')).toEqual(new Uint8Array(0));
  });

  test('matches Buffer base64 for UTF-8 text', () => {
    const text = 'echo "终端 ✅"';
    expect(utf8ToBase64(text)).toBe(Buffer.from(text, 'utf-8').toString('base64'));
  });
});

describe('bytesToBase64 / base64ToBytes (raw bytes)', () => {
  test('all 256 byte values round trip losslessly', () => {
    const bytes = new Uint8Array(256).map((_, i) => i);
    expect(base64ToBytes(bytesToBase64(bytes))).toEqual(bytes);
  });

  test('decoding never mangles a multi-byte sequence split across frames', () => {
    // '好' is 3 UTF-8 bytes; split them across two base64 frames the way the
    // pty stream can. Byte-level concatenation must reassemble the character.
    const full = new TextEncoder().encode('好');
    const frame1 = bytesToBase64(full.subarray(0, 1));
    const frame2 = bytesToBase64(full.subarray(1));
    const joined = new Uint8Array([...base64ToBytes(frame1), ...base64ToBytes(frame2)]);
    expect(decode(joined)).toBe('好');
  });

  test('large buffer crosses the fromCharCode chunk boundary (0x8000)', () => {
    const bytes = new Uint8Array(0x8000 * 2 + 17).map((_, i) => (i * 7 + 3) % 256);
    const b64 = bytesToBase64(bytes);
    expect(b64).toBe(Buffer.from(bytes).toString('base64'));
    expect(base64ToBytes(b64)).toEqual(bytes);
  });
});
