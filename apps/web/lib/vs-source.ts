import { vs as vsDocs } from '@/.source/index';

export type VsPage = (typeof vsDocs)[number];

// Re-export the generated collection.
export const vs = vsDocs;

export type CompareCell = string | boolean;

export interface VsProductCard {
  pitch: string;
  chips?: string[];
}

export interface VsHighlight {
  stat: string;
  label: string;
  detail?: string;
}

export interface VsComparisonRow {
  feature: string;
  vicoa: CompareCell;
  rival: CompareCell;
}

export interface VsPricingColumn {
  price: string;
  rows?: string[];
}

export interface VsChoice {
  points: string[];
  ideal?: string;
}

export interface VsFaq {
  q: string;
  a: string;
}

export interface VsKeyTakeaway {
  label: string;
  text: string;
}

export interface VsFeatureSection {
  eyebrow?: string;
  title: string;
  body: string;
  points?: string[];
  /** Live demo component key (e.g. "fleet"); shown instead of `image` when set. */
  demo?: string;
  image?: string;
  imageAlt?: string;
  imageWidth?: number;
  imageHeight?: number;
  linkText?: string;
  linkHref?: string;
}

export interface VsFrontmatter {
  title: string;
  metaTitle?: string;
  description: string;
  competitor: string;
  competitorAliases?: string[];
  tagline?: string;
  shortAnswer?: string;
  publishedAt: string;
  updatedAt?: string;
  author: {
    name: string;
    avatar?: string;
  };
  tags?: string[];
  image?: string;
  imageAlt?: string;
  imageWidth?: number;
  imageHeight?: number;
  featured?: boolean;

  // Structured landing-page sections
  vicoa?: VsProductCard;
  rival?: VsProductCard;
  trustChips?: string[];
  keyTakeaways?: VsKeyTakeaway[];
  featureSections?: VsFeatureSection[];
  highlights?: VsHighlight[];
  comparison?: VsComparisonRow[];
  pricing?: {
    vicoa: VsPricingColumn;
    rival: VsPricingColumn;
    note?: string;
  };
  rivalStrengths?: { title: string; body: string }[];
  chooseVicoa?: VsChoice;
  chooseRival?: VsChoice;
  faqs?: VsFaq[];
}

const vsPagesBySlug = new Map(
  vs.map((page) => {
    const slug = page.info.path.replace(/\.mdx$/, '');
    return [slug, page] as const;
  })
);

export function getVsSlug(page: VsPage): string {
  return page.info.path.replace(/\.mdx$/, '');
}

export function getVsPageData(page: VsPage) {
  const raw = page as any;
  return {
    ...((raw.frontmatter ?? {}) as Record<string, unknown>),
    ...raw,
  } as VsFrontmatter & Record<string, unknown>;
}

export function getVsUrl(page: VsPage): string {
  return `/vs/${getVsSlug(page)}`;
}

/** All comparison pages, featured first, then newest-first. */
export function getAllVsPages(): VsPage[] {
  return Array.from(vs).sort((a, b) => {
    const dataA = getVsPageData(a);
    const dataB = getVsPageData(b);
    if (Boolean(dataA.featured) !== Boolean(dataB.featured)) {
      return dataA.featured ? -1 : 1;
    }
    const dateA = new Date(dataA.publishedAt || 0).getTime();
    const dateB = new Date(dataB.publishedAt || 0).getTime();
    return dateB - dateA;
  });
}

export function getVsPageBySlug(slug: string): VsPage | undefined {
  return vsPagesBySlug.get(slug);
}

export function formatDate(date: string | Date | undefined): string {
  if (!date) return 'Date not available';
  const parsed = new Date(date);
  if (isNaN(parsed.getTime())) return 'Invalid date';
  return parsed.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

