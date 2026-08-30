import { useState, useEffect, useCallback, useRef } from 'react';
import type { FileMention } from '@/lib/backend-api';
import {
  fetchFileMentions,
  getCachedFileMentions,
  type FileMentionSource,
} from '@/lib/file-mentions-store';

interface MetadataShape {
  metadata?: Record<string, unknown> | null;
  machine_metadata?: Record<string, unknown> | null;
}

interface UseFileMentionsOptions {
  projectPath?: string;
  /** Machine the project lives on. Without it, mentions read the DB copy. */
  machineId?: string | null;
  /** Machine object when the call site has one — skips a doomed RPC. */
  machine?: MetadataShape | null;
  enabled?: boolean; // Allow disabling the hook
}

interface UseFileMentionsResult {
  files: FileMention[];
  isLoading: boolean;
  error: Error | null;
  /** Which source produced `files`; null before the first load resolves. */
  source: FileMentionSource | null;
  refetch: () => Promise<void>;
  /** Background refresh — updates `files` without flipping `isLoading`. */
  refresh: () => void;
}

/**
 * Hook to fetch file mentions for `@` autocomplete.
 *
 * Reads through `lib/file-mentions-store`, which prefers the live daemon index
 * and falls back to the CLI-synced DB copy. Cached entries render on the first
 * frame — this used to refetch the whole index (653 KB on average in
 * production) on every mount.
 *
 * @example
 * ```tsx
 * const { files, refresh } = useFileMentions({ projectPath, machineId });
 * ```
 */
export function useFileMentions({
  projectPath,
  machineId,
  machine,
  enabled = true,
}: UseFileMentionsOptions): UseFileMentionsResult {
  // Lazy initializers: the cache lookup only matters on mount, and running it
  // on every render would be pure waste on a component that re-renders per
  // keystroke.
  const [files, setFiles] = useState<FileMention[]>(
    () => (enabled ? getCachedFileMentions(projectPath, machineId) : undefined) ?? [],
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [source, setSource] = useState<FileMentionSource | null>(() =>
    enabled && getCachedFileMentions(projectPath, machineId) ? 'cache' : null,
  );
  // Survives unmount so a late response can't setState on a dead component.
  const mounted = useRef(true);
  const inFlight = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (background: boolean) => {
      if (!enabled || !projectPath) {
        setFiles([]);
        return;
      }
      if (inFlight.current) return;
      inFlight.current = true;
      // A background refresh must not flip the panel into a loading state —
      // the user is mid-`@` and the current list is still perfectly usable.
      if (!background) setIsLoading(true);
      setError(null);

      try {
        const result = await fetchFileMentions({ projectPath, machineId, machine });
        if (!mounted.current) return;
        setFiles(result.files);
        setSource(result.source);
      } catch (err) {
        if (!mounted.current) return;
        const error = err instanceof Error ? err : new Error('Failed to load file mentions');
        setError(error);
        console.warn('Failed to fetch file mentions:', err);
        // On error, set empty array so the UI is still functional
        if (!background) setFiles([]);
      } finally {
        inFlight.current = false;
        if (mounted.current && !background) setIsLoading(false);
      }
    },
    // `machine` is an object identity that changes on every parent render;
    // depending on it would restart the fetch in a loop. The capability it
    // carries is stable for a given machine, so keying on the id is enough.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectPath, machineId, enabled],
  );

  const refetch = useCallback(() => load(false), [load]);
  const refresh = useCallback(() => {
    void load(true);
  }, [load]);

  useEffect(() => {
    const cachedForKey = enabled ? getCachedFileMentions(projectPath, machineId) : undefined;
    if (cachedForKey) {
      // Serve the cache on the first frame, then freshen behind it. The list
      // is only ever additive-ish, so a swap under the panel is not jarring.
      setFiles(cachedForKey);
      setSource('cache');
      void load(true);
      return;
    }
    void load(false);
  }, [projectPath, machineId, enabled, load]);

  return {
    files,
    isLoading,
    error,
    source,
    refetch,
    refresh,
  };
}
