// Typing a worktree's setup chain into a freshly-spawned shell, safely.
//
// A pty's input queue is small and fixed — 1024 bytes on macOS (XNU `TTYHOG`),
// 4096 on Linux — and whatever doesn't fit while the shell isn't reading is
// DROPPED by the tty, not backpressured to the writer. A setup chain joined
// with ` && ` clears 1KB easily, so writing it in one shot the instant the
// shell emits its first byte (it's still sourcing rc files then, not reading
// stdin) loses the tail — including the trailing CR. The user is left staring
// at a half-typed command that never runs, e.g. `... && echo '--- ` with an
// unclosed quote.
//
// Two guards, both needed: wait for the shell's line editor to be reading
// (`isLineEditorReady`), then feed the input in sub-queue-sized chunks
// (`chunkPtyInput`) so a shell that stalls mid-write can only ever have a
// fraction of a queue outstanding.

/** Per-write ceiling, well under the 1024-byte macOS tty input queue so a
 *  couple of un-drained chunks still can't overflow it. */
export const PTY_INPUT_CHUNK_BYTES = 256;

const utf8Len = (codePoint: number): number =>
  codePoint < 0x80 ? 1 : codePoint < 0x800 ? 2 : codePoint < 0x10000 ? 3 : 4;

/** Split input into chunks of at most `maxBytes` UTF-8 bytes, never splitting a
 *  code point (a half-written surrogate pair would encode to garbage). A single
 *  code point wider than `maxBytes` gets its own oversized chunk rather than
 *  being dropped. */
export function chunkPtyInput(data: string, maxBytes: number = PTY_INPUT_CHUNK_BYTES): string[] {
  const chunks: string[] = [];
  let current = '';
  let bytes = 0;
  for (const char of data) {
    const size = utf8Len(char.codePointAt(0) ?? 0);
    if (current !== '' && bytes + size > maxBytes) {
      chunks.push(current);
      current = '';
      bytes = 0;
    }
    current += char;
    bytes += size;
  }
  if (current !== '') chunks.push(current);
  return chunks;
}

// `ESC [ ? 2 0 0 4 h` — bracketed paste on. Both zsh's zle and bash's readline
// emit it when the line editor takes over the tty, which is exactly the moment
// the shell starts draining its input queue.
const BRACKETED_PASTE_ON = [0x1b, 0x5b, 0x3f, 0x32, 0x30, 0x30, 0x34, 0x68];

/** True when a chunk of shell output shows the line editor is up and reading.
 *  A shell with bracketed paste off never says so — callers must keep their
 *  quiet-period fallback rather than wait on this forever. */
export function isLineEditorReady(bytes: Uint8Array): boolean {
  outer: for (let i = 0; i + BRACKETED_PASTE_ON.length <= bytes.length; i++) {
    for (let j = 0; j < BRACKETED_PASTE_ON.length; j++) {
      if (bytes[i + j] !== BRACKETED_PASTE_ON[j]) continue outer;
    }
    return true;
  }
  return false;
}
