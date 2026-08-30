/**
 * Desktop session notifications — renderer side of the preload bridge.
 *
 * The dashboard already receives every instance status change over the shared
 * WebSocket (agent-dashboard-context applies them to `recentInstances`), so
 * notifications are a pure local reaction: diff consecutive snapshots of that
 * list, and for transitions into a notify-worthy status ask the Electron main
 * process to show a native banner (see `use-desktop-session-notifications.ts`
 * for the delivery policy — background-only, user toggle).
 *
 * Null bridge on plain web / SSR — every consumer no-ops there.
 */

import { getPref, setPref } from '@/lib/desktop-prefs';

export interface SessionNotificationPayload {
  /** Empty string = no session to route to on click (test notification). */
  instanceId: string;
  title: string;
  body: string;
}

export type NotificationAuthorizationStatus =
  | 'authorized'
  | 'denied'
  | 'not-determined'
  | 'unknown';

export interface DesktopNotificationsBridge {
  notify: (payload: SessionNotificationPayload) => void;
  setBadgeCount: (count: number) => void;
  onNavigate: (cb: (path: string) => void) => () => void;
  /** Opens macOS System Settings on Vicoa's Notifications pane. */
  openNotificationSettings: () => Promise<void>;
  /** Real macOS authorization via the bundled helper; null when unavailable. */
  getAuthorizationStatus?: () => Promise<NotificationAuthorizationStatus | null>;
}

/**
 * Read the app's real macOS notification authorization. Resolves null on
 * web, in dev runs (no bundled helper), or on any failure — callers should
 * treat null as "unknown, assume the user may need help".
 */
export async function readNotificationAuthorization(): Promise<NotificationAuthorizationStatus | null> {
  const bridge = getDesktopNotificationsBridge();
  if (bridge === null || typeof bridge.getAuthorizationStatus !== 'function') return null;
  try {
    return await bridge.getAuthorizationStatus();
  } catch {
    return null;
  }
}

export function getDesktopNotificationsBridge(): DesktopNotificationsBridge | null {
  if (typeof window === 'undefined') return null;
  const bridge = (window as unknown as { vicoaDesktopNotifications?: DesktopNotificationsBridge })
    .vicoaDesktopNotifications;
  return bridge && typeof bridge.notify === 'function' ? bridge : null;
}

// ---------------------------------------------------------------------------
// User preference (Settings → General → Notifications). Banners only — the
// dock badge mirrors the sidebar's awaiting-input indicator and is not gated
// by this.
// ---------------------------------------------------------------------------

/**
 * When to show session banners:
 * - 'never'     — no banners at all;
 * - 'unfocused' — only while the window is hidden or behind another app;
 * - 'always'    — every notify-worthy transition, focused or not.
 */
export type NotificationMode = 'never' | 'unfocused' | 'always';

const NOTIFICATIONS_MODE_KEY = 'desktop-notifications-mode';
/** Pre-mode boolean toggle; read once for migration, never written anymore. */
const LEGACY_ENABLED_KEY = 'desktop-notifications-enabled';

export function getDesktopNotificationsMode(): NotificationMode {
  const value = getPref<string>(NOTIFICATIONS_MODE_KEY);
  if (value === 'never' || value === 'unfocused' || value === 'always') {
    return value;
  }
  // Migrate the retired on/off toggle: off -> never; on/unset -> the old
  // delivery behavior (background-only).
  const legacy = getPref<boolean | string>(LEGACY_ENABLED_KEY);
  return legacy === false || legacy === 'false' ? 'never' : 'unfocused';
}

export function setDesktopNotificationsMode(mode: NotificationMode): void {
  setPref(NOTIFICATIONS_MODE_KEY, mode);
}

// ---------------------------------------------------------------------------
// Phone-push foreground mute (Settings → General → Notifications). When on
// (the default), the desktop app reports its window foreground state to the
// backend over the shared WebSocket; the backend then suppresses the FCM phone
// push while the user is actively looking at the desktop app — mirroring the
// "Only when unfocused" banner policy, but for the phone. Desktop-only: the
// plain-web build never reports foreground, so it never suppresses.
// ---------------------------------------------------------------------------

const SILENCE_PHONE_WHEN_FOCUSED_KEY = 'phone-push-silence-when-focused';

/** Fired on window whenever the phone-mute preference changes. */
const SILENCE_PHONE_EVENT = 'vicoa-desktop-phone-mute-changed';

export function getSilencePhoneWhenFocused(): boolean {
  // Default on: don't double-notify someone already looking at the desktop app.
  return getPref<boolean>(SILENCE_PHONE_WHEN_FOCUSED_KEY) !== false;
}

