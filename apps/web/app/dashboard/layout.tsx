'use client';

import { usePathname } from 'next/navigation';
import DashboardLayoutComponent from './dashboard-layout';

// The authenticated dashboard segment (/dashboard/*). Everything here gets the
// full dashboard shell (sidebar + session chrome) EXCEPT the upgrade paywall,
// which is a focused, self-contained full-screen page with its own back button
// and therefore renders bare.
//
// Desktop routing (marketing-root redirect, login-required gating) is owned
// entirely by DesktopAuthGate in the root layout — not here.
export default function DashboardSegmentLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // The upgrade paywall opts out of the sidebar chrome (full-screen, self-contained).
  if (pathname === '/dashboard/upgrade') {
    return <section className="min-h-screen">{children}</section>;
  }

  return <DashboardLayoutComponent>{children}</DashboardLayoutComponent>;
}
