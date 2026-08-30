import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import {
  getAllVsPages,
  getVsPageBySlug,
  getVsPageData,
  getVsUrl,
  getVsSlug,
  type VsFrontmatter,
} from '@/lib/vs-source';
import { MdxPre } from '@/components/blog/mdx-pre';
import { BlogImage } from '@/components/blog/blog-image';
import { Callout } from '@/components/vs/vs-callout';
import { ChooseCards, ChooseCard } from '@/components/vs/choice-cards';
import { VsCta } from '@/components/vs/vs-cta';
import { VsHero } from '@/components/vs/vs-hero';
import { CompareTable } from '@/components/vs/compare-table';
import { PricingCompare } from '@/components/vs/pricing-compare';
import { FAQSection } from '@/components/faq-section';
import { FeatureShowcase } from '@/components/vs/feature-showcase';
import { ScreenshotMat } from '@/components/vs/screenshot-mat';
import {
  VsSection,
  KeyTakeaways,
  HighlightCards,
  RivalStrengths,
  KeepComparing,
} from '@/components/vs/vs-sections';
import { pageMetadata } from '@/lib/seo';

const SITE_URL = 'https://vicoa.ai';
const OG_FALLBACK = '/images/hero.png';

// MDX components available inside the deep-dive body of every /vs article.
const mdxComponents = {
  pre: MdxPre,
  img: BlogImage,
  Callout,
  ChooseCards,
  ChooseCard,
  VsCta,
};

interface VsPageProps {
  params: Promise<{ slug: string }>;
}

export async function generateStaticParams() {
  return getAllVsPages().map((page) => ({ slug: getVsSlug(page) }));
}

export async function generateMetadata(
  props: VsPageProps
): Promise<Metadata> {
  const { slug } = await props.params;
  const page = getVsPageBySlug(slug);

  if (!page) {
    return { title: 'Comparison Not Found' };
  }

  const data = getVsPageData(page);
  const title = (data.metaTitle || data.title) as string;
  const description = data.description as string;
  const author = data.author as { name: string } | undefined;
  const image = (data.image as string | undefined) || OG_FALLBACK;
  const imageAlt =
    (data.imageAlt as string | undefined) || (data.title as string);

  return pageMetadata(getVsUrl(page), {
    title: `${title} | Vicoa`,
    description,
    authors: author ? [{ name: author.name }] : undefined,
    openGraph: {
      title: `${title} | Vicoa`,
      description,
      type: 'article',
      publishedTime: data.publishedAt as string,
      modifiedTime: (data.updatedAt || data.publishedAt) as string,
      authors: author ? [author.name] : undefined,
      images: [{ url: image, alt: imageAlt }],
    },
    twitter: {
      card: 'summary_large_image',
      title: `${title} | Vicoa`,
      description,
      images: [image],
    },
  });
}

