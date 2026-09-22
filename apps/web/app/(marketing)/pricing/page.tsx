import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { FAQSection, type FAQItem } from '@/components/faq-section';
import { PricingCards } from '@/components/billing/pricing-cards';
import { ExcludedGlyph, IncludedGlyph } from '@/components/billing/plan-glyphs';
import { PostHogPageEvent } from '@/components/posthog-page-event';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Pricing Plans - Vicoa | Affordable Remote AI Coding Assistant',
  description: 'Choose the perfect Vicoa plan for your coding needs. A free desktop, web and mobile app with one remote machine, Pro for unlimited machines and automations, or custom Enterprise plans. Run Claude Code, Codex, and 40+ coding agents from anywhere.',
  keywords: [
    'Vicoa pricing',
    'AI coding assistant pricing',
    'coding assistant plans',
    'developer tools pricing',
    'AI code generator cost',
    'coding AI subscription',
    'free coding assistant',
  ],
  openGraph: {
    title: 'Vicoa Pricing - Free, Pro & Enterprise Plans',
    description: 'Flexible pricing for developers of all levels. Start free on one machine, or upgrade to Pro to run agents across every machine you own.',
    type: 'website',
    url: 'https://vicoa.ai/pricing',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Vicoa Pricing Plans',
    description: 'Choose the perfect plan for your coding needs. Free on one machine; Pro for unlimited machines and automations.',
  },
  alternates: {
    canonical: 'https://vicoa.ai/pricing',
  },
};

const pricingFaqs: FAQItem[] = [
  {
    question: 'What are the limits on the Free plan?',
    answer:
      'Free includes one remote machine and up to ten automations. There is no message cap: desktop, web and mobile use is unmetered. When you connect a second machine or add an eleventh automation, we ask you to upgrade to Pro. Your sessions, settings and data are always preserved.'
  },
  {
    question: 'Can I change plans anytime?',
    answer:
      'Yes. Web subscriptions can be managed from dashboard settings, and iOS subscriptions can be managed through your Apple account settings.'
  },
  {
    question: 'What payment methods do you accept?',
    answer:
      'We accept payments using cards or Fast links in the web via Stripe. You can subscribe via App Store or Google Play Store using in-app payments.'
  },
  {
    question: 'Do you offer refunds?',
    answer:
      "Annual Pro includes a free trial. If you're not satisfied, you can cancel anytime during the trial period at no charge. For subscriptions via mobile apps, refunds are handled by App Store and Google Play Store."
  },
  {
    question: 'What do Enterprise plans include?',
    answer:
      'Enterprise adds centralized billing with an admin portal, SSO & SCIM provisioning, on-premise deployment, usage analytics, advanced security, and an SLA with a dedicated account manager and direct access to our engineering team. Pricing depends on seat count and deployment, so email hi@vicoa.ai and we will put together a quote.'
  },
  {
    question: 'Do I need my own AI subscription or API keys?',
    answer:
      'Yes. Vicoa does not resell model access on any plan: sign in with the Claude, ChatGPT/Codex, GitHub Copilot or other subscription you already have, or bring your own API keys. Vicoa provides the infrastructure to run your agents from anywhere; you keep control of your provider accounts and pay them directly, with no usage markup.'
  }
];

