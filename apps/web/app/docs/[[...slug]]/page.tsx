import { DocsPage, DocsBody } from 'fumadocs-ui/page';
import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import type { TableOfContents } from 'fumadocs-core/server';
import type { ComponentType } from 'react';
import { Tab, Tabs } from 'fumadocs-ui/components/tabs';
import { LiteYouTubeEmbed } from '@/components/ui/lite-youtube-embed';
import {
  DOCS_BASE_URL,
  type DocEntry,
  getDocBreadcrumbs,
  getDocPageTitle,
  getDocUrl,
  resolveDoc,
  staticDocSlugs,
  toDocSlugKey
} from '@/lib/docs-source';
import { getFaqEntries } from '@/lib/docs-faq';

interface PageProps {
  params: Promise<{ slug?: string[] }>;
}

const FALLBACK_DESCRIPTION = 'Vicoa documentation';
const OG_IMAGE = `${DOCS_BASE_URL}/images/vicoa-banner.png`;

function renderDoc(doc: DocEntry) {
  const Content = doc.body as ComponentType<
    { components: typeof defaultMdxComponents } & Record<string, unknown>
  >;
  const toc = (doc.toc ?? []) as TableOfContents;
  const mdxComponents = { ...defaultMdxComponents, LiteYouTubeEmbed, Tab, Tabs };

  return (
    <DocsPage toc={toc} article={{ className: 'gap-16' }}>
      <DocsBody>
        <Content components={mdxComponents} />
      </DocsBody>
    </DocsPage>
  );
}

/**
 * TechArticle + BreadcrumbList on every page, plus FAQPage on the FAQ so its
 * Q&As are eligible for rich results.
 */
function buildJsonLd(doc: DocEntry, slug?: string[]) {
  const slugKey = toDocSlugKey(slug);
  const url = `${DOCS_BASE_URL}${getDocUrl(slugKey)}`;
  const crumbs = getDocBreadcrumbs(slug);

  const graph: Record<string, unknown>[] = [
    {
      '@context': 'https://schema.org',
      '@type': 'TechArticle',
      headline: getDocPageTitle(doc),
      description: doc.description ?? FALLBACK_DESCRIPTION,
      url,
      inLanguage: 'en',
      isPartOf: {
        '@type': 'WebSite',
        name: 'Vicoa',
        url: DOCS_BASE_URL
      },
      publisher: {
        '@type': 'Organization',
        name: 'Vicoa',
        logo: {
          '@type': 'ImageObject',
          url: `${DOCS_BASE_URL}/images/vicoa-light.png`
        }
      }
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: crumbs.map((crumb, index) => ({
        '@type': 'ListItem',
        position: index + 1,
        name: crumb.name,
        item: `${DOCS_BASE_URL}${crumb.url}`
      }))
    }
  ];

  if (slugKey === 'faq') {
    const faqEntries = getFaqEntries();
    if (faqEntries.length > 0) {
      graph.push({
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        mainEntity: faqEntries.map((entry) => ({
          '@type': 'Question',
          name: entry.question,
          acceptedAnswer: {
            '@type': 'Answer',
            text: entry.answer
          }
        }))
      });
    }
  }

  return graph;
}

export default async function Page({ params }: PageProps) {
  const { slug } = await params;
  const doc = resolveDoc(slug);

  if (!doc) {
    notFound();
  }

  return (
    <>
      {buildJsonLd(doc, slug).map((node, index) => (
        <script
          key={index}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(node) }}
        />
      ))}
      {renderDoc(doc)}
    </>
  );
}


export function generateStaticParams() {
  return staticDocSlugs.map((slug) =>
    slug === '' ? { slug: [] } : { slug: slug.split('/') }
  );
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const doc = resolveDoc(slug);

  if (!doc) {
    return {
      title: 'Documentation',
      description: FALLBACK_DESCRIPTION
    };
  }

  const title = getDocPageTitle(doc);
  const description = doc.description ?? FALLBACK_DESCRIPTION;
  // Canonical form, so /docs/agents/index folds into /docs/agents instead of
  // competing with it. Without this every docs page inherits the root layout's
  // canonical and points at the homepage.
  const url = `${DOCS_BASE_URL}${getDocUrl(toDocSlugKey(slug))}`;

  return {
    title,
    description,
    alternates: {
      canonical: url
    },
    openGraph: {
      type: 'article',
      locale: 'en_US',
      siteName: 'Vicoa',
      url,
      title,
      description,
      images: [
        {
          url: OG_IMAGE,
          width: 1200,
          height: 630,
          alt: title
        }
      ]
    },
    twitter: {
      card: 'summary_large_image',
      site: '@Vicoa',
      creator: '@Vicoa',
      title,
      description,
      images: [OG_IMAGE]
    }
  };
}
