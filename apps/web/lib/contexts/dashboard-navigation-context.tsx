'use client';

import { createContext, useContext } from 'react';

// Create a context for dashboard navigation
export interface DashboardNavigationContextType {
  openSession: (instanceId: string) => void;
  openSidebar: () => void;
}

export const DashboardNavigationContext = createContext<DashboardNavigationContextType | null>(null);

export const useDashboardNavigation = () => {
  const context = useContext(DashboardNavigationContext);
  if (!context) {
    throw new Error('useDashboardNavigation must be used within DashboardNavigationContext');
  }
  return context;
};