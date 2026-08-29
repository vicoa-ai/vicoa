import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// One stable mock object across `vi.resetModules()` — the tests below re-import
// the module to exercise its compile-time SURFACE branch and its module-level
// guards, and a factory returning a fresh object each time would strand these
// spies.
const { mockPosthog } = vi.hoisted(() => ({
  mockPosthog: {
    capture: vi.fn(),
    identify: vi.fn(),
    reset: vi.fn(),
  },
}));

vi.mock('posthog-js', () => ({ default: mockPosthog }));

type Telemetry = typeof import('./desktop-telemetry');

/**
 * Load a fresh copy of the module with SURFACE resolved for `surface`.
 *
 * SURFACE is read from `process.env` at module scope (Next inlines it at build
 * time; under vitest it's a real read), so flipping it means re-importing.
 * Re-importing also clears the module-level guards, which is what the guard
 * tests want anyway.
 */
async function loadTelemetry(surface: 'web' | 'desktop'): Promise<Telemetry> {
  vi.resetModules();
  vi.stubEnv('NEXT_PUBLIC_VICOA_DESKTOP', surface === 'desktop' ? '1' : '');
  return import('./desktop-telemetry');
}

function stubStorage(impl: Partial<Storage>) {
  vi.stubGlobal('window', { localStorage: impl });
}

/** A working in-memory localStorage, plus the backing store to assert against. */
function memoryStorage() {
  const store: Record<string, string> = {};
  stubStorage({
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
  });
  return store;
}

/** The (event, payload) of the only capture that should have happened. */
function onlyCapture(): [string, unknown] {
  expect(mockPosthog.capture).toHaveBeenCalledTimes(1);
  return mockPosthog.capture.mock.calls[0] as [string, unknown];
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('SURFACE', () => {
  it('is desktop only when the renderer bundle is baked with the flag', async () => {
    expect((await loadTelemetry('desktop')).SURFACE).toBe('desktop');
    expect((await loadTelemetry('web')).SURFACE).toBe('web');
  });

  it('treats an unset flag as web', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_VICOA_DESKTOP', undefined);
    expect((await import('./desktop-telemetry')).SURFACE).toBe('web');
  });
});

describe('scanPayload', () => {
  it('lists installed agent ids and counts them', async () => {
    const { scanPayload } = await loadTelemetry('desktop');
    expect(
      scanPayload([
        { id: 'claude', label: 'Claude Code', installed: true },
        { id: 'codex', label: 'Codex', installed: false },
        { id: 'opencode', label: 'OpenCode', installed: true },
      ]),
    ).toEqual({ installed: ['claude', 'opencode'], installed_count: 2 });
  });

  it('reports zero when nothing is installed — the "can never activate" case', async () => {
    const { scanPayload } = await loadTelemetry('desktop');
    expect(scanPayload([{ id: 'claude', label: 'Claude Code', installed: false }])).toEqual({
      installed: [],
      installed_count: 0,
    });
  });

  it('degrades to zero rather than throwing on malformed input', async () => {
    // Called from the scan's render path. A machine row carrying a junk
    // `available_agents` must cost us the telemetry, never the onboarding step.
    const { scanPayload } = await loadTelemetry('desktop');
    const empty = { installed: [], installed_count: 0 };
    expect(scanPayload(null)).toEqual(empty);
    expect(scanPayload(undefined)).toEqual(empty);
    expect(scanPayload({} as never)).toEqual(empty);
    expect(scanPayload([null, undefined] as never)).toEqual(empty);
  });

  it('ignores rows whose id is not a string', async () => {
    const { scanPayload } = await loadTelemetry('desktop');
    expect(
      scanPayload([
        { id: 42, label: 'junk', installed: true },
        { id: 'claude', label: 'Claude Code', installed: true },
      ] as never),
    ).toEqual({ installed: ['claude'], installed_count: 1 });
  });
});

