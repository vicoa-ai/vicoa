/**
 * Send a message to a session from outside its chat page (the peek panel, a
 * plugin), resuming it first when its agent has stopped.
 *
 * The same decision the session page makes from its live state: a reachable
 * agent gets the message directly; a stopped one is relaunched on its machine
 * with the message as its next prompt; an offline machine can't take either.
 */

import type { getBackendAPI } from '@/lib/backend-api';
import { canResumeSession, resumeSession } from '@/lib/session-resume';
import { isReachable, resolveLiveState } from '@/lib/session-liveness';

type Api = ReturnType<typeof getBackendAPI>;

export type ContinueOutcome = 'sent' | 'resumed';

export class ContinueSessionError extends Error {
  readonly reason: 'machine-offline' | 'not-resumable';

  constructor(reason: 'machine-offline' | 'not-resumable', message: string) {
    super(message);
    this.reason = reason;
  }
}

export async function continueSession(
  api: Api,
  sessionId: string,
  text: string,
): Promise<ContinueOutcome> {
  const detail = await api.getInstanceDetail(sessionId, 1);
  let machine: { last_heartbeat_at?: string | null } | undefined;
  if (detail.machine_id) {
    try {
      machine = (await api.listMachines()).find((m) => m.machine_id === detail.machine_id);
    } catch {
      machine = undefined;
    }
  }
  const state = resolveLiveState(detail, machine);
  if (isReachable(state) || state === 'unknown') {
    await api.createUserMessage(sessionId, { content: text });
    return 'sent';
  }
  if (state === 'machine_offline') {
    throw new ContinueSessionError('machine-offline', "The session's machine is offline");
  }
  if (!canResumeSession(detail, state)) {
    throw new ContinueSessionError('not-resumable', "This session can't be continued");
  }
  const result = await resumeSession(detail, { prompt: text });
  // A reopen of an agent that was still running ignores the prompt.
  if (result.alreadyRunning) {
    await api.createUserMessage(sessionId, { content: text });
    return 'sent';
  }
  return 'resumed';
}
