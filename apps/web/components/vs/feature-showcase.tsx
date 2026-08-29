import Image from 'next/image';
import Link from 'next/link';
import { ArrowRight, Check } from 'lucide-react';
import type { VsFeatureSection } from '@/lib/vs-source';
import { ScreenshotMat } from '@/components/vs/screenshot-mat';
import { DemoFleet } from '@/components/landing/feature-demos';

// Live, animated landing-page demos usable in a `/vs` feature row via the
// frontmatter `demo` key (in place of a screenshot). Frameless, like the
// landing page — they sit on the page background rather than a screenshot mat.
const DEMOS: Record<string, React.ComponentType> = {
  fleet: DemoFleet,
  // Fleet mockup without the OpenCode row — used on /vs/codex.
  'fleet-codex': () => <DemoFleet exclude={['opencode']} />,
};

/**
 * Alternating screenshot + copy rows for the marquee differentiators of a `/vs`
 * page. Each row places a product screenshot on one side and the pitch (title,
 * body, checklist, optional link) on the other, flipping sides every other row.
 *
 * The screenshots carry their own window chrome, so they render frameless — no
 * border, card background, or glow behind them — at their natural aspect ratio,
 * with just rounded corners and a soft drop shadow so they read as floating.
 */
export function FeatureShowcase({ items }: { items: VsFeatureSection[] }) {
  return (
    <div className="space-y-16 md:space-y-24">
      {items.map((item, i) => {
        const reverse = i % 2 === 1;
        const hasIntrinsic = Boolean(item.imageWidth && item.imageHeight);
        const Demo = item.demo ? DEMOS[item.demo] : undefined;
        return (
          <div
            key={i}
            className="grid items-center gap-8 md:grid-cols-2 md:gap-12 lg:gap-16"
          >
            {/* Copy */}
            <div className={reverse ? 'md:order-2' : ''}>
              {item.eyebrow && (
                <div className="mb-3 text-xs font-medium uppercase tracking-[0.18em] text-primary">
                  {item.eyebrow}
                </div>
              )}
              <h3 className="text-xl font-medium leading-tight text-foreground md:text-2xl">
                {item.title}
              </h3>
              <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
                {item.body}
              </p>
              {item.points && item.points.length > 0 && (
                <ul className="mt-5 space-y-2.5">
                  {item.points.map((point, j) => (
                    <li
                      key={j}
                      className="flex items-start gap-2.5 text-sm text-foreground/80"
                    >
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              )}
              {item.linkText && item.linkHref && (
                <Link
                  href={item.linkHref}
                  className="group mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-primary"
                >
                  {item.linkText}
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </Link>
              )}
            </div>

            {/* A live demo (frameless) or a screenshot on a soft gradient mat */}
            <div className={reverse ? 'md:order-1' : ''}>
              {Demo ? (
                <div className="flex items-center justify-center">
                  <Demo />
                </div>
              ) : item.image ? (
                <ScreenshotMat className="p-2 sm:p-4">
                  {hasIntrinsic ? (
                    <Image
                      src={item.image}
                      alt={item.imageAlt || item.title}
                      width={item.imageWidth}
                      height={item.imageHeight}
                      sizes="(min-width: 768px) 34rem, 100vw"
                      className="h-auto w-full rounded-lg"
                    />
                  ) : (
                    <div className="relative aspect-[3/2]">
                      <Image
                        src={item.image}
                        alt={item.imageAlt || item.title}
                        fill
                        sizes="(min-width: 768px) 34rem, 100vw"
                        className="rounded-lg object-cover object-left-top"
                      />
                    </div>
                  )}
                </ScreenshotMat>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
