'use client';

import { useEffect, useRef } from 'react';
import { EditorState, Compartment, Annotation } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { indentWithTab } from '@codemirror/commands';
import { basicSetup } from 'codemirror';
import { oneDark } from '@codemirror/theme-one-dark';
import { languageExtensionForPath } from './cm-languages';
import { SCROLL_PERSIST_MS, scrollToAnchor, topAnchor } from './cm-scroll';
import { CM_SCROLLBAR_FIREFOX, CM_SCROLLBAR_WEBKIT } from './styles';

/**
 * The one editor surface, isolated behind a stable prop contract
 * (`value`/`readOnly`/`wrap`/`onChange`/`onSave`) so the CodeMirror internals
 * can be swapped for another engine (e.g. Monaco) without touching the panel,
 * the save engine, or the conflict handling around it.
 */
export interface FileEditorProps {
  /** File path — drives syntax highlighting by extension. */
  path: string;
  /** The current buffer to display/edit. */
  value: string;
  readOnly?: boolean;
  wrap?: boolean;
  onChange: (value: string) => void;
  /** Fired on Cmd/Ctrl+S. */
  onSave: () => void;
  /** Scroll anchor (1-based top line + sub-line px offset) to restore on mount —
   * where the tab was last left. Read once when the editor is created. */
  initialScrollLine?: number;
  initialScrollOffset?: number;
  /** Reports the top scroll anchor (debounced while scrolling, and flushed when
   * the editor is torn down) so the parent can remember it. `path` is the file
   * this editor was created for, so a scroll-then-switch attributes correctly. */
  onScrollAnchor?: (path: string, line: number, offset: number) => void;
}

/** Matches the panel's fixed dark surface (independent of the theme token). */
const PANEL_BG = '#171717';

/** Marks a programmatic doc replacement (external reload) so the change
 * listener doesn't echo it back to the parent as if the user typed it. */
const External = Annotation.define<boolean>();

const baseTheme = EditorView.theme({
  '&': { height: '100%', fontSize: '12px', backgroundColor: PANEL_BG },
  '.cm-scroller': {
    fontFamily: 'var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)',
    lineHeight: '1.5',
    ...CM_SCROLLBAR_FIREFOX,
  },
  '.cm-gutters': { backgroundColor: PANEL_BG, border: 'none' },
  '&.cm-focused': { outline: 'none' },
  // Thin site-standard scrollbar (matches app/globals.css `.custom-scrollbar`).
  ...CM_SCROLLBAR_WEBKIT,
});

export function FileEditor({
  path,
  value,
  readOnly = false,
  wrap = true,
  onChange,
  onSave,
  initialScrollLine,
  initialScrollOffset,
  onScrollAnchor,
}: FileEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  // Latest callbacks, read through refs so the editor is created once per file
  // (not recreated every render as the parent's closures change).
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  const onScrollAnchorRef = useRef(onScrollAnchor);
  const initialAnchorRef = useRef({ line: initialScrollLine, offset: initialScrollOffset });
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;
  onScrollAnchorRef.current = onScrollAnchor;
  initialAnchorRef.current = { line: initialScrollLine, offset: initialScrollOffset };

  const langComp = useRef(new Compartment());
  const readOnlyComp = useRef(new Compartment());
  const wrapComp = useRef(new Compartment());

  // Create the editor once per file identity. `value` updates are applied by
  // the sync effect below so the cursor and undo history survive them.
  useEffect(() => {
    const parent = containerRef.current;
    if (!parent) return;
    const lang = languageExtensionForPath(path);
    const saveKeymap = keymap.of([
      {
        key: 'Mod-s',
        preventDefault: true,
        run: () => {
          onSaveRef.current();
          return true;
        },
      },
    ]);
    const updateListener = EditorView.updateListener.of((u) => {
      if (!u.docChanged) return;
      if (u.transactions.some((tr) => tr.annotation(External))) return;
      onChangeRef.current(u.state.doc.toString());
    });
    const view = new EditorView({
      parent,
      state: EditorState.create({
        // Seeded with the current `value`; subsequent updates flow through the
        // sync effect below (this effect only re-runs when `path` changes).
        doc: value,
        extensions: [
          saveKeymap, // highest precedence so Cmd/Ctrl+S is ours, not the browser's
          keymap.of([indentWithTab]),
          basicSetup,
          oneDark,
          baseTheme,
          langComp.current.of(lang ?? []),
          readOnlyComp.current.of(EditorState.readOnly.of(readOnly)),
          wrapComp.current.of(wrap ? EditorView.lineWrapping : []),
          updateListener,
        ],
      }),
    });
    viewRef.current = view;

    // Restore the last anchor for this file (scheduled via scrollIntoView +
    // measure, so it lands after CodeMirror's first layout).
    const init = initialAnchorRef.current;
    if (init.line && init.line > 1) scrollToAnchor(view, { line: init.line, offset: init.offset ?? 0 });

    // Remember the top anchor as the user scrolls (debounced), and flush the
    // final position on teardown so a quick scroll-then-switch isn't lost.
    // `path` is the file this view was built for, so the report is always
    // attributed to the right tab even after a re-render for a new file.
    let scrollTimer: ReturnType<typeof setTimeout> | undefined;
    const report = () => {
      const a = topAnchor(view);
      onScrollAnchorRef.current?.(path, a.line, a.offset);
    };
    const handleScroll = () => {
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(report, SCROLL_PERSIST_MS);
    };
    view.scrollDOM.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      clearTimeout(scrollTimer);
      view.scrollDOM.removeEventListener('scroll', handleScroll);
      report();
      view.destroy();
      viewRef.current = null;
    };
    // Only `path` — value/readOnly/wrap are reconfigured live below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  // Apply external `value` changes (e.g. reload-from-disk) to the live doc
  // without resetting cursor/undo and without echoing back through onChange.
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (value === current) return;
    view.dispatch({
      changes: { from: 0, to: current.length, insert: value },
      annotations: External.of(true),
    });
  }, [value]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: readOnlyComp.current.reconfigure(EditorState.readOnly.of(readOnly)),
    });
  }, [readOnly]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: wrapComp.current.reconfigure(wrap ? EditorView.lineWrapping : []),
    });
  }, [wrap]);

  return <div ref={containerRef} className="h-full w-full overflow-hidden" />;
}

export default FileEditor;
