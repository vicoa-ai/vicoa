import { PostHogPageEvent } from '@/components/posthog-page-event';

// Import individual sections
import { HeroSection } from '@/components/landing/sections/hero-section';
import { SocialProofSection } from '@/components/landing/sections/social-proof-section';
import { ProblemSection } from '@/components/landing/sections/problem-section';
import { FeatureShowcaseSection } from '@/components/landing/sections/feature-showcase-section';
import { StatsBandSection } from '@/components/landing/sections/stats-band-section';
import { FeaturedSection } from '@/components/landing/sections/featured-section';
import { ScreenshotGallerySection } from '@/components/landing/sections/screenshot-gallery-section';
import { HowItWorksSection } from '@/components/landing/sections/how-it-works-section';
import { TestimonialsSection } from '@/components/landing/sections/testimonials-section';
import { CTASection } from '@/components/landing/sections/cta-section';
import { FAQSection } from '@/components/landing/sections/faq-section';

// Server Component: the static sections (feature showcase, how-it-works, faq,
// featured, cta copy) render to HTML with no client JS. The interactive pieces
// stay client islands: HeroSection fetches its own session for CTA
// personalization, the gallery/testimonials carry their own 'use client', and
// PostHogPageEvent fires the page-view capture.
export default function HomePage() {
  return (
    <main>
      <PostHogPageEvent event="landing_page_viewed" />
      <HeroSection />
      {/* <SocialProofSection /> */}
      {/* <ProblemSection /> */}
      <FeatureShowcaseSection />
      {/* <StatsBandSection /> */}
      <HowItWorksSection />
      <ScreenshotGallerySection />
      <TestimonialsSection />
      <FeaturedSection />
      <FAQSection />
      <CTASection />
    </main>
  );
}
