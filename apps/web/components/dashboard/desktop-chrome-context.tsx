'use client';

import { createContext, useContext } from 'react';

/**
 * Lets deep children (e.g. the agent chat header) render the desktop
 * "collapsed sidebar" control inline. When the left sidebar is collapsed there
 * is no titlebar to host the brand + expand button, so the chat header shows
 * them itself and flows its title after them (instead of the title sliding to
 * the far left under a floating overlay). Defaults are inert on web.
 */
export interface DesktopChrome {
  isDesktop: boolean;
  sidebarCollapsed: boolean;
  expandSidebar: () => void;
}

const DesktopChromeContext = createContext<DesktopChrome>({
  isDesktop: false,
  sidebarCollapsed: false,
  expandSidebar: () => {},
});

export const DesktopChromeProvider = DesktopChromeContext.Provider;

export const useDesktopChrome = (): DesktopChrome => useContext(DesktopChromeContext);
