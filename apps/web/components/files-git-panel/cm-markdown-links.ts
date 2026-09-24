import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import { StateEffect, StateField } from '@codemirror/state';
import type { EditorState, Extension } from '@codemirror/state';
import { Decoration, EditorView, ViewPlugin } from '@codemirror/view';
import type { DecorationSet } from '@codemirror/view';
import { isLinkModifierHeld } from '@/components/terminal-pane/terminal-links';
import { openExternalUrl } from '@/lib/open-external';

/**
 * Following links from the live-preview markdown editor: ⌘/Ctrl+click opens a
 * web link in the browser, exactly as the terminal pane does (see
 * components/terminal-pane/terminal-links.ts for why the modifier is required
 * and why the open goes through `openExternalUrl` rather than `window.open`).
 *
 * A plain click must keep placing the cursor — that is how the live preview
 * reveals a construct's raw markdown for editing — so the modifier is what
 * separates "edit this link" from "follow this link".
 *
 * Only genuine web URLs are opened. A README's relative links point at files in
 * the repo, and handing those to the browser lands the user on the dashboard's
 * own origin (vicoa-ai/vicoa#46); they fall through to a normal click instead.
 */

/** The `@lezer/common` node type, reached through the tree rather than imported
 *  — the package is a transitive dependency, not one of ours. */
type SyntaxNode = ReturnType<ReturnType<typeof syntaxTree>['resolveInner']>;

/** Schemes that may be handed to the browser. `mailto:` included — a markdown
 *  `[me](mailto:…)` is a real link; everything else (relative paths, `file:`,
 *  and notably `javascript:`) is not followed. */
const OPENABLE = /^(?:https?|mailto):/i;

/** Markdown backslash escapes, which are literal characters in a destination. */
const ESCAPED_PUNCT = /\\([!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])/g;

/** How long a click may spend finishing the parse when resolving a reference
 *  link. Reference definitions collect at the bottom of a long README, past the
 *  region the lazy parser has reached. */
const REFERENCE_PARSE_BUDGET_MS = 50;

/** The class on the link under the modifier, styled by the theme below. */
const FOLLOW_CLASS = 'cm-md-follow';

/** A `<…>`-wrapped or escaped destination as the plain URL it stands for. */
function cleanDestination(raw: string): string {
  const trimmed = raw.trim();
  const unwrapped =
    trimmed.startsWith('<') && trimmed.endsWith('>') ? trimmed.slice(1, -1) : trimmed;
  return unwrapped.replace(ESCAPED_PUNCT, '$1');
}

/** A reference label normalised for matching: CommonMark compares labels
 *  case-insensitively with internal whitespace collapsed. */
function normalizeLabel(raw: string): string {
  const inner = raw.startsWith('[') && raw.endsWith(']') ? raw.slice(1, -1) : raw;
  return inner.trim().replace(/\s+/g, ' ').toLowerCase();
}

/** The destination a `Link`/`Autolink` node spells out inline, i.e. its
 *  `(url)` / `<url>` part. Null for a reference link, which names its
 *  destination elsewhere in the document. */
export function inlineDestination(state: EditorState, node: SyntaxNode): string | null {
  const url = node.getChild('URL');
  return url ? cleanDestination(state.doc.sliceString(url.from, url.to)) : null;
}

/** The label a reference link points at: its explicit `[label]`, or — for the
 *  collapsed `[text][]` and shortcut `[text]` forms — its own text. */
function referenceLabel(state: EditorState, link: SyntaxNode): string | null {
  const label = link.getChild('LinkLabel');
  if (label) {
    const normalized = normalizeLabel(state.doc.sliceString(label.from, label.to));
    if (normalized) return normalized;
  }
  const marks = link.getChildren('LinkMark');
  if (marks.length < 2) return null;
  const text = state.doc.sliceString(marks[0].to, marks[1].from);
  return normalizeLabel(text) || null;
}

/** The destination of the `[label]: url` definition matching `label`. */
function resolveReference(state: EditorState, label: string): string | null {
  const tree = ensureSyntaxTree(state, state.doc.length, REFERENCE_PARSE_BUDGET_MS) ??
    syntaxTree(state);
  let found: string | null = null;
  tree.iterate({
    enter: (node) => {
      if (found) return false;
      if (node.name !== 'LinkReference') return;
      const def = node.node;
      const defLabel = def.getChild('LinkLabel');
      const url = def.getChild('URL');
      if (!defLabel || !url) return false;
      if (normalizeLabel(state.doc.sliceString(defLabel.from, defLabel.to)) === label) {
        found = cleanDestination(state.doc.sliceString(url.from, url.to));
      }
      return false;
    },
  });
  return found;
}

/** A link in the document: where it points, and the text that stands for it. */
export interface MarkdownLink {
  url: string;
  from: number;
  to: number;
}

/** Walk out from `node` to the link construct containing it, and report where
 *  that link points. Null when the position isn't inside a link at all. */
function linkFromNode(state: EditorState, node: SyntaxNode): MarkdownLink | null {
  for (let n: SyntaxNode | null = node; n; n = n.parent) {
    // The raw destination itself — visible whenever the cursor has revealed a
    // link's source, and the whole node for a bare GFM autolink.
    if (n.name === 'URL') {
      return { url: cleanDestination(state.doc.sliceString(n.from, n.to)), from: n.from, to: n.to };
    }
    if (n.name === 'Link' || n.name === 'Autolink') {
      const inline = inlineDestination(state, n);
      const label = inline || n.name !== 'Link' ? null : referenceLabel(state, n);
      const url = inline ?? (label ? resolveReference(state, label) : null);
      return url ? { url, from: n.from, to: n.to } : null;
    }
    // An image's alt text is not a link (its URL text still is, above).
    if (n.name === 'Image') return null;
  }
  return null;
}

