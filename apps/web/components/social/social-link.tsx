'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import posthog from 'posthog-js';
import { ArrowUpRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export type SocialLinkProps = {
  /** Stable key for the `social_link_clicked` event, e.g. `discord`. */
  id: string;
  href: string;
  label: string;
  /** Muted text on the right: a handle, a store name, a platform list. */
  detail?: string;
  icon: ReactNode;
  /** Opens in a new tab and shows the outbound arrow. */
  external?: boolean;
  /** Filled row for the one action the page leads with. */
  primary?: boolean;
};

/**
 * One full-width row on the /social link page. A client component only so the
 * click can be attributed: the page is where bio links (X, LinkedIn, Discord)
 * land, and `social_link_clicked` shows which row they leave through.
 */
export function SocialLink({ id, href, label, detail, icon, external, primary }: SocialLinkProps) {
  const className = cn(
    'group flex h-12 w-full cursor-pointer items-center gap-3 rounded-xl border px-4 text-sm font-medium transition-colors',
    'outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    primary
      ? 'border-transparent bg-foreground text-background hover:bg-foreground/85'
      : // Dark `--muted` equals `--card`, so the border carries the hover there.
        'border-border bg-card text-card-foreground hover:border-foreground/25 hover:bg-muted'
  );

  const content = (
    <>
      <span className="flex h-5 w-5 shrink-0 items-center justify-center">{icon}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {detail && (
        <span
          className={cn(
            'max-w-[45%] truncate text-xs font-normal',
            primary ? 'text-background/70' : 'text-muted-foreground'
          )}
        >
          {detail}
        </span>
      )}
      {external && (
        <ArrowUpRight
          aria-hidden="true"
          className="h-3.5 w-3.5 shrink-0 opacity-50 transition-opacity group-hover:opacity-100"
        />
      )}
    </>
  );

  const onClick = () => posthog.capture('social_link_clicked', { link: id });

  if (external) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" onClick={onClick} className={className}>
        {content}
      </a>
    );
  }

  // `mailto:` and the like: same tab, and not a route for next/link to handle.
  if (!href.startsWith('/')) {
    return (
      <a href={href} onClick={onClick} className={className}>
        {content}
      </a>
    );
  }

  return (
    <Link href={href} onClick={onClick} className={className}>
      {content}
    </Link>
  );
}
