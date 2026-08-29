'use client';

import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { splitOnQuery } from '@/lib/find-highlight';

interface FindHighlightValue {
  /** Active search term, or '' when find is closed. */
  query: string;
  /** Chat-item key (== message id) of the currently-focused match, if any. */
  activeKey: string | null;
}

const FindHighlightContext = createContext<FindHighlightValue>({ query: '', activeKey: null });

/**
 * Broadcasts the current find query + active match down to the virtualized
 * rows. Only mounted rows consume it, so highlighting stays O(visible).
 */
export function FindHighlightProvider({
  query,
  activeKey,
  children,
}: {
  query: string;
  activeKey: string | null;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ query, activeKey }), [query, activeKey]);
  return <FindHighlightContext.Provider value={value}>{children}</FindHighlightContext.Provider>;
}

export function useFindHighlight(): FindHighlightValue {
  return useContext(FindHighlightContext);
}

/**
 * Renders `text` with case-insensitive `query` matches wrapped in
 * `<mark class="find-hit">`. Whitespace is preserved by the caller's
 * `whitespace-pre-wrap` container.
 */
export function HighlightedText({ text, query }: { text: string; query: string }) {
  if (!query) return <>{text}</>;
  const segments = splitOnQuery(text, query);
  if (segments.length === 1 && !segments[0].hit) return <>{text}</>;
  return (
    <>
      {segments.map((segment, i) =>
        segment.hit ? (
          <mark key={i} className="find-hit">
            {segment.text}
          </mark>
        ) : (
          <span key={i}>{segment.text}</span>
        ),
      )}
    </>
  );
}