describe('step events', () => {
  let t: Telemetry;
  beforeEach(async () => {
    t = await loadTelemetry('desktop');
    vi.clearAllMocks();
  });

  it('intro_started carries no payload', () => {
    t.trackIntroStarted();
    expect(onlyCapture()).toEqual(['desktop_onboarding_intro_started', undefined]);
  });

  it('intro_step_viewed carries the slide index and id', () => {
    t.trackIntroStepViewed(2, 'sync');
    expect(onlyCapture()).toEqual([
      'desktop_onboarding_intro_step_viewed',
      { step_index: 2, step_id: 'sync' },
    ]);
  });

  it('intro_completed distinguishes Skip from Get started', () => {
    t.trackIntroCompleted(true, 2);
    expect(onlyCapture()).toEqual([
      'desktop_onboarding_intro_completed',
      { skipped: true, steps_completed: 2 },
    ]);
  });

  it('signin_started names the handoff method', () => {
    t.trackSignInStarted();
    expect(onlyCapture()).toEqual([
      'desktop_onboarding_signin_started',
      { method: 'browser_handoff' },
    ]);
  });

  it('signin_returned carries the outcome — the only step that fails in another app', () => {
    for (const outcome of ['success', 'mismatch', 'error'] as const) {
      mockPosthog.capture.mockClear();
      t.trackSignInReturned(outcome);
      expect(onlyCapture()).toEqual(['desktop_onboarding_signin_returned', { outcome }]);
    }
  });

  it('scan_viewed carries no payload', () => {
    t.trackScanViewed();
    expect(onlyCapture()).toEqual(['desktop_onboarding_scan_viewed', undefined]);
  });

  it('scan_completed merges the scan payload with the phase', () => {
    t.trackScanCompleted([{ id: 'claude', label: 'Claude Code', installed: true }], 'found');
    expect(onlyCapture()).toEqual([
      'desktop_onboarding_scan_completed',
      { installed: ['claude'], installed_count: 1, phase: 'found' },
    ]);
  });

  it('scan_completed reports an empty phase with a zeroed payload', () => {
    t.trackScanCompleted(null, 'empty');
    expect(onlyCapture()).toEqual([
      'desktop_onboarding_scan_completed',
      { installed: [], installed_count: 0, phase: 'empty' },
    ]);
  });

  it('scan_rescanned carries the count at press time', () => {
    t.trackScanRescanned(0);
    expect(onlyCapture()).toEqual(['desktop_onboarding_scan_rescanned', { installed_count: 0 }]);
  });

  it('scan_continued records whether the user had nothing installed', () => {
    t.trackScanContinued(true);
    expect(onlyCapture()).toEqual(['desktop_onboarding_scan_continued', { skipped: true }]);
  });

  it('onboarding_completed carries the final count and the paywall outcome', () => {
    t.trackOnboardingCompleted(2, false);
    expect(onlyCapture()).toEqual([
      'desktop_onboarding_completed',
      { installed_count: 2, paywall_skipped: false },
    ]);
  });
});

describe('shared business events', () => {
  let t: Telemetry;
  beforeEach(async () => {
    t = await loadTelemetry('desktop');
    vi.clearAllMocks();
  });

  it('uses mobile\'s paywall_opened, not a desktop_ name', () => {
    t.trackPaywallOpened();
    expect(onlyCapture()).toEqual(['paywall_opened', undefined]);
  });

  it('uses mobile\'s paywall_declined', () => {
    t.trackPaywallDeclined('annual');
    expect(onlyCapture()).toEqual(['paywall_declined', { interval: 'annual' }]);
  });

  it('matches web\'s {plan, interval} payload on pricing_cta_clicked', () => {
    // pricing-cards.tsx emits {plan:'pro', interval}. A mismatched shape here
    // would make the merged cross-surface event unqueryable.
    t.trackPricingCtaClicked('monthly');
    expect(onlyCapture()).toEqual(['pricing_cta_clicked', { plan: 'pro', interval: 'monthly' }]);
  });

  it('matches web\'s payload on checkout_started', () => {
    t.trackCheckoutStarted('annual');
    expect(onlyCapture()).toEqual(['checkout_started', { plan: 'pro', interval: 'annual' }]);
  });

  it('checkout_failed carries the API status and is distinct from checkout_abandoned', () => {
    t.trackCheckoutFailed('annual', 500);
    expect(onlyCapture()).toEqual([
      'checkout_failed',
      { plan: 'pro', interval: 'annual', status: 500 },
    ]);
  });

  it('checkout_failed tolerates a status-less error', () => {
    t.trackCheckoutFailed('monthly', null);
    expect(onlyCapture()).toEqual([
      'checkout_failed',
      { plan: 'pro', interval: 'monthly', status: null },
    ]);
  });

  it('keeps paywall_skipped_entitled desktop-specific — no other surface has it', () => {
    t.trackPaywallSkippedEntitled('apple');
    expect(onlyCapture()).toEqual(['desktop_paywall_skipped_entitled', { provider: 'apple' }]);
  });
});

describe('trackAppOpened', () => {
  it('fires the open event with first_run and app_version', async () => {
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();

    t.trackAppOpened({ first_run: true, app_version: '1.2.3' });

    expect(onlyCapture()).toEqual([
      'desktop_app_opened',
      { first_run: true, app_version: '1.2.3' },
    ]);
  });

  it('tolerates a null app_version (updates bridge absent)', async () => {
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();

    t.trackAppOpened({ first_run: false, app_version: null });

    expect(onlyCapture()).toEqual([
      'desktop_app_opened',
      { first_run: false, app_version: null },
    ]);
  });

  it('fires once per load, not once per gate mount (StrictMode / nested gate)', async () => {
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();

    t.trackAppOpened({ first_run: true, app_version: '1.2.3' });
    t.trackAppOpened({ first_run: true, app_version: '1.2.3' });
    t.trackAppOpened({ first_run: true, app_version: '1.2.3' });

    expect(mockPosthog.capture).toHaveBeenCalledTimes(1);
  });
});

