'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Decoration, DecorationSet, EditorView } from '@codemirror/view';
import type { StateField, StateEffectType } from '@codemirror/state';
import type { SearchQuery } from '@codemirror/search';
import type { FindOptions } from './use-in-file-find';

/**
 * In-file find for the panel's CodeMirror surfaces (editable file, editable
 * diff, live-preview markdown). Instead of opening CodeMirror's own (docked,
 * unstyled) search panel, this drives our floating find bar over the editor.
 *
 * We reuse `@codemirror/search`'s matcher (`SearchQuery.getCursor` — regex /
 * case / whole-word, no extension needed) but paint the hits with our OWN
 * decorations: amber for every match, orange for the focused one — the exact
 * chat-find palette. We deliberately do NOT move the editor selection to the
 * active match, so oneDark's selection background never layers over the orange
 * and the base search theme's cyan/magenta never competes.
 *
 * CodeMirror is code-split; a mounted editor means its chunks are loaded, so
 * the dynamic import resolves from cache. Type-only imports keep it off the
 * base bundle.
 */

const MAX_HITS = 5000;

interface CmRuntime {
  view: typeof import('@codemirror/view');
  search: typeof import('@codemirror/search');
  state: typeof import('@codemirror/state');
  setDeco: StateEffectType<DecorationSet>;
  field: StateField<DecorationSet>;
  hitMark: Decoration;
  activeMark: Decoration;
}

interface Match {
  from: number;
  to: number;
}

function makeRuntime(
  view: CmRuntime['view'],
  search: CmRuntime['search'],
  state: CmRuntime['state'],
): CmRuntime {
  const setDeco = state.StateEffect.define<DecorationSet>();
  const field = state.StateField.define<DecorationSet>({
    create: () => view.Decoration.none,
    update(deco, tr) {
      deco = deco.map(tr.changes);
      for (const e of tr.effects) if (e.is(setDeco)) deco = e.value;
      return deco;
    },
    provide: (f) => view.EditorView.decorations.from(f),
  });
  const hitMark = view.Decoration.mark({ class: 'cm-vicoa-find' });
  const activeMark = view.Decoration.mark({ class: 'cm-vicoa-find-active' });
  return { view, search, state, setDeco, field, hitMark, activeMark };
}

export interface CmFind {
  matchCount: number;
  activeOrdinal: number;
  regexError: boolean;
  goNext: () => void;
  goPrev: () => void;
}

