import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { PricingCards } from '@/components/billing/pricing-cards';
import { Button } from '@/components/ui/button';
import { PostHogPageEvent } from '@/components/posthog-page-event';

export default function DashboardUpgradePage() {
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-12">
      <div className="mb-8">
        <Button asChild variant="ghost" size="icon" className="size-14 rounded-full">
          <Link href="/dashboard" aria-label="Return to dashboard">
            <ArrowLeft className="size-5" />
          </Link>
        </Button>
      </div>

      <div className="mx-auto max-w-3xl text-center">
        <h1 className="text-3xl text-foreground sm:text-4xl">
          Upgrade your plan
        </h1>
        <p className="mt-3 text-sm text-muted-foreground sm:text-base">
          Choose the plan that fits you. Manage your subscription from settings after checkout.
        </p>
      </div>

      <PostHogPageEvent event="upgrade_page_viewed" />
      <div className="mt-10">
        <PricingCards />
      </div>
    </div>
  );
}
