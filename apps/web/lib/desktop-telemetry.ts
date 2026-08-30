/**
 * The desktop onboarding event vocabulary — the single owner of every event
 * name, payload shape, and identity call the desktop funnel emits.
 *
 * **Why a module and not inline `posthog.capture('some_string', {...})`:** the
 * rest of the web app has ~28 scattered capture sites with no shared
 * definition, and the consequences are on the record — the canonical event list
 * had to be reverse-engineered from source into
 * `.claude/skills/posthog-analytics/SKILL.md`, and `source` silently acquired
 * two meanings (surface vs. trigger reason). The desktop events reproduced the
 * pattern immediately: 14 raw strings that drifted from their own design doc
 * inside a day. Names and payloads are string-literal-union typed here, so a
 * typo is a build error rather than an event that quietly goes nowhere.
 *
 * **Governing constraint: no telemetry failure may block onboarding.** Captures
 * are fire-and-forget (`posthog-js` does not throw from `capture`, and no-ops
 * entirely on a missing token); `identify`/`reset` are wrapped, matching the
 * localStorage discipline in `desktop-auth.ts` and `desktop-onboarding.ts`.
 *
 * Naming is deliberately split:
 *  - `desktop_onboarding_*` for step events, which have no web/mobile analogue
 *    (mobile onboards through survey/news/personalizing; desktop scans a
 *    machine for agents). Splitting also sidesteps the three-way `onboarding_*`
 *    conflation the posthog-analytics skill already warns about.
 *  - **existing shared names** for cross-surface business events (paywall,
 *    checkout, activation), which are only worth anything if they compare
 *    across surfaces. Each adopts whichever name already exists — `paywall_*`
 *    from mobile, `checkout_*` from web — so the event spans the two surfaces
 *    that can meaningfully be compared.
 */

import posthog from 'posthog-js';
import type { BillingInterval } from '@/lib/backend-api';
import type { ScannedAgent } from '@/lib/desktop-agent-scan';

/**
 * Which app this bundle is.
 *
 * Compile-time, matching the `posthog-identify.tsx` / `desktop-auth-gate.tsx`
 * precedent: `build-renderer.mjs` bakes `NEXT_PUBLIC_VICOA_DESKTOP=1` into the
 * desktop renderer bundle, so this folds to a constant per build.
 *
 * Known limitation: the **dev shell** (`next dev` on :3000) has no such flag
 * and therefore tags `source: 'web'` — dogfooding lands in the web funnel. A
 * runtime `getDesktopConfig()` read would fix it, but this value is consumed by
 * `instrumentation-client.ts` at client init, before the preload global is a
 * safe read. One developer against ~2,000 web landers/month; accepted, not
 * fixed.
 */
export const SURFACE: 'desktop' | 'web' =
  process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1' ? 'desktop' : 'web';

/** Agent ids installed on this machine, plus their count. */
export interface ScanPayload {
  installed: string[];
  installed_count: number;
}

/**
 * The event catalog: name → payload shape.
 *
 * Every desktop event in the product is on this list. If it isn't here, it
 * cannot be captured through this module — which is the point.
 */
type EventMap = {
  // ── App lifecycle ─────────────────────────────────────────────────────────
  /**
   * The desktop app was launched. Fires once per renderer load (≈ once per app
   * open) from `DesktopAuthGate`, BEFORE any onboarding/auth branch — so unlike
   * `desktop_onboarding_intro_started` (which fires only on the first-run intro)
   * it also captures **returning** users reopening an already-onboarded app.
   * This is the open signal the download→open→activate funnel needs; without it
   * "did they open the app after installing?" is unanswerable for anyone who
   * skips or has already seen onboarding.
   *
   * `first_run` is true on a machine that has never seen the intro. Mac-vs-
   * Windows split comes free from the autocaptured `$os`; `app_version` is
   * carried here because Electron's app version is not in the user agent, so
   * posthog-js cannot autocapture it (`$app_version` is a mobile-SDK property).
   */
  desktop_app_opened: { first_run: boolean; app_version: string | null };

  // ── Step funnel ───────────────────────────────────────────────────────────
  desktop_onboarding_intro_started: Record<string, never>;
  desktop_onboarding_intro_step_viewed: { step_index: number; step_id: string };
  desktop_onboarding_intro_completed: { skipped: boolean; steps_completed: number };
  desktop_onboarding_signin_started: { method: 'browser_handoff' };
  desktop_onboarding_signin_returned: { outcome: SignInOutcome };
  desktop_onboarding_scan_viewed: Record<string, never>;
  desktop_onboarding_scan_completed: ScanPayload & { phase: 'found' | 'empty' };
  desktop_onboarding_scan_rescanned: { installed_count: number };
  desktop_onboarding_scan_continued: { skipped: boolean };
  desktop_onboarding_completed: { installed_count: number; paywall_skipped: boolean };

  // ── Shared business events (existing names, split by the `source` super
  //    property rather than by a name prefix) ────────────────────────────────
  paywall_opened: Record<string, never>;
  paywall_declined: { interval: BillingInterval };
  pricing_cta_clicked: { plan: 'pro'; interval: BillingInterval };
  checkout_started: { plan: 'pro'; interval: BillingInterval };
  checkout_failed: { plan: 'pro'; interval: BillingInterval; status: number | null };
  first_web_message_sent: Record<string, never>;
  first_desktop_message_sent: Record<string, never>;

  // ── Desktop-only ──────────────────────────────────────────────────────────
  /**
   * An already-entitled user (typically an iOS/Android subscriber — the backend
   * keeps one subscription row per user with a `provider` column) was correctly
   * NOT re-prompted. No other surface has this concept, so it keeps its
   * desktop-specific name.
   */
  desktop_paywall_skipped_entitled: { provider: string | null };
};

