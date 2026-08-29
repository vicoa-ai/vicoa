/**
 * Desktop onboarding progress flags.
 *
 * Two independent milestones, both per-install:
 *
 *  - INTRO  — the pre-auth welcome/value slides. Seen once, then the app rests
 *             on /desktop-welcome (sign-in) on every later signed-out launch.
 *  - SETUP  — the post-auth agent scan + paywall. Done once, then the app goes
 *             straight to /dashboard.
 *
 * Per-install (localStorage) rather than per-user (backend) is deliberate: the
 * scan half of setup is inherently about *this machine*, and keeping the flags
 * local means the flow ships without a schema change. The cost is that a
 * reinstall re-onboards — which for the scan is arguably correct.
 *
 * Every read fails to `false`. Re-showing the intro is a mildly annoying
 * failure; locking someone out of it is not.
 */

export const DESKTOP_INTRO_KEY = 'vicoa_desktop_intro_v1_seen';
export const DESKTOP_SETUP_KEY = 'vicoa_desktop_setup_v1_done';

function readFlag(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === 'true';
  } catch {
    // localStorage can throw (private mode, disabled storage, quota). Treat an
    // unreadable flag as "not done" so the step simply runs again.
    return false;
  }
}

function writeFlag(key: string): void {
  try {
    window.localStorage.setItem(key, 'true');
  } catch {
    // Non-fatal: the step replays next launch. Blocking the user on a storage
    // write would be a far worse outcome than repeating the intro.
  }
}

export function hasSeenDesktopIntro(): boolean {
  return readFlag(DESKTOP_INTRO_KEY);
}

export function markDesktopIntroSeen(): void {
  writeFlag(DESKTOP_INTRO_KEY);
}

export function hasCompletedDesktopSetup(): boolean {
  return readFlag(DESKTOP_SETUP_KEY);
}

export function markDesktopSetupDone(): void {
  writeFlag(DESKTOP_SETUP_KEY);
}
