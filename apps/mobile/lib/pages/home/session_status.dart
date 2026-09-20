// Session status vocabulary for the home filters and the status grouping —
// the mobile twin of `CLOSED_STATUSES` and the status filter switch in the
// web's `session-grouping.ts` (and of the backend's `active_only`), so
// "Active", "Closed" and "In progress" select the same sessions on every
// client.

/// Terminal statuses: what the "Closed" filter shows and "Active" hides.
/// Everything else — including STALE (heartbeat lost, not ended), PAUSED and
/// STARTING — is still a live session.
const Set<String> kClosedStatuses = {
  'COMPLETED',
  'FAILED',
  'KILLED',
  'DELETED',
  'DISCONNECTED',
};

bool isClosedStatus(String? status) => kClosedStatuses.contains(status);

/// "In progress": the agent is working, or was when last heard from.
bool isInProgressStatus(String? status) =>
    status == 'ACTIVE' || status == 'STALE';
