// Session statuses treated as "closed" — kept in sync with
// _closedSessionStatuses in vicoa-app (custom_functions.dart). A closed
// session produces no live updates worth streaming, so the SSE message
// stream should not be (re)opened for one.
const CLOSED_SESSION_STATUSES = new Set([
  'COMPLETED',
  'FAILED',
  'KILLED',
  'DELETED',
  'CANCELLED',
  'DISCONNECTED',
  'PAUSED',
  'STALE',
]);

export function isSessionClosed(status: string | null | undefined): boolean {
  if (!status) return false;
  return CLOSED_SESSION_STATUSES.has(status.toUpperCase());
}
