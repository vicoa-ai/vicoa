import { describe, expect, it } from 'vitest';

import {
  collectComposerPaste,
  nameClipboardFile,
  pasteTargetIsEditable,
  type ClipboardTransfer,
} from './chat-paste';

/** A `DataTransfer` stand-in shaped like the one a `paste` event carries. */
function transfer(opts: {
  text?: string;
  items?: { kind: string; file: File | null }[];
  files?: File[];
  throwOnGetData?: boolean;
}): ClipboardTransfer {
  return {
    getData: () => {
      if (opts.throwOnGetData) throw new Error('no clipboard access');
      return opts.text ?? '';
    },
    items: (opts.items ?? []).map((it) => ({ kind: it.kind, getAsFile: () => it.file })),
    files: opts.files ?? [],
  };
}

const NOW = new Date(2026, 8, 11, 14, 30, 5); // 2026-09-11 14:30:05 local

function png(name: string, bytes = 8): File {
  return new File([new Uint8Array(bytes)], name, { type: 'image/png' });
}

describe('collectComposerPaste', () => {
  it('takes a screenshot off an otherwise-empty clipboard', () => {
    const result = collectComposerPaste(
      transfer({ items: [{ kind: 'file', file: png('image.png') }] }),
      NOW,
    );
    expect(result.handled).toBe(true);
    expect(result.files).toHaveLength(1);
    expect(result.files[0].name).toBe('pasted-image-20260911-143005.png');
    expect(result.files[0].type).toBe('image/png');
  });

  it('leaves a plain text paste to the browser', () => {
    const result = collectComposerPaste(transfer({ text: 'hello' }), NOW);
    expect(result).toEqual({ files: [], handled: false });
  });

  // Copying a range out of Excel/Numbers/Figma puts both a bitmap and the text
  // on the clipboard; the text is what the user meant.
  it('prefers text when the clipboard carries text and an image', () => {
    const result = collectComposerPaste(
      transfer({ text: 'a\tb', items: [{ kind: 'file', file: png('image.png') }] }),
      NOW,
    );
    expect(result).toEqual({ files: [], handled: false });
  });

  it('keeps a real filename from a copied file', () => {
    const result = collectComposerPaste(
      transfer({ items: [{ kind: 'file', file: png('screenshot-of-bug.png') }] }),
      NOW,
    );
    expect(result.files[0].name).toBe('screenshot-of-bug.png');
  });

  it('ignores string items and null files', () => {
    const result = collectComposerPaste(
      transfer({
        items: [
          { kind: 'string', file: null },
          { kind: 'file', file: null },
        ],
      }),
      NOW,
    );
    expect(result).toEqual({ files: [], handled: false });
  });

  it('falls back to the flat file list when items is empty', () => {
    const result = collectComposerPaste(transfer({ files: [png('image.png')] }), NOW);
    expect(result.handled).toBe(true);
    expect(result.files[0].name).toBe('pasted-image-20260911-143005.png');
  });

  it('takes every image when several are on the clipboard', () => {
    const result = collectComposerPaste(
      transfer({
        items: [
          { kind: 'file', file: png('a.png') },
          { kind: 'file', file: png('b.png') },
        ],
      }),
      NOW,
    );
    expect(result.files.map((f) => f.name)).toEqual(['a.png', 'b.png']);
  });

  it('survives a clipboard that refuses getData', () => {
    const result = collectComposerPaste(
      transfer({ throwOnGetData: true, items: [{ kind: 'file', file: png('image.png') }] }),
      NOW,
    );
    expect(result.handled).toBe(true);
  });

  it('handles a missing transfer', () => {
    expect(collectComposerPaste(null, NOW)).toEqual({ files: [], handled: false });
    expect(collectComposerPaste(undefined, NOW)).toEqual({ files: [], handled: false });
  });
});

describe('nameClipboardFile', () => {
  it.each([
    ['image/png', 'pasted-image-20260911-143005.png'],
    ['image/jpeg', 'pasted-image-20260911-143005.jpg'],
    ['image/gif', 'pasted-image-20260911-143005.gif'],
    ['image/webp', 'pasted-image-20260911-143005.webp'],
    ['image/svg+xml', 'pasted-image-20260911-143005.svg'],
  ])('names a %s clipboard bitmap %s', (mime, expected) => {
    const file = new File([new Uint8Array(4)], 'image.png', { type: mime });
    expect(nameClipboardFile(file, NOW).name).toBe(expected);
  });

  it('falls back to the mime subtype for an unknown type', () => {
    const file = new File([new Uint8Array(4)], '', { type: 'image/heic' });
    expect(nameClipboardFile(file, NOW).name).toBe('pasted-image-20260911-143005.heic');
  });

  it('preserves the file contents', async () => {
    const file = new File([new Uint8Array([1, 2, 3])], 'image.png', { type: 'image/png' });
    const renamed = nameClipboardFile(file, NOW);
    expect(new Uint8Array(await renamed.arrayBuffer())).toEqual(new Uint8Array([1, 2, 3]));
  });
});

describe('pasteTargetIsEditable', () => {
  const el = (tagName: string, extra: Record<string, unknown> = {}) =>
    ({ tagName, closest: () => null, ...extra }) as unknown as EventTarget;

  it('claims nothing when the paste landed on plain markup', () => {
    expect(pasteTargetIsEditable(el('DIV'))).toBe(false);
    expect(pasteTargetIsEditable(el('BODY'))).toBe(false);
    expect(pasteTargetIsEditable(null)).toBe(false);
  });

  // xterm types into a helper <textarea>; taking its paste would break terminal
  // paste outright.
  it('defers to fields that take typing', () => {
    expect(pasteTargetIsEditable(el('TEXTAREA'))).toBe(true);
    expect(pasteTargetIsEditable(el('INPUT'))).toBe(true);
    expect(pasteTargetIsEditable(el('SELECT'))).toBe(true);
  });

  it('defers to contenteditable, directly or by ancestor', () => {
    expect(pasteTargetIsEditable(el('DIV', { isContentEditable: true }))).toBe(true);
    expect(
      pasteTargetIsEditable(el('SPAN', { closest: (s: string) => (s.includes('contenteditable') ? {} : null) })),
    ).toBe(true);
  });

  it('tolerates a target that is not an element', () => {
    // A paste can target the document itself, which has no `tagName`.
    expect(pasteTargetIsEditable({} as EventTarget)).toBe(false);
    expect(pasteTargetIsEditable({ nodeType: 9 } as unknown as EventTarget)).toBe(false);
  });
});
