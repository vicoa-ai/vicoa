import type { BillingSeats, BillingSubscription, SeatPrice } from '@/lib/backend-api';

/** Buying or changing seats, apart from the plan picker at /dashboard/upgrade.
 *  Every seat entry point links here, whatever plan the payer is on. */
export const SEATS_PAGE_HREF = '/dashboard/seats';

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

function seats(n: number): string {
  return `${n} ${n === 1 ? 'seat' : 'seats'}`;
}

/**
 * How the seats read on the team page and in Billing (collaboration §6). Over
 * seats is a state, not a punishment: nobody loses access, the payer just
 * can't add anyone until they buy seats or remove someone.
 */
export function seatSummary(state: Pick<BillingSeats, 'used' | 'included' | 'over'>): {
  headline: string;
  detail: string;
} {
  if (state.included === null) {
    return { headline: `${seats(state.used)} in use`, detail: 'Your plan has no seat limit.' };
  }
  if (state.over) {
    return {
      headline: `${seats(state.used)} in use, ${state.included} included`,
      detail:
        "Nobody loses access, but you can't add people until you add seats or remove some.",
    };
  }
  return {
    headline: `${state.used} of ${seats(state.included)} in use`,
    detail:
      'A seat is anyone on a team you own, or anyone outside them you gave edit access. Viewers and commenters are free.',
  };
}

/** "$8" / "€7.50": a Stripe per-seat price for display. */
export function formatSeatPrice(price: SeatPrice): string {
  const amount = price.unit_amount / 100;
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: price.currency.toUpperCase(),
      minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    }).format(amount);
  } catch {
    return `${amount} ${price.currency.toUpperCase()}`;
  }
}