export default async function VsArticlePage(props: VsPageProps) {
  const { slug } = await props.params;
  const page = getVsPageBySlug(slug);

  if (!page) {
    notFound();
  }

  const data = getVsPageData(page) as VsFrontmatter & Record<string, unknown>;
  const MDXContent = page.body as React.ComponentType<any>;

  const {
    title,
    description,
    competitor,
    tagline,
    shortAnswer,
    publishedAt,
    updatedAt,
    author,
    image,
    imageAlt,
    imageWidth,
    imageHeight,
    vicoa,
    rival,
    trustChips,
    keyTakeaways,
    featureSections,
    highlights,
    comparison,
    pricing,
    rivalStrengths,
    chooseVicoa,
    chooseRival,
    faqs,
  } = data;

  const url = `${SITE_URL}${getVsUrl(page)}`;
  // "Last updated" freshness signal, shown by the comparison table (not a byline).
  const lastUpdatedLabel = new Date(updatedAt || publishedAt).toLocaleDateString(
    'en-US',
    { month: 'long', year: 'numeric' }
  );

  // Other comparisons for the "keep comparing" grid.
  const otherPages = getAllVsPages()
    .filter((p) => getVsSlug(p) !== slug)
    .slice(0, 3)
    .map((p) => {
      const d = getVsPageData(p);
      return {
        title: d.title as string,
        competitor: d.competitor as string,
        href: getVsUrl(p),
        description: d.description as string,
      };
    });

  // JSON-LD: the comparison article and its breadcrumb trail. The FAQPage
  // schema is emitted by the reused <FAQSection> component from the same
  // `faqs` data, so it is deliberately not duplicated here.
  const jsonLd: Record<string, unknown>[] = [
    {
      '@context': 'https://schema.org',
      '@type': 'Article',
      headline: title,
      description,
      image: image ? `${SITE_URL}${image}` : undefined,
      datePublished: publishedAt,
      dateModified: updatedAt || publishedAt,
      author: author ? { '@type': 'Person', name: author.name } : undefined,
      publisher: {
        '@type': 'Organization',
        name: 'Vicoa',
        logo: {
          '@type': 'ImageObject',
          url: `${SITE_URL}/images/vicoa-light.png`,
        },
      },
      mainEntityOfPage: { '@type': 'WebPage', '@id': url },
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: SITE_URL },
        {
          '@type': 'ListItem',
          position: 2,
          name: 'Compare',
          item: `${SITE_URL}/vs`,
        },
        { '@type': 'ListItem', position: 3, name: title, item: url },
      ],
    },
  ];

  return (
    <>
      {jsonLd.map((node, i) => (
        <script
          key={i}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(node) }}
        />
      ))}

      <div className="bg-background">
        {/* Hero with dual product cards */}
        <VsHero
          title={title}
          competitor={competitor}
          tagline={tagline}
          description={description}
          vicoa={vicoa}
          rival={rival}
          trustChips={trustChips}
        />

        {/* Hero product shot — links through to the Vicoa home page */}
        {image && (
          <div className="container mx-auto max-w-5xl px-4 pt-6">
            <Link href="/" aria-label="Vicoa home" className="group block">
              <ScreenshotMat className="p-2 transition-transform duration-300 group-hover:scale-[1.01] sm:p-4">
                <Image
                  src={image}
                  alt={imageAlt || title}
                  width={imageWidth ?? 1600}
                  height={imageHeight ?? 1000}
                  sizes="(min-width: 1024px) 64rem, 100vw"
                  priority
                  className="h-auto w-full rounded-xl"
                />
              </ScreenshotMat>
            </Link>
          </div>
        )}

        {/* Short answer + TL;DR */}
        {(shortAnswer || (keyTakeaways && keyTakeaways.length > 0)) && (
          <VsSection eyebrow="The short answer">
            <div className="mx-auto max-w-3xl">
              {shortAnswer && (
                <Callout variant="verdict" title={`Vicoa vs ${competitor}`}>
                  <p className="text-[15px] leading-relaxed text-foreground/90">
                    {shortAnswer}
                  </p>
                </Callout>
              )}
            </div>
            {keyTakeaways && keyTakeaways.length > 0 && (
              <KeyTakeaways items={keyTakeaways} />
            )}
          </VsSection>
        )}

        {/* Headline differentiators */}
        {highlights && highlights.length > 0 && (
          <VsSection
            eyebrow="Why switch"
            title={`What Vicoa adds over ${competitor}`}
          >
            <HighlightCards items={highlights} />
          </VsSection>
        )}

        {/* At-a-glance table */}
        {comparison && comparison.length > 0 && (
          <VsSection
            eyebrow="Side by side"
            title={`Vicoa vs ${competitor} at a glance`}
            muted
          >
            <CompareTable competitor={competitor} rows={comparison} />
            <p className="mt-4 text-center text-xs text-muted-foreground">
              Last updated {lastUpdatedLabel}
            </p>
          </VsSection>
        )}

        {/* Marquee differentiators (alternating screenshot + copy) */}
        {featureSections && featureSections.length > 0 && (
          <VsSection
            eyebrow="The Vicoa difference"
            title={`Built to run more than ${competitor} does`}
          >
            <FeatureShowcase items={featureSections} />
          </VsSection>
        )}

        {/* Deep-dive narrative (MDX body) */}
        <VsSection eyebrow="In depth" title="How they compare, point by point">
          <div className="vs-prose prose prose-neutral mx-auto max-w-3xl dark:prose-invert">
            <MDXContent components={mdxComponents} />
          </div>
        </VsSection>

        {/* Where the competitor wins */}
        {rivalStrengths && rivalStrengths.length > 0 && (
          <VsSection
            eyebrow="The honest take"
            title={`Where ${competitor} is the stronger pick`}
            muted
          >
            <RivalStrengths items={rivalStrengths} />
          </VsSection>
        )}

        {/* Pricing */}
        {pricing && (
          <VsSection
            eyebrow="Pricing"
            title={`Pricing: Vicoa vs ${competitor}`}
          >
            <div className="mx-auto max-w-3xl">
              <PricingCompare
                competitor={competitor}
                vicoa={pricing.vicoa}
                rival={pricing.rival}
                note={pricing.note}
              />
            </div>
          </VsSection>
        )}

        {/* Who should choose which */}
        {(chooseVicoa || chooseRival) && (
          <VsSection
            eyebrow="Decision"
            title="Who should choose which"
            muted
          >
            <div className="mx-auto max-w-3xl">
              <ChooseCards>
                {chooseVicoa && (
                  <ChooseCard
                    product="Vicoa"
                    recommended
                    points={chooseVicoa.points}
                    ideal={chooseVicoa.ideal}
                  />
                )}
                {chooseRival && (
                  <ChooseCard
                    product={competitor}
                    points={chooseRival.points}
                    ideal={chooseRival.ideal}
                  />
                )}
              </ChooseCards>
            </div>
          </VsSection>
        )}

        {/* FAQ — reuses the landing-page accordion (which also emits the
            FAQPage JSON-LD, so it is intentionally omitted from `jsonLd` above). */}
        {faqs && faqs.length > 0 && (
          <VsSection eyebrow="FAQ" title="Frequently asked questions">
            <FAQSection
              idPrefix="vs-faq"
              faqs={faqs.map((f) => ({ question: f.q, answer: f.a }))}
              sectionClassName=""
              containerClassName="mx-auto max-w-3xl"
            />
          </VsSection>
        )}

        {/* Final CTA */}
        <div className="container mx-auto max-w-5xl px-4 py-8">
          <VsCta
            slug={slug}
            heading={`Try the fuller ${competitor} alternative, free`}
            subheading="Vicoa works with the coding agents already on your machine. No credit card required."
          />
        </div>

        {/* Keep comparing */}
        {/*
        {otherPages.length > 0 && (
          <VsSection
            eyebrow="Keep comparing"
            title="More Vicoa comparisons"
            muted
          >
            <KeepComparing items={otherPages} />
          </VsSection>
        )}
        */}
        <div className="container mx-auto max-w-5xl px-4 py-12">
        </div>
      </div>
    </>
  );
}
