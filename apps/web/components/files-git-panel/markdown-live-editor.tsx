'use client';

import { useEffect, useRef } from 'react';
import { EditorState, Compartment, Annotation } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { indentWithTab } from '@codemirror/commands';
import { basicSetup } from 'codemirror';
import { oneDark } from '@codemirror/theme-one-dark';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { markdownLivePreview } from './cm-markdown-live';
import { SCROLL_PERSIST_MS, scrollToAnchor, topAnchor } from './cm-scroll';
import { CM_SCROLLBAR_FIREFOX, CM_SCROLLBAR_WEBKIT, PANEL_BG } from './styles';
import { resolvedThemeNow, useIsDarkTheme } from '@/lib/hooks/use-resolved-theme';

/**
 * The live-preview markdown editor — the same swappable prop contract as
 * {@link FileEditor} (`value`/`wrap`/`onChange`/`onSave`), with a live-preview
 * layer (see {@link markdownLivePreview}) so the user edits the *rendered*
 * document in place rather than toggling to raw source.
 *
 * Crucially, the buffer is still plain markdown text — edits flow through
 * `onChange` exactly like {@link FileEditor}, so the panel's save/conflict/poll
 * engine drives it unchanged and every save is byte-for-byte the file's markdown.
 */
export interface MarkdownLiveEditorProps {
  /** File path — kept for parity with FileEditor and to key the editor. */
  path: string;
  /** The current buffer to display/edit. */
  value: string;
  wrap?: boolean;
  onChange: (value: string) => void;
  /** Fired on Cmd/Ctrl+S. */
  onSave: () => void;
  /** Scroll anchor (1-based top line + sub-line px offset) to restore on mount. */
  initialScrollLine?: number;
  initialScrollOffset?: number;
  /** Reports the top scroll anchor (debounced while scrolling, flushed on
   * teardown) so the parent can remember it; `path` attributes it to this tab. */
  onScrollAnchor?: (path: string, line: number, offset: number) => void;
}

/** Marks a programmatic doc replacement (external reload) so the change
 * listener doesn't echo it back to the parent as if the user typed it. */
const External = Annotation.define<boolean>();

// Dark gets oneDark; light falls through to `basicSetup`'s bundled
// `defaultHighlightStyle`. Compartmentalized so a theme flip reconfigures the
// live editor rather than rebuilding it (see FileEditor for the same idiom).
const syntaxTheme = (dark: boolean) => (dark ? oneDark : []);

const baseTheme = EditorView.theme({
  '&': { height: '100%', fontSize: '13px', backgroundColor: PANEL_BG },
  // A document-scale reading column, not a code gutter, for the "formatted" feel.
  '.cm-content': { maxWidth: '820px', padding: '10px 20px 40px' },  // margin: '0 auto', to make the markdown content central algined. 
  '.cm-scroller': {
    fontFamily: 'var(--font-mono, ui-sans-serif, system-ui, sans-serif)',
    lineHeight: '1.7',
    ...CM_SCROLLBAR_FIREFOX,
  },
  // Line numbers/fold gutter make no sense on a rendered document — hide them.
  '.cm-gutters': { display: 'none' },
  '&.cm-focused': { outline: 'none' },
  // Thin site-standard scrollbar (matches app/globals.css `.custom-scrollbar`).
  ...CM_SCROLLBAR_WEBKIT,
});

export function MarkdownLiveEditor({
  path,
  value,
  wrap = true,
  onChange,
  onSave,
  initialScrollLine,
  initialScrollOffset,
  onScrollAnchor,
}: MarkdownLiveEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  // Latest callbacks read through refs so the editor is created once per file
  // (not recreated every render as the parent's closures change).
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  const onScrollAnchorRef = useRef(onScrollAnchor);
  const initialAnchorRef = useRef({ line: initialScrollLine, offset: initialScrollOffset });
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;
  onScrollAnchorRef.current = onScrollAnchor;
  initialAnchorRef.current = { line: initialScrollLine, offset: initialScrollOffset };

  // The editor is built once per file and re-themed in place (effect at the
  // bottom), so the create-effect reads the palette straight off <html> rather
  // than through this state — no first-frame flash of the wrong syntax colors.
  const isDark = useIsDarkTheme();

  const wrapComp = useRef(new Compartment());
  const themeComp = useRef(new Compartment());

  // Create the editor once per file identity. `value`/`wrap` updates are applied
  // by the effects below so cursor and undo history survive them.
  useEffect(() => {
    const parent = containerRef.current;
    if (!parent) return;
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
        doc: value,
        extensions: [
          saveKeymap, // highest precedence so Cmd/Ctrl+S is ours, not the browser's
          keymap.of([indentWithTab]),
          basicSetup,
          themeComp.current.of(syntaxTheme(resolvedThemeNow() === 'dark')),
          baseTheme,
          // GFM base (not commonmark) so tables + strikethrough are parsed —
          // the live layer renders/styles them.
          markdown({ base: markdownLanguage }),
          markdownLivePreview(),
          wrapComp.current.of(wrap ? EditorView.lineWrapping : []),
          updateListener,
        ],
      }),
    });
    viewRef.current = view;

    // Restore the last anchor for this file (scheduled via scrollIntoView +
    // measure so it lands after CodeMirror's first layout).
    const init = initialAnchorRef.current;
    if (init.line && init.line > 1) scrollToAnchor(view, { line: init.line, offset: init.offset ?? 0 });

    // Remember the top anchor as the user scrolls (debounced), flushed on
    // teardown. `path` attributes the report to this tab even after a re-render.
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
    // Only `path` — value/wrap are reconfigured live below.
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
      effects: wrapComp.current.reconfigure(wrap ? EditorView.lineWrapping : []),
    });
  }, [wrap]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: themeComp.current.reconfigure(syntaxTheme(isDark)),
    });
  }, [isDark]);

  return <div ref={containerRef} className="h-full w-full overflow-hidden" />;
}

export default MarkdownLiveEditor;
