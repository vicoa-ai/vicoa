'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowLeft,
  Bot,
  ChevronRight,
  Keyboard,
  ListTodo,
  Monitor,
  Palette,
  Puzzle,
  Settings,
  User,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { DesktopTitlebarLead } from '@/components/desktop/window-chrome';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import { PROJECTS_CHANGED_EVENT, projectSettingsHref } from '@/lib/project-settings-route';
import { getBackendAPI, type ProjectResponse } from '@/lib/backend-api';

/**
 * Left panel while the desktop app is on /dashboard/settings: replaces the
 * session list with a settings nav — "← Back to app" on top, then one entry
 * per settings tab, then the user's projects. The active tab renders in the
 * middle panel (DesktopSettings); there is no right panel on settings routes.
 */

/** sessionStorage key: last non-settings dashboard path, written by the shell,
    so "Back to app" returns exactly where the user left off. */
export const DESKTOP_LAST_APP_PATH_KEY = 'desktop-last-app-path';

export const DESKTOP_SETTINGS_TABS = [
  { id: 'general', label: 'General', Icon: Settings },
  { id: 'appearance', label: 'Appearance', Icon: Palette },
  { id: 'profile', label: 'Profile', Icon: User },
  { id: 'providers', label: 'Providers', Icon: Bot },
  { id: 'machines', label: 'Machines', Icon: Monitor },
  { id: 'tasks', label: 'Tasks', Icon: ListTodo },
  { id: 'plugins', label: 'Plugins', Icon: Puzzle },
  { id: 'shortcuts', label: 'Keyboard shortcuts', Icon: Keyboard },
] as const;

export type DesktopSettingsTab =
  | (typeof DESKTOP_SETTINGS_TABS)[number]['id']
  | 'project';

/** Resolve the ?tab= param to a known tab (general is the default). `project`
    is the dynamic per-project pane (carries a projectId param). */
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
      fallback={<aside className="w-64 shrink-0 border-r border-border bg-surface-nav" aria-hidden />}
    >
      <DesktopSettingsSidebarInner />
    </Suspense>
  );
}

const NAV_ROW =
  'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors';
const NAV_ROW_ACTIVE = 'bg-foreground/10 text-foreground';
const NAV_ROW_IDLE =
  'text-muted-foreground hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground';

function DesktopSettingsSidebarInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = activeSettingsTab(searchParams.get('tab'));
  const activeProjectId = searchParams.get('projectId') ?? '';
  // The DB projects, in the backend's order (the user's synced drag order,
  // then recency) — the same rows, names and icons as the app sidebar's
  // project groups, plus the archived ones so Unarchive / Delete stay
  // reachable. Refetched when navigating between panes, on window focus, and
  // whenever the middle pane reports a mutation (rename, icon, archive, …).
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const searchKey = searchParams.toString();
  useEffect(() => {
    const load = () => {
      getBackendAPI(true)
        .listProjects(true)
        .then(setProjects)
        .catch(() => {
          /* best-effort: the list keeps its last value until the next load */
        });
    };
    load();
    window.addEventListener('focus', load);
    window.addEventListener(PROJECTS_CHANGED_EVENT, load);
    return () => {
      window.removeEventListener('focus', load);
      window.removeEventListener(PROJECTS_CHANGED_EVENT, load);
    };
  }, [searchKey]);

  const { active, archived } = useMemo(
    () => ({
      active: projects.filter((p) => !p.is_archived),
      archived: projects.filter((p) => p.is_archived),
    }),
    [projects],
  );

  // Landing on an archived project's pane opens the group so its row is visible.
  useEffect(() => {
    if (tab === 'project' && archived.some((p) => p.id === activeProjectId)) setShowArchived(true);
  }, [tab, archived, activeProjectId]);

  const backToApp = useCallback(() => {
    let target: string | null = null;
    try {
      target = window.sessionStorage.getItem(DESKTOP_LAST_APP_PATH_KEY);
    } catch {
      // sessionStorage unavailable — fall back to the dashboard root.
    }
    router.push(target || '/dashboard');
  }, [router]);

  const projectRow = (project: ProjectResponse) => {
    const isActive = tab === 'project' && activeProjectId === project.id;
    return (
      <button
        key={project.id}
        type="button"
        onClick={() => router.replace(projectSettingsHref(project.id))}
        className={cn(NAV_ROW, isActive ? NAV_ROW_ACTIVE : NAV_ROW_IDLE, project.is_archived && 'opacity-70')}
      >
        <ProjectIcon project={project} />
        <span className="truncate">{project.name}</span>
      </button>
    );
  };

  return (
    <aside className="relative z-10 flex h-full w-64 shrink-0 flex-col border-r border-border bg-surface-nav font-mono text-sm">
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
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground"
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
            className={cn(NAV_ROW, tab === id ? NAV_ROW_ACTIVE : NAV_ROW_IDLE)}
          >
            <Icon className="h-3.5 w-3.5 shrink-0" />
            {label}
          </button>
        ))}

        {projects.length > 0 && (
          <>
            <div className="px-2 pt-4 pb-1 text-xs font-light text-muted-foreground/70">
              Projects
            </div>
            {active.map(projectRow)}
            {archived.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={() => setShowArchived((v) => !v)}
                  aria-expanded={showArchived}
                  className="flex w-full cursor-pointer items-center gap-1 px-2 pt-3 pb-1 text-xs font-light text-muted-foreground/70 transition-colors hover:text-foreground"
                >
                  <ChevronRight
                    className={cn('h-3 w-3 transition-transform', showArchived && 'rotate-90')}
                  />
                  Archived
                  <span className="text-muted-foreground/50">{archived.length}</span>
                </button>
                {showArchived && archived.map(projectRow)}
              </>
            )}
          </>
        )}
      </nav>
    </aside>
  );
}
