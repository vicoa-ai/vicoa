import React, { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import 'highlight.js/styles/atom-one-dark.css';
import { diffLineBackgroundClass, formatDiffLines, formatTaskNotifications, normalizeCommandOutput } from '@/components/ui/message-markdown-utils';
import { makeFindHighlightPlugin } from '@/lib/find-highlight';

interface MessageMarkdownProps {
  children: string;
  agentType?: 'claude' | 'codex' | 'opencode';
  /** When set, matches of this term are wrapped in `<mark class="find-hit">`. */
  highlightQuery?: string;
}

// Chat-message code is the one place that stays monospace after the app-wide
// Geist Sans font sweep. We pin it to Geist Mono explicitly (loaded in
// app/layout.tsx as --font-geist-mono) rather than the `font-mono` utility,
// because that utility / --font-mono token has been repointed to Geist Sans
// for the rest of the UI. See app/globals.css for the token decision.
const CHAT_CODE_FONT_FAMILY =
  'var(--font-geist-mono), ui-monospace, SFMono-Regular, Menlo, monospace';

function MessageMarkdownImpl({ children, agentType, highlightQuery }: MessageMarkdownProps) {
  // Plain alphabetic sentinel: hljs's markdown highlighter parses `__x__` as
  // bold and `_x_` as italic, which fragments the placeholder across multiple
  // text nodes and breaks restoreNode's string-replacement walk. Underscores
  // and other markdown-syntax characters must be avoided here.
  const codeFencePlaceholder = 'XCODEFENCEPLACEHOLDERX';
  const todoRegex = /([●◐○])([^\n]*)/g;

  const transformTodoLine = (line: string) => {
    return line.replace(todoRegex, (match, symbol, text) => {
      const trimmedText = text.trim();
      if (symbol === '●') {
        // Completed: checked box with strikethrough
        return `- [x] ~~${trimmedText}~~`;
      } else if (symbol === '◐') {
        // In-progress: unchecked box with bold text
        return `- [ ] **${trimmedText}**`;
      } else if (symbol === '○') {
        // Pending: unchecked box
        return `- [ ] ${trimmedText}`;
      }
      return match;
    });
  };

  const preprocessContent = (content: string) => {
    const lines = content.split('\n');
    let inFence = false;
    let fenceChar = '';
    let fenceLength = 0;
    let fenceInfoString = '';
    let innerFenceDepth = 0;
    let markdownOuterCloseIndex = -1;
    const output: string[] = [];

    const isMarkdownInfoString = (info: string) => {
      const firstWord = info.split(/\s+/)[0];
      return firstWord === 'markdown' || firstWord === 'md' || firstWord === 'mdown';
    };

    const findLastMatchingFence = (startIdx: number, char: string, len: number) => {
      for (let i = lines.length - 1; i > startIdx; i -= 1) {
        const m = lines[i].match(/^(\s*)(`{3,}|~{3,})(.*)$/);
        if (m && m[2][0] === char && m[2].length >= len) {
          return i;
        }
      }
      return -1;
    };

    for (let idx = 0; idx < lines.length; idx += 1) {
      const line = lines[idx];

      if (!inFence) {
        const openMatch = line.match(/^(\s*)(`{3,}|~{3,})(.*)$/);
        if (openMatch) {
          inFence = true;
          fenceChar = openMatch[2][0];
          fenceLength = openMatch[2].length;
          fenceInfoString = (openMatch[3] || '').trim().toLowerCase();
          innerFenceDepth = 0;
          markdownOuterCloseIndex = isMarkdownInfoString(fenceInfoString)
            ? findLastMatchingFence(idx, fenceChar, fenceLength)
            : -1;
          output.push(line);
          continue;
        }

        output.push(transformTodoLine(line));
        continue;
      }

      // Markdown-flavored outer fence: pin the close to the last matching fence in
      // the document. Every interior fence-shaped line is treated as content, so
      // ambiguous info-less ``` openings inside the markdown source don't get
      // misread as the outer close.
      if (markdownOuterCloseIndex !== -1) {
        if (idx === markdownOuterCloseIndex) {
          inFence = false;
          fenceChar = '';
          fenceLength = 0;
          fenceInfoString = '';
          markdownOuterCloseIndex = -1;
          output.push(line);
          continue;
        }

        const fenceMatch = line.match(/^(\s*)(`{3,}|~{3,})(.*)$/);
        if (
          fenceMatch &&
          fenceMatch[2][0] === fenceChar &&
          fenceMatch[2].length >= fenceLength
        ) {
          output.push(line.replace(/```/g, codeFencePlaceholder));
          continue;
        }

        output.push(line);
        continue;
      }

      const fenceMatch = line.match(/^(\s*)(`{3,}|~{3,})(.*)$/);
      if (fenceMatch) {
        const leadingWhitespace = fenceMatch[1] || '';
        const fence = fenceMatch[2];
        const fenceInfo = fenceMatch[3] || '';
        if (fence[0] === fenceChar && fence.length >= fenceLength) {
          // Inside a diff fence, lines with leading whitespace are diff context lines
          // (e.g. " ```bash" showing a code fence within the file being diffed).
          // Treat them as content so they don't prematurely close the outer fence.
          if (fenceInfoString.includes('diff') && leadingWhitespace.length > 0) {
            output.push(line.replace(/```/g, codeFencePlaceholder));
            continue;
          }

          if (fenceInfo.trim().length > 0) {
            innerFenceDepth += 1;
            output.push(line.replace(/```/g, codeFencePlaceholder));
            continue;
          }

          if (innerFenceDepth > 0) {
            innerFenceDepth -= 1;
            output.push(line.replace(/```/g, codeFencePlaceholder));
            continue;
          }

          inFence = false;
          fenceChar = '';
          fenceLength = 0;
          fenceInfoString = '';
          output.push(line);
          continue;
        }
      }

      if (fenceChar === '`') {
        output.push(line.replace(/```/g, codeFencePlaceholder));
      } else {
        output.push(line);
      }
    }

    return output.join('\n');
  };

  const transformedContent = preprocessContent(formatTaskNotifications(normalizeCommandOutput(children)));

  const restorePlaceholders = (value: string) => value.split(codeFencePlaceholder).join('```');

  const restoreNode = (node: React.ReactNode): React.ReactNode => {
    if (typeof node === 'string') return restorePlaceholders(node);
    if (Array.isArray(node)) return node.map((child) => restoreNode(child));
    if (React.isValidElement(node)) {
      const element = node as React.ReactElement<{ children?: React.ReactNode }>;
      const childNodes = element.props?.children;
      if (!childNodes) return element;
      const restoredChildren = restoreNode(childNodes);
      if (restoredChildren === childNodes) return element;
      return React.cloneElement(element, { children: restoredChildren });
    }
    return node;
  };

  const flattenText = (node: React.ReactNode): string => {
    if (typeof node === 'string' || typeof node === 'number') return String(node);
    if (Array.isArray(node)) return node.map(flattenText).join('');
    if (React.isValidElement(node)) {
      const element = node as React.ReactElement<{ children?: React.ReactNode }>;
      return flattenText(element.props?.children);
    }
    return '';
  };

  // A GFM task-list item counts as "in progress" only when its whole label is
  // bold — i.e. it came from the `◐ …` → `- [ ] **…**` transform above. A plain
  // `- [ ]` item that merely *starts* with a bold phrase (e.g. a checklist entry
  // written as "**HIGH —** rest of the sentence") must NOT get the in-progress
  // border. Decide from the hast node, not the rendered children: after dropping
  // the checkbox <input> and whitespace-only text, every remaining child has to
  // be a <strong>. Anything trailing it (text, `code`, *em*) means partial bold.
  const isEntirelyBoldTaskItem = (node: any): boolean => {
    const kids = (node?.children ?? []).filter(
      (child: any) =>
        !(child?.type === 'element' && child?.tagName === 'input') &&
        !(child?.type === 'text' && String(child?.value ?? '').trim() === ''),
    );
    return kids.length > 0 && kids.every((child: any) => child?.type === 'element' && child?.tagName === 'strong');
  };

  return (
    <div className="font-mono">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          [rehypeHighlight, { detect: true, ignoreMissing: true }],
          // Runs after syntax highlighting so prose text nodes are still whole
          // when we split them; a no-op when there's no active find query.
          ...(highlightQuery ? [makeFindHighlightPlugin(highlightQuery)] : []),
        ]}
        components={{
        h1: ({ children }) => (
          <h1 className="text-lg text-foreground mt-6 mb-6 first:mt-0">
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-base text-foreground mt-5 mb-5 first:mt-0">
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm text-foreground mt-5 mb-5 first:mt-0">
            {children}
          </h3>
        ),
        p: ({ children }) => {
          return <p className="text-sm leading-relaxed mb-3 last:mb-0 text-message-text whitespace-pre-wrap">{children}</p>;
        },
        strong: ({ children }) => <strong className="font-medium text-foreground text-sm leading-relaxed">{children}</strong>,
        em: ({ children }) => <em className="italic text-message-text text-sm leading-relaxed">{children}</em>,
        code: (props) => {
          const { children, className } = props;
          const inline = (props as { inline?: boolean }).inline;
          const isBlock = className?.includes('language-') || inline === false;
          const text = restorePlaceholders(flattenText(children));
          const restoredChildren = restoreNode(children);
          const shouldMergeDiff = agentType !== 'codex';

          if (isBlock && className?.includes('language-diff')) {
            const unifiedLines = formatDiffLines(text, shouldMergeDiff, { compactContext: true });

            return (
              <code className="block text-xs text-foreground overflow-x-auto [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full dark:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/20" style={{ whiteSpace: 'break-spaces', fontFamily: CHAT_CODE_FONT_FAMILY }}>
                {unifiedLines.map((item, index: number) => {
                  const lineClassName =
                    item.type === 'ellipsis'
                      ? 'text-muted-foreground text-center'
                      : diffLineBackgroundClass(item.type);
                  const content = item.content === '' ? ' ' : item.content;

                  return (
                    <span key={index} className={`block whitespace-pre px-2 py-0.5 ${lineClassName}`} style={{ minWidth: '100%', display: 'inline-block' }}>
                      {content}
                    </span>
                  );
                })}
              </code>
            );
          }

          if (!isBlock && !text.includes('\n')) {
            return <code className="text-sm" style={{ color: 'var(--color-inline-code)', fontFamily: CHAT_CODE_FONT_FAMILY }}>{restoredChildren}</code>;
          }

          // For code blocks, don't add padding as <pre> already has it
          return <code className="block text-xs text-foreground" style={{ whiteSpace: 'break-spaces', fontFamily: CHAT_CODE_FONT_FAMILY }}>{restoredChildren}</code>;
        },
        pre: ({ children }) => <pre className="bg-muted border border-border rounded-md p-3 text-xs overflow-x-auto mb-2 text-foreground [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full dark:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/20" style={{ whiteSpace: 'break-spaces', fontFamily: CHAT_CODE_FONT_FAMILY }}>{children}</pre>,
        ul: ({ children, node }) => {
          // Check if any of the children are task list items (contain checkboxes)
          const childrenArray = Array.isArray(children) ? children : [children];
          const isTaskList = childrenArray.some((child: any) => {
            const grandchildren = Array.isArray(child?.props?.children) ? child.props.children : [child?.props?.children];
            return grandchildren.some((gc: any) => gc?.props?.type === 'checkbox');
          });

          return (
            <ul
              className={`${
                isTaskList ? 'list-none pl-0 ml-0' : 'list-disc list-outside pl-4'
              } space-y-1 mb-3 text-message-text text-sm leading-relaxed font-mono`}
            >
              {children}
            </ul>
          );
        },
        ol: ({ children }) => {
          // Check if any of the children are task list items (contain checkboxes)
          const childrenArray = Array.isArray(children) ? children : [children];
          const isTaskList = childrenArray.some((child: any) => {
            const grandchildren = Array.isArray(child?.props?.children) ? child.props.children : [child?.props?.children];
            return grandchildren.some((gc: any) => gc?.props?.type === 'checkbox');
          });

          return (
            <ol
              className={`${
                isTaskList ? 'list-none pl-0 ml-0' : 'list-decimal list-outside pl-7'
              } space-y-0 mb-3 text-message-text text-sm leading-relaxed font-mono`}
            >
              {children}
            </ol>
          );
        },
        li: ({ children, node }) => {
          // Check if this is a task list item (contains checkbox)
          const childrenArray = Array.isArray(children) ? children : [children];

          const checkboxChild = childrenArray.find((child: any) =>
            child?.props?.type === 'checkbox'
          );
          const hasCheckbox = !!checkboxChild;
          const isCompleted = checkboxChild?.props?.checked === true;
          const isInProgress = hasCheckbox && isEntirelyBoldTaskItem(node);

          if (hasCheckbox) {
            // Render as a two-item flex row: [checkbox, label]. react-markdown
            // hands the checkbox <input> and the label as *sibling* inline nodes,
            // so the label must be wrapped in a single element — otherwise every
            // inline run (each **bold**, `code`, or text fragment) becomes its own
            // flex item and the text lays out as narrow side-by-side columns
            // instead of one wrapping paragraph.
            const labelChildren = childrenArray.filter((child: any) => child !== checkboxChild);
            return (
              <li className={`list-none ml-0 pl-0 flex items-start gap-2 mb-1.5 text-message-text text-sm leading-relaxed rounded-md transition-colors [&>pre]:mt-2 font-mono ${
                isInProgress
                  ? 'border-l-4 border-l-blue-500 dark:border-l-blue-400'
                  : ''
              } ${
                isCompleted
                  ? 'opacity-60'
                  : ''
              }`} style={{ listStyleType: 'none' }}>
                {checkboxChild}
                <span className="min-w-0 flex-1">{labelChildren}</span>
              </li>
            );
          }

          // Regular list item - inherit list style from parent (ol/ul)
          return (
            <li
              className="mb-0 first:mt-0.0 text-message-text text-sm leading-relaxed [&>p]:inline [&>p]:mb-0 [&>pre]:mt-1 font-mono"
              style={{ display: 'list-item' }}
            >
              {children}
            </li>
          );
        },
        table: ({ children }) => (
          <div className="w-full overflow-x-auto custom-scrollbar mb-4">
            <table className="w-full border border-border rounded-md text-sm">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead className="bg-muted/60 text-foreground">{children}</thead>,
        tbody: ({ children }) => <tbody className="divide-y divide-border text-foreground">{children}</tbody>,
        tr: ({ children }) => <tr className="even:bg-muted/30">{children}</tr>,
        th: ({ children }) => (
          <th className="text-left font-semibold px-3 py-2 border-b border-border align-middle text-foreground">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-2 align-top border-b border-border/80 text-foreground">
            {children}
          </td>
        ),
        a: ({ children, href }) => <a href={href} className="text-blue-600 hover:text-blue-800 underline text-sm" target="_blank" rel="noopener noreferrer">{children}</a>,
        hr: () => <hr className="my-3 border-0 border-t border-border" />,
        blockquote: ({ children }) => <blockquote className="border-l-4 border-border pl-3 italic text-muted-foreground text-sm leading-relaxed mb-2">{children}</blockquote>,
        input: ({ type, checked, disabled }) => {
          if (type === 'checkbox') {
            return (
              <input
                type="checkbox"
                checked={checked}
                disabled={true}
                readOnly
                className="mr-2 mt-0.5 h-4 w-4 flex-shrink-0 rounded border border-foreground/40 bg-transparent appearance-none cursor-default relative align-middle checked:bg-transparent checked:after:content-['✓'] checked:after:absolute checked:after:inset-0 checked:after:flex checked:after:items-center checked:after:justify-center checked:after:text-[0.7rem] checked:after:leading-none checked:after:text-foreground/40"
              />
            );
          }
          return null;
        },
      }}
      >
        {transformedContent}
      </ReactMarkdown>
    </div>
  );
}

// Markdown parsing + rehype-highlight is expensive (~5-30ms per message).
// Memo by children+agentType so a streaming WS message only re-parses itself,
// not every existing message in the list.
export const MessageMarkdown = memo(MessageMarkdownImpl);