describe('trackFirstMessageSent', () => {
  it('fires the desktop event and guard key on desktop', async () => {
    const t = await loadTelemetry('desktop');
    const store = memoryStorage();
    vi.clearAllMocks();

    t.trackFirstMessageSent();

    expect(onlyCapture()).toEqual(['first_desktop_message_sent', undefined]);
    expect(store['vicoa:first_desktop_message_sent']).toBe('1');
  });

  it('fires the web event on web, under the pre-existing guard key', async () => {
    // The key must stay byte-identical to the one the inline code used, or
    // every already-activated web user re-fires activation on their next message.
    const t = await loadTelemetry('web');
    const store = memoryStorage();
    vi.clearAllMocks();

    t.trackFirstMessageSent();

    expect(onlyCapture()).toEqual(['first_web_message_sent', undefined]);
    expect(store['vicoa:first_web_message_sent']).toBe('1');
  });

  it('does not re-fire for an install that already activated', async () => {
    const t = await loadTelemetry('web');
    stubStorage({ getItem: () => '1', setItem: () => {} });
    vi.clearAllMocks();

    t.trackFirstMessageSent();

    expect(mockPosthog.capture).not.toHaveBeenCalled();
  });

  it('fires once, not once per message', async () => {
    const t = await loadTelemetry('web');
    memoryStorage();
    vi.clearAllMocks();

    t.trackFirstMessageSent();
    t.trackFirstMessageSent();
    t.trackFirstMessageSent();

    expect(mockPosthog.capture).toHaveBeenCalledTimes(1);
  });

  it('still fires once when storage throws, and never throws itself', async () => {
    // Private mode / disabled storage. This used to run inside the chat page's
    // send try-block, where the throw rolled back a delivered message and
    // alerted "Failed to send message". The in-memory guard caps the fallout at
    // one event per page load.
    const t = await loadTelemetry('web');
    stubStorage({
      getItem: () => {
        throw new Error('storage disabled');
      },
      setItem: () => {
        throw new Error('storage disabled');
      },
    });
    vi.clearAllMocks();

    expect(() => {
      t.trackFirstMessageSent();
      t.trackFirstMessageSent();
    }).not.toThrow();
    expect(mockPosthog.capture).toHaveBeenCalledTimes(1);
    expect(mockPosthog.capture).toHaveBeenCalledWith('first_web_message_sent', undefined);
  });
});

describe('identity', () => {
  it('identifies with the Supabase uuid and email', async () => {
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();

    t.identifyDesktopUser('uuid-1', 'a@example.com');

    expect(mockPosthog.identify).toHaveBeenCalledExactlyOnceWith('uuid-1', {
      email: 'a@example.com',
    });
  });

  it('omits the property bag when there is no email', async () => {
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();

    t.identifyDesktopUser('uuid-1', null);

    expect(mockPosthog.identify).toHaveBeenCalledExactlyOnceWith('uuid-1', undefined);
  });

  it('does not re-identify the same user on a token refresh', async () => {
    // onAuthStateChange fires on TOKEN_REFRESHED too; re-identifying there
    // would emit a $set event roughly hourly, per user, forever.
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();

    t.identifyDesktopUser('uuid-1', 'a@example.com');
    t.identifyDesktopUser('uuid-1', 'a@example.com');

    expect(mockPosthog.identify).toHaveBeenCalledTimes(1);
  });

  it('identifies a different user after a reset — shared hardware', async () => {
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();

    t.identifyDesktopUser('uuid-a');
    t.resetIdentity();
    t.identifyDesktopUser('uuid-b');

    expect(mockPosthog.reset).toHaveBeenCalledTimes(1);
    expect(mockPosthog.identify).toHaveBeenCalledTimes(2);
    expect(mockPosthog.identify).toHaveBeenLastCalledWith('uuid-b', undefined);
  });

  it('re-identifies user B even though A signed out on the same machine', async () => {
    // The whole point of reset() here: without it, B inherits A's person.
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();

    t.identifyDesktopUser('uuid-a');
    t.resetIdentity();
    t.identifyDesktopUser('uuid-a');

    expect(mockPosthog.identify).toHaveBeenCalledTimes(2);
  });

  it('swallows a throwing identify — auth must not fail on telemetry', async () => {
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();
    mockPosthog.identify.mockImplementationOnce(() => {
      throw new Error('posthog exploded');
    });

    expect(() => t.identifyDesktopUser('uuid-1')).not.toThrow();
  });

  it('swallows a throwing reset — sign-out must not fail on telemetry', async () => {
    const t = await loadTelemetry('desktop');
    vi.clearAllMocks();
    mockPosthog.reset.mockImplementationOnce(() => {
      throw new Error('posthog exploded');
    });

    expect(() => t.resetIdentity()).not.toThrow();
  });
});
