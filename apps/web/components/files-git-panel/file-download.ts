// Copying a whole file off the session's machine, one `read-file-range` slice
// at a time. The daemon caps a slice at 1 MiB (one relay frame), so anything
// bigger than that, and every file the panel can only preview in part, has to be
// stitched back together here. Mobile does the same in `rpc_files.dart`.
//
// Pure on purpose: the slice reader is passed in, so the ordering and the
// "the file changed under us" rule are unit-tested without a socket.

/** Bytes asked per slice: half the daemon's cap, so the slices in flight
 * together still clear the relay's 30 s RPC timeout on a slow uplink. */
export const DOWNLOAD_CHUNK_BYTES = 512 * 1024;

/** Slices in flight at once. */
export const DOWNLOAD_PARALLELISM = 3;

/** One decoded `read-file-range` reply. `size` and `mtime` describe the file at
 * the moment this slice was read. */
export interface FileSlice {
  bytes: Uint8Array;
  size: number;
  mtime: number;
}

export type ReadSlice = (offset: number, length: number) => Promise<FileSlice>;

export type DownloadFailure = 'file_changed' | 'cancelled';

/** Why a copy stopped on our side (a daemon or relay failure keeps its own
 * `code`, as `RpcError` does). */
export class FileDownloadError extends Error {
  readonly code: DownloadFailure;
  constructor(code: DownloadFailure) {
    super(`file download failed: ${code}`);
    this.name = 'FileDownloadError';
    this.code = code;
  }
}

export interface FetchSlicesOptions {
  readSlice: ReadSlice;
  chunkBytes?: number;
  parallelism?: number;
  /** Polled before each slice is requested; true stops the copy. */
  isCancelled?: () => boolean;
  /** Bytes received so far and the file's total size. */
  onProgress?: (received: number, total: number) => void;
}

/**
 * Read every byte of a file as in-order slices.
 *
 * The first slice fixes the file's size and mtime. Every later slice has to
 * agree with them and come back the length that size implies, or the copy stops
 * with `file_changed`: stitching two versions of a file together would save one
 * that never existed. Without that guard a file the agent rewrites mid-copy
 * would be saved silently corrupted.
 */
export async function fetchFileSlices({
  readSlice,
  chunkBytes = DOWNLOAD_CHUNK_BYTES,
  parallelism = DOWNLOAD_PARALLELISM,
  isCancelled,
  onProgress,
}: FetchSlicesOptions): Promise<{ parts: Uint8Array[]; size: number }> {
  if (isCancelled?.()) throw new FileDownloadError('cancelled');
  const first = await readSlice(0, chunkBytes);
  const { size, mtime } = first;
  const expectedLength = (offset: number): number => Math.min(chunkBytes, size - offset);
  if (first.bytes.length !== expectedLength(0)) throw new FileDownloadError('file_changed');

  const chunkCount = Math.ceil(size / chunkBytes);
  const parts: Uint8Array[] = new Array<Uint8Array>(chunkCount);
  let received = first.bytes.length;
  if (chunkCount > 0) parts[0] = first.bytes;
  onProgress?.(received, size);

  let next = 1;
  let failed = false;
  const worker = async (): Promise<void> => {
    try {
      while (!failed && next < chunkCount) {
        if (isCancelled?.()) throw new FileDownloadError('cancelled');
        const index = next++;
        const offset = index * chunkBytes;
        const slice = await readSlice(offset, chunkBytes);
        if (failed) return;
        if (
          slice.size !== size ||
          slice.mtime !== mtime ||
          slice.bytes.length !== expectedLength(offset)
        ) {
          throw new FileDownloadError('file_changed');
        }
        parts[index] = slice.bytes;
        received += slice.bytes.length;
        onProgress?.(received, size);
      }
    } catch (err) {
      failed = true;
      throw err;
    }
  };

  const workers = Math.max(1, Math.min(parallelism, chunkCount - 1));
  await Promise.all(Array.from({ length: workers }, worker));
  return { parts, size };
}

const MESSAGE_BY_CODE: Record<string, string> = {
  file_changed: 'the file changed while it was downloading, try again',
  path_not_found: 'the file no longer exists',
  permission_denied: 'permission denied',
  outside_project: 'path is outside the project',
  not_a_file: 'not a regular file',
  no_handler: 'update the daemon on this machine to download files',
  target_disconnected: 'machine is offline',
  timeout: 'request timed out',
  not_connected: 'not connected',
};

/** The reason shown after "Couldn’t download <file>:" when a download fails.
 * Takes anything thrown: both `RpcError` and {@link FileDownloadError} carry a
 * string `code`. */
export function downloadErrorMessage(err: unknown): string {
  const code =
    typeof err === 'object' && err !== null && 'code' in err && typeof err.code === 'string'
      ? err.code
      : null;
  if (code === null) return 'something went wrong';
  return MESSAGE_BY_CODE[code] ?? code;
}
