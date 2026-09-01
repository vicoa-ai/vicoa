'use client';

import { Suspense, useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, Bot, Folder, Keyboard, Monitor, Settings, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { DesktopTitlebarLead } from '@/components/desktop/window-chrome';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { projectSettingsTargets } from '@/components/dashboard/session-grouping';

/**
 * Left panel while the desktop app is on /dashboard/settings: replaces the
 * session list with a settings nav — "← Back to app" on top, then one entry
 * per settings tab. The active tab renders in the middle panel
 * (DesktopSettings); there is no right panel on settings routes.
 */

/** sessionStorage key: last non-settings dashboard path, written by the shell,
    so "Back to app" returns exactly where the user left off. */
export const DESKTOP_LAST_APP_PATH_KEY = 'desktop-last-app-path';

export const DESKTOP_SETTINGS_TABS = [
  { id: 'general', label: 'General', Icon: Settings },
  { id: 'profile', label: 'Profile', Icon: User },
  { id: 'providers', label: 'Providers', Icon: Bot },
  { id: 'machines', label: 'Machines', Icon: Monitor },
  { id: 'shortcuts', label: 'Keyboard shortcuts', Icon: Keyboard },
] as const;

export type DesktopSettingsTab =
  | (typeof DESKTOP_SETTINGS_TABS)[number]['id']
  | 'project';

/** Resolve the ?tab= param to a known tab (general is the default). `project`
    is the dynamic per-project pane (carries machineId+dir params). */
export function activeSettingsTab(tabParam: string | null): DesktopSettingsTab {
  if (tabParam === 'project') return 'project';
  return DESKTOP_SETTINGS_TABS.some((tab) => tab.id === tabParam)
    ? (tabParam as DesktopSettingsTab)
    : 'general';
}

export function DesktopSettingsSidebar() {
  return (
    // useSearchParams needs a Suspense boundary during prerender; the fallback
    // keeps the panel's frame so the layout doesn't jump.
    <Suspense
      fallback={<aside className="w-64 shrink-0 border-r border-border bg-[#272726]" aria-hidden />}
    >
      <DesktopSettingsSidebarInner />
    </Suspense>
  );
}

function DesktopSettingsSidebarInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = activeSettingsTab(searchParams.get('tab'));
  const activeMachineId = searchParams.get('machineId') ?? '';
  const activeDir = searchParams.get('dir') ?? '';
  const { recentInstances } = useAgentDashboard();
  const projectTargets = useMemo(() => projectSettingsTargets(recentInstances), [recentInstances]);

  const backToApp = useCallback(() => {
    let target: string | null = null;
    try {
      target = window.sessionStorage.getItem(DESKTOP_LAST_APP_PATH_KEY);
    } catch {
      // sessionStorage unavailable — fall back to the dashboard root.
    }
    router.push(target || '/dashboard');
  }, [router]);

  return (
    <aside className="relative z-10 flex h-full w-64 shrink-0 flex-col border-r border-border bg-[#272726] font-mono text-sm">
      {/* Titlebar strip (window drag region), reserving the traffic lights. */}
      <div
        style={DRAG_REGION}
        className="flex h-11 shrink-0 items-center gap-1.5 border-b border-border/60 pl-2 pr-2"
      >
        <DesktopTitlebarLead />
      </div>

      <div className="px-2 pt-2">
        <button
          type="button"
          onClick={backToApp}
          style={NO_DRAG}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-foreground/10 hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to app
        </button>
      </div>

      <div className="px-4 pt-3 pb-1">
        <span className="text-xs font-light text-muted-foreground/70">Settings</span>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 custom-scrollbar">
        {DESKTOP_SETTINGS_TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() =>
              router.replace(id === 'general' ? '/dashboard/settings' : `/dashboard/settings?tab=${id}`)
            }
            className={cn(
              'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors',
              tab === id
                ? 'bg-foreground/10 text-foreground'
                : 'text-muted-foreground hover:bg-foreground/10 hover:text-foreground',
            )}
          >
            <Icon className="h-3.5 w-3.5 shrink-0" />
            {label}
          </button>
        ))}

        {projectTargets.length > 0 && (
          <>
            <div className="px-2 pt-4 pb-1 text-xs font-light text-muted-foreground/70">
              Projects
            </div>
            {projectTargets.map((target) => {
              const active =
                tab === 'project' &&
                activeMachineId === target.machineId &&
                activeDir === target.dir;
              return (
                <button
                  key={target.key}
                  type="button"
                  onClick={() =>
                    router.replace(
                      `/dashboard/settings?tab=project&machineId=${encodeURIComponent(
                        target.machineId,
                      )}&dir=${encodeURIComponent(target.dir)}&label=${encodeURIComponent(target.label)}`,
                    )
                  }
                  className={cn(
                    'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors',
                    active
                      ? 'bg-foreground/10 text-foreground'
                      : 'text-muted-foreground hover:bg-foreground/10 hover:text-foreground',
                  )}
                >
                  <Folder className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{target.label}</span>
                </button>
              );
            })}
          </>
        )}
      </nav>
    </aside>
  );
}
