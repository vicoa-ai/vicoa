import { Check, Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { FAQSection, type FAQItem } from '@/components/faq-section';
import { PricingCards } from '@/components/billing/pricing-cards';
import { PostHogPageEvent } from '@/components/posthog-page-event';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Pricing Plans - Vicoa | Affordable Remote AI Coding Assistant',
  description: 'Choose the perfect Vicoa plan for your coding needs. A free, unlimited desktop app plus a free mobile tier (20 messages/month), Pro for unlimited messages everywhere, or custom Teams plans. Run Claude Code, Codex, and 6+ more agents from anywhere.',
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
    title: 'Vicoa Pricing - Free, Pro & Teams Plans',
    description: 'Flexible pricing for developers of all levels. Start with a free, unlimited desktop app and 20 free mobile messages, or upgrade to Pro for unlimited AI-powered coding assistance.',
    type: 'website',
    url: 'https://vicoa.ai/pricing',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Vicoa Pricing Plans',
    description: 'Choose the perfect plan for your coding needs. Free, unlimited desktop app; free mobile tier with 20 messages/month.',
  },
  alternates: {
    canonical: 'https://vicoa.ai/pricing',
  },
};

const pricingFaqs: FAQItem[] = [
  {
    question: 'What happens when I reach the free tier limit?',
    answer:
      "The 20-message monthly limit applies to the mobile app. The desktop app stays free and unlimited, so you can keep coding there anytime. To lift the mobile limit, upgrade to Pro for unlimited messages across every device. Your data and settings are preserved when you upgrade."
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
    question: "What's included in Enterprise support?",
    answer:
      'Enterprise customers get a dedicated account manager, priority support with SLA guarantees, custom onboarding and training, and direct access to our engineering team for technical issues.'
  },
  {
    question: 'Can I use my own API keys?',
    answer:
      'Yes, all plans require you to provide your own API keys for Claude or other AI providers. Vicoa provides the infrastructure to run your agents remotely, while you maintain control of your AI provider accounts.'
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
          <div className="text-center mb-16">
            <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-6">
              Compare Plans
            </h2>
            <p className="text-base sm:text-lg lg:text-xl text-muted-foreground max-w-2xl mx-auto">
              Find the perfect fit for your coding needs
            </p>
          </div>

          <div className="max-w-5xl mx-auto">
            <div className="overflow-x-auto custom-scrollbar">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b-2 border-border">
                    <th className="text-left py-6 px-4 text-base font-semibold text-foreground">Feature</th>
                    <th className="text-center py-6 px-4 text-base font-semibold text-foreground">Free</th>
                    <th className="text-center py-6 px-4 text-base font-semibold text-blue-600 dark:text-blue-400">Pro</th>
                    <th className="text-center py-6 px-4 text-base font-semibold text-foreground">Teams</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  <ComparisonSection title="Usage" />
                  <ComparisonRow feature="Mobile messages / month" free="20" pro="Unlimited" enterprise="Unlimited" />
                  <ComparisonRow feature="Desktop app (Mac, Windows, Linux)" free="Unlimited" pro="Unlimited" enterprise="Unlimited" />
                  <ComparisonRow feature="Web & mobile apps (iOS, Android)" free={true} pro={true} enterprise={true} />
                  <ComparisonRow feature="Agent sessions" free="Unlimited on desktop" pro="Unlimited everywhere" enterprise="Unlimited everywhere" />

                  <ComparisonSection title="Agents & models" />
                  <ComparisonRow feature="Claude Code, Codex, OpenCode, Gemini, Cursor, Copilot, Kimi, Hermes, Pi, Oh My Pi" free={true} pro={true} enterprise={true} />
                  <ComparisonRow feature="300+ models via OpenRouter" free={true} pro={true} enterprise={true} />
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
                  <ComparisonRow feature="Session organization: rename, pin, group & filter" free={true} pro={true} enterprise={true} />

                  <ComparisonSection title="Code & review" />
                  <ComparisonRow feature="Git diffs, commit history & in-place file editing" free={true} pro={true} enterprise={true} />
                  <ComparisonRow feature="Built-in terminals (local, remote & web)" free={true} pro={true} enterprise={true} />
                  <ComparisonRow feature="Live preview & workspace search" free={true} pro={true} enterprise={true} />
                  <ComparisonRow feature="Slash commands & @ file search" free={true} pro={true} enterprise={true} />
                  <ComparisonRow feature="Image & file attachments" free={true} pro={true} enterprise={true} />
                  <ComparisonRow feature="Context & rate-limit usage insights" free={true} pro={true} enterprise={true} />

                  <ComparisonSection title="Support & teams" />
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
              className="rounded-full px-8"
            >
              <Link href="/docs">View Documentation</Link>
            </Button>
            <Button
              asChild
              className="rounded-full px-8 bg-black hover:bg-gray-800 text-white dark:bg-white dark:text-black dark:hover:bg-gray-200"
            >
              <a href="mailto:hi@vicoa.ai">
                Contact Support
                <Mail className="ml-2 h-4 w-4" />
              </a>
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
    <tr className="bg-muted/40">
      <td
        colSpan={4}
        className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
      >
        {title}
      </td>
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
      return value ? (
        <Check className="h-5 w-5 text-foreground mx-auto" />
      ) : (
        <span className="text-muted-foreground text-sm">—</span>
      );
    }
    return <span className="text-sm text-foreground">{value}</span>;
  };

  return (
    <tr className="hover:bg-muted/20 transition-colors">
      <td className="py-4 px-4 text-sm text-foreground">{feature}</td>
      <td className="py-4 px-4 text-center">{renderCell(free)}</td>
      <td className="py-4 px-4 text-center bg-blue-50/50 dark:bg-blue-950/20">{renderCell(pro)}</td>
      <td className="py-4 px-4 text-center">{renderCell(enterprise)}</td>
    </tr>
  );
}