/** The markdown link at document position `pos`, or null. */
export function linkAt(state: EditorState, pos: number): MarkdownLink | null {
  const tree = syntaxTree(state);
  // Both sides of the position, so a click landing on either edge of a link
  // (its first or last character) still resolves to it.
  for (const side of [1, -1] as const) {
    const link = linkFromNode(state, tree.resolveInner(pos, side));
    if (link) return link;
  }
  return null;
}

/** Where the markdown link at `pos` points, or null. Exported for tests. */
export function destinationAt(state: EditorState, pos: number): string | null {
  return linkAt(state, pos)?.url ?? null;
}

/** {@link linkAt}, narrowed to the links we may hand to the browser. */
export function followableLinkAt(state: EditorState, pos: number): MarkdownLink | null {
  const link = linkAt(state, pos);
  return link && OPENABLE.test(link.url) ? link : null;
}

/** {@link followableLinkAt}'s destination alone. Exported for tests. */
export function followableUrlAt(state: EditorState, pos: number): string | null {
  return followableLinkAt(state, pos)?.url ?? null;
}

/** The link under the mouse, or null when the pointer isn't over one (or is
 *  past the end of a line, where `posAtCoords` reports no position). */
function linkAtEvent(view: EditorView, event: MouseEvent): MarkdownLink | null {
  const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
  return pos == null ? null : followableLinkAt(view.state, pos);
}

// ── The link under the modifier ──────────────────────────────────────────────

/** Marks the followable link the pointer is on while the modifier is held:
 *  underlined and under a hand, the way every editor says "this is now a
 *  link, not text". A decoration rather than a class on the editor, so the
 *  affordance covers exactly the link — including a bare URL, which carries no
 *  link styling of its own. */
const FOLLOW_MARK = Decoration.mark({ class: FOLLOW_CLASS });

const setFollowed = StateEffect.define<MarkdownLink | null>();

const followedLink = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(deco, tr) {
    for (const effect of tr.effects) {
      if (effect.is(setFollowed)) {
        return effect.value
          ? Decoration.set([FOLLOW_MARK.range(effect.value.from, effect.value.to)])
          : Decoration.none;
      }
    }
    // An edit can move or dissolve the link out from under the pointer; the
    // next mouse move puts it back if it is still there.
    return tr.docChanged ? Decoration.none : deco;
  },
  provide: (f) => EditorView.decorations.from(f),
});

/** The range currently marked, so a mouse move over the same link is not a
 *  transaction. */
function followedRange(state: EditorState): { from: number; to: number } | null {
  const iter = state.field(followedLink, false)?.iter();
  return iter?.value ? { from: iter.from, to: iter.to } : null;
}

function setFollowCursor(view: EditorView, link: MarkdownLink | null): void {
  const current = followedRange(view.state);
  if (current?.from === link?.from && current?.to === link?.to) return;
  view.dispatch({ effects: setFollowed.of(link) });
}

/**
 * Puts the caret cursor back when the modifier is released — on `window`, not
 * on the editor: a ⌘+click deliberately never focuses the editor, so a keyup
 * there lands on the document body and the editor would never hear it. `blur`
 * covers releasing the key after switching away from the window entirely.
 *
 * (Pressing the modifier doesn't light the hand up on its own; the hovered
 * position is only known from a mouse event, so `mousemove` is what sets it.)
 */
const followCursorReset = ViewPlugin.fromClass(
  class {
    private readonly onKeyUp: (event: KeyboardEvent) => void;
    private readonly onBlur: () => void;

    constructor(view: EditorView) {
      this.onKeyUp = (event) => {
        if (!isLinkModifierHeld(event)) setFollowCursor(view, null);
      };
      this.onBlur = () => setFollowCursor(view, null);
      window.addEventListener('keyup', this.onKeyUp);
      window.addEventListener('blur', this.onBlur);
    }

    destroy(): void {
      window.removeEventListener('keyup', this.onKeyUp);
      window.removeEventListener('blur', this.onBlur);
    }
  },
);

const followTheme = EditorView.theme({
  [`.${FOLLOW_CLASS}`]: {
    cursor: 'pointer',
    // The standing link look. A `[text](url)` link already wears it, so the
    // hand is its cue; a bare URL, which is only syntax-highlighted, turns
    // link-blue and underlined under the modifier.
    color: 'hsl(var(--info))',
    textDecoration: 'underline',
    textUnderlineOffset: '2px',
  },
  // …over the syntax theme's own colour, which sits on a span inside this one.
  [`.${FOLLOW_CLASS} span`]: { color: 'inherit' },
});

/**
 * ⌘/Ctrl+click a link in the live-preview markdown editor to open it in the
 * browser, with the pointer turning into a hand while the modifier is held over
 * one (the affordance every editor uses for this).
 */
export function markdownLinkOpener(): Extension {
  return [
    EditorView.domEventHandlers({
      mousedown(event, view) {
        // Left button only: middle-click pastes on Linux and right-click opens
        // the context menu.
        if (event.button !== 0 || !isLinkModifierHeld(event)) return false;
        const link = linkAtEvent(view, event);
        if (!link) return false;
        // Claim the click: unhandled, CodeMirror would add a second cursor.
        event.preventDefault();
        setFollowCursor(view, null);
        openExternalUrl(link.url);
        return true;
      },
      mousemove(event, view) {
        setFollowCursor(view, isLinkModifierHeld(event) ? linkAtEvent(view, event) : null);
        return false;
      },
      mouseleave(_event, view) {
        setFollowCursor(view, null);
        return false;
      },
    }),
    followedLink,
    followCursorReset,
    followTheme,
  ];
}
