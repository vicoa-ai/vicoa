import type { NextConfig } from 'next';
import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

const nextConfig: NextConfig = {
  // Self-contained server build (`.next/standalone`) — consumed by the desktop
  // packaging (apps/desktop/scripts/build-renderer.mjs); a no-op for the regular
  // server deploy, which keeps using `next start`.
  output: 'standalone',
  // NOTE: ppr + clientSegmentCache (Next canary features) used to be enabled for
  // the web deploy. They were removed: with `ppr: true` every prerendered route
  // is marked partially-dynamic, so the Netlify Next runtime resumed each one
  // through the serverless function on every request — even the fully-static
  // marketing/docs/blog pages, which then never hit the CDN. That blew past the
  // Netlify Functions invocation quota for zero benefit (auth state in the navbar
  // is fetched client-side, so the server has no dynamic hole to postpone). With
  // PPR off, those pages ship as pure static CDN assets and only the API routes
  // and genuinely dynamic renders touch the function. Removing PPR also lets us
  // run stable Next instead of canary (PPR is canary-only). The desktop build
  // already ran with these off (they were the prime suspect for a Windows
  // "blank main page" hang). Do not re-add PPR without re-checking Netlify usage.
  async redirects() {
    return [
      // `/cancel-subscription` is a short link to the help page, which is part
      // of the open marketing site (always present), so it's unconditional.
      {
        source: '/cancel-subscription',
        destination: '/help/cancel-subscription',
        permanent: true,
      },
      // Folder indexes used to be linked as /docs/agents/index, which duplicated
      // /docs/agents. Fold the alias into the canonical URL.
      {
        source: '/docs/:path*/index',
        destination: '/docs/:path*',
        permanent: true,
      },
      // Nested pages were briefly reachable at the top level (a stale
      // generateStaticParams flattened the folder meta.json files). Point the
      // strays at the real pages instead of leaving them to 404.
      ...['claude-code', 'codex', 'opencode', 'more-coding-agents'].map((slug) => ({
        source: `/docs/${slug}`,
        destination: `/docs/agents/${slug}`,
        permanent: true,
      })),
      ...['mobile-app', 'vicoa-cli'].map((slug) => ({
        source: `/docs/${slug}`,
        destination: `/docs/changelog/${slug}`,
        permanent: true,
      })),
    ];
  },
  images: {
    // AVIF first: ~30–50% smaller than WebP at equal sharpness, so we can serve
    // denser images (crisp on low-DPI external monitors) without growing bytes.
    formats: ['image/avif', 'image/webp'],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'startupfa.me',
      },
      {
        protocol: 'https',
        hostname: 'cdn.prod.website-files.com',
      },
      {
        protocol: 'https',
        hostname: 'fazier.com',
      },
      {
        protocol: 'https',
        hostname: 'similarlabs.com',
      },
      {
        protocol: 'https',
        hostname: 'launchigniter.com',
      },
      {
        protocol: 'https',
        hostname: 'twelve.tools',
      },
      {
        protocol: 'https',
        hostname: 'findly.tools',
      },
      {
        protocol: 'https',
        hostname: 'img.turbo0.com',
      },
      {
        protocol: 'https',
        hostname: 'embed.filekitcdn.com',
      },
      {
        protocol: 'https',
        hostname: 'cdn.aidirectori.es',
      },
    ],
  },
};

export default withMDX(nextConfig);
