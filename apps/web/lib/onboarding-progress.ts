'use client';

/**
 * Same-document nudge that a piece of onboarding progress just happened in THIS
 * client — e.g. the user created their first task or automation.
 *
 * The setup checklist ("Onboarding" card) derives each row from a live backend
 * read, but those reads only re-run when the agent-instance list changes.
 * Creating a task or automation touches neither the instance list nor the
 * WebSocket instance stream, so without a nudge the card sits stale until a
 * page reload. Emit `notifyOnboardingProgress()` right after such a create call
 * resolves; the card listens via `subscribeOnboardingProgress` and re-checks
 * its still-incomplete steps.
 *
 * (The "Send your first message" step needs no emit here — it's already covered
 * by the WS new-message stream advancing each session's `latest_message_at`.)
 */

const ONBOARDING_PROGRESS_EVENT = 'vicoa:onboarding-progress';

export function notifyOnboardingProgress(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event(ONBOARDING_PROGRESS_EVENT));
}

/** Subscribe to onboarding-progress nudges; returns an unsubscribe fn. */
export function subscribeOnboardingProgress(callback: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(ONBOARDING_PROGRESS_EVENT, callback);
  return () => window.removeEventListener(ONBOARDING_PROGRESS_EVENT, callback);
}
