'use client';

import { useEffect, useRef, type KeyboardEvent } from 'react';
import { ChevronDown, ChevronUp, Search, X } from 'lucide-react';
import { NO_DRAG } from '@/lib/app-region';

interface ChatFindBarProps {
  query: string;
  onQueryChange: (query: string) => void;
  matchCount: number;
  /** 1-based position of the active match; 0 when there are none. */
  activeOrdinal: number;
  onNext: () => void;
  onPrev: () => void;
  onClose: () => void;
}

/**
 * Floating find bar pinned to the top-right of the transcript. It's a
 * zero-layout overlay (like the scroll-to-bottom button) so it never disturbs
 * Virtuoso's measurement / stick-to-bottom machinery.
 */
export function ChatFindBar({
  query,
  onQueryChange,
  matchCount,
  activeOrdinal,
  onNext,
  onPrev,
  onClose,
}: ChatFindBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Autofocus + select on open so a prefilled selection is replaceable.
    const el = inputRef.current;
    if (!el) return;
    el.focus();
    el.select();
  }, []);

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (e.shiftKey) onPrev();
      else onNext();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  const hasQuery = query.trim().length > 0;
  const noMatches = hasQuery && matchCount === 0;

  return (
    <div
      className="absolute right-4 top-3 z-30 flex items-center gap-1.5 rounded-lg border border-border bg-background/95 px-2 py-1.5 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-background/80"
      style={NO_DRAG}
      role="search"
    >
      <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <input
        ref={inputRef}
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Find in conversation"
        className="w-44 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
        aria-label="Find in conversation"
        spellCheck={false}
        autoComplete="off"
      />
      <span
        className={`min-w-[3.75rem] shrink-0 text-right text-xs tabular-nums ${
          noMatches ? 'text-destructive' : 'text-muted-foreground'
        }`}
      >
        {noMatches ? 'No results' : hasQuery ? `${activeOrdinal}/${matchCount}` : ''}
      </span>
      <div className="flex items-center">
        <button
          type="button"
          onClick={onPrev}
          disabled={matchCount === 0}
          aria-label="Previous match"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <ChevronUp className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={matchCount === 0}
          aria-label="Next match"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <ChevronDown className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close find"
          className="ml-0.5 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
