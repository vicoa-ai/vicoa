'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { getBackendAPI, MessageResponse } from '@/lib/backend-api';
import { useAgentStreaming } from '@/lib/contexts/agent-streaming-context';

interface UseMessageStreamOptions {
  instanceId: string;
  enabled?: boolean;
  onMessage?: (message: MessageResponse) => void;
  onStatusUpdate?: (status: string) => void;
  onError?: (error: Error) => void;
  onConnectionStateChange?: (connected: boolean) => void;
}

export function useMessageStream({
  instanceId,
  enabled = true,
  onMessage,
  onStatusUpdate,
  onError,
  onConnectionStateChange,
}: UseMessageStreamOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  // Set once the instance reaches a terminal state. Blocks all reconnection —
  // the stream is dead for good, retrying just hammers a closed session.
  const terminatedRef = useRef(false);
  const maxReconnectAttempts = 5;
  const baseReconnectDelay = 1000; // 1 second
  
  // Get streaming context if available
  let streamingContext;
  try {
    streamingContext = useAgentStreaming();
  } catch {
    // Context not available, continue without it
    streamingContext = null;
  }

  const updateConnectionState = useCallback((connected: boolean) => {
    setIsConnected(connected);
    onConnectionStateChange?.(connected);
    
    // Update global streaming context
    if (streamingContext) {
      if (connected) {
        streamingContext.registerConnection(instanceId);
      } else {
        streamingContext.unregisterConnection(instanceId);
      }
    }
  }, [onConnectionStateChange, streamingContext, instanceId]);

  const handleError = useCallback((err: Error) => {
    setError(err);
    onError?.(err);
    streamingContext?.recordError();
  }, [onError, streamingContext]);

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    updateConnectionState(false);
  }, [updateConnectionState]);

  const connect = useCallback(async () => {
    // Check both local enabled flag and global streaming setting
    const globalEnabled = streamingContext?.globalStreamingEnabled ?? true;
    if (!enabled || !instanceId || !globalEnabled) return;
    // Instance already terminated — do not open or reconnect a dead stream.
    if (terminatedRef.current) return;

    try {
      cleanup();

      const api = getBackendAPI(true);
      const streamUrl = await api.getMessageStreamUrl(instanceId);

      const eventSource = new EventSource(streamUrl);
      eventSourceRef.current = eventSource;

      // Reset the backoff only when the stream proves it carries traffic (see
      // markStreamHealthy) — not on `onopen`, which fires the instant the
      // connection opens, before it has survived or delivered anything. A busy
      // channel may never emit a heartbeat, so data events reset it too.
      const markStreamHealthy = () => {
        reconnectAttempts.current = 0;
      };

      eventSource.onopen = () => {
        updateConnectionState(true);
        setError(null);
      };

      // Listen for connection confirmation event
      eventSource.addEventListener('connected', (event) => {
        try {
          const data = JSON.parse(event.data);
        } catch (err) {
          console.error('Error parsing connected event:', err);
        }
      });

      // Listen for status update events (named event)
      eventSource.addEventListener('status_update', (event) => {
        markStreamHealthy();
        try {
          const data = JSON.parse(event.data);
          if (data.status && onStatusUpdate) {
            onStatusUpdate(data.status);
          }
        } catch (err) {
          console.error('Error parsing status update:', err);
          handleError(new Error('Failed to parse status update'));
        }
      });

      // Listen for message updates (named event)
      eventSource.addEventListener('message_update', (event) => {
        markStreamHealthy();
        try {
          const data = JSON.parse(event.data);
          onMessage?.(data);
        } catch (err) {
          console.error('Error parsing message update:', err);
        }
      });

      // Listen for terminate events — the instance reached a terminal state
      // (completed/killed/deleted/etc). Stop permanently; never reconnect.
      eventSource.addEventListener('terminate', (event) => {
        const messageEvent = event as MessageEvent;
        try {
          if (messageEvent.data) {
            const data = JSON.parse(messageEvent.data);
            if (data.status) {
              onStatusUpdate?.(data.status);
            }
          }
        } catch (err) {
          console.error('Error parsing terminate event:', err);
        }
        terminatedRef.current = true;
        cleanup();
      });

      // Listen for agent heartbeat events (named event)
      eventSource.addEventListener('agent_heartbeat', (event) => {
        markStreamHealthy();
        try {
          const data = JSON.parse(event.data);
          // You can add a callback for heartbeat updates if needed
        } catch (err) {
          console.error('Error parsing agent heartbeat:', err);
        }
      });

      // Listen for heartbeat events to keep connection alive (named event)
      eventSource.addEventListener('heartbeat', (event) => {
        markStreamHealthy();
        try {
          const data = JSON.parse(event.data);
        } catch (err) {
          console.error('Error parsing heartbeat:', err);
        }
      });

      // Listen for error events (named event)
      eventSource.addEventListener('error', (event: Event) => {
        const messageEvent = event as MessageEvent;
        if (!messageEvent.data) {
          handleError(new Error('Stream error'));
          return;
        }
        try {
          const data = JSON.parse(messageEvent.data);
          console.error('Stream error event:', data);
          handleError(new Error(data.error || 'Stream error'));
        } catch (err) {
          console.error('Error parsing error event:', err);
          handleError(new Error('Stream error'));
        }
      });

      // Default message handler (for event: message which is sent for message_insert)
      eventSource.onmessage = (event) => {
        markStreamHealthy();
        try {
          const data = JSON.parse(event.data);

          // This handles message_insert which backend sends as "event: message"
          onMessage?.(data);
          streamingContext?.recordMessage();
        } catch (err) {
          console.error('Error parsing SSE message:', err, event.data);
          handleError(new Error('Failed to parse message from stream'));
        }
      };

      eventSource.onerror = (event) => {
        console.error('Message stream error:', event);
        updateConnectionState(false);

        // Instance terminated — the stream close is expected, do not reconnect.
        if (terminatedRef.current) return;

        // Attempt to reconnect with exponential backoff
        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = baseReconnectDelay * Math.pow(2, reconnectAttempts.current);
          reconnectAttempts.current++;

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        } else {
          handleError(new Error('Max reconnection attempts reached'));
        }
      };

    } catch (err) {
      console.error('Failed to connect to message stream:', err);
      handleError(err instanceof Error ? err : new Error('Failed to connect to stream'));
    }
  }, [enabled, instanceId, onMessage, handleError, updateConnectionState, cleanup, streamingContext?.globalStreamingEnabled]);

  const disconnect = useCallback(() => {
    cleanup();
  }, [cleanup]);

  const reconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    terminatedRef.current = false;
    connect();
  }, [connect]);

  // Initialize connection
  useEffect(() => {
    const globalEnabled = streamingContext?.globalStreamingEnabled ?? true;
    if (enabled && instanceId && globalEnabled) {
      // Fresh instance — clear any terminal state carried from a prior one.
      terminatedRef.current = false;
      connect();
    } else if (!globalEnabled) {
      cleanup();
    }

    return cleanup;
  }, [enabled, instanceId, streamingContext?.globalStreamingEnabled]);

  return {
    isConnected,
    error,
    reconnect,
    disconnect,
  };
}