'use client';

import { useEffect, useRef, useCallback } from 'react';
import { getBackendAPI, AgentInstanceResponse } from '@/lib/backend-api';

interface UseInstanceStreamOptions {
  enabled?: boolean;
  onInstanceCreated?: (instance: AgentInstanceResponse) => void;
  onInstanceUpdated?: (instance: Partial<AgentInstanceResponse> & { id: string }) => void;
}

/**
 * Subscribes to /api/v1/agent-instances/stream and delivers instant
 * instance list updates (new sessions, status changes) without polling.
 *
 * Reconnects automatically with exponential back-off up to 5 attempts,
 * then falls back to silence (the dashboard's 5-min full-refresh acts as
 * a safety net).
 */
export function useInstanceStream({
  enabled = true,
  onInstanceCreated,
  onInstanceUpdated,
}: UseInstanceStreamOptions) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const baseReconnectDelay = 1000;

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const connect = useCallback(async () => {
    if (!enabled) return;

    cleanup();

    try {
      const api = getBackendAPI(true);
      const streamUrl = await api.getInstanceStreamUrl();
      const es = new EventSource(streamUrl);
      eventSourceRef.current = es;

      // Reset the backoff only when the stream proves it carries traffic — a
      // received event (heartbeat or real data). Resetting on `onopen` instead
      // counts a connection that dies immediately as healthy, so backoff never
      // escalates and reconnects storm at the 1s base delay. A busy channel
      // may never emit a heartbeat (the server only sends one after 15s of
      // silence), so data events must reset the counter too.
      const markStreamHealthy = () => {
        reconnectAttempts.current = 0;
      };

      es.addEventListener('instance_created', (event) => {
        markStreamHealthy();
        try {
          const data = JSON.parse(event.data) as AgentInstanceResponse;
          onInstanceCreated?.(data);
        } catch (err) {
          console.error('[InstanceStream] Error parsing instance_created event:', err);
        }
      });

      es.addEventListener('instance_updated', (event) => {
        markStreamHealthy();
        try {
          const data = JSON.parse(event.data) as Partial<AgentInstanceResponse> & { id: string };
          onInstanceUpdated?.(data);
        } catch (err) {
          console.error('[InstanceStream] Error parsing instance_updated event:', err);
        }
      });

      es.addEventListener('heartbeat', () => {
        markStreamHealthy();
      });

      es.onerror = () => {
        console.warn('[InstanceStream] Connection error, reconnecting...', {
          attempt: reconnectAttempts.current + 1,
          max: maxReconnectAttempts,
        });
        cleanup();
        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = baseReconnectDelay * Math.pow(2, reconnectAttempts.current);
          reconnectAttempts.current++;
          reconnectTimeoutRef.current = setTimeout(() => connect(), delay);
        } else {
          console.warn('[InstanceStream] Max reconnect attempts reached, falling back to polling');
        }
      };
    } catch (err) {
      console.error('Failed to connect to instance stream:', err);
    }
  }, [enabled, onInstanceCreated, onInstanceUpdated, cleanup]);

  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      cleanup();
    }
    return cleanup;
  }, [enabled]);

  return { reconnect: () => { reconnectAttempts.current = 0; connect(); } };
}
