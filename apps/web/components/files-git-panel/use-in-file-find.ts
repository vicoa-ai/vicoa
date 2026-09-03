'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * In-file find for the panel's READ-ONLY surfaces — the git Changes diff, a
 * truncated/binary file body, rendered markdown. (Editable files render in
 * CodeMirror; those are driven through `useCmFind` instead.)
 *
 * Highlighting uses the CSS Custom Highlight API (`CSS.highlights` + `Range`s)
 * rather than injecting `<mark>` nodes: the surfaces are React-rendered, and
 * mutating their DOM would fight reconciliation. Highlights are painted over
 * live Ranges instead, so React's DOM is left untouched. Where the API is
 * unavailable (older browsers), navigation/scroll still work — only the tint is
 * absent. Electron (Chromium) always supports it.
 */

const HL_ALL = 'vicoa-file-find';
const HL_ACTIVE = 'vicoa-file-find-active';
// A very high number of hits would blow the Highlight() constructor's argument
// list; cap generously — real files/diffs never approach this.
const MAX_HITS = 2000;

export interface FindOptions {
  caseSensitive: boolean;
  regexp: boolean;
  wholeWord: boolean;
}

interface HighlightRegistryLike {
  set(name: string, highlight: object): void;
  delete(name: string): void;
}
interface HighlightCtor {
  new (...ranges: Range[]): object;
}

function highlightApi(): { registry: HighlightRegistryLike; Ctor: HighlightCtor } | null {
  const g = globalThis as unknown as {
    CSS?: { highlights?: HighlightRegistryLike };
    Highlight?: HighlightCtor;
  };
  if (g.CSS?.highlights && typeof g.Highlight === 'function') {
    return { registry: g.CSS.highlights, Ctor: g.Highlight };
  }
  return null;
}

