'use client';

import { useCallback, useEffect, useRef } from 'react';
import {
  EditorState,
  Annotation,
  Compartment,
  type Extension,
  type StateCommand,
} from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { indentWithTab } from '@codemirror/commands';
import { basicSetup } from 'codemirror';
import { oneDark } from '@codemirror/theme-one-dark';
import {
  MergeView,
  unifiedMergeView,
  getChunks,
  goToNextChunk,
  goToPreviousChunk,
} from '@codemirror/merge';
import { languageExtensionForPath } from './cm-languages';
import { SCROLL_PERSIST_MS, scrollToAnchor, topAnchor } from './cm-scroll';
import { CM_SCROLLBAR_FIREFOX, CM_SCROLLBAR_WEBKIT, PANEL_BG } from './styles';
import { resolvedThemeNow, useIsDarkTheme } from '@/lib/hooks/use-resolved-theme';

/**
 * The editable diff surface, isolated behind the same swappable contract as
 * {@link FileEditor}. The working buffer (`value`) is the editable "modified"
 * side; `original` is the read-only HEAD baseline it's diffed against.
 *
 * - `sideBySide` off → a single `EditorView` with `unifiedMergeView`: an inline
 *   red/green diff whose document (the modified side) is editable in place.
 * - `sideBySide` on → a two-panel `MergeView`: read-only original on the left,
 *   editable working copy on the right.
 *
 * Edits flow through `onChange` exactly like {@link FileEditor}, so the panel's
 * existing save/conflict/poll engine drives both surfaces unchanged.
 */
/** Change-to-change navigation handle the diff surface publishes to the panel
 *  toolbar: `next`/`prev` jump the viewport (and selection) to the adjacent
 *  changed chunk, wrapping at the ends; `count` is the live number of changed
 *  chunks so the buttons can disable when there's nothing to step through. */
export interface DiffNav {
  next: () => void;
  prev: () => void;
  count: number;
}

export interface DiffEditorProps {
  /** File path — drives syntax highlighting by extension. */
  path: string;
  /** The HEAD baseline (read-only original side of the diff). */
  original: string;
  /** The working buffer to display/edit (the modified side). */
  value: string;
  /** Two-panel side-by-side when true; single-panel inline diff when false. */
  sideBySide: boolean;
  wrap?: boolean;
  onChange: (value: string) => void;
  /** Fired on Cmd/Ctrl+S. */
  onSave: () => void;
  /** Scroll anchor (1-based top line + sub-line px offset) to restore on mount.
   * The line is the working ("b") side's line, which matches the plain editor's
   * lines, so a tab keeps its place when flipped between edit and diff. */
  initialScrollLine?: number;
  initialScrollOffset?: number;
  /** Reports the top scroll anchor (debounced while scrolling, flushed on
   * teardown); `path` attributes it to this tab. */
  onScrollAnchor?: (path: string, line: number, offset: number) => void;
  /** Publishes the change-navigation handle (or `null` on teardown / when the
   * surface has no changes) so the toolbar can drive its up/down buttons. */
  onDiffNav?: (nav: DiffNav | null) => void;
}

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

// Overrides @codemirror/merge's built-in diff decorations, whose faint muddy
// `rgba(...,.08)` line tints and 2px underline gradient on changed words read as
// noise on either surface. We retint to a GitHub-style palette (green for adds,
// red for deletes) and swap the word underline for a soft solid box. The 3px
// change-gutter bar is removed separately (gutter:false in the view config).
// `!important` beats @codemirror/merge's base theme, whose `&dark.cm-merge-*`
// selectors would otherwise win on specificity.
//
// With `highlightChanges:false` the word-level marks only survive on genuine
// same-line edits in the unified view (added span → `.cm-changedText`, removed
// span → the inline `<del class=cm-deletedText>`); pure add/delete lines carry
// just the line background. So the two word rules below intentionally style only
// that case — the redundant full-line box on pure inserts/deletes is gone.
function makeMergeTheme(add: string, addWord: string, del: string, delWord: string, dark: boolean) {
  return EditorView.theme(
    {
      // Whole changed lines: additions (the editable/b side + the unified inline
      // changed line) green; the original/a side + deleted chunks red.
      '&.cm-merge-b .cm-changedLine, & .cm-inlineChangedLine': {
        backgroundColor: `${add} !important`,
      },
      '&.cm-merge-a .cm-changedLine, & .cm-deletedChunk': {
        backgroundColor: `${del} !important`,
      },
      // Word-level emphasis on same-line edits only: a soft solid box, not the
      // default underline. Added span green; inline removed span red.
      '&.cm-merge-b .cm-changedText': {
        background: `${addWord} !important`,
        borderRadius: '2px',
      },
      '&.cm-merge-b .cm-deletedText': {
        background: `${delWord} !important`,
        borderRadius: '2px',
      },
    },
    { dark },
  );
}

