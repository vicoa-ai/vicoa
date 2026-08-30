import { defineConfig, defineDocs } from 'fumadocs-mdx/config';
import { z } from 'zod';

export const { docs, meta } = defineDocs({
  dir: 'content/docs',
});

export const { docs: blog, meta: blogMeta } = defineDocs({
  dir: 'content/blog',
  docs: {
    schema: z.object({
      title: z.string(),
      description: z.string(),
      publishedAt: z.string(),
      updatedAt: z.string().optional(),
      author: z.object({
        name: z.string(),
        avatar: z.string().optional(),
      }),
      tags: z.array(z.string()).optional(),
      image: z.string().optional(),
      imageAlt: z.string().optional(),
    }),
  },
});

// Competitor comparison ("X vs Y") pages rendered at /vs/<slug>. These are SEO
// landing pages, so they carry a few comparison-specific fields on top of the
// blog shape: `competitor` (the tool we compare against), an optional
// `shortAnswer` rendered as the GEO direct-answer callout, and `metaTitle` so
// the on-page H1 (`title`) can differ from the search-optimized <title>.
export const { docs: vs, meta: vsMeta } = defineDocs({
  dir: 'content/vs',
  docs: {
    schema: z.object({
      title: z.string(),
      // SEO <title> override; falls back to `title` when omitted.
      metaTitle: z.string().optional(),
      description: z.string(),
      // The product we compare Vicoa against, e.g. "Happy".
      competitor: z.string(),
      // Other names the competitor is searched by, e.g. ["Happy Coder"].
      competitorAliases: z.array(z.string()).optional(),
      // Short subhead shown under the H1.
      tagline: z.string().optional(),
      // One-paragraph direct answer, surfaced in the callout under the hero for
      // AI Overviews / featured snippets. Plain text (no markdown links).
      shortAnswer: z.string().optional(),
      publishedAt: z.string(),
      updatedAt: z.string().optional(),
      author: z.object({
        name: z.string(),
        avatar: z.string().optional(),
      }),
      tags: z.array(z.string()).optional(),
      image: z.string().optional(),
      imageAlt: z.string().optional(),
      // Intrinsic pixel size of `image`, so the clickable hero shot renders at
      // its natural aspect ratio (matching the landing hero) with no layout shift.
      imageWidth: z.number().optional(),
      imageHeight: z.number().optional(),
      // Pin to the top of the /vs index.
      featured: z.boolean().optional(),

      // ---- Structured landing-page sections (all optional) ----
      // "The gist" TL;DR list shown under the short-answer callout: a labeled
      // one-liner per decision axis (agents, desktop, price, ...).
      keyTakeaways: z
        .array(z.object({ label: z.string(), text: z.string() }))
        .optional(),
      // Alternating screenshot + copy rows for the marquee differentiators.
      // Rendered wide (image on one side, text on the other, sides alternating).
      featureSections: z
        .array(
          z.object({
            eyebrow: z.string().optional(),
            title: z.string(),
            body: z.string(),
            points: z.array(z.string()).optional(),
            // A live landing-page demo component (by key, e.g. "fleet") shown in
            // place of a screenshot. When set, `image` is ignored.
            demo: z.string().optional(),
            image: z.string().optional(),
            imageAlt: z.string().optional(),
            // Intrinsic pixel size of the screenshot, so it renders at its
            // natural aspect ratio (borderless, no crop).
            imageWidth: z.number().optional(),
            imageHeight: z.number().optional(),
            linkText: z.string().optional(),
            linkHref: z.string().optional(),
          })
        )
        .optional(),
      // The two product cards in the hero.
      vicoa: z
        .object({
          pitch: z.string(),
          chips: z.array(z.string()).optional(),
        })
        .optional(),
      rival: z
        .object({
          pitch: z.string(),
          chips: z.array(z.string()).optional(),
        })
        .optional(),
      // Small reassurance chips under the hero CTA.
      trustChips: z.array(z.string()).optional(),
      // Three headline differentiators (big number + label + one line).
      highlights: z
        .array(
          z.object({
            stat: z.string(),
            label: z.string(),
            detail: z.string().optional(),
          })
        )
        .optional(),
      // At-a-glance comparison rows. `vicoa`/`rival` are either a short string
      // or a boolean (true → check, false → not available).
      comparison: z
        .array(
          z.object({
            feature: z.string(),
            vicoa: z.union([z.string(), z.boolean()]),
            rival: z.union([z.string(), z.boolean()]),
          })
        )
        .optional(),
      // Two-column pricing snapshot.
      pricing: z
        .object({
          vicoa: z.object({
            price: z.string(),
            rows: z.array(z.string()).optional(),
          }),
          rival: z.object({
            price: z.string(),
            rows: z.array(z.string()).optional(),
          }),
          note: z.string().optional(),
        })
        .optional(),
      // Honest "where the competitor is the stronger pick" cards.
      rivalStrengths: z
        .array(z.object({ title: z.string(), body: z.string() }))
        .optional(),
      // "Who should choose which" cards.
      chooseVicoa: z
        .object({ points: z.array(z.string()), ideal: z.string().optional() })
        .optional(),
      chooseRival: z
        .object({ points: z.array(z.string()), ideal: z.string().optional() })
        .optional(),
      // FAQ — drives the accordion AND the FAQPage JSON-LD (plain-text answers).
      faqs: z
        .array(z.object({ q: z.string(), a: z.string() }))
        .optional(),
    }),
  },
});

// Product changelog entries rendered at /updates. Unlike blog posts these have
// no author byline — they are release notes, not articles — and `summary` is
// the short lede shown under the headline on the index page.
export const { docs: updates, meta: updatesMeta } = defineDocs({
  dir: 'content/updates',
  docs: {
    schema: z.object({
      title: z.string(),
      description: z.string(),
      summary: z.string(),
      publishedAt: z.string(),
      updatedAt: z.string().optional(),
      tags: z.array(z.string()).optional(),
      image: z.string().optional(),
      imageAlt: z.string().optional(),
    }),
  },
});

export default defineConfig({
  mdxOptions: {
    rehypeCodeOptions: {
      themes: {
        light: 'github-light',
        dark: 'github-dark',
      },
    },
  },
});
