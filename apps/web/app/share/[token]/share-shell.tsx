'use client';

// The public share page's chrome (collaboration §8.4): the dashboard's shape —
// a sidebar over a main pane — so a shared session reads as "Vicoa" and not
// as a bare transcript. The sidebar is public-safe by construction: it only
// ever holds what the share resolver returned (the shared sessions or board,
// and the owner only when the link opted in), never the viewer's own
// workspace. A signed-in viewer's own projects belong in the dashboard's
// "Shared with me" (P5), not here; what they get is their own identity in the
// account slot and an "Open in Vicoa" action. An anonymous visitor gets the
// dashboard's nav rows (each opens a small sign-in panel beside the sidebar),
// Log in / Sign up in the header and a sign-up card at the bottom — that is
// the growth loop. A project link that carries tasks turns the Tasks nav row
// into this page's own — clicking it shows the shared board, and it is marked
// current while you are there, the same way the dashboard marks it.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ArrowUpRight, Bot, CalendarClock, ListTodo, Menu, Plus, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { PrincipalAvatar, PrincipalAvatarSrcProvider } from '@/components/ui/principal-avatar';
import { type Principal, principalFromResponse } from '@/lib/principals';
import { publicAvatarSrc } from '@/lib/public-share-api';
import type { PublicShareResponse } from '@/lib/backend-api';
import { cn } from '@/lib/utils';

const SIDEBAR_WIDTH = 256; // matches the dashboard's w-64

/** Same selected-row treatment as the dashboard sidebar. */
export const SHARE_ROW_SELECTED = 'bg-foreground/[0.08] dark:bg-foreground/10 text-foreground';

interface ShareChrome {
  share: PublicShareResponse;
  /** Whether the visitor is signed in (the resolver echoed a viewer). */
  signedIn: boolean;
  /** Where sign-in / sign-up send the visitor afterwards: this page. */
  returnHref: string;
  openSidebar: () => void;
  closeSidebar: () => void;
}

const ShareChromeContext = createContext<ShareChrome | null>(null);

export function useShareChrome(): ShareChrome {
  const ctx = useContext(ShareChromeContext);
  if (!ctx) throw new Error('useShareChrome must be used inside <ShareShell>');
  return ctx;
}

/**
 * Where to send the visitor after signing in: back to this exact page,
 * including `?session=` on a project link. Read lazily — the query string is
 * not available during SSR without a Suspense boundary, and the path alone is
 * a fine first-paint fallback.
 */
function useReturnHref(): string {
  const pathname = usePathname();
  const [href, setHref] = useState(pathname ?? '/');
  useEffect(() => {
    setHref(window.location.pathname + window.location.search);
  }, [pathname]);
  return href;
}

/**
 * Log in + Sign up (primary), the pair every anonymous surface uses. In the
 * header Log in is a ghost button; inside a panel it gets a border so the two
 * read as a pair of buttons rather than a link next to a button.
 */
function AuthButtons({
  returnHref,
  className,
  loginVariant = 'ghost',
}: {
  returnHref: string;
  className?: string;
  loginVariant?: 'ghost' | 'outline';
}) {
  const back = encodeURIComponent(returnHref);
  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      <Button asChild size="sm" variant={loginVariant} className="h-7 text-xs">
        <Link href={`/sign-in?redirect=${back}`}>Log in</Link>
      </Button>
      <Button asChild size="sm" className="h-7 text-xs">
        <Link href={`/sign-up?redirect=${back}`}>Sign up for free</Link>
      </Button>
    </div>
  );
}

/** Space between the sidebar's right border and a panel opened beside it. */
const EDGE_GAP = 6;

/** How far right of a row a panel must sit to clear the sidebar (see pr-hover-card.tsx). */
function offsetToSidebarEdge(row: HTMLElement): number {
  const sidebar = row.closest('aside');
  if (!sidebar) return EDGE_GAP;
  const gap = sidebar.getBoundingClientRect().right - row.getBoundingClientRect().right;
  return Math.max(0, Math.round(gap)) + EDGE_GAP;
}

/** The nav rows a share page can stand in for. */
export type ShareNav = 'tasks';

/** A nav row the share page owns: it selects a view here instead of leaving. */
export interface ShareNavTarget {
  active: boolean;
  onSelect: () => void;
}

const NAV: { key?: ShareNav; label: string; icon: LucideIcon; href: string; pitch: string }[] = [
  {
    label: 'New Session',
    icon: Plus,
    href: '/dashboard/agents/new-session',
    pitch: 'Start Claude Code, Codex or another agent on any of your machines, from here or from your phone.',
  },
  {
    key: 'tasks',
    label: 'Tasks',
    icon: ListTodo,
    href: '/dashboard/tasks',
    pitch: 'A backlog for you and your agents: file work, hand it to an agent, follow it to a pull request.',
  },
  {
    label: 'Automations',
    icon: CalendarClock,
    href: '/dashboard/automation',
    pitch: 'Agent runs on a schedule: nightly reviews, weekly dependency bumps, whatever you would rather not babysit.',
  },
  {
    label: 'Agents',
    icon: Bot,
    href: '/dashboard/agents',
    pitch: 'Saved presets: a provider, a model and your instructions, ready to start with one click.',
  },
];

