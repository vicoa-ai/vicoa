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
    case 'coinpay':
      return 'CoinPay';
    default:
      return null;
  }
}

/**
 * A prepaid provider cannot charge again: the pass ends at
 * `current_period_end` and "manage" means "buy more time", which the backend
 * serves through the portal endpoint as a fresh checkout.
 */
export function isPrepaidProvider(provider?: BillingSubscription['provider']) {
  return provider === 'coinpay';
}

/** One line for the settings page: when a prepaid pass ends, and whether it is meant to be renewed. */
export function describePrepaidPass(
  subscription: Pick<BillingSubscription, 'provider' | 'current_period_end' | 'cancel_at_period_end'>
) {
  const provider = getBillingProviderLabel(subscription.provider) ?? 'crypto';
  const ends = formatBillingDate(subscription.current_period_end);
  if (!ends) {
    return `Paid through ${provider}. Nothing renews on its own.`;
  }
  return subscription.cancel_at_period_end
    ? `Paid through ${provider}. Your pass ends on ${ends}.`
    : `Paid through ${provider}. Your pass runs until ${ends}; extend it any time to add more days.`;
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
