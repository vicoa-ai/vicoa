import type { Metadata } from 'next';
import Link from 'next/link';
import { UPDATE_GRID, UPDATE_LIST, UpdateEntryBlock } from '@/components/updates/update-entry';
import {
  UPDATES_BASE_URL,
  getAllUpdates,
  getUpdateData,
  getUpdateSlug
} from '@/lib/updates-source';

const TITLE = 'Vicoa Updates — New Features and Release Notes';
const DESCRIPTION =
  'Everything new in Vicoa: support for Claude Code, Codex, and OpenCode, live preview, voice coding, slash commands, and every release shipped to the mobile and web app.';
const URL = `${UPDATES_BASE_URL}/updates`;

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  keywords: [
    'Vicoa updates',
    'Vicoa changelog',
    'Vicoa release notes',
    'Vicoa new features',
    'Claude Code mobile updates',
    'AI coding agent changelog'
  ],
  alternates: {
    canonical: URL,
    types: {
      'application/rss+xml': `${UPDATES_BASE_URL}/updates/rss.xml`
    }
  },
  openGraph: {
    type: 'website',
    url: URL,
    siteName: 'Vicoa',
    title: TITLE,
    description: DESCRIPTION,
    images: [{ url: '/images/vicoa-banner.png', width: 1200, height: 630, alt: TITLE }]
  },
  twitter: {
    card: 'summary_large_image',
    title: TITLE,
    description: DESCRIPTION,
    images: ['/images/vicoa-banner.png']
  }
};

export default function UpdatesPage() {
  const entries = getAllUpdates();

  const jsonLd = [
    {
      '@context': 'https://schema.org',
      '@type': 'CollectionPage',
      name: TITLE,
      description: DESCRIPTION,
      url: URL,
      isPartOf: {
        '@type': 'WebSite',
        name: 'Vicoa',
        url: UPDATES_BASE_URL
      },
      mainEntity: {
        '@type': 'ItemList',
        itemListOrder: 'https://schema.org/ItemListOrderDescending',
        numberOfItems: entries.length,
        itemListElement: entries.map((entry, index) => {
          const data = getUpdateData(entry);
          return {
            '@type': 'ListItem',
            position: index + 1,
            url: `${URL}/${getUpdateSlug(entry)}`,
            name: data.title
          };
        })
      }
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: UPDATES_BASE_URL },
        { '@type': 'ListItem', position: 2, name: 'Updates', item: URL }
      ]
    }
  ];

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <div className="bg-background">
        <div className="container mx-auto max-w-4xl px-4 py-12 md:py-16">
          <div className={UPDATE_GRID}>
            <div aria-hidden="true" />
            {/* Same size and tone as the date rail — a quiet label, not a hero. */}
            <div className="mb-8 flex items-baseline justify-between gap-4">
              <h1 className="text-sm font-normal text-muted-foreground">Updates</h1>
              <Link
                href="/docs/changelog"
                className="cursor-pointer text-sm font-normal text-muted-foreground transition-colors hover:text-foreground"
              >
                Changelog →
              </Link>
            </div>
          </div>

          {entries.length === 0 ? (
            <p className="py-16 text-center text-muted-foreground">
              No updates yet. Check back soon.
            </p>
          ) : (
            <div className={UPDATE_LIST}>
              {entries.map((entry, index) => (
                <UpdateEntryBlock
                  key={getUpdateSlug(entry)}
                  entry={entry}
                  priority={index === 0}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