/**
 * The dashboard's nav rows. A signed-in viewer goes straight to the page; an
 * anonymous one gets a panel beside the sidebar that says what the tab is
 * and offers the two auth buttons — the same anchoring as the worktree PR
 * panel, so it overlays the content area instead of covering sibling rows.
 * A row the page owns (`tasksNav`) is neither: it selects a view in place.
 */
function NavRows({
  signedIn,
  returnHref,
  tasksNav,
}: {
  signedIn: boolean;
  returnHref: string;
  tasksNav?: ShareNavTarget;
}) {
  const [openLabel, setOpenLabel] = useState<string | null>(null);
  const [sideOffset, setSideOffset] = useState(EDGE_GAP);
  return (
    <div className="px-2">
      {NAV.map(({ key, label, icon: Icon, href, pitch }, index) => {
        const row = (
          <>
            <Icon className="mr-2 h-4 w-4" />
            {label}
          </>
        );
        if (key === 'tasks' && tasksNav) {
          return (
            <Button
              key={label}
              variant="subtle"
              aria-current={tasksNav.active ? 'page' : undefined}
              onClick={tasksNav.onSelect}
              className={cn(
                'h-auto w-full justify-start py-1.5 text-xs',
                index > 0 && 'mt-1',
                tasksNav.active && SHARE_ROW_SELECTED,
              )}
            >
              {row}
            </Button>
          );
        }
        if (signedIn) {
          return (
            <Button
              key={label}
              asChild
              variant="subtle"
              className={cn('h-auto w-full justify-start py-1.5 text-xs', index > 0 && 'mt-1')}
            >
              <Link href={href}>{row}</Link>
            </Button>
          );
        }
        return (
          <Popover key={label} open={openLabel === label} onOpenChange={(o) => setOpenLabel(o ? label : null)}>
            <PopoverTrigger asChild>
              <Button
                variant="subtle"
                className={cn(
                  'h-auto w-full justify-start py-1.5 text-xs',
                  index > 0 && 'mt-1',
                  openLabel === label && 'bg-foreground/10 text-foreground',
                )}
                onPointerDown={(event) => setSideOffset(offsetToSidebarEdge(event.currentTarget))}
              >
                {row}
              </Button>
            </PopoverTrigger>
            <PopoverContent
              side="right"
              align="start"
              alignOffset={-6}
              sideOffset={sideOffset}
              collisionPadding={8}
              className="w-72 p-3 font-mono"
            >
              <div className="flex items-center gap-1.5 text-xs font-medium">
                <Icon className="h-3.5 w-3.5" />
                {label}
              </div>
              <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">{pitch}</p>
              <p className="mt-2 text-[11px] text-muted-foreground">Sign in to use it.</p>
              <AuthButtons returnHref={returnHref} loginVariant="outline" className="mt-2.5" />
            </PopoverContent>
          </Popover>
        );
      })}
    </div>
  );
}