export function setSilencePhoneWhenFocused(value: boolean): void {
  setPref(SILENCE_PHONE_WHEN_FOCUSED_KEY, value);
  try {
    window.dispatchEvent(new Event(SILENCE_PHONE_EVENT));
  } catch {
    // No window (SSR) — nothing subscribes there anyway.
  }
}

/** Subscribe to phone-mute preference changes. Returns an unsubscribe fn. */
export function onSilencePhoneWhenFocusedChange(cb: (value: boolean) => void): () => void {
  const handler = () => cb(getSilencePhoneWhenFocused());
  window.addEventListener(SILENCE_PHONE_EVENT, handler);
  return () => window.removeEventListener(SILENCE_PHONE_EVENT, handler);
}

// ---------------------------------------------------------------------------
// One-time System Settings nudge. macOS notification authorization state is
// not queryable from stock Electron (renderer Notification.permission always
// reads "granted"; UNUserNotificationCenter needs a native module), so the
// nudge is blind: after the FIRST real session banner is posted, an in-app
// bar offers the System Settings jump once, until dismissed.
// ---------------------------------------------------------------------------

const FIRST_BANNER_SENT_KEY = 'desktop-notifications-first-sent';
const NUDGE_DISMISSED_KEY = 'desktop-notifications-nudge-dismissed';

/** Fired on window whenever the nudge's localStorage state changes. */
export const NOTIFICATION_NUDGE_EVENT = 'vicoa-desktop-notification-nudge';

/** Record that a real session banner went out (settings test banners don't). */
export function markSessionBannerSent(): void {
  try {
    if (window.localStorage.getItem(FIRST_BANNER_SENT_KEY) !== null) return;
    window.localStorage.setItem(FIRST_BANNER_SENT_KEY, new Date().toISOString());
    window.dispatchEvent(new Event(NOTIFICATION_NUDGE_EVENT));
  } catch {
    // localStorage unavailable — the nudge just never shows.
  }
}

export function shouldShowNotificationNudge(): boolean {
  try {
    return (
      window.localStorage.getItem(FIRST_BANNER_SENT_KEY) !== null &&
      window.localStorage.getItem(NUDGE_DISMISSED_KEY) === null
    );
  } catch {
    return false;
  }
}

export function dismissNotificationNudge(): void {
  try {
    window.localStorage.setItem(NUDGE_DISMISSED_KEY, new Date().toISOString());
    window.dispatchEvent(new Event(NOTIFICATION_NUDGE_EVENT));
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Snapshot diffing (pure — unit-tested in desktop-notifications.test.ts)
// ---------------------------------------------------------------------------

/** Statuses whose *transitions into* surface a banner, with the banner copy. */
const NOTIFY_BODY: Readonly<Partial<Record<string, string>>> = {
  AWAITING_INPUT: 'Needs your input',
  COMPLETED: 'Session completed',
  FAILED: 'Session failed',
};

interface SessionStatusRow {
  id: string;
  status: string;
  name?: string | null;
}

export interface SessionStatusDiff {
  /** Snapshot to carry as the next diff's baseline. */
  statuses: Map<string, string>;
  /** One payload per notify-worthy transition since the previous snapshot. */
  transitions: SessionNotificationPayload[];
  /** Sessions currently awaiting input (drives the dock badge). */
  awaitingCount: number;
}

/**
 * Diff an instance-list snapshot against the previous one.
 *
 * - `prev === null` (first snapshot) seeds the baseline without transitions,
 *   so app start / list reset never fires a burst of stale banners.
 * - Ids absent from `prev` are new arrivals, not transitions — skipped. Their
 *   next real status change diffs normally.
 * - Reconnect catch-up diffs like any other update: a session that flipped to
 *   AWAITING_INPUT while the machine slept still produces its banner.
 */
export function diffSessionStatuses(
  prev: Map<string, string> | null,
  instances: readonly SessionStatusRow[],
): SessionStatusDiff {
  const statuses = new Map<string, string>();
  const transitions: SessionNotificationPayload[] = [];
  let awaitingCount = 0;

  for (const instance of instances) {
    statuses.set(instance.id, instance.status);
    if (instance.status === 'AWAITING_INPUT') {
      awaitingCount += 1;
    }
    if (prev === null) continue;
    const before = prev.get(instance.id);
    if (before === undefined || before === instance.status) continue;
    const body = NOTIFY_BODY[instance.status];
    if (body === undefined) continue;
    transitions.push({
      instanceId: instance.id,
      title: instance.name?.trim() || 'Vicoa session',
      body,
    });
  }

  return { statuses, transitions, awaitingCount };
}
