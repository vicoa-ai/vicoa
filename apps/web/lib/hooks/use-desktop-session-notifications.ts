'use client';

/**
 * Desktop-shell reactions to the dashboard's live instance list: native
 * banners on notify-worthy status transitions and the dock badge count.
 * Mounted once inside AgentDashboardProvider so every update path — WS
 * frames, the chat page's manual status patches, REST refreshes — funnels
 * through the same `recentInstances` diff. No-ops on plain web (null bridge).
 */

import { useEffect, useRef } from 'react';
import type { AgentInstanceResponse } from '@/lib/backend-api';
import {
  diffSessionStatuses,
  getDesktopNotificationsBridge,
  getDesktopNotificationsMode,
  markSessionBannerSent,
} from '@/lib/desktop-notifications';

export function useDesktopSessionNotifications(instances: AgentInstanceResponse[]): void {
  const prevStatusesRef = useRef<Map<string, string> | null>(null);
  const lastBadgeRef = useRef<number | null>(null);

  useEffect(() => {
    const bridge = getDesktopNotificationsBridge();
    if (bridge === null) return;

    const { statuses, transitions, awaitingCount } = diffSessionStatuses(
      prevStatusesRef.current,
      instances,
    );
    prevStatusesRef.current = statuses;

    if (lastBadgeRef.current !== awaitingCount) {
      lastBadgeRef.current = awaitingCount;
      bridge.setBadgeCount(awaitingCount);
    }

    // Delivery policy comes from the mode preference. The transition is
    // consumed either way, so refocusing later never replays stale banners.
    if (transitions.length === 0) return;
    const mode = getDesktopNotificationsMode();
    if (mode === 'never') return;
    // 'unfocused' (default): banners only while the window is in the
    // background — in the foreground the sidebar's status dot already has
    // the user's attention. 'always' skips the focus check.
    if (mode === 'unfocused' && document.hasFocus()) return;
    for (const transition of transitions) {
      bridge.notify(transition);
    }
    // Arms the one-time "didn't see it? open System Settings" nudge.
    markSessionBannerSent();
  }, [instances]);
}

/**
 * Routes notification clicks: main focuses/re-shows the window and sends the
 * session path over the preload bridge; this hook pushes it into the router.
 */
export function useDesktopNotificationNavigation(navigate: (path: string) => void): void {
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  useEffect(() => {
    const bridge = getDesktopNotificationsBridge();
    if (bridge === null) return;
    return bridge.onNavigate((path) => {
      // Main only ever sends /dashboard/agents/<id>; anything else is dropped.
      if (typeof path === 'string' && path.startsWith('/dashboard/')) {
        navigateRef.current(path);
      }
    });
  }, []);
}