export function ShareShell({
  token,
  share,
  sidebar,
  tasksNav,
  children,
}: {
  /** The link token: it authorizes every image fetch under this shell. */
  token: string;
  share: PublicShareResponse;
  /** The subject-specific middle of the sidebar (the shared session rows). */
  sidebar: React.ReactNode;
  /** Present when this page carries the shared tasks: the Tasks row selects them. */
  tasksNav?: ShareNavTarget;
  children: React.ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const openSidebar = useCallback(() => setMobileOpen(true), []);
  const closeSidebar = useCallback(() => setMobileOpen(false), []);
  const returnHref = useReturnHref();
  const signedIn = share.viewer !== null;
  const chrome = useMemo<ShareChrome>(
    () => ({ share, signedIn, returnHref, openSidebar, closeSidebar }),
    [share, signedIn, returnHref, openSidebar, closeSidebar],
  );

  const owner = principalFromResponse(share.owner);
  const viewer = principalFromResponse(share.viewer);
  // Every avatar on this page — the owner card, the viewer, an assignee, a
  // comment author — resolves through the token, not the cookie proxy.
  const resolveAvatar = useCallback((principal: Principal) => publicAvatarSrc(token, principal), [token]);

  return (
    <ShareChromeContext.Provider value={chrome}>
      <PrincipalAvatarSrcProvider resolve={resolveAvatar}>
      <div className="flex h-dvh max-w-full overflow-hidden bg-background text-foreground">
        {/* Mobile scrim: the sidebar is a drawer below lg. */}
        {mobileOpen && (
          <div className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm lg:hidden" onClick={closeSidebar} />
        )}

        <aside
          className={cn(
            'fixed inset-y-0 left-0 z-50 flex shrink-0 transform flex-col border-r border-border bg-surface-nav font-mono text-sm transition-[transform] duration-300 ease-in-out lg:relative lg:translate-x-0',
            mobileOpen ? 'translate-x-0' : '-translate-x-full',
          )}
          style={{ width: SIDEBAR_WIDTH }}
        >
          {/* Brand row — the same slot the dashboard's logo sits in. */}
          <div className="flex items-center justify-between pb-3 pl-5 pr-3 pt-2">
            <Link href="/" className="flex items-center" aria-label="Vicoa">
              <Image src="/images/vicoa-logo-text.webp" alt="Vicoa" width={0} height={0} sizes="100vw" className="h-6 w-auto" priority />
            </Link>
            <Button type="button" variant="ghost" size="icon" className="h-8 w-8 lg:hidden" onClick={closeSidebar}>
              <X className="h-5 w-5" />
              <span className="sr-only">Close sidebar</span>
            </Button>
          </div>

          <NavRows signedIn={signedIn} returnHref={returnHref} tasksNav={tasksNav} />

          <div className="mx-2 my-2 h-px bg-muted/30" />

          {/* Who shared it — only when the link opted in. Display name only; never an email on a public surface. */}
          {owner && (
            <div className="mx-2 mb-1 flex items-center gap-2.5 rounded-md bg-muted/40 px-2.5 py-2">
              <PrincipalAvatar principal={owner} size="sm" />
              <div className="min-w-0">
                <div className="truncate text-xs">{owner.name ?? 'A Vicoa user'}</div>
                <div className="truncate text-[11px] text-muted-foreground">shared this with you</div>
              </div>
            </div>
          )}

          <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-2 py-2">{sidebar}</div>

          {/* Account slot: the viewer's own identity, or the sign-up card. */}
          <div className="border-t border-border/60 p-2">
            {viewer ? (
              <Link
                href="/dashboard"
                className="flex items-center gap-3 rounded-md p-2 transition-colors hover:bg-muted/40"
              >
                <PrincipalAvatar principal={viewer} size="md" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs">{viewer.name ?? 'You'}</div>
                  <div className="truncate text-[11px] text-muted-foreground">Signed in · open Vicoa</div>
                </div>
                <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              </Link>
            ) : (
              <div className="p-2 pb-1">
                <div className="text-xs font-medium">Run agents anywhere</div>
                <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                  Claude Code, Codex and other coding agents, from your laptop or your phone. Share sessions like
                  this one.
                </p>
                <Button asChild size="sm" className="mt-4 h-7 w-full text-xs">
                  <Link href={`/sign-up?redirect=${encodeURIComponent(returnHref)}`}>Sign up for free</Link>
                </Button>
                <Link
                  href="/"
                  className="mt-3.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  Learn more
                  <ArrowUpRight className="h-3 w-3" />
                </Link>
              </div>
            )}
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">{children}</main>
      </div>
      </PrincipalAvatarSrcProvider>
    </ShareChromeContext.Provider>
  );
}

/**
 * The main pane's header: the mobile sidebar toggle, the view's own identity
 * line (`children`), and the auth actions on the right — Log in / Sign up for
 * an anonymous visitor, "Open in Vicoa" for a signed-in one. `openHref` is
 * where that button goes when the viewer can see the target in their own
 * dashboard (the owner looking at their own session); otherwise the dashboard.
 */
export function ShareHeader({ children, openHref }: { children: React.ReactNode; openHref?: string | null }) {
  const { openSidebar, signedIn, returnHref } = useShareChrome();
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-border/60 py-2 pl-2 pr-2 lg:pl-4">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0 lg:hidden"
        onClick={openSidebar}
        title="Open sidebar"
      >
        <Menu className="h-5 w-5" />
        <span className="sr-only">Open sidebar</span>
      </Button>
      <div className="min-w-0 flex-1">{children}</div>
      {signedIn ? (
        <Button asChild size="sm" variant="outline" className="h-7 shrink-0 gap-1 text-xs">
          <Link href={openHref ?? '/dashboard'}>
            Open in Vicoa
            <ArrowUpRight className="h-3 w-3" />
          </Link>
        </Button>
      ) : (
        <AuthButtons returnHref={returnHref} className="shrink-0" />
      )}
    </div>
  );
}

/**
 * A sidebar group: a label over its rows, in the dashboard sidebar's group
 * header style (sentence case, normal weight, muted) — never uppercase or bold.
 */
export function ShareSidebarSection({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <div className="mb-0.5 flex min-w-0 items-center gap-1.5 px-2 py-1 text-[0.8rem] font-normal text-muted-foreground">
        {label}
      </div>
      {children}
    </div>
  );
}
