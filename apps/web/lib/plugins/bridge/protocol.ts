/**
 * Wire protocol between a plugin page (sandboxed iframe) and the host.
 *
 * The page talks to Vicoa only by `postMessage`: it sends requests, the host
 * answers each one by id, and the host pushes events (theme changes, watch
 * updates, header clicks). Every message carries the `__vicoa: 1` marker so
 * stray messages from libraries inside the page are ignored. The host only
 * accepts messages whose `event.source` is its own iframe.
 */

/** Version of the `window.vicoa` API, exposed as `vicoa.apiVersion`. */
export const BRIDGE_API_VERSION = 1;

export const BRIDGE_TAG = '__vicoa';

/** Guardrails on what one page may send. */
export const BRIDGE_LIMITS = {
  /** Largest request the host reads (serialized JSON). */
  maxMessageBytes: 1_000_000,
  /** Requests per rolling second; more are refused with `rate_limited`. */
  maxRequestsPerSecond: 60,
  /** Live `watch` subscriptions per page. */
  maxWatches: 32,
} as const;

export interface BridgeRequest {
  [BRIDGE_TAG]: 1;
  kind: 'req';
  id: number;
  method: string;
  params: unknown;
}

export type BridgeErrorCode =
  | 'permission_denied'
  | 'unknown_method'
  | 'invalid_params'
  | 'rate_limited'
  | 'too_large'
  | 'not_found'
  | 'not_allowed'
  | 'machine_offline'
  | 'daemon_outdated'
  | 'not_available'
  | 'failed';

export interface BridgeErrorBody {
  code: BridgeErrorCode;
  message: string;
}

export type BridgeResponse =
  | { [BRIDGE_TAG]: 1; kind: 'res'; id: number; ok: true; result: unknown }
  | { [BRIDGE_TAG]: 1; kind: 'res'; id: number; ok: false; error: BridgeErrorBody };

export interface BridgeEvent {
  [BRIDGE_TAG]: 1;
  kind: 'event';
  name: string;
  payload: unknown;
}

export type HostMessage = BridgeResponse | BridgeEvent;

/** An error a bridge method throws to answer the page with a code. */
export class BridgeError extends Error {
  readonly code: BridgeErrorCode;

  constructor(code: BridgeErrorCode, message: string) {
    super(message);
    this.code = code;
  }
}

export function isBridgeRequest(data: unknown): data is BridgeRequest {
  if (!data || typeof data !== 'object') return false;
  const m = data as Record<string, unknown>;
  return (
    m[BRIDGE_TAG] === 1 &&
    m.kind === 'req' &&
    typeof m.id === 'number' &&
    Number.isFinite(m.id) &&
    typeof m.method === 'string' &&
    m.method.length > 0 &&
    m.method.length <= 64
  );
}

export function okResponse(id: number, result: unknown): BridgeResponse {
  return { [BRIDGE_TAG]: 1, kind: 'res', id, ok: true, result: result ?? null };
}

export function errorResponse(id: number, error: BridgeErrorBody): BridgeResponse {
  return { [BRIDGE_TAG]: 1, kind: 'res', id, ok: false, error };
}

export function eventMessage(name: string, payload: unknown): BridgeEvent {
  return { [BRIDGE_TAG]: 1, kind: 'event', name, payload: payload ?? null };
}

/** Counts requests in a rolling one-second window. */
export class RateLimiter {
  private stamps: number[] = [];

  constructor(private readonly perSecond: number) {}

  /** Whether one more request is allowed at `now` (ms); records it if so. */
  take(now: number): boolean {
    const cutoff = now - 1000;
    while (this.stamps.length && this.stamps[0] <= cutoff) this.stamps.shift();
    if (this.stamps.length >= this.perSecond) return false;
    this.stamps.push(now);
    return true;
  }
}
