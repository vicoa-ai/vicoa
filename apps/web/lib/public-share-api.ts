/**
 * The public share-link API (collaboration §3.4, P4): `/api/v1/public/shares/<token>/…`.
 *
 * Deliberately not a method on `BackendAPI`: that client always attaches the
 * browser's bearer, and this surface must work with none. The token in the URL
 * is the capability. A bearer is added only when the browser happens to have
 * one — that is how an `authenticated`-audience link tells a signed-in visitor
 * apart, and how a comment gets attributed to a real account.
 *
 * Every failure the server can't distinguish for us (unknown, revoked,
 * expired, wrong audience, id not covered) arrives as the same 404 and is
 * surfaced as `ShareNotFoundError` — the viewer renders one honest "not
 * available" state and never guesses which it was.
 */

import type {
  PublicBoardResponse,
  PublicMessagesPage,
  PublicSessionSummary,
  PublicSessionsPage,
  PublicShareResponse,
  TaskTimelineResponse,
} from '@/lib/backend-api';
import { getBrowserAccessToken } from '@/lib/auth/browser-token';
import { getCloudApiBase, getDesktopConfig } from '@/lib/runtime-config';

export class ShareNotFoundError extends Error {
  constructor() {
    super('Share not found');
    this.name = 'ShareNotFoundError';
  }
}

export class ShareRateLimitedError extends Error {
  retryAfterSeconds: number;
  constructor(retryAfterSeconds: number) {
    super('Too many requests');
    this.name = 'ShareRateLimitedError';
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export class ShareRequestError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ShareRequestError';
    this.status = status;
  }
}

function basePath(token: string): string {
  return `${getCloudApiBase()}/api/v1/public/shares/${encodeURIComponent(token)}`;
}

/**
 * The public URL a link is shared as. On the web it is this deployment's own
 * origin (a self-host shares its own address); the desktop renderer is served
 * from a loopback port, so it names the web deployment it belongs to instead.
 */
export function shareUrl(token: string): string {
  const desktop = getDesktopConfig();
  const origin = desktop
    ? (process.env.NEXT_PUBLIC_VICOA_WEB_URL ?? 'https://vicoa.ai')
    : typeof window !== 'undefined'
      ? window.location.origin
      : (process.env.NEXT_PUBLIC_VICOA_WEB_URL ?? 'https://vicoa.ai');
  return `${origin.replace(/\/$/, '')}/share/${token}`;
}

/** The share-scoped attachment URL — no cookie proxy; the token authorizes it. */
export function publicAttachmentUrl(token: string, attachmentId: string): string {
  return `${basePath(token)}/attachments/${attachmentId}`;
}

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  signal?: AbortSignal;
  /** A pre-obtained bearer (server components read the cookie session). */
  accessToken?: string | null;
}

async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  const appVersion = process.env.NEXT_PUBLIC_APP_VERSION;
  if (appVersion) headers['X-Client-Version'] = appVersion;
  const token =
    options.accessToken !== undefined
      ? options.accessToken
      : typeof window !== 'undefined'
        ? await getBrowserAccessToken().catch(() => null)
        : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(url, {
    method: options.method ?? 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
    cache: 'no-store',
  });
  if (response.status === 404) throw new ShareNotFoundError();
  if (response.status === 429) {
    const retry = Number.parseInt(response.headers.get('retry-after') ?? '5', 10);
    throw new ShareRateLimitedError(Number.isFinite(retry) ? retry : 5);
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string' && body.detail.trim()) detail = body.detail;
    } catch {
      // keep the generic message
    }
    throw new ShareRequestError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function fetchPublicShare(
  token: string,
  options: RequestOptions = {},
): Promise<PublicShareResponse> {
  return request<PublicShareResponse>(basePath(token), options);
}

export function fetchPublicSessions(
  token: string,
  params: { limit?: number; offset?: number } = {},
  options: RequestOptions = {},
): Promise<PublicSessionsPage> {
  const query = new URLSearchParams();
  if (params.limit) query.set('limit', String(params.limit));
  if (params.offset) query.set('offset', String(params.offset));
  const suffix = query.size ? `?${query.toString()}` : '';
  return request<PublicSessionsPage>(`${basePath(token)}/sessions${suffix}`, options);
}

export function fetchPublicSession(
  token: string,
  instanceId: string,
  options: RequestOptions = {},
): Promise<PublicSessionSummary> {
  return request<PublicSessionSummary>(`${basePath(token)}/sessions/${instanceId}`, options);
}

export function fetchPublicMessages(
  token: string,
  instanceId: string,
  params: { after?: string; before?: string; limit?: number } = {},
  options: RequestOptions = {},
): Promise<PublicMessagesPage> {
  const query = new URLSearchParams();
  if (params.after) query.set('after', params.after);
  if (params.before) query.set('before', params.before);
  if (params.limit) query.set('limit', String(params.limit));
  const suffix = query.size ? `?${query.toString()}` : '';
  return request<PublicMessagesPage>(
    `${basePath(token)}/sessions/${instanceId}/messages${suffix}`,
    options,
  );
}

export function fetchPublicBoard(
  token: string,
  options: RequestOptions = {},
): Promise<PublicBoardResponse> {
  return request<PublicBoardResponse>(`${basePath(token)}/board`, options);
}

export function fetchPublicTaskTimeline(
  token: string,
  taskId: string,
  options: RequestOptions = {},
): Promise<TaskTimelineResponse> {
  return request<TaskTimelineResponse>(`${basePath(token)}/tasks/${taskId}/timeline`, options);
}

export function postPublicComment(
  token: string,
  taskId: string,
  data: { body: string; parent_comment_id?: string | null },
): Promise<TaskTimelineResponse> {
  return request<TaskTimelineResponse>(`${basePath(token)}/tasks/${taskId}/comments`, {
    method: 'POST',
    body: data,
  });
}
