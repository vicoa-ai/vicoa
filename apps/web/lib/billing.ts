import type { BillingSubscription } from '@/lib/backend-api';

export const BILLING_PLAN_LABELS: Record<string, string> = {
  free: 'Free',
  pro: 'Pro',
  enterprise: 'Enterprise',
};

export function getBillingPlanLabel(planType?: string | null) {
  if (!planType) {
    return BILLING_PLAN_LABELS.free;
  }

  return BILLING_PLAN_LABELS[planType] || planType;
}

export function getBillingProviderLabel(
  provider?: BillingSubscription['provider']
) {
  switch (provider) {
    case 'stripe':
      return 'Stripe';
    case 'apple':
      return 'App Store';
    case 'google':
      return 'Google Play';
    default:
      return null;
  }
}

export function formatBillingDate(value?: string | null) {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}
