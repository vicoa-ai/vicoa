'use client';

import { usePathname } from 'next/navigation';
import DashboardLayoutComponent from './dashboard-layout';

// The authenticated dashboard segment (/dashboard/*). Everything here gets the
// full dashboard shell (sidebar + session chrome) EXCEPT the upgrade page, a
// focused full-screen page with its own back button that renders bare. It is
// only reached from outside the app now (the pricing page's sign-up redirect);
// in the app, Upgrade opens a dialog over the shell. Leaving the shell
// unmounts the session list and its live connection, and coming back loads
// them all again, which is why the seats page renders inside it.
//
// Desktop routing (marketing-root redirect, login-required gating) is owned
// entirely by DesktopAuthGate in the root layout — not here.
const BARE_PAGES = new Set(['/dashboard/upgrade']);

export default function DashboardSegmentLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // The upgrade page opts out of the sidebar chrome (full-screen, self-contained).
  if (BARE_PAGES.has(pathname)) {
    return <section className="min-h-screen">{children}</section>;
  }

  return <DashboardLayoutComponent>{children}</DashboardLayoutComponent>;
}
