// Same look as the chat scroller (see app/dashboard/agents/[instanceId]/page.tsx).
// Defined here so vertical + horizontal scrollers across the panel stay consistent.
export const SCROLL_STYLE =
  '[&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar]:h-2 ' +
  '[&::-webkit-scrollbar-track]:bg-transparent ' +
  '[&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full ' +
  'dark:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/20';

/** The panel's surface, as a CSS value. Follows the site theme: `--panel` is
 *  #171717 in dark (what the panel used to hard-code) and white in light. Used
 *  by the CodeMirror editors and the commit graph, which need a real color
 *  string rather than a Tailwind class; JSX should prefer `bg-panel`. */
export const PANEL_BG = 'hsl(var(--panel))';

/** The panel's dropdown/menu surface — the shared `--menu` token (#2D2D2D in
 *  dark, white in light), so the panel's hand-positioned menus match the rest
 *  of the app's overlays. */
export const DROPDOWN_BG = 'hsl(var(--menu))';

// Scrollbar styling for the panel's CodeMirror surfaces (plain editor, markdown
// live editor, and both diff panels), matching the site-wide `.custom-scrollbar`
// (app/globals.css): thin 6px, transparent track, rounded, brighten on hover.
// The thumb is keyed off `--muted-foreground` at low opacity rather than
// `--border`: `--border` is near-white in light and would flare against the
// dark panel, whereas `--muted-foreground` reads on both surfaces. Spread
// `CM_SCROLLBAR_WEBKIT` into an `EditorView.theme` object and merge
// `CM_SCROLLBAR_FIREFOX` into that theme's `.cm-scroller` block. Kept here so the
// three editors can't drift apart.
export const CM_SCROLLBAR_WEBKIT = {
  '.cm-scroller::-webkit-scrollbar': { width: '6px', height: '6px' },
  '.cm-scroller::-webkit-scrollbar-track': { background: 'transparent' },
  '.cm-scroller::-webkit-scrollbar-thumb': {
    backgroundColor: 'hsl(var(--muted-foreground) / 0.3)',
    borderRadius: '3px',
  },
  '.cm-scroller::-webkit-scrollbar-thumb:hover': {
    backgroundColor: 'hsl(var(--muted-foreground) / 0.5)',
  },
};

/** Firefox scrollbar props — merge into each editor theme's `.cm-scroller`
 *  block (can't live in {@link CM_SCROLLBAR_WEBKIT}, which would clobber the
 *  scroller's font rules on spread). */
export const CM_SCROLLBAR_FIREFOX = {
  scrollbarWidth: 'thin',
  scrollbarColor: 'hsl(var(--muted-foreground) / 0.3) transparent',
};

// The tab strip overflows horizontally when there are many tabs; keep its
// scrollbar extra-thin (3px) so it doesn't eat into the compact tab row. Firefox
// gets `scrollbar-width: none` — its thin bar still reserves too much height in
// the short strip; the tabs remain wheel/trackpad-scrollable.
export const TAB_SCROLL_STYLE =
  '[&::-webkit-scrollbar]:h-[3px] ' +
  '[&::-webkit-scrollbar-track]:bg-transparent ' +
  '[&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full ' +
  'dark:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/20 ' +
  '[scrollbar-width:none]';
