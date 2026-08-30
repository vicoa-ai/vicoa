// Base64 <-> bytes codec helpers for the PTY wire protocol.
//
// Terminal output arrives as base64-encoded raw bytes and must reach xterm as
// a Uint8Array: decoding to a JS string first (plain atob -> term.write) would
// mangle multi-byte UTF-8 sequences that get split across frames. Keystrokes
// go the other way: UTF-8 encode the input string, then base64 the bytes.

const CHUNK_SIZE = 0x8000;

/** Encode raw bytes to base64 (chunked so large buffers don't overflow the
 *  argument list of String.fromCharCode). */
export function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += CHUNK_SIZE) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK_SIZE));
  }
  return btoa(binary);
}

/** Decode base64 to raw bytes. Never round-trips through a UTF-16 string as
 *  text, so multi-byte UTF-8 (CJK, emoji) survives arbitrary frame splits. */
export function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/** UTF-8 encode a string (user keystrokes / paste) and base64 the bytes. */
export function utf8ToBase64(text: string): string {
  return bytesToBase64(new TextEncoder().encode(text));
}
