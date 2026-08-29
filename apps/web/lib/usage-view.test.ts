import { describe, expect, it } from 'vitest';

import {
  deriveUsageView,
  formatCost,
  formatReset,
  formatTokens,
} from '@/lib/usage-view';
import type { SessionUsage } from '@/lib/backend-api';

describe('formatTokens', () => {
  it('abbreviates thousands and millions', () => {
    expect(formatTokens(512)).toBe('512');
    expect(formatTokens(48213)).toBe('48k');
    expect(formatTokens(1_000_000)).toBe('1m');
    expect(formatTokens(1_500_000)).toBe('1.5m');
  });
});

describe('formatCost', () => {
  it('uses 4 decimals under a cent, else 2', () => {
    expect(formatCost(0.0004)).toBe('$0.0004');
    expect(formatCost(0.42)).toBe('$0.42');
  });
});

describe('formatReset', () => {
  // Local-time literals (no trailing Z) so the assertions are independent of the
  // machine's timezone — both the input and the formatter read local fields.
  const now = new Date('2026-07-16T12:00:00').getTime();

  it('shows just the clock time when the reset lands today', () => {
    expect(formatReset('2026-07-16T13:40:00', now)).toBe('Resets 1:40pm');
    expect(formatReset('2026-07-16T23:00:00', now)).toBe('Resets 11pm');
  });

  it('shows the month and day for a later day this year', () => {
    expect(formatReset('2026-08-19T23:00:00', now)).toBe('Resets Aug 19 at 11pm');
  });

  it('includes the year across a year boundary', () => {
    expect(formatReset('2027-08-19T23:00:00', now)).toBe('Resets Aug 19, 2027 at 11pm');
  });

  it('handles the elapsed case and bad input', () => {
    expect(formatReset('2026-07-16T11:00:00', now)).toBe('Resetting now');
    expect(formatReset(null, now)).toBeNull();
    expect(formatReset(undefined, now)).toBeNull();
    expect(formatReset('not-a-date', now)).toBeNull();
  });
});

describe('deriveUsageView', () => {
  it('is empty for null usage', () => {
    const view = deriveUsageView(null);
    expect(view.hasAnything).toBe(false);
    expect(view.contextPct).toBeNull();
    expect(view.tightest).toBeNull();
  });

  it('computes context pct from used/max', () => {
    const usage: SessionUsage = {
      context: { used_tokens: 50000, max_tokens: 200000, cost_usd: 0.42 },
    };
    const view = deriveUsageView(usage);
    expect(view.hasAnything).toBe(true);
    expect(view.contextPct).toBeCloseTo(25);
  });

  it('leaves contextPct null when max is unknown but still has content', () => {
    const usage: SessionUsage = {
      context: { used_tokens: 50000, max_tokens: null, cost_usd: null },
    };
    const view = deriveUsageView(usage);
    expect(view.contextPct).toBeNull();
    expect(view.hasAnything).toBe(true);
  });

  it('drops a zero-token context with no known window (brand-new / logged-out)', () => {
    const usage: SessionUsage = {
      context: { used_tokens: 0, max_tokens: null, cost_usd: 0 },
    };
    const view = deriveUsageView(usage);
    expect(view.context).toBeNull();
    expect(view.contextPct).toBeNull();
    expect(view.hasAnything).toBe(false);
  });

  it('keeps a zero-token context once a max window is known (renders the ring)', () => {
    const usage: SessionUsage = {
      context: { used_tokens: 0, max_tokens: 200000, cost_usd: null },
    };
    const view = deriveUsageView(usage);
    expect(view.context).not.toBeNull();
    expect(view.contextPct).toBe(0);
    expect(view.hasAnything).toBe(true);
  });

  it('clamps context pct to 100', () => {
    const usage: SessionUsage = {
      context: { used_tokens: 250000, max_tokens: 200000, cost_usd: null },
    };
    expect(deriveUsageView(usage).contextPct).toBe(100);
  });

  it('surfaces windows, credits, and the tightest window', () => {
    const usage: SessionUsage = {
      limits: {
        windows: [
          { id: 'session', label: 'Session', used_pct: 63, resets_at: null },
          { id: 'weekly', label: 'Weekly', used_pct: 82, resets_at: null },
        ],
        credits: { unit: 'usd', remaining: 4.1 },
      },
    };
    const view = deriveUsageView(usage);
    expect(view.windows).toHaveLength(2);
    expect(view.credits?.remaining).toBe(4.1);
    expect(view.tightest).toBe(82);
    expect(view.contextPct).toBeNull();
    expect(view.hasAnything).toBe(true);
  });
});
