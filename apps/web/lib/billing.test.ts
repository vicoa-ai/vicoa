import { describe, expect, it } from 'vitest';

import {
  describePrepaidPass,
  formatBillingDate,
  getBillingPlanLabel,
  getBillingProviderLabel,
  isPrepaidProvider,
} from './billing';

describe('billing labels', () => {
  it('maps plan types and falls back to the raw value', () => {
    expect(getBillingPlanLabel()).toBe('Free');
    expect(getBillingPlanLabel('pro')).toBe('Pro');
    expect(getBillingPlanLabel('team')).toBe('team');
  });

  it('names every provider the backend can report', () => {
    expect(getBillingProviderLabel('stripe')).toBe('Stripe');
    expect(getBillingProviderLabel('apple')).toBe('App Store');
    expect(getBillingProviderLabel('google')).toBe('Google Play');
    expect(getBillingProviderLabel('coinpay')).toBe('CoinPay');
    expect(getBillingProviderLabel(null)).toBeNull();
  });
});

describe('prepaid providers', () => {
  it('only coinpay is prepaid', () => {
    expect(isPrepaidProvider('coinpay')).toBe(true);
    expect(isPrepaidProvider('stripe')).toBe(false);
    expect(isPrepaidProvider(null)).toBe(false);
  });

  it('describes a running pass, a cancelled pass, and an open-ended one', () => {
    const ends = formatBillingDate('2026-10-05T12:00:00Z');
    expect(ends).toMatch(/2026/);
    expect(
      describePrepaidPass({ provider: 'coinpay', current_period_end: '2026-10-05T12:00:00Z', cancel_at_period_end: false })
    ).toBe(`Paid through CoinPay. Your pass runs until ${ends}; extend it any time to add more days.`);
    expect(
      describePrepaidPass({ provider: 'coinpay', current_period_end: '2026-10-05T12:00:00Z', cancel_at_period_end: true })
    ).toBe(`Paid through CoinPay. Your pass ends on ${ends}.`);
    expect(
      describePrepaidPass({ provider: 'coinpay', current_period_end: null, cancel_at_period_end: false })
    ).toBe('Paid through CoinPay. Nothing renews on its own.');
  });
});
