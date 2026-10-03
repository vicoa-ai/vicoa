'use client';

import { usePathname } from 'next/navigation';
import { SEATS_PAGE_HREF } from '@/lib/billing';
import DashboardLayoutComponent from './dashboard-layout';

// The authenticated dashboard segment (/dashboard/*). Everything here gets the
// full dashboard shell (sidebar + session chrome) EXCEPT the upgrade paywall
// and the seats page, which are focused, self-contained full-screen pages with
// their own back button and therefore render bare.
//
// Desktop routing (marketing-root redirect, login-required gating) is owned
// entirely by DesktopAuthGate in the root layout — not here.
const BARE_PAGES = new Set(['/dashboard/upgrade', SEATS_PAGE_HREF]);

export default function DashboardSegmentLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // The paywall pages opt out of the sidebar chrome (full-screen, self-contained).
  if (BARE_PAGES.has(pathname)) {
    return <section className="min-h-screen">{children}</section>;
  }

  return <DashboardLayoutComponent>{children}</DashboardLayoutComponent>;
}
