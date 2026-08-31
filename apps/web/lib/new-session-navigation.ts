import type { useRouter } from 'next/navigation';

type AppRouter = ReturnType<typeof useRouter>;

/**
 * Whether opening a just-created session should take over the user's view.
 *
 * Creating a session is async — the `spawn-session` RPC plus the `waitForEntity`
 * that follows can take several seconds. If the user navigates elsewhere while it
 * runs (clicks another session in the sidebar, opens settings, …), yanking them
 * to the freshly-created session on completion is jarring: they deliberately
 * moved on. So we only open it when the user is still on the page they launched
 * from.
 *
 * Pathname-only comparison: a query-string change on the same page (e.g. the
 * new-session form swapping its `?directory=`/`?worktreeBranch=` params) is not
 * "navigating away", so it must not suppress the open.
 */
export function shouldOpenCreatedSession(startPath: string, currentPath: string): boolean {
  return startPath === currentPath;
}

/**
 * Push to `target` only if the user hasn't navigated away from `startPath` since
 * the create began. Reads the live `window.location`, so it stays correct across
 * the `await`s that precede it (a value captured before them would be stale).
 * See {@link shouldOpenCreatedSession}.
 *
 * `startPath` should be captured with `currentPathname()` at the very top of the
 * submit handler, before the first `await`.
 */
export function openCreatedSession(
  router: Pick<AppRouter, 'push'>,
  startPath: string,
  target: string,
): void {
  if (shouldOpenCreatedSession(startPath, currentPathname())) {
    router.push(target);
  }
}

/** The live pathname (no query/hash), or `''` when running on the server. */
export function currentPathname(): string {
  return typeof window === 'undefined' ? '' : window.location.pathname;
}