type EventName = keyof EventMap;

/** Sole capture seam. Typed so an unknown name or a wrong payload won't build. */
function capture<E extends EventName>(
  event: E,
  ...[payload]: EventMap[E] extends Record<string, never> ? [] : [EventMap[E]]
): void {
  posthog.capture(event, payload);
}

// ── App lifecycle ─────────────────────────────────────────────────────────

/**
 * Once-per-load guard. `DesktopAuthGate` can mount more than once (StrictMode's
 * double-invoke in dev; a nested gate), and a single launch must be one open.
 */
let appOpenedFired = false;

/**
 * The desktop app was opened. Fire-and-forget from `DesktopAuthGate`'s mount,
 * on every launch regardless of auth/onboarding state.
 */
export function trackAppOpened(payload: { first_run: boolean; app_version: string | null }): void {
  if (appOpenedFired) return;
  appOpenedFired = true;
  capture('desktop_app_opened', payload);
}

// ── Intro (pre-auth) ────────────────────────────────────────────────────────

export function trackIntroStarted(): void {
  capture('desktop_onboarding_intro_started');
}

export function trackIntroStepViewed(stepIndex: number, stepId: string): void {
  capture('desktop_onboarding_intro_step_viewed', { step_index: stepIndex, step_id: stepId });
}

export function trackIntroCompleted(skipped: boolean, stepsCompleted: number): void {
  capture('desktop_onboarding_intro_completed', { skipped, steps_completed: stepsCompleted });
}

// ── Sign-in handoff ─────────────────────────────────────────────────────────

export type SignInOutcome = 'success' | 'mismatch' | 'error';

export function trackSignInStarted(): void {
  // `method` is a constant today, but the browser handoff is not the only
  // conceivable desktop sign-in (an in-window flow has been floated), and a
  // one-valued property is far cheaper now than a rename later.
  capture('desktop_onboarding_signin_started', { method: 'browser_handoff' });
}

export function trackSignInReturned(outcome: SignInOutcome): void {
  capture('desktop_onboarding_signin_returned', { outcome });
}

// ── Agent scan ──────────────────────────────────────────────────────────────

/**
 * Which agents are installed, and how many.
 *
 * Bounded to the agents Vicoa's own catalog knows about — this is emphatically
 * not a machine inventory. It answers the two questions the scan step exists to
 * answer: what share of installs can never activate (`installed_count === 0`),
 * and which agent to prioritise.
 *
 * Anything other than a real array reads as "we don't know" → zero, rather than
 * throwing: this is called from the scan's render path, and a malformed
 * `available_agents` on a machine row must degrade the telemetry, not the
 * onboarding step.
 */
export function scanPayload(agents: readonly ScannedAgent[] | null | undefined): ScanPayload {
  if (!Array.isArray(agents)) return { installed: [], installed_count: 0 };
  const installed = agents
    .filter((agent) => agent?.installed === true && typeof agent.id === 'string')
    .map((agent) => agent.id);
  return { installed, installed_count: installed.length };
}

export function trackScanViewed(): void {
  capture('desktop_onboarding_scan_viewed');
}

/**
 * The scan settled.
 *
 * `phase: 'empty'` means the machine had not appeared after the empty-timeout —
 * the user is watching "Starting up…". It is NOT terminal: the poll keeps
 * running, so a slow daemon emits `empty` and then `found`. Treat `found` as
 * the authoritative outcome for a person and `empty` as "waited through the
 * timeout"; querying the LAST `desktop_onboarding_scan_completed` per person
 * gives the right answer either way.
 */
export function trackScanCompleted(
  agents: readonly ScannedAgent[] | null | undefined,
  phase: 'found' | 'empty',
): void {
  capture('desktop_onboarding_scan_completed', { ...scanPayload(agents), phase });
}

