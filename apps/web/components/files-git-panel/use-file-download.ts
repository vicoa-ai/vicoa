'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { rpcReadFileRange } from './rpc';
import {
  downloadErrorMessage,
  fetchFileSlices,
  FileDownloadError,
} from './file-download';

export type FileDownloadStatus =
  | { kind: 'idle' }
  | { kind: 'downloading'; path: string; received: number; total: number | null }
  | { kind: 'error'; path: string; message: string };

const IDLE: FileDownloadStatus = { kind: 'idle' };

/** How long the object URL outlives the click. The browser reads the blob when
 * the download starts, so this only has to cover that, and it bounds how long a
 * large copy stays in memory after it was saved. */
const REVOKE_AFTER_MS = 60_000;

function basename(path: string): string {
  const i = path.lastIndexOf('/');
  return i < 0 ? path : path.slice(i + 1);
}

/** Hand the bytes to the browser as a file save (the desktop shell shows its
 * own save dialog for the same click). */
function saveParts(parts: Uint8Array[], fileName: string): void {
  const blob = new Blob(parts as BlobPart[], { type: 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
}

/**
 * Save a project file from the session's machine to this device, whole, however
 * large and whatever its type: the open file's preview is capped (1 MB of text,
 * 5 MB of image), the download is not.
 *
 * One copy at a time; `start` while one runs is ignored. A copy that is
 * cancelled, or still running when the panel unmounts, saves nothing.
 */
export function useFileDownload({
  machineId,
  cwd,
}: {
  machineId: string | null;
  cwd: string | null;
}) {
  const [status, setStatus] = useState<FileDownloadStatus>(IDLE);
  // The running copy's cancel flag; null when nothing runs.
  const running = useRef<{ cancelled: boolean } | null>(null);

  useEffect(
    () => () => {
      if (running.current) running.current.cancelled = true;
    },
    [],
  );

  const start = useCallback(
    async (path: string) => {
      if (!machineId || !cwd || running.current) return;
      const job = { cancelled: false };
      running.current = job;
      setStatus({ kind: 'downloading', path, received: 0, total: null });
      try {
        const { parts } = await fetchFileSlices({
          readSlice: (offset, length) => rpcReadFileRange(machineId, cwd, path, offset, length),
          isCancelled: () => job.cancelled,
          onProgress: (received, total) => {
            if (!job.cancelled) setStatus({ kind: 'downloading', path, received, total });
          },
        });
        if (job.cancelled) throw new FileDownloadError('cancelled');
        saveParts(parts, basename(path));
        setStatus(IDLE);
      } catch (err) {
        const cancelled = err instanceof FileDownloadError && err.code === 'cancelled';
        // A cancel is the user's own doing, not a failure to report.
        setStatus(cancelled ? IDLE : { kind: 'error', path, message: downloadErrorMessage(err) });
      } finally {
        running.current = null;
      }
    },
    [machineId, cwd],
  );

  const cancel = useCallback(() => {
    if (running.current) running.current.cancelled = true;
  }, []);

  const dismiss = useCallback(() => {
    setStatus((s) => (s.kind === 'error' ? IDLE : s));
  }, []);

  return { status, start, cancel, dismiss };
}
