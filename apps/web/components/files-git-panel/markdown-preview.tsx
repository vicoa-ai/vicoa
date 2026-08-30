'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/atom-one-dark.css';

// The app repoints `font-mono` to a sans face, so pin the real monospace family
// for code (same reason the chat renderer does).
const CODE_FONT = 'var(--font-geist-mono), ui-monospace, SFMono-Regular, Menlo, monospace';

/** Read-only, document-scale markdown render for the file viewer. Self-contained
 *  (imports its own hljs theme). No rehype-raw: embedded HTML shows as literal
 *  text, never executed. Renders the body only — the viewer owns the scroll. */
export function MarkdownPreview({ content }: { content: string }) {
  return (
    <div className="px-4 py-3 text-sm leading-relaxed text-foreground/90">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{
          h1: ({ children }) => <h1 className="mt-4 mb-2 text-xl font-semibold text-foreground first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="mt-4 mb-2 text-lg font-semibold text-foreground first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mt-3 mb-1.5 text-base font-semibold text-foreground first:mt-0">{children}</h3>,
          h4: ({ children }) => <h4 className="mt-3 mb-1 text-sm font-semibold text-foreground first:mt-0">{children}</h4>,
          p: ({ children }) => <p className="my-2">{children}</p>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-400 underline underline-offset-2 hover:text-blue-300">{children}</a>
          ),
          ul: ({ children }) => <ul className="my-2 list-disc pl-5 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal pl-5 space-y-1">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          blockquote: ({ children }) => <blockquote className="my-2 border-l-2 border-border pl-3 text-muted-foreground">{children}</blockquote>,
          hr: () => <hr className="my-4 border-border" />,
          code: ({ className, children }) => {
            const isBlock = (className ?? '').includes('language-') || (className ?? '').includes('hljs');
            if (isBlock) {
              return <code className={`${className ?? ''} hljs`} style={{ fontFamily: CODE_FONT }}>{children}</code>;
            }
            return <code className="rounded bg-muted px-1 py-0.5 text-[0.85em]" style={{ fontFamily: CODE_FONT }}>{children}</code>;
          },
          pre: ({ children }) => (
            <pre className="custom-scrollbar my-3 overflow-x-auto rounded-md bg-[#282c34] p-3 text-xs" style={{ fontFamily: CODE_FONT }}>{children}</pre>
          ),
          table: ({ children }) => (
            <div className="custom-scrollbar my-3 overflow-x-auto">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="border-b border-border">{children}</thead>,
          th: ({ children }) => <th className="px-2 py-1 text-left font-semibold">{children}</th>,
          td: ({ children }) => <td className="border-t border-border/50 px-2 py-1 align-top">{children}</td>,
          img: ({ src, alt }) => <img src={typeof src === 'string' ? src : undefined} alt={alt ?? ''} className="my-2 max-w-full rounded" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
