/**
 * Drag-and-drop onto the chat composer.
 *
 * A dropped FOLDER is handled two ways, by capability:
 *  - Desktop app — the absolute path is resolvable (`webUtils.getPathForFile`),
 *    so the folder is referenced by `@path/` and the agent reads it in place.
 *  - Plain web — browsers deliberately hide local paths, so the folder's files
 *    are enumerated and uploaded instead (capped downstream at
 *    `MAX_ATTACHMENTS_PER_MESSAGE`).
 * Loose files/images always upload.
 */

import { getDesktopFilePath } from '@/lib/runtime-config';

export interface CollectedDrop {
  /** Loose files + web-enumerated folder contents, to upload. */
  files: File[];
  /** Absolute folder paths the desktop resolved, to reference by `@path/`. */
  folderPaths: string[];
}

// Bound the web folder walk. Uploads are capped at 5 downstream, so we only
// need a small surplus for the size filter to choose from — walking a whole
// dropped `node_modules` would otherwise freeze the tab.
const MAX_ENUM_FILES = 25;

type FsEntry = FileSystemEntry & {
  file?: (cb: (f: File) => void, err?: (e: unknown) => void) => void;
  createReader?: () => FileSystemDirectoryReader;
};

function entryToFile(entry: FsEntry): Promise<File | null> {
  return new Promise((resolve) => {
    if (!entry.file) {
      resolve(null);
      return;
    }
    entry.file(
      (f) => resolve(f),
      () => resolve(null),
    );
  });
}

function readDirBatch(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve) => {
    reader.readEntries(
      (entries) => resolve(entries),
      () => resolve([]),
    );
  });
}

// `readEntries` returns directory children in batches; an empty batch is EOF.
async function readAllDirEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  const all: FileSystemEntry[] = [];
  for (;;) {
    const batch = await readDirBatch(reader);
    if (batch.length === 0) break;
    all.push(...batch);
  }
  return all;
}

async function collectEntryFiles(entry: FsEntry, out: File[], limit: number): Promise<void> {
  if (out.length >= limit) return;
  if (entry.isFile) {
    const file = await entryToFile(entry);
    if (file) out.push(file);
    return;
  }
  if (entry.isDirectory && entry.createReader) {
    const children = await readAllDirEntries(entry.createReader());
    for (const child of children) {
      if (out.length >= limit) break;
      await collectEntryFiles(child as FsEntry, out, limit);
    }
  }
}

/**
 * Inspect a composer drop.
 *
 * Must run against a live `DataTransfer`: the `File`/entry handles are
 * snapshotted synchronously at the top (they're only valid during the drop
 * event), then read across awaits — the transfer list itself is cleared once
 * the handler returns.
 */
export async function collectComposerDrop(dt: DataTransfer): Promise<CollectedDrop> {
  const files: File[] = [];
  const folderPaths: string[] = [];

  const roots = Array.from(dt.items)
    .filter((it) => it.kind === 'file')
    .map((it) => ({
      entry: (it.webkitGetAsEntry?.() ?? null) as FsEntry | null,
      file: it.getAsFile(),
    }));

  // Some engines don't populate `items` for programmatic drops — fall back to
  // the flat file list (loose files only; no folder info there).
  if (roots.length === 0) {
    for (const file of Array.from(dt.files)) files.push(file);
    return { files, folderPaths };
  }

  for (const { entry, file } of roots) {
    const isDir = entry?.isDirectory ?? false;
    if (isDir) {
      const abs = file ? getDesktopFilePath(file) : null;
      if (abs) {
        folderPaths.push(abs);
      } else if (entry) {
        await collectEntryFiles(entry, files, MAX_ENUM_FILES);
      }
    } else if (file) {
      files.push(file);
    }
  }

  return { files, folderPaths };
}

/** Last path segment, for a folder chip's label (e.g. "/a/b/c/" → "c"). */
export function folderDisplayName(path: string): string {
  const trimmed = path.replace(/\/+$/, '');
  const idx = trimmed.lastIndexOf('/');
  const name = idx === -1 ? trimmed : trimmed.slice(idx + 1);
  return name || path;
}

/**
 * Absolute folder path → the composer's `@`-mention form: relative to the
 * project root when inside it (else absolute), always with a trailing "/" to
 * match the file index's folder entries.
 */
export function folderPathToMention(abs: string, projectPath?: string | null): string {
  let rel = abs;
  if (projectPath) {
    const root = projectPath.replace(/\/+$/, '');
    if (abs === root) {
      rel = '';
    } else if (abs.startsWith(`${root}/`)) {
      rel = abs.slice(root.length + 1);
    }
  }
  rel = rel.replace(/\/+$/, '');
  return rel.length === 0 ? './' : `${rel}/`;
}
