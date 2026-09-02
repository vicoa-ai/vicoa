'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Plus, Loader2, LogIn, LogOut, User, PanelLeft, ListTodo, CalendarClock, BookOpen, Cog, ArrowUpCircle, Smartphone, Flag, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { createClient } from '@/lib/auth/supabase-client';
import { getDesktopConfig, type DesktopRuntimeConfig } from '@/lib/runtime-config';
import type { AgentInstanceResponse } from '@/lib/backend-api';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { DesktopTitlebarLead } from '@/components/desktop/window-chrome';
import { useMobileSidebarHidden } from '@/lib/mobile-sidebar-pref';
import { ReportIssueDialog } from '@/components/dashboard/report-issue-dialog';
import { SidebarUpdateCallout } from '@/components/dashboard/sidebar-update-callout';
import { comboKeycaps, getShortcutCombo } from '@/lib/desktop-shortcuts';
import { SidebarSessions } from '@/components/dashboard/sidebar-sessions';
import { PluginSidebarItems } from '@/components/plugins/plugin-sidebar-items';
import { SetupChecklist } from '@/components/dashboard/setup-checklist';
import { useTerminalSessions } from '@/components/terminal-pane/terminal-sessions';

// Selected-row highlight for the nav buttons (New Session / Mobile / Tasks).
const ITEM_SELECTED = 'bg-foreground/10 text-foreground';

// Desktop sidebar is user-resizable; width persists across reloads. Clamp keeps
// the session list usable without letting it eat the chat/files panels.
const DESKTOP_SIDEBAR_MIN_WIDTH = 200;
const DESKTOP_SIDEBAR_MAX_WIDTH = 480;
const DESKTOP_SIDEBAR_DEFAULT_WIDTH = 256; // w-64
const DESKTOP_SIDEBAR_WIDTH_KEY = 'desktop-sidebar-width';

const clampSidebarWidth = (width: number) =>
  Math.min(DESKTOP_SIDEBAR_MAX_WIDTH, Math.max(DESKTOP_SIDEBAR_MIN_WIDTH, width));

/**
 * Minimal sidebar for the desktop app: an OS titlebar, "New session" + nav, the
 * shared session list, and an account area. No billing, no settings menus, no
 * upgrade prompts, and no `/api/user` SWR — in desktop-local mode there is no
 * Supabase session and those endpoints would all fail.
 *
 * The session list itself is the shared `<SidebarSessions>` component (also used
 * by the web dashboard). Desktop turns on its extra capabilities: worktree
 * sub-grouping (backed by the local daemon) and the ⌘-key session shortcuts.
 */