export default async function PricingPage() {
  const rawTrialDays = Number(process.env.NEXT_PUBLIC_STRIPE_PRO_TRIAL_DAYS ?? '7');
  const trialDays = Number.isFinite(rawTrialDays) && rawTrialDays > 0
    ? rawTrialDays
    : 7;

  return (
    <main>
      <PostHogPageEvent event="pricing_page_viewed" />
      {/* Hero Section - Simplified */}
      <section className="py-16 sm:py-20 lg:py-24">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="text-3xl sm:text-4xl lg:text-5xl text-foreground mb-4">
            Vicoa Pricing Plans
          </h1>
          <p className="text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto">
            Free on one machine. Go Pro to code across all of them.
          </p>
        </div>
      </section>

      {/* Pricing Cards Section */}
      <section className="pb-20 sm:pb-24 lg:pb-32 relative">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <PricingCards trialDays={trialDays} />
        </div>
      </section>

      {/* Features Comparison */}
      <section className="py-20 sm:py-24 lg:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground text-center mb-12 lg:mb-16">
            Compare plans
          </h2>

          {/* overflow-visible on lg so the sticky header sticks to the page,
              not to a horizontal scroll container that never scrolls vertically */}
          <div className="max-w-5xl mx-auto overflow-x-auto custom-scrollbar lg:overflow-visible">
            <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
              <thead className="sticky top-0 z-10 bg-background">
                <tr>
                  <th scope="col" className="w-2/5 border-b border-border py-4 pr-4 text-left">
                    <span className="sr-only">Feature</span>
                  </th>
                  <th scope="col" className="border-b border-border py-4 pl-4 text-left text-base font-semibold text-foreground">Free</th>
                  <th scope="col" className="border-b border-border py-4 pl-4 text-left text-base font-semibold text-foreground">Pro</th>
                  <th scope="col" className="border-b border-border py-4 pl-4 text-left text-base font-semibold text-foreground">Enterprise</th>
                </tr>
              </thead>
              <tbody>
                <ComparisonSection title="Usage" />
                <ComparisonRow feature="Remote machines" free="1" pro="Unlimited" enterprise="Unlimited" />
                <ComparisonRow feature="Automations" free="10" pro="Unlimited" enterprise="Unlimited" />
                <ComparisonRow feature="Desktop app (Mac, Windows, Linux)" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Web & mobile apps (iOS, Android)" free={true} pro={true} enterprise={true} />

                <ComparisonSection title="Agents & models" />
                <ComparisonRow feature="Claude Code, Codex, OpenCode, Gemini, Antigravity, Cursor, Copilot, Kimi, Hermes, Pi, Oh My Pi" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="30+ more agents via ACP: Amp, Cline, Devin, goose, Kiro, Qwen Code & others" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Any other ACP-compatible agent, with your own command" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Bring your own subscriptions & API keys (no usage markup)" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Parallel sessions, each on its own git worktree" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Permission modes, thinking toggle & mid-session model switch" free={true} pro={true} enterprise={true} />

                <ComparisonSection title="Work from anywhere" />
                <ComparisonRow feature="Remote connections to your machines" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Start, resume & interrupt sessions from any device" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Real-time cross-device sync" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Push notifications & one-tap approvals" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Talk to code (voice dictation)" free={true} pro={true} enterprise={true} />

                <ComparisonSection title="Plan & automate" />
                <ComparisonRow feature="Tasks: board & list views, sub-tasks, labels" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Scheduled automations & run history" free={true} pro={true} enterprise={true} />

                <ComparisonSection title="Code & review" />
                <ComparisonRow feature="Git diffs, commit history & in-place file editing" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Built-in terminals (local, remote & web)" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Live preview & workspace search" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Slash commands & @ file search" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Image & file attachments" free={true} pro={true} enterprise={true} />
                <ComparisonRow feature="Context & rate-limit usage insights" free={true} pro={true} enterprise={true} />

                <ComparisonSection title="Support & enterprise" />
                <ComparisonRow feature="Support" free="Community" pro="Priority" enterprise="Dedicated" />
                <ComparisonRow feature="Early feature access" free={false} pro={true} enterprise={true} />
                <ComparisonRow feature="Centralized billing & admin portal" free={false} pro={false} enterprise={true} />
                <ComparisonRow feature="SSO & SCIM provisioning" free={false} pro={false} enterprise={true} />
                <ComparisonRow feature="On-premise deployment" free={false} pro={false} enterprise={true} />
                <ComparisonRow feature="Usage analytics" free={false} pro={false} enterprise={true} />
                <ComparisonRow feature="Advanced security" free={false} pro={false} enterprise={true} />
                <ComparisonRow feature="SLA guarantee" free={false} pro={false} enterprise={true} />
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="py-20 sm:py-24 lg:py-32 bg-background">
        <FAQSection
          title="Frequently Asked Questions"
          subtitle="Everything you need to know about our pricing"
          faqs={pricingFaqs}
          idPrefix="pricing-faq"
          sectionClassName="py-0 bg-transparent"
          containerClassName="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8"
          headerClassName="text-center mb-16"
          titleClassName="text-2xl sm:text-3xl lg:text-5xl font-semibold text-foreground mb-6"
          subtitleClassName="text-base sm:text-lg text-muted-foreground"
        />

        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center mt-16 pt-12 border-t border-border/50">
          <h3 className="text-xl text-foreground mb-6">
            Still have questions?
          </h3>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Button
              asChild
              variant="outline"
              className="h-12 rounded-full px-8"
            >
              <Link href="/docs">View Documentation</Link>
            </Button>
            <Button
              asChild
              className="h-12 rounded-full px-8 bg-black hover:bg-gray-800 text-white dark:bg-white dark:text-black dark:hover:bg-gray-200"
            >
              <a href="mailto:hi@vicoa.ai">Contact Support</a>
            </Button>
          </div>
        </div>
      </section>

      {/* Footer */}
    </main>
  );
}

function ComparisonSection({ title }: { title: string }) {
  return (
    <tr>
      <th
        scope="colgroup"
        colSpan={4}
        className="pt-10 pb-3 text-left text-base font-semibold text-foreground"
      >
        {title}
      </th>
    </tr>
  );
}

function ComparisonRow({
  feature,
  free,
  pro,
  enterprise,
}: {
  feature: string;
  free: string | boolean;
  pro: string | boolean;
  enterprise: string | boolean;
}) {
  const renderCell = (value: string | boolean) => {
    if (typeof value === 'boolean') {
      return value ? <IncludedGlyph /> : <ExcludedGlyph />;
    }
    return value;
  };

  return (
    <tr>
      <td className="border-b border-border/60 py-3.5 pr-4 text-foreground/80">{feature}</td>
      <td className="border-b border-border/60 py-3.5 pl-4 text-foreground">{renderCell(free)}</td>
      <td className="border-b border-border/60 py-3.5 pl-4 text-foreground">{renderCell(pro)}</td>
      <td className="border-b border-border/60 py-3.5 pl-4 text-foreground">{renderCell(enterprise)}</td>
    </tr>
  );
}
