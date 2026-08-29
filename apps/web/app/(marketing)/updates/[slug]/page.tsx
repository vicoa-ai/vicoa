import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { UPDATE_GRID, UPDATE_LIST, UpdateEntryBlock } from '@/components/updates/update-entry';
import {
  UPDATES_BASE_URL,
  getAdjacentUpdates,
  getAllUpdates,
  getUpdateBySlug,
  getUpdateData,
  getUpdateSlug,
  getUpdateUrl,
  toIsoDate
} from '@/lib/updates-source';

interface UpdatePageProps {
  params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
  return getAllUpdates().map((entry) => ({ slug: getUpdateSlug(entry) }));
}

export async function generateMetadata(props: UpdatePageProps): Promise<Metadata> {
  const { slug } = await props.params;
  const entry = getUpdateBySlug(slug);

  if (!entry) {
    return { title: 'Update Not Found | Vicoa' };
  }

  const data = getUpdateData(entry);
  const url = `${UPDATES_BASE_URL}/updates/${slug}`;
  const title = `${data.title} | Vicoa Updates`;
  const image = data.image ?? '/images/vicoa-banner.png';

  return {
    title,
    description: data.description,
    keywords: data.tags,
    alternates: { canonical: url },
    openGraph: {
      type: 'article',
      url,
      siteName: 'Vicoa',
      title,
      description: data.description,
      publishedTime: toIsoDate(data.publishedAt),
      modifiedTime: toIsoDate(data.updatedAt ?? data.publishedAt),
      images: [{ url: image, alt: data.imageAlt ?? data.title }]
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description: data.description,
      images: [image]
    }
  };
}

export default async function UpdatePage(props: UpdatePageProps) {
  const { slug } = await props.params;
  const entry = getUpdateBySlug(slug);

  if (!entry) {
    notFound();
  }

  const data = getUpdateData(entry);
  const url = `${UPDATES_BASE_URL}/updates/${slug}`;
  const publishedIso = toIsoDate(data.publishedAt);
  const { newer, older } = getAdjacentUpdates(entry);

  const jsonLd = [
    {
      '@context': 'https://schema.org',
      '@type': 'TechArticle',
      headline: data.title,
      description: data.description,
      image: data.image ? `${UPDATES_BASE_URL}${data.image}` : undefined,
      datePublished: publishedIso,
      dateModified: toIsoDate(data.updatedAt ?? data.publishedAt),
      mainEntityOfPage: { '@type': 'WebPage', '@id': url },
      author: { '@type': 'Organization', name: 'Vicoa', url: UPDATES_BASE_URL },
      publisher: {
        '@type': 'Organization',
        name: 'Vicoa',
        logo: { '@type': 'ImageObject', url: `${UPDATES_BASE_URL}/images/vicoa-light.png` }
      }
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: UPDATES_BASE_URL },
        { '@type': 'ListItem', position: 2, name: 'Updates', item: `${UPDATES_BASE_URL}/updates` },
        { '@type': 'ListItem', position: 3, name: data.title, item: url }
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
        {/* Same container and columns as /updates, so opening a permalink keeps
            the date rail and the entry exactly where they were on the index. */}
        <div className="container mx-auto max-w-4xl px-4 py-12 md:py-16">
          <div className={UPDATE_GRID}>
            <div aria-hidden="true" />
            <nav aria-label="Breadcrumb" className="mb-8 text-sm">
              <Link
                href="/updates"
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                Updates
              </Link>
            </nav>
          </div>

          <div className={UPDATE_LIST}>
            <UpdateEntryBlock entry={entry} variant="permalink" priority />
          </div>

          {(newer || older) && (
            <div className={`mt-16 ${UPDATE_GRID}`}>
              <div aria-hidden="true" />
              <nav
                aria-label="More updates"
                className="grid gap-4 border-t border-border pt-8 sm:grid-cols-2"
              >
                {/* Previous is the older entry and sits left, Next is the newer
                    one and sits right — the reading order those labels imply. */}
                {older ? (
                  <Link
                    href={getUpdateUrl(older)}
                    className="rounded-xl border border-border p-4 transition-colors hover:bg-muted/50"
                  >
                    <span className="text-xs text-muted-foreground">← Previous</span>
                    <span className="mt-1 block font-medium">{getUpdateData(older).title}</span>
                  </Link>
                ) : (
                  <span />
                )}
                {newer && (
                  <Link
                    href={getUpdateUrl(newer)}
                    className="rounded-xl border border-border p-4 transition-colors hover:bg-muted/50 sm:text-right"
                  >
                    <span className="text-xs text-muted-foreground">Next →</span>
                    <span className="mt-1 block font-medium">{getUpdateData(newer).title}</span>
                  </Link>
                )}
              </nav>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