export function DesktopSidebar({
  isCollapsed,
  onToggleCollapsed,
  onOpenSearch,
}: {
  isCollapsed: boolean;
  onToggleCollapsed: () => void;
  onOpenSearch: () => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const mobileHidden = useMobileSidebarHidden();
  const { api, updateInstanceStatus } = useAgentDashboard();

  // Archiving/completing/deleting a session tears its terminals + persisted
  // layout down. On desktop the ptys run against the LOCAL daemon, so leaving
  // them alive keeps real shell processes running until the app quits — kill
  // them here just as the web dashboard does.
  const { closeSession: closeTerminalSession } = useTerminalSessions();

  // Platform-dependent (⌘ K vs Ctrl K) — computed post-mount to avoid a
  // server/client hydration mismatch.
  const [searchKeycaps, setSearchKeycaps] = useState<string[]>([]);
  useEffect(() => {
    setSearchKeycaps(comboKeycaps(getShortcutCombo('open-search')));
  }, []);

  // The shared list highlights the selected row and clears its nav spinner off
  // this id; on desktop the open session is the one in the URL.
  const selectedInstanceId = useMemo(
    () => pathname?.match(/^\/dashboard\/agents\/([^/]+)$/)?.[1] ?? null,
    [pathname],
  );

  // Opening an awaiting-input session marks it reviewed (optimistic local flip
  // first so the blue dot clears immediately, then the API call; the WS stream
  // reconciles either way). Navigation itself is handled inside the shared list.
  const handleSessionOpened = useCallback((instance: AgentInstanceResponse) => {
    if (instance.status === 'AWAITING_INPUT' && api) {
      updateInstanceStatus(instance.id, 'REVIEWED');
      void api.updateAgentStatus(instance.id, { status: 'REVIEWED' }).catch((error) => {
        console.error(`Failed to mark ${instance.id} as reviewed:`, error);
      });
    }
  }, [api, updateInstanceStatus]);

  // Runtime config is client-only (preload-injected); read it after mount so the
  // SSR pass — which renders this sidebar in desktop builds — stays consistent.
  // Until then the account area renders an empty placeholder.
  const [config, setConfig] = useState<DesktopRuntimeConfig | null>(null);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setConfig(getDesktopConfig());
    setMounted(true);
  }, []);

  // Resizable width. Default on SSR (localStorage read post-mount keeps the
  // first client paint identical to the server). During a drag the width is
  // written straight to the DOM node via a ref and only committed to state +
  // localStorage on release, so the session list doesn't re-render per frame.
  const [width, setWidth] = useState(DESKTOP_SIDEBAR_DEFAULT_WIDTH);
  const asideRef = useRef<HTMLElement>(null);
  const liveWidthRef = useRef(width);
  const draggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  useEffect(() => {
    const saved = window.localStorage.getItem(DESKTOP_SIDEBAR_WIDTH_KEY);
    const parsed = saved ? parseInt(saved, 10) : NaN;
    if (Number.isFinite(parsed)) {
      const next = clampSidebarWidth(parsed);
      liveWidthRef.current = next;
      setWidth(next);
    }
  }, []);

  useEffect(() => {
    liveWidthRef.current = width;
  }, [width]);

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = liveWidthRef.current;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!draggingRef.current) return;
      const next = clampSidebarWidth(dragStartWidthRef.current + (moveEvent.clientX - dragStartXRef.current));
      liveWidthRef.current = next;
      if (asideRef.current) asideRef.current.style.width = `${next}px`;
    };

    const onMouseUp = () => {
      draggingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      const final = liveWidthRef.current;
      setWidth(final);
      window.localStorage.setItem(DESKTOP_SIDEBAR_WIDTH_KEY, String(final));
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, []);

  // Collapsed: the panel yields all width to the chat/files columns. The window
  // stays draggable + re-expandable via the floating control the shell overlays
  // on the middle panel (see DesktopCollapsedTitlebar in dashboard-layout).
  if (isCollapsed) return null;

  return (
    <aside
      ref={asideRef}
      style={{ width }}
      className="relative z-10 flex h-full shrink-0 flex-col border-r border-border bg-[#272726] font-mono text-sm"
    >
      {/* Titlebar header (drag region). Reserves space for the macOS traffic
          lights, shows the brand, and collapses the panel. */}
      <div
        style={DRAG_REGION}
        className="flex h-11 shrink-0 items-center gap-1.5 border-b border-border/60 pl-2 xl:pl-6 pr-2"
      >
        <DesktopTitlebarLead />
        <span className="text-sm font-normal text-foreground">Vicoa</span>
        <button
          type="button"
          onClick={onToggleCollapsed}
          style={NO_DRAG}
          title="Collapse sidebar"
          aria-label="Collapse sidebar"
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
        >
          <PanelLeft className="h-4 w-4" />
        </button>
      </div>

      {/* New session */}
      <div className="px-2">
        <Button
          variant="subtle"
          className="w-full justify-start h-auto py-1.5 mb-0.5 text-xs font-normal"
          onClick={() => router.push('/dashboard/agents/new-session')}
          title="Start new session"
        >
          <Plus className="h-4 w-4 mr-1.5" />
          New Session
        </Button>
        {!mobileHidden && (
          <Button
            variant="subtle"
            className={cn(
              'w-full justify-start h-auto py-1.5 mb-0.5 text-xs font-normal',
              pathname === '/dashboard/mobile' && ITEM_SELECTED,
            )}
            onClick={() => router.push('/dashboard/mobile')}
            title="Vicoa Mobile"
          >
            <Smartphone className="h-4 w-4 mr-1.5" />
            Vicoa Mobile
          </Button>
        )}
        {/* Human task backlog — distinct from the session list below. */}
        <Button
          variant="subtle"
          className={cn(
            'w-full justify-start h-auto py-1.5 mb-0.5 text-xs font-normal',
            pathname === '/dashboard/tasks' && ITEM_SELECTED,
          )}
          onClick={() => router.push('/dashboard/tasks')}
          title="Tasks"
        >
          <ListTodo className="h-4 w-4 mr-1.5" />
          Tasks
        </Button>

        {/* Scheduled agent runs. */}
        <Button
          variant="subtle"
          className={cn(
            'w-full justify-start h-auto py-1.5 mb-0.5 text-xs font-normal',
            pathname === '/dashboard/automation' && ITEM_SELECTED,
          )}
          onClick={() => router.push('/dashboard/automation')}
          title="Automations"
        >
          <CalendarClock className="h-4 w-4 mr-1.5" />
          Automations
        </Button>

        {/* Agent skills installed per machine. */}
        <Button
          variant="subtle"
          className={cn(
            'w-full justify-start h-auto py-1.5 mb-0.5 text-xs font-normal',
            pathname === '/dashboard/skills' && ITEM_SELECTED,
          )}
          onClick={() => router.push('/dashboard/skills')}
          title="Skills"
        >
          <BookOpen className="h-4 w-4 mr-1.5" />
          Skills
        </Button>

        {/* Nav entries contributed by installed plugins (Tier 1). */}
        <PluginSidebarItems slot="nav" />

        {/* Workspace search across sessions, tasks, automations (also ⌘K). */}
        <Button
          variant="subtle"
          className="w-full justify-start h-auto py-1.5 mb-0.5 text-xs font-normal"
          onClick={onOpenSearch}
          title="Search"
        >
          <Search className="h-4 w-4 mr-1.5" />
          Search
          {searchKeycaps.length > 0 ? (
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

      <div className="bg-muted/30 h-px" />

      {/* Session list (shared with the web dashboard). */}
      <SidebarSessions
        selectedInstanceId={selectedInstanceId}
        onSessionOpened={handleSessionOpened}
        onAfterCloseSession={closeTerminalSession}
        enableWorktrees
        enableKeyboardShortcuts
        enableInfiniteScroll
      />

      {/* Desktop auto-update notice — sits directly above the account row, its
          own top border forming the seam (see SidebarUpdateCallout). Renders
          nothing on web/SSR or in non-actionable states. */}
      <SidebarUpdateCallout />

      {/* Onboarding guide — floats just above the account row. Hides itself in
          local (signed-out) mode. */}
      <div className="shrink-0 px-2 pb-2 pt-1">
        <SetupChecklist />
      </div>

      {/* Account area */}
      <div className="border-t border-border p-2">
        {!mounted ? null : config?.mode === 'cloud' ? (
          <CloudAccountArea />
        ) : (
          <LocalAccountArea />
        )}
      </div>

      {/* Drag-to-resize handle on the right edge. The visible line thickens on
          hover (a wider highlighted bar) while the hit area stays generous. */}
      <div
        onMouseDown={handleResizeStart}
        className="group absolute right-0 top-0 bottom-0 z-20 w-1.5 cursor-col-resize"
        aria-hidden
      >
        <div className="absolute right-0 top-0 bottom-0 w-px bg-transparent transition-colors duration-150 group-hover:bg-muted-foreground/60 group-active:bg-muted-foreground/70" />
      </div>
    </aside>
  );
}

/** Local (logged-out) mode: the "login connects your phone" entry point. */
function LocalAccountArea() {
  const router = useRouter();
  return (
    <div className="px-1 py-1">
      <div className="flex items-center gap-0.5">
        <Button
          variant="subtle"
          className="flex-1 justify-start h-auto py-1.5 text-xs"
          onClick={() => router.push('/desktop-signin')}
        >
          <LogIn className="h-4 w-4 mr-2" />
          Connect account
        </Button>
        <button
          type="button"
          title="Settings"
          aria-label="Settings"
          onClick={() => router.push('/dashboard/settings')}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
        >
          <Cog className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-1 px-2 text-[10px] text-muted-foreground/60">
        Sync sessions to your phone
      </p>
    </div>
  );
}

/** Cloud (logged-in) mode: account email + sign out via the Electron bridge. */
function CloudAccountArea() {
  const [email, setEmail] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const [reportIssueOpen, setReportIssueOpen] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    let cancelled = false;
    void supabase.auth.getSession().then(({ data: { session } }) => {
      if (cancelled) return;
      // Cloud mode always carries a validated Supabase session now (the gate
      // enforces it), so identity comes straight from the session.
      setEmail(session?.user?.email ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    try {
      // Clear the renderer session first so the reloaded window is signed out
      // too. scope 'local' — signing out of the app must not revoke the user's
      // website/other-device sessions (the default scope is 'global').
      const supabase = createClient();
      await supabase.auth.signOut({ scope: 'local' });
    } catch {
      // Best-effort; the shell-side sign-out is what flips the mode. A dead
      // session that survives here is cleaned up by DesktopAuthHandoff when its
      // key mint gets rejected.
    }
    const bridge = getDesktopAuthBridge();
    if (bridge) {
      try {
        const result = await bridge.signOut();
        if (result.ok) return; // shell restarts local-only and reloads
      } catch {
        // Fall through to re-enable the button.
      }
    }
    setSigningOut(false);
  };

  return (
    <>
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          title="Account"
          aria-label="Account menu"
          className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left transition-colors hover:bg-muted/60"
        >
          <User className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="flex-1 min-w-0 truncate text-xs text-muted-foreground" title={email ?? undefined}>
            {email ?? 'Signed in'}
          </span>
          {signingOut && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-56 font-mono text-xs">
        <div className="flex items-center gap-2 bg-muted/40 px-3 py-2">
          <User className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 truncate text-muted-foreground" title={email ?? undefined}>
            {email ?? 'Account'}
          </span>
        </div>
        <DropdownMenuItem asChild className="cursor-pointer gap-2 text-xs text-foreground/80">
          <Link href="/dashboard/settings" className="flex w-full items-center gap-2">
            <Cog className="h-4 w-4" />
            <span>Settings</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild className="cursor-pointer gap-2 text-xs text-foreground/80">
          <Link href="/dashboard/upgrade" className="flex w-full items-center gap-2">
            <ArrowUpCircle className="h-4 w-4" />
            <span>Upgrade plan</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem
          className="cursor-pointer gap-2 text-xs text-foreground/80"
          onSelect={() => setReportIssueOpen(true)}
        >
          <Flag className="h-4 w-4" />
          <span>Report an issue</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="cursor-pointer gap-2 text-xs text-foreground/80"
          disabled={signingOut}
          onSelect={(e) => {
            e.preventDefault();
            void handleSignOut();
          }}
        >
          {signingOut ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
          <span>Sign out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    {/* Sibling of the menu, not a child: the dialog must outlive the dropdown
        unmounting on select. */}
    <ReportIssueDialog
      open={reportIssueOpen}
      onOpenChange={setReportIssueOpen}
      userEmail={email ?? undefined}
    />
    </>
  );
}
