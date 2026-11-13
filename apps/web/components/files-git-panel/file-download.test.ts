import { describe, test, expect } from 'vitest';
import {
  DOWNLOAD_CHUNK_BYTES,
  downloadErrorMessage,
  fetchFileSlices,
  FileDownloadError,
  type FileSlice,
  type ReadSlice,
} from './file-download';

/** A deterministic file of `size` bytes whose every offset is distinguishable
 * from its neighbours, so a slice stitched in the wrong place changes the sum. */
function makeFile(size: number): Uint8Array {
  const data = new Uint8Array(size);
  for (let i = 0; i < size; i++) data[i] = (i * 31 + (i >> 8)) & 0xff;
  return data;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

/** A daemon over `data`: `read-file-range` semantics (a slice is clamped to the
 * end, one at the end is empty), each reply stamped with the file's size and
 * mtime. `delay` lets a test finish slices out of order. */
function fakeDaemon(
  data: Uint8Array,
  opts: { mtime?: number; delay?: (offset: number) => number } = {},
) {
  const log = { calls: [] as number[], inFlight: 0, maxInFlight: 0 };
  const readSlice: ReadSlice = async (offset, length) => {
    log.calls.push(offset);
    log.inFlight++;
    log.maxInFlight = Math.max(log.maxInFlight, log.inFlight);
    await new Promise((r) => setTimeout(r, opts.delay?.(offset) ?? 0));
    log.inFlight--;
    return {
      bytes: data.slice(offset, offset + length),
      size: data.length,
      mtime: opts.mtime ?? 1000,
    };
  };
  return { readSlice, log };
}

const CHUNK = 4;

describe('fetchFileSlices', () => {
  test.each([
    ['an empty file', 0],
    ['a file smaller than one slice', 3],
    ['exactly one slice', 4],
    ['a size that is a multiple of the slice', 16],
    ['a size that ends on a short slice', 18],
  ])('copies %s byte for byte', async (_name, size) => {
    const data = makeFile(size);
    const { readSlice } = fakeDaemon(data);
    const result = await fetchFileSlices({ readSlice, chunkBytes: CHUNK });
    expect(result.size).toBe(size);
    expect(concat(result.parts)).toEqual(data);
  });

  test('copies a file over 1 MiB with the production slice size', async () => {
    const data = makeFile(2 * 1024 * 1024 + 12345);
    const { readSlice, log } = fakeDaemon(data);
    const result = await fetchFileSlices({ readSlice });
    // `toEqual` on a 2 MiB typed array takes seconds; compare the bytes directly.
    expect(Buffer.from(concat(result.parts)).equals(Buffer.from(data))).toBe(true);
    expect(log.calls.length).toBe(Math.ceil(data.length / DOWNLOAD_CHUNK_BYTES));
  });

  test('puts slices back in file order even when they finish out of order', async () => {
    const data = makeFile(40);
    // The earlier the slice, the longer it takes.
    const { readSlice } = fakeDaemon(data, { delay: (offset) => 40 - offset });
    const result = await fetchFileSlices({ readSlice, chunkBytes: CHUNK, parallelism: 4 });
    expect(concat(result.parts)).toEqual(data);
  });

  test('never has more slices in flight than the parallelism', async () => {
    const data = makeFile(60);
    const { readSlice, log } = fakeDaemon(data, { delay: () => 3 });
    await fetchFileSlices({ readSlice, chunkBytes: CHUNK, parallelism: 3 });
    expect(log.maxInFlight).toBe(3);
  });

  test('reports progress up to the file size', async () => {
    const data = makeFile(10);
    const { readSlice } = fakeDaemon(data);
    const seen: Array<[number, number]> = [];
    await fetchFileSlices({
      readSlice,
      chunkBytes: CHUNK,
      parallelism: 1,
      onProgress: (received, total) => seen.push([received, total]),
    });
    expect(seen).toEqual([
      [4, 10],
      [8, 10],
      [10, 10],
    ]);
  });

  describe('a file that changes mid-copy', () => {
    /** The file as of its first slice, then `later` for every slice after it. */
    function changesAfterFirst(first: Uint8Array, later: Uint8Array, laterMtime: number) {
      let calls = 0;
      const readSlice: ReadSlice = async (offset, length) => {
        const isFirst = calls++ === 0;
        const data = isFirst ? first : later;
        return {
          bytes: data.slice(offset, offset + length),
          size: data.length,
          mtime: isFirst ? 1000 : laterMtime,
        };
      };
      return { readSlice, callCount: () => calls };
    }

    test('stops with file_changed when the mtime moves', async () => {
      const data = makeFile(20);
      const { readSlice } = changesAfterFirst(data, data, 1001);
      await expect(fetchFileSlices({ readSlice, chunkBytes: CHUNK })).rejects.toMatchObject({
        code: 'file_changed',
      });
    });

    test('stops with file_changed when the size moves', async () => {
      const { readSlice } = changesAfterFirst(makeFile(20), makeFile(24), 1000);
      await expect(fetchFileSlices({ readSlice, chunkBytes: CHUNK })).rejects.toMatchObject({
        code: 'file_changed',
      });
    });

    test('stops with file_changed when a slice comes back short', async () => {
      const data = makeFile(20);
      const readSlice: ReadSlice = async (offset, length) => ({
        // Right size and mtime, but the slice at 8 lost a byte: truncated
        // between the daemon's fstat and its read.
        bytes: data.slice(offset, offset + length - (offset === 8 ? 1 : 0)),
        size: data.length,
        mtime: 1000,
      });
      await expect(fetchFileSlices({ readSlice, chunkBytes: CHUNK })).rejects.toBeInstanceOf(
        FileDownloadError,
      );
    });

    test('stops with file_changed when the first slice disagrees with its own size', async () => {
      const readSlice: ReadSlice = async () => ({
        bytes: new Uint8Array(2),
        size: 20,
        mtime: 1000,
      });
      await expect(fetchFileSlices({ readSlice, chunkBytes: CHUNK })).rejects.toMatchObject({
        code: 'file_changed',
      });
    });

    test('asks for no more slices once one has failed', async () => {
      const data = makeFile(400);
      const { readSlice, callCount } = changesAfterFirst(data, data, 1001);
      await expect(
        fetchFileSlices({ readSlice, chunkBytes: CHUNK, parallelism: 2 }),
      ).rejects.toMatchObject({ code: 'file_changed' });
      // The first slice, plus at most one in flight per worker when it failed.
      expect(callCount()).toBeLessThanOrEqual(3);
    });
  });

  test('an error from the daemon stops the copy and keeps its code', async () => {
    const data = makeFile(40);
    const readSlice: ReadSlice = async (offset, length): Promise<FileSlice> => {
      if (offset === 12) throw Object.assign(new Error('rpc call failed'), { code: 'timeout' });
      return { bytes: data.slice(offset, offset + length), size: data.length, mtime: 1000 };
    };
    await expect(fetchFileSlices({ readSlice, chunkBytes: CHUNK })).rejects.toMatchObject({
      code: 'timeout',
    });
  });

  test('cancelling stops the copy with cancelled', async () => {
    const data = makeFile(100);
    const { readSlice, log } = fakeDaemon(data);
    let cancelled = false;
    await expect(
      fetchFileSlices({
        readSlice,
        chunkBytes: CHUNK,
        parallelism: 1,
        isCancelled: () => cancelled,
        onProgress: (received) => {
          if (received >= 8) cancelled = true;
        },
      }),
    ).rejects.toMatchObject({ code: 'cancelled' });
    expect(log.calls.length).toBeLessThan(Math.ceil(data.length / CHUNK));
  });

  test('cancelled before it starts reads nothing', async () => {
    const { readSlice, log } = fakeDaemon(makeFile(10));
    await expect(
      fetchFileSlices({ readSlice, chunkBytes: CHUNK, isCancelled: () => true }),
    ).rejects.toMatchObject({ code: 'cancelled' });
    expect(log.calls).toEqual([]);
  });
});

describe('downloadErrorMessage', () => {
  test('words the codes the daemon, the relay and the copy itself can raise', () => {
    expect(downloadErrorMessage({ code: 'file_changed' })).toMatch(/changed while it was downloading/);
    expect(downloadErrorMessage({ code: 'path_not_found' })).toBe('the file no longer exists');
    expect(downloadErrorMessage({ code: 'target_disconnected' })).toBe('machine is offline');
    expect(downloadErrorMessage({ code: 'no_handler' })).toMatch(/update the daemon/);
  });

  test('shows an unknown code as it is, and a non-coded error generically', () => {
    expect(downloadErrorMessage({ code: 'rpc_failed' })).toBe('rpc_failed');
    expect(downloadErrorMessage(new Error('boom'))).toBe('something went wrong');
    expect(downloadErrorMessage('boom')).toBe('something went wrong');
    expect(downloadErrorMessage(null)).toBe('something went wrong');
  });
});
