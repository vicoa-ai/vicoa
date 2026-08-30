// In-memory, stale-while-revalidate cache for the Tasks page, mirroring the
// session caches (`recentInstances` in agent-dashboard-context, the
// `lib/message-store.ts` singleton): a module-level singleton that lives above
// the route, so switching tabs and coming back paints the last-loaded board
// instantly while the page revalidates in the background. Not persisted —
// resets on a full reload / app restart, exactly like the session caches.
//
// Caveat inherited from those caches: it is not keyed by user and not cleared
// on sign-out. In practice sign-out unmounts the dashboard and a real account
// switch reloads the process; the page's own revalidate overwrites stale rows
// on the next load either way.

import type {
  ProjectResponse,
  TaskLabelResponse,
  TaskResponse,
} from '@/lib/backend-api';

export interface TasksCacheData {
  projects: ProjectResponse[];
  tasks: TaskResponse[];
  labels: TaskLabelResponse[];
}

let cache: TasksCacheData | null = null;

export function getTasksCache(): TasksCacheData | null {
  return cache;
}

export function setTasksCache(data: TasksCacheData): void {
  cache = data;
}
