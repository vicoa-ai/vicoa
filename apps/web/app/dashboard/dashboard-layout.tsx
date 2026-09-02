'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import {
  Kanban,
  ListTodo,
  CalendarClock,
  Menu,
  LogOut,
  Key,
  Cog,
  BookOpen,
  Layers2,
  ArrowUpCircle,
  User,
  X,
  Plus,
  Sidebar,
  Flag,
  PanelLeft,
  Search,
  Settings,
} from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { AgentDashboardProvider, useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import useSWR from 'swr';
import type { AuthUser } from '@/lib/auth/user';
import { DashboardNavigationContext } from '@/lib/contexts/dashboard-navigation-context';
import { StartRemoteSessionDialog } from '@/components/dashboard/start-remote-session-dialog';
import { parseAskUserQuestionPayload } from '@/components/dashboard/ask-user-question-panel';
import { extractMessageOptions } from '@/components/ui/message-markdown-utils';
// import { getBillingPlanLabel } from '@/lib/billing';
import { ReportIssueDialog } from '@/components/dashboard/report-issue-dialog';
import { OnboardingModal } from '@/components/dashboard/onboarding-modal';
import { DesktopSidebar } from '@/components/dashboard/desktop-sidebar';
import { SidebarSessions } from '@/components/dashboard/sidebar-sessions';
import { SetupChecklist } from '@/components/dashboard/setup-checklist';
import { DesktopSettingsSidebar, DESKTOP_LAST_APP_PATH_KEY } from '@/components/dashboard/desktop-settings-sidebar';
import { TerminalSessionsProvider, useTerminalSessions } from '@/components/terminal-pane/terminal-sessions';
import { matchesShortcut, comboKeycaps, getShortcutCombo } from '@/lib/desktop-shortcuts';
import { SearchPalette } from '@/components/dashboard/search-palette';
import { useDesktopNotificationNavigation } from '@/lib/hooks/use-desktop-session-notifications';
import { DesktopConnectionBanner } from '@/components/dashboard/desktop-connection-banner';
import { DesktopNotificationNudge } from '@/components/dashboard/desktop-notification-nudge';
import { DesktopChromeProvider } from '@/components/dashboard/desktop-chrome-context';
import { PluginSidebarItems } from '@/components/plugins/plugin-sidebar-items';
import { PluginCatalogSync } from '@/components/plugins/plugin-catalog-sync';
import { PluginTrustGate } from '@/components/plugins/plugin-trust-gate';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { DesktopTitlebarLead, useDesktopWindows } from '@/components/desktop/window-chrome';
import type { AgentInstanceResponse } from '@/lib/backend-api';

const fetcher = (url: string) => fetch(url).then((res) => {
  if (!res.ok) {
    if (res.status === 401) return null;
    throw new Error('Failed to fetch');
  }
  return res.json();
});

// Desktop builds run their own local Next server with this flag set (same
// signal middleware.ts uses). Being a compile-time constant it's identical on
// server and client, so it can drive structural chrome choices (which sidebar
// to render) without hydration mismatches — and the feature-heavy web sidebar,
// with its /api/user SWR fetches, never mounts on desktop at all. Runtime
// state (local vs cloud mode) still comes from lib/runtime-config.ts inside
// the desktop components.
const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';

const SIDEBAR_MIN_WIDTH = 180;
const SIDEBAR_MAX_WIDTH = 600;
const SIDEBAR_DEFAULT_WIDTH = 256; // w-64


const sidebarItemSelected = "bg-foreground/10 text-foreground";

function DashboardSidebar({
  isMobileOpen,
  onMobileClose,
  activeTab,
  selectedInstanceId,
  onStartRemoteSession,
  onReportIssue,
  onOpenSearch,
  isCollapsed,
  onToggleCollapsed,
  sidebarWidth,
  onSidebarWidthChange,
}: {
  isMobileOpen: boolean;
  onMobileClose: () => void;
  activeTab: string;
  selectedInstanceId: string | null;
  onStartRemoteSession: () => void;
  onReportIssue: () => void;
  onOpenSearch: () => void;
  isCollapsed: boolean;
  onToggleCollapsed: () => void;
  sidebarWidth: number;
  onSidebarWidthChange: (width: number) => void;
}) {
  const { api, recentInstances } = useAgentDashboard();
  const { data: user } = useSWR<AuthUser>('/api/supabase-user', fetcher);
  const showSideBar = !isCollapsed;

  // Platform-dependent (⌘ K vs Ctrl K) — computed post-mount to avoid a
  // server/client hydration mismatch.
  const [searchKeycaps, setSearchKeycaps] = useState<string[]>([]);
  useEffect(() => {
    setSearchKeycaps(comboKeycaps(getShortcutCombo('open-search')));
  }, []);

  // Archiving/deleting a session tears its terminals + persisted layout down;
  // the shared session list invokes this after the operation completes.
  const { closeSession: closeTerminalSession } = useTerminalSessions();

  // Dedupe in-flight "mark reviewed on open" inspections and the >7-day stale
  // auto-completions below.
  const autoReviewingSessionIdsRef = useRef<Set<string>>(new Set());
  const autoCompletingSessionIdsRef = useRef<Set<string>>(new Set());

  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);
  const sidebarRef = useRef<HTMLElement>(null);
  const liveSidebarWidthRef = useRef(sidebarWidth);
  const pendingSidebarWidthRef = useRef<number | null>(null);
  const dragAnimationFrameRef = useRef<number | null>(null);

  const flushSidebarWidth = useCallback(() => {
    dragAnimationFrameRef.current = null;

    if (pendingSidebarWidthRef.current === null) {
      return;
    }

    const nextWidth = pendingSidebarWidthRef.current;
    pendingSidebarWidthRef.current = null;
    liveSidebarWidthRef.current = nextWidth;

    if (sidebarRef.current) {
      sidebarRef.current.style.width = `${nextWidth}px`;
    }
  }, []);

  const scheduleSidebarWidth = useCallback((width: number) => {
    pendingSidebarWidthRef.current = width;

    if (dragAnimationFrameRef.current !== null) {
      return;
    }

    dragAnimationFrameRef.current = window.requestAnimationFrame(flushSidebarWidth);
  }, [flushSidebarWidth]);

  useEffect(() => {
    liveSidebarWidthRef.current = sidebarWidth;

    if (showSideBar && sidebarRef.current) {
      sidebarRef.current.style.width = `${sidebarWidth}px`;
    }
  }, [showSideBar, sidebarWidth]);

  useEffect(() => {
    return () => {
      if (dragAnimationFrameRef.current !== null) {
        window.cancelAnimationFrame(dragAnimationFrameRef.current);
      }
    };
  }, []);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = liveSidebarWidthRef.current;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const delta = moveEvent.clientX - dragStartXRef.current;
      const newWidth = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, dragStartWidthRef.current + delta));
      if (newWidth !== liveSidebarWidthRef.current || pendingSidebarWidthRef.current !== null) {
        scheduleSidebarWidth(newWidth);
      }
    };

    const onMouseUp = () => {
      isDraggingRef.current = false;

      if (dragAnimationFrameRef.current !== null) {
        window.cancelAnimationFrame(dragAnimationFrameRef.current);
        flushSidebarWidth();
      }

      if (liveSidebarWidthRef.current !== sidebarWidth) {
        onSidebarWidthChange(liveSidebarWidthRef.current);
      }

      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, [flushSidebarWidth, onSidebarWidthChange, scheduleSidebarWidth, sidebarWidth]);

  const router = useRouter();

  const userDisplayName = useMemo(() => {
    return user?.name || user?.email || 'User';
  }, [user]);

  const userEmail = user?.email || '';

  const userInitials = useMemo(() => {
    if (user?.name) {
      const parts = user.name.trim().split(/\s+/).filter(Boolean);
      if (parts.length >= 2) {
        return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
      }
      if (parts.length === 1) {
        return parts[0][0].toUpperCase();
      }
    }

    if (user?.email) {
      return user.email.charAt(0).toUpperCase();
    }

    return 'U';
  }, [user]);

  const handleTabClick = useCallback((tab: string) => {
    if (tab === 'agent-hub') {
      router.push('/dashboard/kanban');
    } else if (tab === 'tasks') {
      router.push('/dashboard/tasks');
    } else if (tab === 'automation') {
      router.push('/dashboard/automation');
    } else if (tab === 'skills') {
      router.push('/dashboard/skills');
    }
    onMobileClose();
  }, [router, onMobileClose]);

  // Opening a session navigates + shows a spinner inside the shared list; here we
  // only do the web's smarter auto-review: mark an awaiting-input session
  // reviewed on open UNLESS its last message is still asking the user something.
  const handleSessionOpened = useCallback((instance: AgentInstanceResponse) => {
    const instanceId = instance.id;
    if (!api || instance.status !== 'AWAITING_INPUT' || autoReviewingSessionIdsRef.current.has(instanceId)) {
      onMobileClose();
      return;
    }
    autoReviewingSessionIdsRef.current.add(instanceId);
    void api.getInstanceDetail(instanceId, 20)
      .then((detail) => {
        const lastMessage = detail.messages[detail.messages.length - 1];
        const hasAskUserQuestion = lastMessage ? Boolean(parseAskUserQuestionPayload(lastMessage)) : false;
        const hasOptions = lastMessage ? extractMessageOptions(lastMessage.content || '').options.length > 0 : false;
        if (hasAskUserQuestion || hasOptions) {
          return;
        }
        return api.updateAgentStatus(instanceId, { status: 'REVIEWED' }).catch((error) => {
          console.error(`Failed to mark ${instanceId} as REVIEWED:`, error);
        });
      })
      .catch((error) => {
        console.error(`Failed to inspect ${instanceId} before auto-review:`, error);
      })
      .finally(() => {
        autoReviewingSessionIdsRef.current.delete(instanceId);
      });
    onMobileClose();
  }, [api, onMobileClose]);

  useEffect(() => {
    if (!api || recentInstances.length === 0) {
      return;
    }

    const staleCutoffTime = Date.now() - (7 * 24 * 60 * 60 * 1000);
    const staleSessions = recentInstances.filter((instance) => {
      if (!['ACTIVE', 'AWAITING_INPUT'].includes(instance.status)) {
        return false;
      }

      if (autoCompletingSessionIdsRef.current.has(instance.id)) {
        return false;
      }

      const lastActivityTime = new Date(instance.latest_message_at || instance.started_at).getTime();
      return Number.isFinite(lastActivityTime) && lastActivityTime <= staleCutoffTime;
    });

    if (staleSessions.length === 0) {
      return;
    }

    staleSessions.forEach((instance) => {
      autoCompletingSessionIdsRef.current.add(instance.id);
    });

    void Promise.allSettled(
      staleSessions.map(async (instance) => {
        try {
          await api.updateAgentStatus(instance.id, { status: 'COMPLETED' });
        } catch (error) {
          console.error(`Failed to auto-complete stale session ${instance.id}:`, error);
          autoCompletingSessionIdsRef.current.delete(instance.id);
        }
      })
    );
  }, [api, recentInstances]);

  return (
    <aside
      ref={sidebarRef}
      className={`fixed inset-y-0 left-0 z-50 bg-surface-nav border-r border-border flex flex-col xl:relative xl:translate-x-0 transform transition-[transform] duration-300 ease-in-out font-mono text-sm ${
        isMobileOpen ? 'translate-x-0' : '-translate-x-full'
      } xl:block`}
      style={{ width: showSideBar ? sidebarWidth : 56 }}
    >
      {/* Mobile close overlay */}
      {isMobileOpen && (
        <div
          className="xl:hidden fixed inset-0 bg-background/80 backdrop-blur-sm z-40"
          onClick={onMobileClose}
        />
      )}

      {/* Sidebar content */}
      <div className="relative z-50 flex flex-col h-full bg-surface-nav">
        {/* Logo Header */}
        <div className={cn("flex items-center", showSideBar ? "justify-between pl-5 pr-3 pt-2 pb-3" : "justify-center px-2 py-3")}>
          {!showSideBar ? (
            <button
              type="button"
              onClick={onToggleCollapsed}
              className="group relative flex h-9 w-9 items-center justify-center rounded-lg transition-colors hover:bg-muted/40"
              aria-label="Open sidebar"
              title="Open sidebar"
            >
              <Image
                src="/images/vicoa-light.webp"
                alt="Vicoa"
                width={20}
                height={20}
                className="h-5 w-5 rounded-md transition-opacity duration-200 group-hover:opacity-0"
              />
              <Sidebar className="absolute h-4 w-4 opacity-0 transition-opacity duration-200 group-hover:opacity-100" />
            </button>
          ) : (
            <>
              <Link href="/dashboard" className="flex items-center">
                <Image
                  src="/images/vicoa-logo-text.webp"
                  alt="Vicoa Logo"
                  width={0}
                  height={0}
                  sizes="100vw"
                  className="h-6 w-auto"
                />
              </Link>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="hidden xl:inline-flex h-8 w-8"
                  onClick={onToggleCollapsed}
                  title="Hide sidebar"
                >
                  <Sidebar className="h-4 w-4" />
                  <span className="sr-only">Hide sidebar</span>
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="xl:hidden h-8 w-8"
                  onClick={onMobileClose}
                >
                  <X className="h-5 w-5" />
                  <span className="sr-only">Close sidebar</span>
                </Button>
              </div>
            </>
          )}
        </div>

        {/* Navigation Tabs */}
        <div className={cn("px-2", !showSideBar && "flex flex-col items-center gap-2 px-1")}>
          {!showSideBar ? (
            <Button
              variant="subtle"
              size="icon"
              className="h-9 w-9 rounded-lg bg-transparent"
              onClick={onStartRemoteSession}
              disabled={!api}
              title="Start new session"
            >
              <Plus className="h-4 w-4" />
              <span className="sr-only">Start new session</span>
            </Button>
          ) : (
            <Button
              variant="subtle"
              className="w-full justify-start h-auto py-1.5 text-xs"
              onClick={onStartRemoteSession}
              disabled={!api}
              title="Start new session"
            >
              <Plus className="h-4 w-4 mr-2" />
              New Session
            </Button>
          )}

          {/* Kanban lives in the Workspaces row (shared list) when expanded; the
              collapsed rail keeps a quick-access icon for it. */}
          {!showSideBar && (
            <Button
              variant="subtle"
              size="icon"
              className="h-9 w-9 justify-center rounded-lg px-0 bg-transparent"
              onClick={() => handleTabClick('agent-hub')}
              title="Kanban"
            >
              <Kanban className="h-4 w-4" />
              <span className="sr-only">Kanban</span>
            </Button>
          )}

          {/* Human task backlog — distinct from Kanban (agent sessions). */}
          <Button
            variant="subtle"
            className={cn(
              !showSideBar
                ? "h-9 w-9 justify-center rounded-lg px-0 bg-transparent"
                : "w-full justify-start h-auto py-1.5 mt-1 text-xs",
              showSideBar && activeTab === 'tasks' && sidebarItemSelected
            )}
            onClick={() => handleTabClick('tasks')}
            title="Tasks"
          >
            <ListTodo className={cn("h-4 w-4", showSideBar && "mr-2")} />
            {showSideBar ? 'Tasks' : null}
          </Button>

          {/* Scheduled agent runs. */}
          <Button
            variant="subtle"
            className={cn(
              !showSideBar
                ? "h-9 w-9 justify-center rounded-lg px-0 bg-transparent"
                : "w-full justify-start h-auto py-1.5 mt-1 text-xs",
              showSideBar && activeTab === 'automation' && sidebarItemSelected
            )}
            onClick={() => handleTabClick('automation')}
            title="Automations"
          >
            <CalendarClock className={cn("h-4 w-4", showSideBar && "mr-2")} />
            {showSideBar ? 'Automations' : null}
          </Button>

          {/* Agent skills installed per machine. */}
          <Button
            variant="subtle"
            className={cn(
              !showSideBar
                ? "h-9 w-9 justify-center rounded-lg px-0 bg-transparent"
                : "w-full justify-start h-auto py-1.5 mt-1 text-xs",
              showSideBar && activeTab === 'skills' && sidebarItemSelected
            )}
            onClick={() => handleTabClick('skills')}
            title="Skills"
          >
            <Layers2 className={cn("h-4 w-4", showSideBar && "mr-2")} />
            {showSideBar ? 'Skills' : null}
          </Button>

          {/* Nav entries contributed by installed plugins (Tier 1). */}
          <PluginSidebarItems
            slot="nav"
            collapsed={!showSideBar}
            onNavigate={onMobileClose}
          />

          {/* Workspace search across sessions, tasks, automations (also ⌘K). */}
          <Button
            variant="subtle"
            className={cn(
              !showSideBar
                ? "h-9 w-9 justify-center rounded-lg px-0 bg-transparent"
                : "w-full justify-start h-auto py-1.5 mt-1 text-xs"
            )}
            onClick={() => { onOpenSearch(); onMobileClose(); }}
            title="Search"
          >
            <Search className={cn("h-4 w-4", showSideBar && "mr-2")} />
            {showSideBar ? 'Search' : null}
            {showSideBar && searchKeycaps.length > 0 ? (
              <span className="ml-auto flex gap-0.5">
                {searchKeycaps.map((key) => (
                  <kbd
                    key={key}
                    className="rounded border bg-muted px-1 py-0.5 font-sans text-[10px] font-medium leading-none text-foreground/70"
                  >
                    {key}
                  </kbd>
                ))}
              </span>
            ) : null}
          </Button>
        </div>

        {showSideBar && (
          <div className="bg-muted/30 h-px" />
        )}

        {/* Agent Sessions (shared with the desktop sidebar). Web enables
            infinite scroll and, like desktop, tears down a closed session's
            terminals. Worktree sub-grouping is available here too (opt-in via
            the Display → Worktree toggle) — it splits from stored session fields
            and doesn't need the local daemon; only the live `git worktree list`
            + worktree deletion stay desktop-only. ⌘-shortcuts stay off. */}
        {showSideBar ? (
          <SidebarSessions
            selectedInstanceId={activeTab === 'session' ? selectedInstanceId : null}
            onSessionOpened={handleSessionOpened}
            onAfterCloseSession={closeTerminalSession}
            enableWorktrees
            enableInfiniteScroll
          />
        ) : (
          <div className="flex-1" />
        )}

        {/* Onboarding guide — floats just above the account row. Hidden in the
            collapsed rail; the component itself hides when signed-out. */}
        {showSideBar && (
          <div className="shrink-0 px-2 pb-2 pt-1">
            <SetupChecklist />
          </div>
        )}

      {/* User Menu at Bottom */}
        <div className="border-border p-1">
          {user ? (
            <div className={cn('flex items-center', showSideBar ? 'gap-1' : 'flex-col')}>
            <div className={cn(showSideBar && 'min-w-0 flex-1')}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className={cn(
                    "h-auto p-2",
                    !showSideBar ? "mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-lg p-0" : "w-full justify-start"
                  )}
                  title={!showSideBar ? userDisplayName : undefined}
                >
                  <div className="flex items-center w-full">
                    <Avatar className={cn("h-8 w-8", showSideBar && "mr-3")}>
                      <AvatarFallback className={cn(
                        "bg-primary/10 text-primary uppercase text-xs font-normal"
                      )}>
                        {userInitials || <User className="h-4 w-4 text-muted-foreground" />}
                      </AvatarFallback>
                    </Avatar>
                    <div className={cn("flex-1 min-w-0 text-left", !showSideBar && "hidden")}>
                        {user.name ? (
                        <>
                          <div className="text-xs truncate">{user.name}</div>
                          <div className="mt-1 text-xs text-muted-foreground truncate">
                            {/* {billingPlanLabel} */}
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="text-xs truncate">{user.email}</div>
                          <div className="mt-1 text-xs text-muted-foreground truncate">
                            {/* {billingPlanLabel} */}
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align={!showSideBar ? 'end' : 'center'}
                side="top"
                className="w-60 p-0 overflow-hidden rounded-xl border border-border/60 bg-popover text-popover-foreground shadow-xl font-mono text-xs"
              >
                <div className="px-4 py-3 bg-muted/40 flex items-center gap-3">
                  <User className="h-4 w-4 text-muted-foreground" />
                  <div className="min-w-0">
                    <div className="truncate text-muted-foreground">{userEmail || 'Account'}</div>
                  </div>
                </div>

                <div className="py-1">
                  <DropdownMenuItem
                    asChild
                    className="cursor-pointer px-4 py-2.5 text-xs text-foreground/80"
                  >
                    <Link href="/dashboard/settings" className="flex w-full items-center gap-2">
                      <Cog className="h-4 w-4" />
                      <span>Settings</span>
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    asChild
                    className="cursor-pointer px-4 py-2.5 text-xs text-foreground/80"
                  >
                    <Link href="/dashboard/upgrade" className="flex w-full items-center gap-2">
                      <ArrowUpCircle className="h-4 w-4" />
                      <span>Upgrade plan</span>
                    </Link>
                  </DropdownMenuItem>

                  <DropdownMenuItem
                    asChild
                    className="cursor-pointer px-4 py-2.5 text-xs text-foreground/80"
                  >
                    <Link href="/docs" className="flex w-full items-center gap-2">
                      <BookOpen className="h-4 w-4" />
                      <div className="flex-1">Documentation</div>
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="cursor-pointer px-4 py-2.5 text-xs text-foreground/80"
                    onSelect={() => onReportIssue()}
                  >
                    <Flag className="h-4 w-4" />
                    <span>Report an issue</span>
                  </DropdownMenuItem>
                </div>

                <DropdownMenuSeparator className="mx-4" />

                <div className="py-1">
                  <DropdownMenuItem
                    asChild
                    className="cursor-pointer px-4 py-2.5 text-xs text-foreground/80">
                    <Link href="/dashboard/api-keys" className="flex w-full items-center gap-2">
                      <Key className="h-4 w-4" />
                      API Keys
                    </Link>
                  </DropdownMenuItem>

                  <DropdownMenuItem
                    className="cursor-pointer px-4 py-2.5 text-xs text-foreground/80"
                    onSelect={async () => {
                      // Handle logout
                      const { signOutBrowser } = await import('@/lib/auth/sign-out');
                      await signOutBrowser();
                      window.location.href = '/';
                    }}
                  >
                    <LogOut className="h-4 w-4" />
                    <span>Log out</span>
                  </DropdownMenuItem>
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
            </div>
            {/* Settings shortcut beside the avatar — straight to the page,
                skipping the account menu (session ask). Expanded rail only. */}
            {showSideBar && (
              <Link
                href="/dashboard/settings"
                title="Settings"
                aria-label="Settings"
                className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Settings className="h-4 w-4" />
              </Link>
            )}
            </div>
          ) : (
            <div className="text-center p-2">
              <div className="text-sm text-muted-foreground">Not logged in</div>
            </div>
          )}
        </div>
      </div>

      {/* Drag resize handle */}
      {showSideBar && (
        <div
          className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize z-[60] hover:bg-primary/30 active:bg-primary/50 transition-colors"
          onMouseDown={handleDragStart}
        />
      )}

    </aside>
  );
}

/**
 * When the desktop sidebar is collapsed, the window's top-left corner belongs to
 * the middle (chat) panel. The macOS traffic lights sit there and the window has
 * no other titlebar, so we overlay a minimal strip: a drag region wide enough to
 * keep the window movable, the traffic-light inset, and an expand button. It sits
 * above the panel content (absolute) so the panels still fill the full height.
 */
function DesktopCollapsedTitlebar({ onExpand }: { onExpand: () => void }) {
  return (
    <div
      style={DRAG_REGION}
      className="absolute left-0 top-0 z-30 flex h-11 items-center gap-1.5 pl-2 xl:pl-6 pr-1.5"
    >
      <DesktopTitlebarLead />
      <span className="text-sm font-normal text-foreground">Vicoa</span>
      <button
        type="button"
        onClick={onExpand}
        style={NO_DRAG}
        title="Expand sidebar"
        aria-label="Expand sidebar"
        className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <PanelLeft className="h-4 w-4" />
      </button>
    </div>
  );
}

function DashboardContent({
  children
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  // App-shell pages own their full height, header, and internal scrolling, so
  // they render flush (no document padding) — otherwise the padding reads as a
  // stray top gap above their own h-11 header (and stacks under the Windows
  // titlebar strip). Document-style pages keep the scroll + padding default.
  const isFullHeightPage =
    pathname === '/dashboard/mobile' ||
    pathname === '/dashboard/automation' ||
    pathname === '/dashboard/tasks' ||
    pathname === '/dashboard/skills' ||
    !!pathname?.match(/^\/dashboard\/agents\/[^\/]+$/);
  if (isFullHeightPage) {
    return (
      <main className="flex-1 flex flex-col h-full overflow-hidden">
        {children}
      </main>
    );
  }

  // Default layout for other dashboard pages
  return (
    <main className="flex-1 overflow-y-auto p-4 lg:p-6 custom-scrollbar">
      {children}
    </main>
  );
}

type DashboardShellProps = {
  children: React.ReactNode;
  activeTab: string;
  selectedInstanceId: string | null;
  isMobileSidebarOpen: boolean;
  setIsMobileSidebarOpen: React.Dispatch<React.SetStateAction<boolean>>;
  isDesktopSidebarCollapsed: boolean;
  setIsDesktopSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  sidebarWidth: number;
  setSidebarWidth: (width: number) => void;
  handleStartRemoteSession: () => void;
  isSpawnDialogOpen: boolean;
  setIsSpawnDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
};

function DashboardShell({
  children,
  activeTab,
  selectedInstanceId,
  isMobileSidebarOpen,
  setIsMobileSidebarOpen,
  isDesktopSidebarCollapsed,
  setIsDesktopSidebarCollapsed,
  sidebarWidth,
  setSidebarWidth,
  handleStartRemoteSession,
  isSpawnDialogOpen,
  setIsSpawnDialogOpen,
}: DashboardShellProps) {
  const shellPathname = usePathname();
  const isInstancePage = !!shellPathname?.match(/^\/dashboard\/agents\/[^\/]+$/);
  const isSettingsPage = !!shellPathname?.startsWith('/dashboard/settings');
  // App-shell pages whose own top header IS the window titlebar: it renders
  // <DesktopCollapsedLead /> when the sidebar is hidden and is itself the drag
  // region (with NO_DRAG controls). They must NOT get the shell's floating
  // DesktopCollapsedTitlebar (the lead would double) nor the macOS drag overlay
  // (it would sit on top of the header and swallow the controls' clicks).
  const hasOwnHeaderChrome =
    isInstancePage ||
    shellPathname === '/dashboard/automation' ||
    shellPathname === '/dashboard/tasks' ||
    shellPathname === '/dashboard/skills';
  // Windows draws its own min/max/close cluster fixed at the window's top-right
  // (DesktopWindowControls). Instance pages clear it via the chat/files headers;
  // every other page needs a reserved titlebar-height strip so its content isn't
  // overlapped. false on macOS/web and until mount (see useDesktopWindows).
  const isWindows = useDesktopWindows();

  // Remember the last non-settings dashboard path so the settings sidebar's
  // "Back to app" returns exactly where the user left off.
  useEffect(() => {
    if (!IS_DESKTOP || !shellPathname || shellPathname.startsWith('/dashboard/settings')) return;
    try {
      window.sessionStorage.setItem(DESKTOP_LAST_APP_PATH_KEY, shellPathname);
    } catch {
      // sessionStorage unavailable — "Back to app" falls back to /dashboard.
    }
  }, [shellPathname]);
  // Kept for the spawn dialog below (StartRemoteSessionDialog needs the API +
  // a refetch hook). Per-session actions now live in the shared session list.
  const { api, refreshData } = useAgentDashboard();
  const [reportIssueOpen, setReportIssueOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  // ⌘K toggles the workspace search palette (web + desktop; rebindable).
  // Capture phase so it wins over focused inputs, like the ⌘, handler.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!matchesShortcut(event, 'open-search')) return;
      event.preventDefault();
      setSearchOpen((current) => !current);
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, []);
  // Desktop-local has no Next-server session; skip this fetch entirely.
  const { data: shellUser } = useSWR<AuthUser>(IS_DESKTOP ? null : '/api/supabase-user', fetcher);
  const shellUserEmail = shellUser?.email || '';

  return (
    <>
      <div className="flex h-screen max-w-full overflow-hidden">
        {!isInstancePage && !IS_DESKTOP && (
          <div className="xl:hidden fixed top-0 left-0 right-0 z-40 flex items-center justify-between bg-background/400 p-4">
            <div className="flex items-center">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
              >
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle sidebar</span>
              </Button>
              <Image
                src="/images/vicoa-logo-text.webp"
                alt="Vicoa Logo"
                width={0}
                height={0}
                sizes="100vw"
                className="h-6 w-auto ml-2"
              />
            </div>
          </div>
        )}

        {IS_DESKTOP ? (
          isSettingsPage ? (
            <DesktopSettingsSidebar />
          ) : (
            <DesktopSidebar
              isCollapsed={isDesktopSidebarCollapsed}
              onToggleCollapsed={() => setIsDesktopSidebarCollapsed((current) => !current)}
              onOpenSearch={() => setSearchOpen(true)}
            />
          )
        ) : (
          <DashboardSidebar
            isMobileOpen={isMobileSidebarOpen}
            onMobileClose={() => setIsMobileSidebarOpen(false)}
            activeTab={activeTab}
            selectedInstanceId={selectedInstanceId}
            onStartRemoteSession={handleStartRemoteSession}
            onReportIssue={() => setReportIssueOpen(true)}
            onOpenSearch={() => setSearchOpen(true)}
            isCollapsed={isDesktopSidebarCollapsed}
            onToggleCollapsed={() => setIsDesktopSidebarCollapsed((current) => !current)}
            sidebarWidth={sidebarWidth}
            onSidebarWidthChange={setSidebarWidth}
          />
        )}

        <div className={cn('flex-1 flex flex-col min-w-0 xl:ml-0 overflow-hidden', IS_DESKTOP && 'relative bg-surface-canvas')}>
          {!isInstancePage && !IS_DESKTOP && <div className="xl:hidden h-16"></div>}
          {/* Windows: every non-instance page reserves a real titlebar-height
              strip (in flow, so content sits below it) so nothing is overlapped
              by the fixed min/max/close controls at the top-right. It's also a
              drag region, so it doubles as the draggable top edge. */}
          {IS_DESKTOP && isWindows && !isInstancePage && (
            <div style={DRAG_REGION} className="h-11 shrink-0" aria-hidden />
          )}
          {/* On the chat page the header hosts the collapsed control inline (so
              the title flows after Vicoa + the panel icon); elsewhere there's no
              header, so float the overlay control instead. On Windows it overlays
              the reserved strip above. */}
          {IS_DESKTOP && isDesktopSidebarCollapsed && !hasOwnHeaderChrome && !isSettingsPage && (
            <DesktopCollapsedTitlebar onExpand={() => setIsDesktopSidebarCollapsed(false)} />
          )}
          {IS_DESKTOP && <DesktopConnectionBanner />}
          {/* macOS/web: no top-right controls to clear (traffic lights sit over
              the sidebar), so pages without their own titlebar (dashboard home,
              kanban) just need a draggable top edge. Overlay (no layout shift) —
              nothing interactive lives in the top strip of these pages. Excluded
              for hasOwnHeaderChrome pages: their header is the drag region, and
              an overlay on top would swallow its controls' clicks. Windows uses
              the reserved in-flow strip above instead. */}
          {IS_DESKTOP && !isWindows && !hasOwnHeaderChrome && !isSettingsPage && !isDesktopSidebarCollapsed && (
            <div style={DRAG_REGION} className="absolute inset-x-0 top-0 z-10 h-11" aria-hidden />
          )}
          {IS_DESKTOP && <DesktopNotificationNudge />}
          <DesktopChromeProvider
            value={{
              isDesktop: IS_DESKTOP,
              sidebarCollapsed: isDesktopSidebarCollapsed,
              expandSidebar: () => setIsDesktopSidebarCollapsed(false),
            }}
          >
            <DashboardContent>
              {children}
            </DashboardContent>
          </DesktopChromeProvider>
        </div>
      </div>

      <StartRemoteSessionDialog
        open={isSpawnDialogOpen}
        onOpenChange={setIsSpawnDialogOpen}
        api={api}
        onSessionRequested={refreshData}
      />

      <ReportIssueDialog
        open={reportIssueOpen}
        onOpenChange={setReportIssueOpen}
        userEmail={shellUserEmail}
      />

      <SearchPalette open={searchOpen} onOpenChange={setSearchOpen} />
    </>
  );
}

export default function DashboardLayout({
  children
}: {
  children: React.ReactNode;
}) {
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isDesktopSidebarCollapsed, setIsDesktopSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidthState] = useState(SIDEBAR_DEFAULT_WIDTH);

  useEffect(() => {
    const saved = localStorage.getItem('sidebar-width');
    const parsed = saved ? parseInt(saved, 10) : NaN;
    if (Number.isFinite(parsed)) {
      setSidebarWidthState(Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, parsed)));
    }
  }, []);

  const setSidebarWidth = useCallback((width: number) => {
    setSidebarWidthState(width);
    localStorage.setItem('sidebar-width', String(width));
  }, []);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedInstanceId, setSelectedInstanceId] = useState<string | null>(null);
  const pathname = usePathname();

  const router = useRouter();

  const [isSpawnDialogOpen, setIsSpawnDialogOpen] = useState(false);

  // Function to open a session directly
  const openSession = useCallback((instanceId: string) => {
    router.push(`/dashboard/agents/${instanceId}`);
  }, [router]);

  // ⌘, opens settings (desktop only; rebindable). Lives here so it works on
  // every dashboard route, including the settings pages themselves.
  useEffect(() => {
    if (!IS_DESKTOP) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (!matchesShortcut(event, 'open-settings')) return;
      event.preventDefault();
      router.push('/dashboard/settings');
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [router]);

  // Notification clicks: the shell focuses the window and hands us the
  // session route to open (desktop only; no-op on web — null bridge).
  useDesktopNotificationNavigation((path) => router.push(path));

  const handleStartRemoteSession = useCallback(() => {
    router.push('/dashboard/agents/new-session');
  }, [router]);

  const openSidebar = useCallback(() => {
    setIsMobileSidebarOpen(true);
  }, []);

  // Create navigation context value
  const navigationContextValue = useMemo(() => ({
    openSession,
    openSidebar,
  }), [openSession, openSidebar]);

  // Update active tab based on current route
  useEffect(() => {
    if (pathname === '/dashboard') {
      setActiveTab('dashboard');
      setSelectedInstanceId(null);
    } else if (pathname === '/dashboard/kanban') {
      setActiveTab('agent-hub');
      setSelectedInstanceId(null);
    } else if (pathname === '/dashboard/tasks') {
      setActiveTab('tasks');
      setSelectedInstanceId(null);
    } else if (pathname === '/dashboard/automation') {
      setActiveTab('automation');
      setSelectedInstanceId(null);
    } else if (pathname === '/dashboard/skills') {
      setActiveTab('skills');
      setSelectedInstanceId(null);
    } else if (pathname === '/dashboard/agents/new-session') {
      setActiveTab('session');
      setSelectedInstanceId(null);
    } else if (pathname.startsWith('/dashboard/agents/')) {
      setActiveTab('session');
      const instanceId = pathname.split('/').pop();
      if (instanceId) {
        setSelectedInstanceId(instanceId);
      }
    }
  }, [pathname]);

  // Auto collapse when going to agent hub page
  // useEffect(() => {
  //   if (pathname === '/dashboard/agent-hub') {
  //     setIsDesktopSidebarCollapsed(true);
  //     return;
  //   }

  //   setIsDesktopSidebarCollapsed(false);
  // }, [pathname]);

  return (
    <AgentDashboardProvider>
      <DashboardNavigationContext.Provider value={navigationContextValue}>
        {/* Terminal panes must outlive route changes (session switches), so
            their keep-alive provider wraps the whole dashboard shell. */}
        <TerminalSessionsProvider>
        <OnboardingModal />
        {/* Plugin system (Tier 1): keep the registry in sync with each machine's
            daemon, and surface the first-load trust prompt for new plugins. */}
        <PluginCatalogSync />
        <PluginTrustGate />
        <DashboardShell
          children={children}
          activeTab={activeTab}
          selectedInstanceId={selectedInstanceId}
          isMobileSidebarOpen={isMobileSidebarOpen}
          setIsMobileSidebarOpen={setIsMobileSidebarOpen}
          isDesktopSidebarCollapsed={isDesktopSidebarCollapsed}
          setIsDesktopSidebarCollapsed={setIsDesktopSidebarCollapsed}
          sidebarWidth={sidebarWidth}
          setSidebarWidth={setSidebarWidth}
          handleStartRemoteSession={handleStartRemoteSession}
          isSpawnDialogOpen={isSpawnDialogOpen}
          setIsSpawnDialogOpen={setIsSpawnDialogOpen}
        />
        </TerminalSessionsProvider>
      </DashboardNavigationContext.Provider>
    </AgentDashboardProvider>
  );
}
