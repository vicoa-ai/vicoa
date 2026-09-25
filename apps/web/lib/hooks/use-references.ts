import { useEffect, useRef, useState } from 'react';
import { getBackendAPI, type ReferenceCandidate } from '@/lib/backend-api';

/** Matches the cmd+K palette's debounce — the same typing rhythm feeds both. */
const REFERENCE_DEBOUNCE_MS = 150;

interface UseReferenceCandidatesOptions {
  /** The text after `#`, or null while the panel is closed. */
  query: string | null;
  /** The session doing the referencing; dropped from the results. */
  excludeSessionId?: string | null;
  enabled?: boolean;
}

interface UseReferenceCandidatesResult {
  items: ReferenceCandidate[];
  isLoading: boolean;
  /** The backend has no `/references` route (older deployment, desktop-local
   * daemon). The caller hides the trigger entirely rather than showing an
   * empty panel on every `#`. */
  unavailable: boolean;
}

/**
 * Candidates for the composer's `#` panel.
 *
 * Unlike `@`, this can't read a cached local index: sessions, tasks and
 * automations live only on the server and change while you type. So every
 * keystroke is a (debounced, abortable) request — cheap, because the endpoint
 * matches titles only and caps each kind at a handful of rows.
 *
 * `items` is left alone while a new query is in flight, so the panel shows the
 * previous matches instead of blanking between keystrokes.
 */
export function useReferenceCandidates({
  query,
  excludeSessionId,
  enabled = true,
}: UseReferenceCandidatesOptions): UseReferenceCandidatesResult {
  const [items, setItems] = useState<ReferenceCandidate[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const active = enabled && !unavailable && query !== null;

  useEffect(() => {
    if (!active) {
      abortRef.current?.abort();
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    const timer = setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const response = await getBackendAPI().listReferences(query ?? '', {
          excludeSessionId,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setItems(response.items);
        setIsLoading(false);
      } catch (err) {
        if (controller.signal.aborted) return;
        if ((err as { status?: number }).status === 404) setUnavailable(true);
        setItems([]);
        setIsLoading(false);
      }
    }, REFERENCE_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [active, query, excludeSessionId]);

  // Drop stale rows once the panel closes, so reopening `#` never flashes the
  // previous session's matches before the new request lands.
  useEffect(() => {
    if (query === null) setItems([]);
  }, [query]);

  useEffect(() => () => abortRef.current?.abort(), []);

  return { items, isLoading, unavailable };
}
