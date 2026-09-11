/**
 * Clipboard paste onto the chat composer.
 *
 * The case that matters is a screenshot (Win+Shift+S, ⌘⇧4, Print Screen): the
 * OS puts a bitmap on the clipboard and nothing else, so Ctrl/⌘+V into the
 * prompt box should attach it instead of doing nothing. The transfer is the
 * same `DataTransfer` a drop carries, so the files land in the same upload
 * pipeline as `chat-drop.ts` (see `MAX_ATTACHMENTS_PER_MESSAGE`).
 *
 * Text pasting must not regress, which decides the one ambiguous case: a
 * clipboard that holds BOTH text and an image. Copying a range out of Excel,
 * Numbers or Figma does exactly that — the payload the user meant is the text,
 * and the bitmap is a rendering of it. So text wins whenever there is text, and
 * files are only taken from an otherwise-textless clipboard. That is also the
 * screenshot case, which is the one being asked for.
 */

/** The slice of `DataTransfer` this module reads — spelled structurally so a
 * test can hand it a literal. */
export interface ClipboardTransfer {
  getData(format: string): string;
  items?: ArrayLike<{ kind: string; getAsFile(): File | null }> | null;
  files?: ArrayLike<File> | null;
}

export interface ClipboardPaste {
  /** Files to hand to the composer's attachment pipeline. */
  files: File[];
  /** True when this paste was consumed as an attachment, so the caller should
   * `preventDefault()` — otherwise the browser's own text paste must run. */
  handled: boolean;
}

/** Extensions for the raster types a clipboard realistically produces; anything
 * else falls back to the mime subtype. */
const MIME_EXTENSIONS: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'image/bmp': 'bmp',
  'image/tiff': 'tiff',
  'image/svg+xml': 'svg',
};

function extensionFor(mimeType: string): string {
  const known = MIME_EXTENSIONS[mimeType];
  if (known) return known;
  const subtype = mimeType.split('/')[1] ?? '';
  const cleaned = subtype.split('+')[0].replace(/[^a-z0-9]/gi, '').toLowerCase();
  return cleaned || 'bin';
}

/** Chromium hands every clipboard bitmap the same placeholder name, so a
 * session with three pasted screenshots is three attachments called
 * "image.png". Anything else — a file copied in Finder/Explorer — keeps the
 * name the user knows it by. */
function isPlaceholderName(name: string): boolean {
  return name === '' || /^image\.[a-z0-9]+$/i.test(name);
}

function pasteTimestamp(now: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  );
}

/** Give a clipboard bitmap a name that means something in a message list and in
 * the agent's prompt ("pasted-image-20260911-143005.png"). */
export function nameClipboardFile(file: File, now: Date = new Date()): File {
  if (!isPlaceholderName(file.name)) return file;
  const name = `pasted-image-${pasteTimestamp(now)}.${extensionFor(file.type)}`;
  return new File([file], name, { type: file.type, lastModified: file.lastModified });
}

/**
 * Inspect a composer paste.
 *
 * Must be called synchronously from the `paste` handler: the item list is only
 * valid for the duration of the event.
 */
export function collectComposerPaste(
  dt: ClipboardTransfer | null | undefined,
  now: Date = new Date(),
): ClipboardPaste {
  if (!dt) return { files: [], handled: false };

  // Text wins outright (see the header). `getData` throws on nothing in any
  // engine we ship on, but a paste handler that throws eats the paste.
  let text = '';
  try {
    text = dt.getData('text/plain') ?? '';
  } catch {
    text = '';
  }
  if (text.length > 0) return { files: [], handled: false };

  const files: File[] = [];
  const items = dt.items ? Array.from(dt.items) : [];
  for (const item of items) {
    if (item.kind !== 'file') continue;
    const file = item.getAsFile();
    if (file) files.push(nameClipboardFile(file, now));
  }
  // Some engines leave `items` empty for a synthesized transfer; the flat file
  // list is the fallback (this is what `chat-drop.ts` does for drops).
  if (files.length === 0 && dt.files) {
    for (const file of Array.from(dt.files)) files.push(nameClipboardFile(file, now));
  }

  return { files, handled: files.length > 0 };
}

const EDITABLE_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

/**
 * Does this paste already belong to something that takes typing?
 *
 * Used by the composer's document-level fallback, which exists because a
 * screenshot is taken in *another* app: the user comes back to a window where
 * nothing is focused and presses Ctrl/⌘+V. That fallback must not steal a paste
 * from the terminal (xterm types into a helper `<textarea>`), a search box, or
 * any other field — those own their own clipboard behaviour.
 */
export function pasteTargetIsEditable(target: EventTarget | null): boolean {
  const el = target as (Element & { isContentEditable?: boolean }) | null;
  if (!el || typeof el.tagName !== 'string') return false;
  if (EDITABLE_TAGS.has(el.tagName.toUpperCase())) return true;
  if (el.isContentEditable) return true;
  return typeof el.closest === 'function' && el.closest('[contenteditable="true"]') !== null;
}
