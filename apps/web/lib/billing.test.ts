import { describe, expect, it } from 'vitest';

import type { BillingSubscription } from './backend-api';
import { accountPlanSummary, formatSeatPrice, getBillingPlanLabel, seatSummary } from './billing';

describe('seatSummary', () => {
  it('reads used of included', () => {
    expect(seatSummary({ used: 2, included: 3, over: false }).headline).toBe('2 of 3 seats in use');
  });

  it('says what over seats means without taking anything away', () => {
    const summary = seatSummary({ used: 5, included: 3, over: true });
    expect(summary.headline).toBe('5 seats in use, 3 included');
    expect(summary.detail).toContain('Nobody loses access');
  });

  it('names the people who bring their own Pro without counting them', () => {
    expect(seatSummary({ used: 2, included: 3, over: false, own_pro: 2 }).headline).toBe(
      '2 of 3 seats in use, plus 2 with their own Pro',
    );
  });

  it('handles an unlimited plan', () => {
    expect(seatSummary({ used: 1, included: null, over: false })).toEqual({
      headline: '1 seat in use',
      detail: 'Your plan has no seat limit.',
    });
  });

  it('never uses an em dash', () => {
    for (const state of [
      { used: 2, included: 3, over: false },
      { used: 5, included: 3, over: true },
    ]) {
      const { headline, detail } = seatSummary(state);
      expect(`${headline} ${detail}`).not.toContain('—');
    }
  });
});

describe('formatSeatPrice', () => {
  it('formats minor units in the currency', () => {
    expect(formatSeatPrice({ unit_amount: 800, currency: 'usd' })).toBe('$8');
    expect(formatSeatPrice({ unit_amount: 750, currency: 'usd' })).toBe('$7.50');
  });
});

describe('getBillingPlanLabel', () => {
  it('names Team apart from Pro, though both are plan_type pro', () => {
    expect(getBillingPlanLabel('pro', 'team')).toBe('Vicoa Team');
    expect(getBillingPlanLabel('pro', 'pro')).toBe('Pro');
    expect(getBillingPlanLabel('pro')).toBe('Pro');
    expect(getBillingPlanLabel(null)).toBe('Free');
  });
});

describe('accountPlanSummary', () => {
  const base: BillingSubscription = {
    id: 'sub',
    plan_type: 'free',
    agent_limit: 1,
    current_period_end: null,
    cancel_at_period_end: false,
    provider: null,
  };

  it('offers Upgrade on Free', () => {
    expect(accountPlanSummary(base)).toEqual({ label: 'Free', detail: null, action: 'upgrade' });
  });

  it('manages a Pro bought anywhere', () => {
    for (const provider of ['stripe', 'apple', 'google'] as const) {
      expect(accountPlanSummary({ ...base, plan_type: 'pro', tier: 'pro', provider })).toEqual({
        label: 'Pro',
        detail: null,
        action: 'manage',
      });
    }
  });

  it('counts the seats a Team payer buys', () => {
    expect(
      accountPlanSummary({ ...base, plan_type: 'pro', tier: 'team', provider: 'stripe', seat_quantity: 5 }),
    ).toEqual({ label: 'Vicoa Team', detail: '5 seats', action: 'manage' });
  });

  it('names who pays for a covered seat, with nothing to manage', () => {
    expect(
      accountPlanSummary({
        ...base,
        plan_type: 'pro',
        tier: 'team',
        covered_by: { name: 'Acme', team_id: 'team' },
      }),
    ).toEqual({ label: 'Vicoa Team', detail: 'Seat from Acme', action: null });
  });
});