export function useCmFind(
  containerRef: React.RefObject<HTMLElement | null>,
  query: string,
  options: FindOptions,
  enabled: boolean,
): CmFind {
  const rtRef = useRef<CmRuntime | null>(null);
  const [ready, setReady] = useState(false);
  const [matchCount, setMatchCount] = useState(0);
  const [ordinal, setOrdinal] = useState(0);
  const [regexError, setRegexError] = useState(false);
  const matchesRef = useRef<Match[]>([]);
  const activeRef = useRef(0);
  // Views the decoration field has been appended to (idempotent).
  const configured = useRef<WeakSet<EditorView>>(new WeakSet());

  // Lazy-load the CodeMirror modules once, when find is first used.
  useEffect(() => {
    if (!enabled || rtRef.current) return;
    let cancelled = false;
    void Promise.all([
      import('@codemirror/view'),
      import('@codemirror/search'),
      import('@codemirror/state'),
    ]).then(([view, search, state]) => {
      if (cancelled) return;
      rtRef.current = makeRuntime(view, search, state);
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  // The editor to search: the one under focus, else the last in the viewer —
  // the editable `b` pane of a side-by-side diff.
  const getView = useCallback((): EditorView | null => {
    const rt = rtRef.current;
    const container = containerRef.current;
    if (!rt || !container) return null;
    const active = document.activeElement as HTMLElement | null;
    let dom = active?.closest('.cm-editor') as HTMLElement | null;
    if (!dom) {
      const editors = container.querySelectorAll<HTMLElement>('.cm-editor');
      dom = editors.length ? editors[editors.length - 1] : null;
    }
    return dom ? rt.view.EditorView.findFromDOM(dom) : null;
  }, [containerRef]);

  const ensureField = useCallback((rt: CmRuntime, view: EditorView) => {
    if (configured.current.has(view)) return;
    configured.current.add(view);
    view.dispatch({ effects: rt.state.StateEffect.appendConfig.of([rt.field]) });
  }, []);

  const buildQuery = useCallback(
    (rt: CmRuntime): SearchQuery =>
      new rt.search.SearchQuery({
        search: query,
        caseSensitive: options.caseSensitive,
        regexp: options.regexp,
        wholeWord: options.wholeWord,
        literal: true, // plain substring unless regex — matches the read-only find
      }),
    [query, options.caseSensitive, options.regexp, options.wholeWord],
  );

  // Repaint from matchesRef/activeRef and scroll the active hit into view.
  const paint = useCallback((rt: CmRuntime, view: EditorView) => {
    const matches = matchesRef.current;
    const activeIdx = activeRef.current;
    const ranges = matches.map((m, i) =>
      (i === activeIdx ? rt.activeMark : rt.hitMark).range(m.from, m.to),
    );
    const deco = rt.view.Decoration.set(ranges, true);
    const activeMatch = matches[activeIdx];
    view.dispatch({
      effects: activeMatch
        ? [rt.setDeco.of(deco), rt.view.EditorView.scrollIntoView(activeMatch.from, { y: 'center' })]
        : [rt.setDeco.of(deco)],
    });
  }, []);

  const scan = useCallback((rt: CmRuntime, view: EditorView, sq: SearchQuery): Match[] => {
    const out: Match[] = [];
    const cursor = sq.getCursor(view.state);
    for (;;) {
      const r = cursor.next();
      if (r.done || out.length >= MAX_HITS) break;
      if (r.value.from < r.value.to) out.push({ from: r.value.from, to: r.value.to });
    }
    return out;
  }, []);

  // Apply the query / options.
  useEffect(() => {
    if (!enabled || !ready) return;
    const rt = rtRef.current;
    const view = getView();
    if (!rt || !view) {
      setMatchCount(0);
      setOrdinal(0);
      return;
    }
    ensureField(rt, view);
    const sq = buildQuery(rt);
    if (!query || !sq.valid) {
      matchesRef.current = [];
      activeRef.current = 0;
      view.dispatch({ effects: rt.setDeco.of(rt.view.Decoration.none) });
      setMatchCount(0);
      setOrdinal(0);
      setRegexError(!!query && !sq.valid && options.regexp);
      return;
    }
    setRegexError(false);
    const matches = scan(rt, view, sq);
    matchesRef.current = matches;
    // Start on the first match at/after the cursor (feels like "find from
    // here"), wrapping to the top; never move the selection itself.
    const head = view.state.selection.main.head;
    const idx = matches.findIndex((m) => m.from >= head);
    activeRef.current = matches.length ? (idx < 0 ? 0 : idx) : 0;
    paint(rt, view);
    setMatchCount(matches.length);
    setOrdinal(matches.length ? activeRef.current + 1 : 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ready, query, options.caseSensitive, options.regexp, options.wholeWord]);

  // Clear the highlight when find closes.
  useEffect(() => {
    if (enabled) return;
    const rt = rtRef.current;
    const view = getView();
    matchesRef.current = [];
    activeRef.current = 0;
    if (rt && view && configured.current.has(view)) {
      view.dispatch({ effects: rt.setDeco.of(rt.view.Decoration.none) });
    }
  }, [enabled, getView]);

  const step = useCallback(
    (delta: number) => {
      const rt = rtRef.current;
      const view = getView();
      const n = matchesRef.current.length;
      if (!rt || !view || !n) return;
      activeRef.current = (((activeRef.current + delta) % n) + n) % n;
      paint(rt, view);
      setOrdinal(activeRef.current + 1);
    },
    [getView, paint],
  );

  const goNext = useCallback(() => step(1), [step]);
  const goPrev = useCallback(() => step(-1), [step]);

  return { matchCount, activeOrdinal: ordinal, regexError, goNext, goPrev };
}
