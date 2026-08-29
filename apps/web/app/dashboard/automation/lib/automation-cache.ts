// In-memory, stale-while-revalidate cache for the Automations page, mirroring
// the session caches (`recentInstances` in agent-dashboard-context, the
// `lib/message-store.ts` singleton): a module-level singleton that lives above
// the route, so switching tabs and coming back paints the last-loaded list
// instantly while the page revalidates in the background. Not persisted —
// resets on a full reload / app restart, exactly like the session caches.
//
// Caveat inherited from those caches: it is not keyed by user and not cleared
// on sign-out. In practice sign-out unmounts the dashboard and a real account
// switch reloads the process; the page's own revalidate overwrites stale rows
// on the next load either way.

import type { AutomationResponse, MachineSummary } from '@/lib/backend-api';
import type { AgentCatalog } from '@/lib/agent-catalog';

export interface AutomationCacheData {
  automations: AutomationResponse[];
  machines: MachineSummary[];
  catalog: AgentCatalog;
}

let cache: AutomationCacheData | null = null;

export function getAutomationCache(): AutomationCacheData | null {
  return cache;
}

export function setAutomationCache(data: AutomationCacheData): void {
  cache = data;
}
