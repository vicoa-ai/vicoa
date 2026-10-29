'use client';

// A markdown field you edit as rendered text: no source view and no
// read/edit swap. The rendered document is the editor (Tiptap, i.e.
// ProseMirror), so clicking into it puts the caret where you clicked and
// nothing moves. Markdown is only the storage format: read in on mount and
// whenever the stored value changes while you aren't editing, written out
// (see markdown-codec) when an edit ends.
//
// An edit ends on blur, ⌘/Ctrl+Enter, or unmount, and is reported only if the
// markdown changed, so focusing and leaving never writes, and a description
// nobody edited is never rewritten in the serializer's style. Escape puts
// back what was there.
//
// `@` files and `/` skills come from the same hooks and panels as the task
// dialog's MentionPromptField, and `#` references from the chat composer's;
// trigger-suggestions only finds the trigger. A picked reference is written
// as a link to its page (lib/reference-links), since stored text has nowhere
// else to keep the id.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import { EditorContent, useEditor, type Editor } from '@tiptap/react';
import { Placeholder } from '@tiptap/extensions';
import 'highlight.js/styles/atom-one-dark.css';
import './rich-markdown.css';

import { FileMentionSuggestions } from '@/components/dashboard/file-mention-suggestions';
import { ReferenceSuggestions } from '@/components/dashboard/reference-suggestions';
import { SlashCommandSuggestions } from '@/components/dashboard/slash-command-suggestions';
import type { FileMention, ReferenceCandidate, ReferenceKind } from '@/lib/backend-api';
import type { SlashCommand } from '@/lib/constants/slash-commands';
import { matchFileMentions, searchableFileMentions } from '@/lib/file-mention-match';
import { useFileMentions } from '@/lib/hooks/use-file-mentions';
import { useReferenceCandidates } from '@/lib/hooks/use-references';
import { useSlashCommands } from '@/lib/hooks/use-slash-commands';
import type { ProjectMentionTarget } from '@/lib/project-mention-target';
import { isReferenceHref, referenceHref } from '@/lib/reference-links';
import { commandInsertText, slashCommandMatches } from '@/lib/slash-command-utils';
import { cn } from '@/lib/utils';

import { markdownExtensions } from './extensions';
import { MarkdownClipboard } from './markdown-clipboard';
import { prepareMarkdown, serializeMarkdown } from './markdown-codec';
import { triggerSuggestions, type ActiveTrigger, type TriggerBridge, type TriggerKind } from './trigger-suggestions';

/** Keep in sync with the panels' `max-h-[320px]` class. */
const PANEL_MAX_HEIGHT = 320;

/** Only web and mail links leave the app; a relative path has nowhere to go. */
const OPENABLE_HREF = /^(https?:|mailto:)/i;

export interface RichMarkdownEditorProps {
  /** The stored markdown, '' for none. */
  value: string;
  /** The edited markdown, trimmed, when an edit ends with a change. */
  onCommit: (markdown: string) => void;
  editable: boolean;
  /** Shown in an empty field while it is editable. */
  placeholder?: string;
  /** Classes for the editable element itself: padding here is still a place
   *  to click into, where padding on a wrapper would be dead space. */
  contentClassName?: string;
  /** Where `@` searches. Without one, `@` is just a character. */
  mentionTarget?: ProjectMentionTarget;
  /** Turn on `#` references (sessions, tasks, automations). */
  referencesEnabled?: boolean;
  /** The thing this field describes, left out of its own `#` list. */
  referenceSelf?: { kind: ReferenceKind; id: string };
  onFocusChange?: (focused: boolean) => void;
  className?: string;
}

type PanelItems =
  | { kind: 'file'; items: FileMention[] }
  | { kind: 'command'; items: SlashCommand[] }
  | { kind: 'reference'; items: ReferenceCandidate[] };

type PanelItem = PanelItems['items'][number];

