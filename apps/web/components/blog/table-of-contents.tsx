import { TableOfContents } from 'fumadocs-core/server';
import { Facebook, Linkedin, Twitter } from 'lucide-react';

interface BlogTableOfContentsProps {
  toc?: TableOfContents;
  shareUrl?: string;
  shareTitle?: string;
}

export function BlogTableOfContents({ toc, shareUrl, shareTitle }: BlogTableOfContentsProps) {
  const filteredToc = toc?.filter((item) => item.depth <= 2) ?? [];
  const hasToc = filteredToc.length > 0;

  if (!hasToc && !shareUrl) return null;

  return (
    <aside className="hidden xl:block sticky top-12 max-h-[calc(100vh-6rem)] overflow-y-auto border-l border-border pl-6 text-sm w-64 [scrollbar-width:thin] [scrollbar-color:theme(colors.border)_transparent]">
      {hasToc && (
        <>
          <h3 className="text-xs uppercase tracking-wide text-muted-foreground mb-4">
            On this page
          </h3>
          <nav className="space-y-2 mb-8">
            {filteredToc.map((item) => (
              <a
                key={item.url}
                href={item.url}
                className="block text-foreground/80 hover:text-primary transition-colors"
                style={{ paddingLeft: `${Math.max(0, (item.depth - 1) * 12)}px` }}
              >
                {item.title}
              </a>
            ))}
          </nav>
        </>
      )}

      {shareUrl && (
        <div className="border-t border-border pt-6">
          <h3 className="text-xs uppercase tracking-wide text-muted-foreground mb-4">
            Share
          </h3>
          <div className="flex items-center gap-3">
            <a
              href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-border bg-background hover:bg-primary/10 hover:text-primary transition-colors shadow-sm"
              aria-label="Share on LinkedIn"
            >
              <Linkedin className="h-4 w-4" />
            </a>
            <a
              href={`https://twitter.com/intent/tweet?url=${encodeURIComponent(shareUrl)}&text=${encodeURIComponent(shareTitle ?? '')}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-border bg-background hover:bg-primary/10 hover:text-primary transition-colors shadow-sm"
              aria-label="Share on X"
            >
              <Twitter className="h-4 w-4" />
            </a>
            <a
              href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-border bg-background hover:bg-primary/10 hover:text-primary transition-colors shadow-sm"
              aria-label="Share on Facebook"
            >
              <Facebook className="h-4 w-4" />
            </a>
          </div>
        </div>
      )}
    </aside>
  );
}