/**
 * Rescan pressed. `installed_count` is the count **at press time** — i.e. the
 * state the user was looking at when they decided to press, which is the thing
 * that explains the press ("I had none, I installed one, let me re-check").
 * Whether it worked is answered by the `installed_count` on the subsequent
 * `desktop_onboarding_completed`.
 */
export function trackScanRescanned(installedCount: number): void {
  capture('desktop_onboarding_scan_rescanned', { installed_count: installedCount });
}

export function trackScanContinued(skipped: boolean): void {
  capture('desktop_onboarding_scan_continued', { skipped });
}

// ── Paywall + checkout ──────────────────────────────────────────────────────

export function trackPaywallOpened(): void {
  capture('paywall_opened');
}

export function trackPaywallDeclined(interval: BillingInterval): void {
  capture('paywall_declined', { interval });
}

export function trackPaywallSkippedEntitled(provider: string | null): void {
  capture('desktop_paywall_skipped_entitled', { provider });
}

export function trackPricingCtaClicked(interval: BillingInterval): void {
  // `plan` matches web's payload (`pricing-cards.tsx`), so the merged event has
  // one shape across both surfaces. Desktop's paywall only sells Pro.
  capture('pricing_cta_clicked', { plan: 'pro', interval });
}

export function trackCheckoutStarted(interval: BillingInterval): void {
  capture('checkout_started', { plan: 'pro', interval });
}

/**
 * Checkout could not be started — an API failure, not a user decision.
 *
 * Deliberately NOT web's `checkout_abandoned`, which means the user closed the
 * Stripe tab. Conflating the two would make a backend outage read as cold feet.
 */
export function trackCheckoutFailed(interval: BillingInterval, status: number | null): void {
  capture('checkout_failed', { plan: 'pro', interval, status });
}

// ── Onboarding complete ─────────────────────────────────────────────────────

export function trackOnboardingCompleted(installedCount: number, paywallSkipped: boolean): void {
  capture('desktop_onboarding_completed', {
    installed_count: installedCount,
    paywall_skipped: paywallSkipped,
  });
}

// ── Activation ──────────────────────────────────────────────────────────────

/**
 * In-memory backstop for the localStorage guard below. Only load-bearing when
 * storage throws (private mode, disabled storage, quota): it holds the event to
 * once per page load instead of once per message.
 */
let firstMessageFired = false;

/**
 * Canonical activation, surface-aware: `first_web_message_sent` on web,
 * `first_desktop_message_sent` on desktop.
 *
 * Owns its own once-per-install guard, keyed per surface. The web key is
 * byte-identical to the one the inline code used (`vicoa:first_web_message_sent`),
 * so existing web installs stay marked and don't re-fire.
 *
 * The guard used to sit inline in the chat page's send `try` block, where a
 * localStorage throw was caught by the *send*'s error handler — rolling back the
 * optimistic message and alerting "Failed to send message" for a message that
 * had in fact been delivered. Telemetry must never be able to do that.
 */
export function trackFirstMessageSent(): void {
  if (firstMessageFired) return;
  const event = SURFACE === 'desktop' ? 'first_desktop_message_sent' : 'first_web_message_sent';
  try {
    const key = `vicoa:${event}`;
    if (window.localStorage.getItem(key)) {
      firstMessageFired = true;
      return;
    }
    window.localStorage.setItem(key, '1');
  } catch {
    // Unreadable storage: fall through and fire. The in-memory guard caps this
    // at one per page load — over-counting a rare cohort slightly beats losing
    // activation for them entirely.
  }
  firstMessageFired = true;
  capture(event);
}

// ── Identity ────────────────────────────────────────────────────────────────

/** Last id handed to `identify`, so a token refresh doesn't re-emit `$set`. */
let lastIdentifiedId: string | null = null;

/**
 * Attach desktop events to the Supabase user.
 *
 * Pre-auth intro events fire against an anonymous id; `identify()` merges them
 * into the person. The browser sign-in leg is a *separate* anonymous id that
 * identifies to the same Supabase UUID, so PostHog merges that too and the
 * funnel joins with no extra work.
 */
export function identifyDesktopUser(userId: string, email?: string | null): void {
  if (lastIdentifiedId === userId) return;
  try {
    posthog.identify(userId, email ? { email } : undefined);
    lastIdentifiedId = userId;
  } catch {
    // Never let an analytics failure surface in an auth path.
  }
}

/**
 * Drop the identified person on sign-out.
 *
 * This matters more on desktop than anywhere else: a Mac is shared physical
 * hardware, so without a reset user B inherits user A's PostHog person and
 * every subsequent event is attributed to the wrong human.
 */
export function resetIdentity(): void {
  try {
    posthog.reset();
    lastIdentifiedId = null;
  } catch {
    // As above.
  }
}
