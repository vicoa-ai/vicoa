import type { AnyExtension } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from '@tiptap/markdown';
import { Image } from '@tiptap/extension-image';
import { TaskItem, TaskList } from '@tiptap/extension-list';
import { Table, TableCell, TableHeader, TableRow } from '@tiptap/extension-table';
import { CodeBlockLowlight } from '@tiptap/extension-code-block-lowlight';
import { common, createLowlight } from 'lowlight';

// One lowlight for every editor: it is a registry of grammars, not state.
// `common` is the same ~35-language set rehype-highlight registers for
// MessageMarkdown, so a fenced block is coloured the same in a comment and in
// the description it was pasted from.
const lowlight = createLowlight(common);

/**
 * The document schema + markdown codec shared by the editor and its tests.
 *
 * Every node here has to survive markdown → document → markdown, because the
 * column stores markdown and agents read it raw. That rules out what markdown
 * cannot write down: Underline (StarterKit turns it on, and ⌘U would produce a
 * mark that serializes as HTML or not at all) and table cell merging.
 */
export function markdownExtensions(): AnyExtension[] {
  return [
    StarterKit.configure({
      underline: false,
      // Replaced by the lowlight variant below.
      codeBlock: false,
      link: {
        // Clicking places the caret; opening is ⌘/Ctrl-click (see the editor).
        openOnClick: false,
        autolink: true,
        linkOnPaste: true,
      },
    }),
    CodeBlockLowlight.configure({ lowlight }),
    // Inline, because a markdown image is: `see ![x](y) here` is one line.
    Image.configure({ inline: true }),
    TaskList,
    TaskItem.configure({ nested: true }),
    Table.configure({ resizable: false }),
    TableRow,
    TableHeader,
    TableCell,
    Markdown,
  ];
}