// GitHub-dark tints (green #3fb950 / red #f85149) on the dark panel; slightly
// stronger GitHub-light tints (#2ea043 / #f85149) so they read on white.
const mergeThemeDark = makeMergeTheme(
  'rgba(63,185,80,0.13)',
  'rgba(63,185,80,0.30)',
  'rgba(248,81,73,0.13)',
  'rgba(248,81,73,0.30)',
  true,
);
const mergeThemeLight = makeMergeTheme(
  'rgba(46,160,67,0.15)',
  'rgba(46,160,67,0.35)',
  'rgba(248,81,73,0.15)',
  'rgba(248,81,73,0.35)',
  false,
);

// The full theme swap: syntax colors + diff tints. In light, oneDark is dropped
// so `basicSetup`'s bundled `defaultHighlightStyle` (a light palette) shows
// through. The `{dark}` flag on the merge theme matters beyond the tints — it
// is what tells CodeMirror which base palette to use for selection etc., so it
// must never claim `dark: true` while the site is light.
const themeExtensions = (dark: boolean): Extension =>
  dark ? [oneDark, mergeThemeDark] : [mergeThemeLight];

export function DiffEditor({
  path,
  original,
  value,
  sideBySide,
  wrap = true,
  onChange,
  onSave,
  initialScrollLine,
  initialScrollOffset,
  onScrollAnchor,
  onDiffNav,
}: DiffEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // The disposable surface: an EditorView (inline) or a MergeView (side-by-side).
  const surfaceRef = useRef<EditorView | MergeView | null>(null);
  // The editable EditorView we sync `value` into and read edits from — the
  // inline view itself, or the right pane (`b`) of a MergeView.
  const editableRef = useRef<EditorView | null>(null);
  // Latest callbacks, read through refs so the surface is created once per
  // (path, sideBySide, original) rather than recreated on every parent render.
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  const onScrollAnchorRef = useRef(onScrollAnchor);
  const onDiffNavRef = useRef(onDiffNav);
  const initialAnchorRef = useRef({ line: initialScrollLine, offset: initialScrollOffset });
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;
  onScrollAnchorRef.current = onScrollAnchor;
  onDiffNavRef.current = onDiffNav;
  initialAnchorRef.current = { line: initialScrollLine, offset: initialScrollOffset };

  // Last chunk count published to the toolbar, so an edit that doesn't change
  // the number of chunks doesn't re-render the panel. Reset to -1 per surface
  // (in the effect) so the first publish always fires.
  const lastNavCountRef = useRef(-1);
  // The surface is built once per (path, layout, baseline) and re-themed in
  // place (effect below), so the create-effect reads the palette straight off
  // <html> rather than through this state — no first-frame flash of the wrong
  // syntax colors. The MergeView's two panes are separate EditorStates, so each
  // needs its own compartment.
  const isDark = useIsDarkTheme();
  const themeCompA = useRef(new Compartment());
  const themeCompB = useRef(new Compartment());
  // Run a chunk-navigation command against the editable pane and refocus it so
  // the moved selection is visible. Stable — reads the view through its ref.
  const runChunkCommand = useCallback((cmd: StateCommand) => {
    const view = editableRef.current;
    if (!view) return;
    cmd({ state: view.state, dispatch: (tr) => view.dispatch(tr) });
    view.focus();
  }, []);
  const goNext = useCallback(() => runChunkCommand(goToNextChunk), [runChunkCommand]);
  const goPrev = useCallback(() => runChunkCommand(goToPreviousChunk), [runChunkCommand]);

  // Recreate the surface on file identity, layout mode, or a new baseline (HEAD
  // moved). `value`/`wrap` updates are applied live by the sync effect below,
  // so typing never rebuilds the editor.
  useEffect(() => {
    const parent = containerRef.current;
    if (!parent) return;
    const lang = languageExtensionForPath(path);
    lastNavCountRef.current = -1;
    // Publishes the nav handle + current chunk count to the toolbar (deduped on
    // count so a no-op edit doesn't churn the panel). `getChunks` is non-null
    // immediately for both the unified and side-by-side surfaces.
    const reportNav = () => {
      const view = editableRef.current;
      if (!view) return;
      const count = getChunks(view.state)?.chunks.length ?? 0;
      if (count === lastNavCountRef.current) return;
      lastNavCountRef.current = count;
      onDiffNavRef.current?.({ next: goNext, prev: goPrev, count });
    };
    // Center the first changed chunk (and drop the caret there) on a fresh open.
    const jumpToFirstChange = (view: EditorView) => {
      const chunks = getChunks(view.state)?.chunks;
      if (!chunks || chunks.length === 0) return;
      const pos = Math.min(chunks[0].fromB, view.state.doc.length);
      view.dispatch({
        selection: { anchor: pos },
        effects: EditorView.scrollIntoView(pos, { y: 'center' }),
      });
    };
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
      // Editing can add/remove whole chunks — keep the toolbar's count current.
      // Runs for external reloads too (before the echo guard below).
      reportNav();
      if (u.transactions.some((tr) => tr.annotation(External))) return;
      onChangeRef.current(u.state.doc.toString());
    });
    const wrapExt: Extension = wrap ? EditorView.lineWrapping : [];
    const editableExtensions: Extension[] = [
      saveKeymap, // highest precedence so Cmd/Ctrl+S is ours, not the browser's
      keymap.of([indentWithTab]),
      basicSetup,
      themeCompB.current.of(themeExtensions(resolvedThemeNow() === 'dark')),
      baseTheme,
      lang ?? [],
      wrapExt,
      updateListener,
    ];

    if (sideBySide) {
      const merge = new MergeView({
        parent,
        orientation: 'a-b',
        // Off: side-by-side can't cheaply tell a pure inserted/deleted line from
        // a same-line edit, so word-level boxes there would just double up the
        // line background. The two columns already show what changed.
        highlightChanges: false,
        // No change gutter — the 3px colored bar at the line start reads as
        // noise; the line tints already mark the changes.
        gutter: false,
        a: {
          doc: original,
          extensions: [
            EditorState.readOnly.of(true),
            EditorView.editable.of(false),
            basicSetup,
            themeCompA.current.of(themeExtensions(resolvedThemeNow() === 'dark')),
            baseTheme,
            lang ?? [],
            wrapExt,
          ],
        },
        b: {
          doc: value,
          extensions: editableExtensions,
        },
      });
      surfaceRef.current = merge;
      editableRef.current = merge.b;
    } else {
      const view = new EditorView({
        parent,
        state: EditorState.create({
          doc: value,
          extensions: [
            ...editableExtensions,
            // The modified doc is the editor's document; deletions from
            // `original` render inline. `mergeControls` (accept/reject widget)
            // and the change `gutter` (3px bar) are off. `highlightChanges:false`
            // drops the redundant full-line word box on pure add/delete lines
            // while the unified view keeps the word-level marks on genuine
            // same-line edits (see mergeTheme).
            unifiedMergeView({
              original,
              mergeControls: false,
              gutter: false,
              highlightChanges: false,
            }),
          ],
        }),
      });
      surfaceRef.current = view;
      editableRef.current = view;
    }

    // Scroll memory over the editable (working) pane — its lines are the file's
    // lines, so the anchor is shared with the plain editor. Restore on mount,
    // then report the top anchor (debounced) and flush on teardown.
    const editable = editableRef.current;
    let scrollTimer: ReturnType<typeof setTimeout> | undefined;
    const report = () => {
      if (!editableRef.current) return;
      const a = topAnchor(editableRef.current);
      onScrollAnchorRef.current?.(path, a.line, a.offset);
    };
    const handleScroll = () => {
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(report, SCROLL_PERSIST_MS);
    };
    if (editable) {
      const init = initialAnchorRef.current;
      if (init.line && init.line > 1) {
        // A remembered mid-file position wins — don't yank the user off it.
        scrollToAnchor(editable, { line: init.line, offset: init.offset ?? 0 });
      } else {
        // Fresh open (top-of-file / no memory): land on the first change so the
        // diff opens where the edits are, not at an unchanged file head.
        jumpToFirstChange(editable);
      }
      editable.scrollDOM.addEventListener('scroll', handleScroll, { passive: true });
    }
    // Hand the nav controls (and initial chunk count) to the toolbar.
    reportNav();

    return () => {
      clearTimeout(scrollTimer);
      if (editable) {
        editable.scrollDOM.removeEventListener('scroll', handleScroll);
        report();
      }
      onDiffNavRef.current?.(null);
      surfaceRef.current?.destroy();
      surfaceRef.current = null;
      editableRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, sideBySide, original]);

  // Re-theme both panes in place when the site theme flips.
  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const ext = themeExtensions(isDark);
    if (surface instanceof MergeView) {
      surface.a.dispatch({ effects: themeCompA.current.reconfigure(ext) });
      surface.b.dispatch({ effects: themeCompB.current.reconfigure(ext) });
    } else {
      surface.dispatch({ effects: themeCompB.current.reconfigure(ext) });
    }
  }, [isDark]);

  // Apply external `value` changes (e.g. reload-from-disk) to the live doc
  // without resetting cursor/undo and without echoing back through onChange.
  useEffect(() => {
    const view = editableRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (value === current) return;
    view.dispatch({
      changes: { from: 0, to: current.length, insert: value },
      annotations: External.of(true),
    });
  }, [value]);

  return <div ref={containerRef} className="h-full w-full overflow-hidden" />;
}

export default DiffEditor;