// The `::highlight()` pseudo-element is injected at runtime rather than living
// in globals.css: the build-time CSS parser (Lightning CSS) rejects it as an
// unknown pseudo-element, whereas the browser parses it fine. Injected once,
// lazily, and only where the Custom Highlight API exists. Both palettes are
// injected together (the `.dark` rule overrides the light one) so the panel's
// find highlights follow the theme without re-injecting on every toggle —
// matching the chat's `mark.find-hit` colors in app/globals.css.
let stylesInjected = false;
function ensureHighlightStyles(): void {
  if (stylesInjected || typeof document === 'undefined') return;
  stylesInjected = true;
  const style = document.createElement('style');
  style.dataset.vicoaFileFind = '';
  style.textContent =
    '::highlight(vicoa-file-find){background-color:#fde68a;color:inherit;}' +
    '.dark ::highlight(vicoa-file-find){background-color:rgb(250 204 21 / 0.35);}' +
    '::highlight(vicoa-file-find-active){background-color:#f97316;color:#1a1205;}';
  document.head.appendChild(style);
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Build the global RegExp for `needle` under the given options, or null when
 *  the query is empty or an invalid user regex. */
function buildMatcher(needle: string, options: FindOptions): RegExp | null {
  if (!needle) return null;
  let source = options.regexp ? needle : escapeRegExp(needle);
  if (options.wholeWord) source = `\\b(?:${source})\\b`;
  try {
    return new RegExp(source, options.caseSensitive ? 'g' : 'gi');
  } catch {
    return null; // invalid regex the user is mid-typing
  }
}

/** Text nodes to ignore: line-number/marker gutters, opted-out regions, and any
 *  CodeMirror surface (it has its own search + managed DOM). */
function skip(node: Text): boolean {
  const parent = node.parentElement;
  if (!parent) return true;
  return !!parent.closest('.select-none, [data-find-skip], .cm-editor');
}

function collectRanges(root: HTMLElement, matcher: RegExp): Range[] {
  const ranges: Range[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const text = node as Text;
      if (!text.nodeValue || skip(text)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let node = walker.nextNode() as Text | null;
  while (node && ranges.length < MAX_HITS) {
    const value = node.nodeValue ?? '';
    matcher.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = matcher.exec(value)) && ranges.length < MAX_HITS) {
      // Zero-width matches (e.g. `a*`) would loop forever — advance past them.
      if (m[0].length === 0) {
        matcher.lastIndex += 1;
        continue;
      }
      const range = document.createRange();
      range.setStart(node, m.index);
      range.setEnd(node, m.index + m[0].length);
      ranges.push(range);
    }
    node = walker.nextNode() as Text | null;
  }
  return ranges;
}

export interface InFileFind {
  matchCount: number;
  /** 1-based position of the active match; 0 when there are none. */
  activeOrdinal: number;
  /** The query is a regex the browser rejected (user still typing). */
  regexError: boolean;
  goNext: () => void;
  goPrev: () => void;
}

export function useInFileFind(
  containerRef: React.RefObject<HTMLElement | null>,
  query: string,
  enabled: boolean,
  options: FindOptions,
  /** Bump to force a recompute when the underlying content changes (file/tab). */
  contentKey: string,
): InFileFind {
  const [matchCount, setMatchCount] = useState(0);
  const [active, setActive] = useState(0);
  const [regexError, setRegexError] = useState(false);
  const rangesRef = useRef<Range[]>([]);
  // Mirrors `active` so stepping computes the next index without a stale
  // closure and without doing side effects inside a setState updater.
  const activeRef = useRef(0);

  const clearPaint = useCallback(() => {
    const api = highlightApi();
    if (!api) return;
    api.registry.delete(HL_ALL);
    api.registry.delete(HL_ACTIVE);
  }, []);

  const paintActive = useCallback((index: number) => {
    const api = highlightApi();
    if (!api) return;
    const range = rangesRef.current[index];
    if (range) api.registry.set(HL_ACTIVE, new api.Ctor(range));
    else api.registry.delete(HL_ACTIVE);
  }, []);

  const scrollTo = useCallback((index: number) => {
    const range = rangesRef.current[index];
    const el = range?.startContainer.parentElement;
    el?.scrollIntoView({ block: 'center', inline: 'nearest' });
  }, []);

  // Recompute matches whenever the query, options, surface, or enabled flag
  // change. Repaints all hits, focuses the first, and reports the count.
  useEffect(() => {
    const container = containerRef.current;
    const matcher = enabled ? buildMatcher(query.trim(), options) : null;
    if (!enabled || !container || !matcher) {
      rangesRef.current = [];
      activeRef.current = 0;
      clearPaint();
      setMatchCount(0);
      setActive(0);
      // Only an invalid *regex* is an error; an empty query just clears.
      setRegexError(enabled && options.regexp && query.trim().length > 0 && matcher === null);
      return;
    }
    setRegexError(false);
    const ranges = collectRanges(container, matcher);
    rangesRef.current = ranges;
    activeRef.current = 0;
    setMatchCount(ranges.length);
    setActive(0);
    const api = highlightApi();
    if (api) {
      ensureHighlightStyles();
      if (ranges.length) api.registry.set(HL_ALL, new api.Ctor(...ranges));
      else api.registry.delete(HL_ALL);
      paintActive(0);
    }
    if (ranges.length) scrollTo(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, enabled, contentKey, options.caseSensitive, options.regexp, options.wholeWord]);

  // Drop highlights when the hook unmounts (panel closed / navigated away).
  useEffect(() => clearPaint, [clearPaint]);

  const step = useCallback(
    (delta: number) => {
      const n = rangesRef.current.length;
      if (!n) return;
      const next = (((activeRef.current + delta) % n) + n) % n;
      activeRef.current = next;
      setActive(next);
      paintActive(next);
      scrollTo(next);
    },
    [paintActive, scrollTo],
  );

  const goNext = useCallback(() => step(1), [step]);
  const goPrev = useCallback(() => step(-1), [step]);

  const activeOrdinal = matchCount > 0 ? Math.min(active, matchCount - 1) + 1 : 0;
  return { matchCount, activeOrdinal, regexError, goNext, goPrev };
}
