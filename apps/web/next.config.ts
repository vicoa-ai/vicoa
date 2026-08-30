import type { NextConfig } from 'next';
import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

// The desktop app bakes this flag at build time (apps/desktop/scripts/build-renderer.mjs
// passes NEXT_PUBLIC_VICOA_DESKTOP=1 into `next build`), and next.config runs
// inside that same build, so it can branch on it here.
const IS_DESKTOP_BUILD = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';

const nextConfig: NextConfig = {
  // Self-contained server build (`.next/standalone`) — consumed by the desktop
  // packaging (apps/desktop/scripts/build-renderer.mjs); a no-op for the regular
  // server deploy, which keeps using `next start`.
  output: 'standalone',
  // ppr + clientSegmentCache are Next canary features that govern client-segment
  // prefetch/streaming. On the WINDOWS desktop build they are the prime suspect
  // for the "blank main page" report: the packaged Windows renderer lands on the
  // New Session route and hangs on an empty Suspense fallback (the client segment
  // never resolves), while the identical mac build works. The desktop app is
  // fully dynamic and auth-gated, so it gains nothing from PPR — turn both off for
  // the desktop standalone build and keep them on for the web deploy. If the
  // Windows blank persists with these off, the cause is elsewhere (see the
  // renderer.log auto-capture in apps/desktop/src/window.ts).
  experimental: IS_DESKTOP_BUILD
    ? {}
    : {
        ppr: true,
        clientSegmentCache: true,
      },
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
