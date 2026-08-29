import { describe, expect, it } from 'vitest';
import {
  annualSavingPercent,
  checkoutErrorMessage,
  isPro,
  shouldShowPaywall,
  webOrigin,
} from './desktop-paywall';

describe('checkoutErrorMessage', () => {
  it('tells a signed-out user to sign in, and never to "try again"', () => {
    // The common failure is a 401 from a request with no Supabase session.
    // "Try again" is worse than useless there — retrying cannot fix it, and it
    // points the user at the wrong problem entirely.
    const msg = checkoutErrorMessage(Object.assign(new Error('No authentication token provided'), { status: 401 }));
    expect(msg).toMatch(/sign/i);
    expect(msg).not.toMatch(/try again/i);
  });

  it('treats 403 as an auth problem too', () => {
    expect(checkoutErrorMessage(Object.assign(new Error('Forbidden'), { status: 403 }))).toMatch(/sign/i);
  });

  it('falls back to retry advice for genuinely transient failures', () => {
    expect(checkoutErrorMessage(Object.assign(new Error('boom'), { status: 500 }))).toMatch(/try again/i);
    expect(checkoutErrorMessage(new Error('network down'))).toMatch(/try again/i);
    expect(checkoutErrorMessage(null)).toMatch(/try again/i);
  });
});

describe('isPro', () => {
  it('is true only for plan_type pro', () => {
    expect(isPro({ plan_type: 'pro' })).toBe(true);
    expect(isPro({ plan_type: 'free' })).toBe(false);
  });
});

describe('shouldShowPaywall', () => {
  it('shows for a free user', () => {
    expect(shouldShowPaywall({ plan_type: 'free' })).toBe(true);
  });

  it('does not show for a pro user', () => {
    expect(shouldShowPaywall({ plan_type: 'pro' })).toBe(false);
  });

  it('does not show when entitlement is unknown', () => {
    // The read failed. Prompting a paying customer because a request timed out
    // is far worse than missing an upsell.
    expect(shouldShowPaywall(null)).toBe(false);
    expect(shouldShowPaywall(undefined)).toBe(false);
  });
});

describe('annualSavingPercent', () => {
  it('matches the saving the pricing page advertises', () => {
    expect(annualSavingPercent()).toBe(25);
  });
});

describe('webOrigin', () => {
  it('is a public https origin, never the desktop loopback', () => {
    // In the packaged app window.location.origin is http://localhost:43117 —
    // the renderer's own server. A Stripe redirect there dead-ends.
    const origin = webOrigin();
    expect(origin).toMatch(/^https:\/\//);
    expect(origin).not.toMatch(/localhost/);
  });
});
