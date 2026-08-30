'use client';

import { useEffect, useRef, type KeyboardEvent } from 'react';
import {
  CaseSensitive,
  ChevronDown,
  ChevronUp,
  Regex,
  Search,
  WholeWord,
  X,
} from 'lucide-react';
import { NO_DRAG } from '@/lib/app-region';

export interface FileFindBarProps {
  query: string;
  onQueryChange: (query: string) => void;
  matchCount: number;
  /** 1-based position of the active match; 0 when there are none. */
  activeOrdinal: number;
  /** True when the query is a regex the engine couldn't parse. */
  regexError: boolean;
  onNext: () => void;
  onPrev: () => void;
  onClose: () => void;
  caseSensitive: boolean;
  onToggleCase: () => void;
  wholeWord: boolean;
  onToggleWholeWord: () => void;
  regexp: boolean;
  onToggleRegexp: () => void;
}

function OptionToggle({
  active,
  label,
  onClick,
  children,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={active}
      title={label}
      className={`flex h-6 w-6 items-center justify-center rounded ${
        active
          ? 'bg-primary/20 text-foreground ring-1 ring-primary/40'
          : 'text-muted-foreground hover:bg-muted hover:text-foreground'
      }`}
    >
      {children}
    </button>
  );
}

/**
 * Floating in-file find bar, pinned top-right of the files/diff viewer — the
 * same overlay treatment as the chat find bar, plus the match-case / whole-word
 * / regex toggles. Drives either CodeMirror or the read-only highlighter; this
 * component is presentational only.
 */
export function FileFindBar({
  query,
  onQueryChange,
  matchCount,
  activeOrdinal,
  regexError,
  onNext,
  onPrev,
  onClose,
  caseSensitive,
  onToggleCase,
  wholeWord,
  onToggleWholeWord,
  regexp,
  onToggleRegexp,
}: FileFindBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
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
  const noMatches = hasQuery && !regexError && matchCount === 0;

  return (
    <div
      className="absolute right-4 top-3 z-30 flex items-center gap-1.5 rounded-lg border border-border bg-background/95 px-2 py-1.5 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-background/80"
      style={NO_DRAG}
      role="search"
    >
      <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <input
        ref={inputRef}
        data-file-find
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Find in file"
        className="w-40 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
        aria-label="Find in file"
        spellCheck={false}
        autoComplete="off"
      />
      <span
        className={`min-w-[3.75rem] shrink-0 text-right text-xs tabular-nums ${
          regexError || noMatches ? 'text-destructive' : 'text-muted-foreground'
        }`}
      >
        {regexError ? 'Bad regex' : noMatches ? 'No results' : hasQuery ? `${activeOrdinal}/${matchCount}` : ''}
      </span>
      <div className="flex items-center gap-0.5 border-l border-border/60 pl-1.5">
        <OptionToggle active={caseSensitive} label="Match case" onClick={onToggleCase}>
          <CaseSensitive className="h-4 w-4" />
        </OptionToggle>
        <OptionToggle active={wholeWord} label="Whole word" onClick={onToggleWholeWord}>
          <WholeWord className="h-4 w-4" />
        </OptionToggle>
        <OptionToggle active={regexp} label="Use regular expression" onClick={onToggleRegexp}>
          <Regex className="h-4 w-4" />
        </OptionToggle>
      </div>
      <div className="flex items-center border-l border-border/60 pl-1">
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