export function RichMarkdownEditor({
  value,
  onCommit,
  editable,
  placeholder,
  contentClassName,
  mentionTarget,
  referencesEnabled = false,
  referenceSelf,
  onFocusChange,
  className,
}: RichMarkdownEditorProps) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // The stored value the document was last built from, and that document
  // serialized: an edit has changed something iff serializing now differs
  // from `baseline`. Comparing against `value` instead would count the
  // serializer's own normalizing (`*` bullets become `-`) as an edit.
  const adoptedRef = useRef(value);
  const baselineRef = useRef<string | null>(null);
  // A newer stored value that arrived mid-edit, adopted when the edit ends
  // without a change of its own.
  const incomingRef = useRef<string | null>(null);

  const [focused, setFocused] = useState(false);
  const [trigger, setTrigger] = useState<ActiveTrigger | null>(null);
  // The plugin reports synchronously and a pick reads it at once, ahead of
  // the re-render that `trigger` waits for.
  const triggerRef = useRef<ActiveTrigger | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // ── Picker data ────────────────────────────────────────────────────────
  const { files, refresh: refreshFiles } = useFileMentions({
    projectPath: mentionTarget?.path,
    machineId: mentionTarget?.machineId,
    enabled: editable && !!mentionTarget,
  });
  const searchableFiles = useMemo(() => searchableFileMentions(files), [files]);
  // As in MentionPromptField: no `machine`, so the live scan isn't gated on
  // capability metadata the daemon doesn't reliably persist.
  const { commands } = useSlashCommands({
    agentType: 'claude',
    machineId: mentionTarget?.machineId,
    projectPath: mentionTarget?.path,
    enabled: editable,
  });
  // `#` rows come from the server per query (debounced), not a local index.
  const referenceQuery = focused && trigger?.kind === 'reference' ? trigger.query : null;
  const {
    items: referenceRows,
    isLoading: referencesLoading,
    unavailable: referencesUnavailable,
  } = useReferenceCandidates({ query: referenceQuery, enabled: editable && referencesEnabled });
  const references = useMemo(
    () =>
      referenceSelf
        ? referenceRows.filter((r) => !(r.kind === referenceSelf.kind && r.id === referenceSelf.id))
        : referenceRows,
    [referenceRows, referenceSelf],
  );
  const referencesOn = editable && referencesEnabled && !referencesUnavailable;

  // The plugin asks "anything to list?" on every transaction inside a trigger,
  // and the panel asks again to render: answer both from one cached match.
  const matchCacheRef = useRef<{
    key: string;
    files: FileMention[];
    commands: SlashCommand[];
    references: ReferenceCandidate[];
    result: PanelItems;
  } | null>(null);
  const match = useCallback(
    (kind: TriggerKind, query: string): PanelItems => {
      const key = `${kind}\0${query}`;
      const cached = matchCacheRef.current;
      if (
        cached &&
        cached.key === key &&
        cached.files === searchableFiles &&
        cached.commands === commands &&
        cached.references === references
      ) {
        return cached.result;
      }
      // `#` rows already answer the current query (the server matched them).
      const result: PanelItems =
        kind === 'file'
          ? { kind, items: mentionTarget ? matchFileMentions(searchableFiles, query) : [] }
          : kind === 'command'
            ? { kind, items: commands.filter((cmd) => slashCommandMatches(cmd, query)) }
            : { kind, items: references };
      matchCacheRef.current = { key, files: searchableFiles, commands, references, result };
      return result;
    },
    [searchableFiles, commands, references, mentionTarget],
  );

  const panel = trigger && focused ? match(trigger.kind, trigger.query) : null;
  // The `#` panel shows while it searches and when nothing matches, as in chat.
  const panelOpen = !!panel && (panel.kind === 'reference' || panel.items.length > 0);

  // ── Plugin ↔ React ─────────────────────────────────────────────────────
  // The extension is built once with the editor; it reaches the current
  // render's state through this ref.
  const latest = useRef({ editable, match, panel, panelOpen, selectedIndex, referencesOn });
  useLayoutEffect(() => {
    latest.current = { editable, match, panel, panelOpen, selectedIndex, referencesOn };
  });

  const pick = useCallback((editor: Editor, item: PanelItem) => {
    const active = triggerRef.current;
    if (!active) return;
    const { doc } = editor.state;
    const next = doc.textBetween(active.range.to, Math.min(active.range.to + 1, doc.content.size), '\n');
    const space = /^\s/.test(next) ? [] : [{ type: 'text', text: ' ' }];
    if (active.kind === 'reference') {
      const ref = item as ReferenceCandidate;
      editor
        .chain()
        .focus()
        .insertContentAt(active.range, [
          {
            type: 'text',
            text: `#${ref.token}`,
            marks: [{ type: 'link', attrs: { href: referenceHref(ref.kind, ref.id) } }],
          },
          ...space,
        ])
        .run();
      return;
    }
    const text = active.kind === 'file' ? `@${(item as FileMention).path}` : commandInsertText(item as SlashCommand);
    editor
      .chain()
      .focus()
      .insertContentAt(active.range, [{ type: 'text', text }, ...space])
      .run();
  }, []);

  const editorRef = useRef<Editor | null>(null);
  const bridge = useMemo<TriggerBridge>(
    () => ({
      shouldOpen: (kind, query) =>
        kind === 'reference'
          ? latest.current.referencesOn
          : latest.current.editable && latest.current.match(kind, query).items.length > 0,
      onChange: (kind, next) => {
        const current = triggerRef.current;
        // Two plugins, one panel: an exit from the one that isn't showing
        // must not close the one that is.
        if (next === null && current?.kind !== kind) return;
        if (next && (current?.kind !== next.kind || current.query !== next.query)) setSelectedIndex(0);
        triggerRef.current = next;
        setTrigger(next);
      },
      onKeyDown: (event) => {
        const { panel: open, selectedIndex: index } = latest.current;
        const editor = editorRef.current;
        // Without rows the keys keep their usual meaning (an empty `#` panel
        // only says "no matches"); Escape still closes it, in the plugin.
        if (!open || open.items.length === 0 || !editor) return event.key === 'Escape';
        const count = open.items.length;
        if (event.key === 'ArrowDown') {
          setSelectedIndex((index + 1) % count);
          return true;
        }
        if (event.key === 'ArrowUp') {
          setSelectedIndex((index - 1 + count) % count);
          return true;
        }
        const plainEnter = event.key === 'Enter' && !event.shiftKey && !event.metaKey && !event.ctrlKey;
        if (plainEnter || event.key === 'Tab') {
          const item = open.items[Math.min(index, count - 1)];
          if (item) pick(editor, item);
          return true;
        }
        // Escape closes the panel (the plugin exits itself after this) and
        // must not also throw the edit away.
        return event.key === 'Escape';
      },
    }),
    [pick],
  );

  // ── Editing lifecycle ──────────────────────────────────────────────────
  const onCommitRef = useRef(onCommit);
  const onFocusChangeRef = useRef(onFocusChange);
  const placeholderRef = useRef(placeholder ?? '');
  const routerRef = useRef(router);
  useLayoutEffect(() => {
    onCommitRef.current = onCommit;
    onFocusChangeRef.current = onFocusChange;
    placeholderRef.current = placeholder ?? '';
    routerRef.current = router;
  });

  const adopt = useCallback((editor: Editor, markdown: string) => {
    editor
      .chain()
      // A stored value arriving is not something to undo back out of.
      .command(({ tr }) => {
        tr.setMeta('addToHistory', false);
        return true;
      })
      .setContent(prepareMarkdown(markdown), { contentType: 'markdown', emitUpdate: false })
      .run();
    adoptedRef.current = markdown;
    baselineRef.current = serializeMarkdown(editor);
    incomingRef.current = null;
  }, []);

  /** End an edit: report it if it changed anything, else take any newer value. */
  const commit = useCallback(
    (editor: Editor) => {
      // No baseline yet means no editor content to compare: nothing to end.
      if (editor.isDestroyed || !latest.current.editable || baselineRef.current === null) return;
      const markdown = serializeMarkdown(editor);
      if (markdown !== baselineRef.current) {
        // Last write wins, as it did with the textarea: this edit replaces a
        // value that changed underneath it.
        adoptedRef.current = markdown;
        baselineRef.current = markdown;
        incomingRef.current = null;
        onCommitRef.current(markdown);
        return;
      }
      if (incomingRef.current !== null) adopt(editor, incomingRef.current);
    },
    [adopt],
  );

  // Built once: useEditor only reads extensions at creation, and fresh option
  // objects each render would make it re-apply props it already has.
  const [extensions] = useState(() => [
    ...markdownExtensions(),
    MarkdownClipboard,
    triggerSuggestions(bridge),
    // Read at draw time: the hint can change after mount (the `@` part
    // waits for the project's folder to load).
    Placeholder.configure({ placeholder: () => placeholderRef.current }),
  ]);
  const [initialContent] = useState(() => prepareMarkdown(value));
  const editor = useEditor({
    // Only rendered on the client after the task loads, never during SSR, so
    // there is no server markup to hydrate against; creating the editor on
    // the first render avoids an empty frame before the text appears.
    immediatelyRender: true,
    editable,
    content: initialContent,
    contentType: 'markdown',
    extensions,
    editorProps: {
      attributes: { class: cn('rich-markdown-content', contentClassName) },
      handleKeyDown: (_view, event) => {
        const current = editorRef.current;
        if (!current) return false;
        // ⌘/Ctrl+Enter ends the edit, panel or not. (It would otherwise be
        // the hard-break shortcut; Shift+Enter still is.)
        if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
          current.commands.blur();
          return true;
        }
        // An open panel owns the rest of its keys (its plugin runs next).
        if (latest.current.panelOpen) return false;
        if (event.key === 'Escape') {
          adopt(current, incomingRef.current ?? adoptedRef.current);
          current.commands.blur();
          return true;
        }
        return false;
      },
      handleDOMEvents: {
        // ⌘/Ctrl-mousedown is ProseMirror's "select this node" gesture (and
        // would focus and move the caret); on a link it means "follow", so
        // ProseMirror doesn't see it at all and the click below does the rest.
        mousedown: (view, event) => {
          if (!view.editable || !(event.metaKey || event.ctrlKey)) return false;
          if (!(event.target as HTMLElement | null)?.closest('a')) return false;
          event.preventDefault();
          return true;
        },
        // Editing, a click places the caret and ⌘/Ctrl-click follows the link;
        // read-only, a click follows it. A `#` reference navigates in the app
        // (a new tab would hand it to the OS browser on desktop); a web or mail
        // link opens in a new tab; anything else (a relative path) has no page.
        click: (view, event) => {
          const anchor = (event.target as HTMLElement | null)?.closest('a');
          if (!anchor) return false;
          if (view.editable && !event.metaKey && !event.ctrlKey) return false;
          event.preventDefault();
          const href = anchor.getAttribute('href') ?? '';
          if (isReferenceHref(href)) routerRef.current.push(href);
          else if (OPENABLE_HREF.test(href)) window.open(href, '_blank', 'noopener,noreferrer');
          return true;
        },
      },
    },
    // A change with the editor unfocused (a task checkbox ticked from outside
    // an edit) has no blur coming to end it, so it ends here.
    onUpdate: ({ editor: updated }) => {
      if (!updated.isFocused) commit(updated);
    },
    onFocus: () => {
      setFocused(true);
      onFocusChangeRef.current?.(true);
    },
    onBlur: ({ editor: blurred }) => {
      commit(blurred);
      setFocused(false);
      onFocusChangeRef.current?.(false);
    },
  });
  // The baseline is taken as soon as the instance exists, not in onCreate:
  // Tiptap emits that a tick after construction, and an update or an unmount
  // in between (React runs effects twice in development) would compare the
  // untouched text against nothing and save it as an edit.
  useLayoutEffect(() => {
    editorRef.current = editor;
    if (editor && !editor.isDestroyed) baselineRef.current = serializeMarkdown(editor);
  }, [editor]);

  // The file index can land after `@` was typed (the live daemon lookup has to
  // time out first when the machine is away). The pickers only re-check on a
  // transaction, so send an empty one, or the panel stays shut until the next
  // keystroke.
  useEffect(() => {
    if (editor && !editor.isDestroyed && editor.isFocused) editor.view.dispatch(editor.state.tr);
  }, [editor, searchableFiles, commands]);

  // Placeholders are decorations, redrawn on a transaction: send an empty one.
  useEffect(() => {
    if (editor && !editor.isDestroyed) editor.view.dispatch(editor.state.tr);
  }, [editor, placeholder]);

  // `editable` can arrive after mount (the project role loads separately), and
  // useEditor only reads it at creation.
  useEffect(() => {
    if (editor && editor.isEditable !== editable) editor.setEditable(editable);
  }, [editor, editable]);

  // A stored value changed: adopt it now, or once the edit in progress ends.
  useEffect(() => {
    if (!editor || value === adoptedRef.current) return;
    incomingRef.current = value;
    if (!editor.isFocused) adopt(editor, value);
  }, [editor, value, adopt]);

  // Leaving the page mid-edit is the end of that edit, not a discard. By now
  // the DOM is detached (so no blur, and no focus to ask about), but the
  // editor outlives this cleanup by a tick: useEditor defers its destroy.
  // commit() is a no-op when nothing changed.
  useEffect(() => {
    if (!editor) return;
    return () => commit(editor);
  }, [editor, commit]);

  // First `@` of this mount: refresh the index in the background, like
  // MentionTextarea, so files an agent just created show up next time.
  const refreshedRef = useRef(false);
  useEffect(() => {
    if (trigger?.kind !== 'file' || refreshedRef.current) return;
    refreshedRef.current = true;
    refreshFiles();
  }, [trigger?.kind, refreshFiles]);

  // ⌘/Ctrl held while editing turns links into pointers: the one cue that a
  // click will now follow them instead of placing the caret.
  const [followLinks, setFollowLinks] = useState(false);
  useEffect(() => {
    if (!editable) return;
    const sync = (event: KeyboardEvent) => setFollowLinks(event.metaKey || event.ctrlKey);
    const clear = () => setFollowLinks(false);
    window.addEventListener('keydown', sync);
    window.addEventListener('keyup', sync);
    window.addEventListener('blur', clear);
    return () => {
      window.removeEventListener('keydown', sync);
      window.removeEventListener('keyup', sync);
      window.removeEventListener('blur', clear);
    };
  }, [editable]);

  // ── Panel placement ────────────────────────────────────────────────────
  // Full width of the field, on the trigger's line: above it when there is
  // room, else below (MentionPromptField's rule).
  const [panelStyle, setPanelStyle] = useState<CSSProperties>();
  useLayoutEffect(() => {
    if (!panelOpen) return;
    const measure = () => {
      const box = containerRef.current?.getBoundingClientRect();
      const caret = triggerRef.current?.clientRect();
      if (!box || !caret) return;
      const spaceAbove = caret.top;
      const openDown = spaceAbove < PANEL_MAX_HEIGHT + 16;
      setPanelStyle({
        left: box.left,
        width: box.width,
        maxHeight: Math.max(
          120,
          Math.min(PANEL_MAX_HEIGHT, (openDown ? window.innerHeight - caret.bottom : spaceAbove) - 16),
        ),
        ...(openDown ? { top: caret.bottom + 8 } : { bottom: window.innerHeight - caret.top + 8 }),
      });
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [panelOpen, trigger]);

  useEffect(() => {
    if (!panelOpen || !listRef.current) return;
    const row = listRef.current.children[selectedIndex] as HTMLElement | undefined;
    row?.scrollIntoView({ block: 'nearest' });
  }, [panelOpen, selectedIndex]);

  return (
    <div
      ref={containerRef}
      className={cn('rich-markdown font-mono', followLinks && 'rich-markdown-follow-links', className)}
    >
      <EditorContent editor={editor} />
      {panelOpen && editor && (
        // Rows are chosen with the editor still focused: a mousedown that
        // moved focus to the panel would end the edit (and save it) first.
        <div onMouseDown={(e) => e.preventDefault()}>
          {panel.kind === 'reference' ? (
            // Same panel box as the textarea composers' portalled `#` panel.
            createPortal(
              <div
                style={panelStyle}
                className="fixed z-50 max-h-[320px] overflow-y-auto rounded-lg border border-border bg-popover shadow-lg custom-scrollbar"
              >
                <ReferenceSuggestions
                  items={panel.items}
                  selectedIndex={selectedIndex}
                  isLoading={referencesLoading}
                  onSelect={(item) => pick(editor, item)}
                  onHover={setSelectedIndex}
                  listRef={listRef}
                />
              </div>,
              document.body,
            )
          ) : panel.kind === 'file' ? (
            <FileMentionSuggestions
              files={panel.items}
              selectedIndex={selectedIndex}
              listRef={listRef}
              onSelect={(file) => pick(editor, file)}
              onHover={setSelectedIndex}
              portal
              panelStyle={panelStyle}
            />
          ) : (
            <SlashCommandSuggestions
              commands={panel.items}
              selectedIndex={selectedIndex}
              listRef={listRef}
              onSelect={(cmd) => pick(editor, cmd)}
              onHover={setSelectedIndex}
              portal
              panelStyle={panelStyle}
            />
          )}
        </div>
      )}
    </div>
  );
}
