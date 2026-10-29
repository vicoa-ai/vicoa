import { Extension, type Range } from '@tiptap/core';
import { PluginKey, type EditorState } from '@tiptap/pm/state';
import { Suggestion } from '@tiptap/suggestion';

// The `@` (files), `/` (skills) and `#` (references) pickers, as ProseMirror
// plugins that only detect the trigger. What a query matches and what the
// panel looks like stay in React, with the same hooks and panels the textarea
// composers use, so this side is just: where is the trigger, what has been
// typed after it, which keys does the open panel claim.

export type TriggerKind = 'file' | 'command' | 'reference';

export interface ActiveTrigger {
  kind: TriggerKind;
  /** What follows the trigger character, up to the caret. */
  query: string;
  /** The trigger character through the caret: what a pick replaces. */
  range: Range;
  /** Viewport rect of that run, read on demand so it follows scrolling. */
  clientRect: () => DOMRect | null;
}

export interface TriggerBridge {
  /** Should the trigger open? For `@` and `/`, only when there is something
   *  to list: a trigger with no rows is plain typing, the way the textarea
   *  composers treat it. `#` searches the server as you type, so it opens
   *  whenever references are available and says when nothing matches. */
  shouldOpen: (kind: TriggerKind, query: string) => boolean;
  onChange: (kind: TriggerKind, trigger: ActiveTrigger | null) => void;
  /** Keys while a panel is open; true when the panel used the key. */
  onKeyDown: (event: KeyboardEvent) => boolean;
}

// `#` and a heading don't collide: a heading is `#` then a space at the start
// of a line, which ends this trigger's token (it allows no spaces) and then
// lets the heading input rule fire; a reference is `#` then a name.
const TRIGGER_CHAR: Record<TriggerKind, string> = { file: '@', command: '/', reference: '#' };

/** Code is literal: `@` in an inline code span or a fenced block is text. */
function inCode(state: EditorState, pos: number): boolean {
  const $pos = state.doc.resolve(pos);
  return !!$pos.parent.type.spec.code || $pos.marks().some((mark) => !!mark.type.spec.code);
}

/** Already a link: a picked `#` reference is `#VIC-42` linked to its page, and
 *  putting the caret in it must not search for it all over again. */
function inLink(state: EditorState, range: Range): boolean {
  const link = state.schema.marks.link;
  return !!link && state.doc.rangeHasMark(range.from, range.to, link);
}

export function triggerSuggestions(bridge: TriggerBridge) {
  return Extension.create({
    name: 'triggerSuggestions',
    addProseMirrorPlugins() {
      return (Object.keys(TRIGGER_CHAR) as TriggerKind[]).map((kind) => {
        const char = TRIGGER_CHAR[kind];
        const report = (props: { query: string; range: Range; clientRect?: (() => DOMRect | null) | null }) =>
          bridge.onChange(kind, {
            kind,
            query: props.query,
            range: props.range,
            clientRect: props.clientRect ?? (() => null),
          });
        return Suggestion({
          editor: this.editor,
          pluginKey: new PluginKey(`trigger-${kind}`),
          char,
          // Start of a line, or after whitespace, like the textarea pickers;
          // so `src/app` and `a@b.c` never open anything.
          allowedPrefixes: [' ', '\n', '\t'],
          allow: ({ state, range }) =>
            !inCode(state, range.from) &&
            !inLink(state, range) &&
            bridge.shouldOpen(kind, state.doc.textBetween(range.from + char.length, range.to)),
          render: () => ({
            onStart: report,
            onUpdate: report,
            onExit: () => bridge.onChange(kind, null),
            onKeyDown: ({ event }) => bridge.onKeyDown(event),
          }),
        });
      });
    },
  });
}
