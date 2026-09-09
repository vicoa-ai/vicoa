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
// Three guards, all needed:
//  1. wait for the shell's line editor to be reading (`isLineEditorReady`);
//  2. hand the text over as a BRACKETED PASTE (`prepareInitialInput`) — see
//     below, this is what actually keeps the queue drained;
//  3. feed it in sub-queue-sized chunks (`chunkPtyInput`) so a shell that
//     stalls mid-write can only ever have a fraction of a queue outstanding.
//
// (2) is not cosmetic. Typed character-by-character, every byte runs the full
// ZLE widget stack, and a stock oh-my-zsh has plenty on it: `url-quote-magic`
// on self-insert, zsh-autosuggestions' history query, zsh-syntax-highlighting
// re-highlighting the whole buffer on each redraw — O(n) work per character
// over a growing line. On a 1.5KB setup chain that is far slower than a writer
// pushing 256 bytes every 20ms, so the queue fills, the tail is dropped, and
// the user is left at a `cmdsubst>` continuation prompt that never returns:
// the "setup hangs" bug. Inside `ESC[200~ … ESC[201~` the shell's paste widget
// instead slurps the whole run out of the tty in one go and inserts it as
// literal text, no per-character widgets — the queue drains as fast as we can
// write. The submitting CR must stay OUTSIDE the markers: inside a paste it is
// literal text (a newline in the buffer), so the chain would sit there, typed
// but never run.

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

/** Bracketed-paste delimiters. A shell that emitted `ESC[?2004h` has told us it
 *  understands these; anything else must be typed raw (the markers would land
 *  in the command line as literal `[200~` garbage). */
const PASTE_START = '\x1b[200~';
const PASTE_END = '\x1b[201~';

/** Split trailing CR/LF — what submits the command — from the text itself. */
function splitSubmit(data: string): [body: string, submit: string] {
  const match = /[\r\n]+$/.exec(data);
  if (match === null) return [data, ''];
  return [data.slice(0, match.index), match[0]];
}

/** The exact sequence of pty writes that types `data` into a live shell.
 *
 *  With `bracketedPaste` the body is wrapped in paste markers and the trailing
 *  CR follows as its own write (a CR inside the markers is literal text, and
 *  would leave the command typed but unexecuted). Without it — a shell that
 *  never advertised bracketed paste — the same chunks go out raw, which is the
 *  best we can do for a line editor that has no fast paste path.
 */
export function prepareInitialInput(
  data: string,
  { bracketedPaste }: { bracketedPaste: boolean },
): string[] {
  const [body, submit] = splitSubmit(data);
  const chunks = chunkPtyInput(body);
  if (bracketedPaste && chunks.length > 0) {
    chunks[0] = PASTE_START + chunks[0];
    chunks[chunks.length - 1] += PASTE_END;
  }
  if (submit !== '') chunks.push(submit);
  return chunks;
}
