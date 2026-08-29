/**
 * Direct data-fetch helpers for the chat page (desktop-app v1, plan item 5).
 *
 * Replaces the `/api/agent-dashboard/direct` Next proxy, which serialized a
 * `/auth/me` round-trip in front of every call. These helpers hit the backend
 * straight from the browser via `getBackendAPI(true)`, which resolves base
 * URL + auth per runtime mode:
 * - plain web / desktop-cloud → `NEXT_PUBLIC_BACKEND_API_URL` + Supabase JWT;
 * - desktop-local → the daemon's local server (`apiBase`) + `Bearer <nonce>`.
 *
 * Response bodies are the backend JSON the proxy used to forward verbatim
 * inside `{success, data}` — callers now get the payload directly.
 */

import {
  getBackendAPI,
  type AgentInstanceDetail,
  type MessageResponse,
} from '@/lib/backend-api';

export interface GetInstanceDetailOptions {
  messageLimit?: number;
  beforeMessageId?: string;
}

/** `GET /api/v1/agent-instances/{id}` with optional message pagination. */
export function getInstanceDetail(
  instanceId: string,
  { messageLimit, beforeMessageId }: GetInstanceDetailOptions = {},
): Promise<AgentInstanceDetail> {
  return getBackendAPI(true).getInstanceDetail(
    instanceId,
    messageLimit,
    beforeMessageId,
  );
}

/** `POST /api/v1/agent-instances/{id}/messages` — send a user message,
 * optionally riding one or more already-uploaded image attachment ids.
 * Returns the created message: its `message_metadata.queue` carries the
 * backend's authoritative queued/not-queued decision for this exact message
 * (queued iff the agent was ACTIVE when it landed), so the caller can correct
 * an optimistic row's placement off the response instead of the slower WS
 * echo. */
export function postInstanceMessage(
  instanceId: string,
  content: string,
  attachmentIds: string[] = [],
): Promise<MessageResponse> {
  return getBackendAPI(true).createUserMessage(instanceId, {
    content,
    ...(attachmentIds.length > 0 ? { attachment_ids: attachmentIds } : {}),
  });
}

/**
 * `POST /api/v1/agent-instances/{id}/messages/{messageId}/cancel` — cancel a
 * still-queued user message. Resolves to `{ cancelled: false }` if the
 * message was already consumed/cancelled by the time the request landed.
 */
export function cancelQueuedMessage(
  instanceId: string,
  messageId: string,
): Promise<{ cancelled: boolean }> {
  return getBackendAPI(true).cancelQueuedMessage(instanceId, messageId);
}
