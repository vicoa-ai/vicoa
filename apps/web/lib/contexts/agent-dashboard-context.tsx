'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react';
import { getBackendAPI, AgentInstanceResponse, AgentStatus, BillingSubscription } from '@/lib/backend-api';
import { readBrowserIdentity } from '@/lib/auth/browser-token';
import { AGENT_HUB_DEFAULT_THRESHOLD, persistAgentHubDefaultFlag } from '@/lib/agent-hub-default';
import { useInstanceStream } from '@/lib/hooks/use-ws-stream';
import { useDesktopSessionNotifications } from '@/lib/hooks/use-desktop-session-notifications';
import { useDesktopForegroundPresence } from '@/lib/hooks/use-desktop-foreground-presence';
import type { NewMessageBody } from '@/lib/ws-client';

const AGENT_INSTANCE_PAGE_SIZE = 50;

interface AgentDashboardContextType {
  api: ReturnType<typeof getBackendAPI> | null;
  recentInstances: AgentInstanceResponse[];
  billingSubscription: BillingSubscription | null;
  isLoading: boolean;
  isLoadingMoreInstances: boolean;
  hasMoreInstances: boolean;
  error: string | null;
  activeOnly: boolean;
  setActiveOnly: (value: boolean) => void;
  syncUser: () => Promise<void>;
  refreshData: () => Promise<void>;
  loadMoreInstances: () => Promise<void>;
  updateInstanceStatus: (instanceId: string, status: string, latestMessage?: string) => void;
  updateInstance: (instanceId: string, updates: Partial<AgentInstanceResponse>) => void;
  removeInstance: (instanceId: string) => void;
}

const AgentDashboardContext = createContext<AgentDashboardContextType | undefined>(undefined);

export function useAgentDashboard() {
  const context = useContext(AgentDashboardContext);
  if (context === undefined) {
    throw new Error('useAgentDashboard must be used within an AgentDashboardProvider');
  }
  return context;
}

interface AgentDashboardProviderProps {
  children: ReactNode;
}

export function AgentDashboardProvider({ children }: AgentDashboardProviderProps) {
  const [api, setApi] = useState<ReturnType<typeof getBackendAPI> | null>(null);
  const [recentInstances, setRecentInstances] = useState<AgentInstanceResponse[]>([]);
  const [billingSubscription, setBillingSubscription] = useState<BillingSubscription | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMoreInstances, setIsLoadingMoreInstances] = useState(false);
  const [hasMoreInstances, setHasMoreInstances] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const billingFetchedRef = useRef(false);
  const [activeOnly, setActiveOnlyState] = useState(() => {
    if (typeof window === 'undefined') return true;
    return localStorage.getItem('sidebar-show-closed') !== 'true';
  });

  // Desktop shell only (no-op on web): native banners on status transitions
  // + dock badge. Every status path — WS frames, chat-page patches, REST
  // refreshes — lands in recentInstances, so this diff sees all of them.
  useDesktopSessionNotifications(recentInstances);

  // Desktop cloud shell only (no-op on web / logged-out local): report window
  // foreground over the shared WS so the backend silences the phone push while
  // the user is looking at the desktop app (opt-in, on by default).
  useDesktopForegroundPresence();

  const setActiveOnly = useCallback((value: boolean) => {
    setActiveOnlyState(current => {
      if (current !== value) {
        setRecentInstances([]);
      }
      return value;
    });
  }, []);

  useEffect(() => {
    if (typeof document === 'undefined' || recentInstances.length < AGENT_HUB_DEFAULT_THRESHOLD) {
      return;
    }
    persistAgentHubDefaultFlag();
  }, [recentInstances.length]);

  // Initialize API client with direct Supabase auth
  useEffect(() => {
    const apiClient = getBackendAPI(true); // Enable Supabase auth
    setApi(apiClient);
  }, []);

  // Sync user with Agent Dashboard API using direct authentication
  const syncUser = async () => {
    if (!api) return;
    
    try {
      setError(null);
      
      // Get the current user from whichever provider issued the session
      const identity = await readBrowserIdentity();

      if (!identity) {
        throw new Error('User not authenticated');
      }

      // Sync user with vicoa backend directly
      await api.syncUser(identity);

      console.log('User synced successfully with Agent Dashboard API');
    } catch (err) {
      console.error('Failed to sync user:', err);
      setError(err instanceof Error ? err.message : 'Failed to sync user');
    }
  };

  const mergeInstances = useCallback((current: AgentInstanceResponse[], incoming: AgentInstanceResponse[]) => {
    const merged = [...current];
    const indexById = new Map(current.map((instance, index) => [instance.id, index]));

    incoming.forEach((instance) => {
      const existingIndex = indexById.get(instance.id);
      if (existingIndex === undefined) {
        indexById.set(instance.id, merged.length);
        merged.push(instance);
        return;
      }

      merged[existingIndex] = {
        ...merged[existingIndex],
        ...instance,
      };
    });

    return merged;
  }, []);

  const refreshData = useCallback(async () => {
    if (!api) return;

    try {
      setIsLoading(true);
      setError(null);

      const fetchBilling = !billingFetchedRef.current;
      const [firstPage, billing] = await Promise.all([
        api.listAllAgentInstancesPage({
          limit: AGENT_INSTANCE_PAGE_SIZE,
          offset: 0,
          activeOnly,
        }).catch(() => null),
        fetchBilling ? api.getBillingSubscription().catch(() => null) : Promise.resolve(null),
      ]);

      if (firstPage) {
        setRecentInstances((prev) => {
          if (prev.length === 0) return firstPage.items;
          return mergeInstances(firstPage.items, prev.slice(firstPage.items.length));
        });
        setHasMoreInstances(firstPage.isPaginated ? firstPage.hasMore : false);
      }

      if (fetchBilling) {
        setBillingSubscription(billing);
        billingFetchedRef.current = true;
      }
    } catch (err) {
      console.error('Failed to refresh data:', err);
      setError(err instanceof Error ? err.message : 'Failed to refresh data');
    } finally {
      setIsLoading(false);
    }
  }, [activeOnly, api, mergeInstances]);

  // Ref tracking `refreshData` so callbacks can invoke the current version
  // without taking it as a dep (which would re-fire the WS hook on every
  // activeOnly / api change). Synced in render — safe in concurrent mode
  // because refreshData is itself a useCallback with stable identity
  // across non-dep renders.
  const refreshDataRef = useRef(refreshData);
  refreshDataRef.current = refreshData;

  const loadMoreInstances = useCallback(async () => {
    if (!api || isLoading || isLoadingMoreInstances || !hasMoreInstances) {
      return;
    }

    try {
      setIsLoadingMoreInstances(true);
      setError(null);

      const page = await api.listAllAgentInstancesPage({
        limit: AGENT_INSTANCE_PAGE_SIZE,
        offset: recentInstances.length,
        activeOnly,
      });

      setRecentInstances((prevInstances) => mergeInstances(prevInstances, page.items));
      setHasMoreInstances(page.isPaginated ? page.hasMore : false);

    } catch (err) {
      console.error('Failed to load more agent instances:', err);
      setError(err instanceof Error ? err.message : 'Failed to load more agent instances');
    } finally {
      setIsLoadingMoreInstances(false);
    }
  }, [activeOnly, api, hasMoreInstances, isLoading, isLoadingMoreInstances, mergeInstances, recentInstances.length]);

  // Initial data load
  useEffect(() => {
    if (api) {
      syncUser().then(() => {
        refreshData();
      });
    }
  }, [api, refreshData]);

  // Re-fetch when activeOnly filter changes
  const initialLoadDoneRef = useRef(false);
  useEffect(() => {
    if (!initialLoadDoneRef.current) {
      initialLoadDoneRef.current = true;
      return;
    }
    if (api) {
      void refreshData();
    }
  }, [activeOnly]); // eslint-disable-line react-hooks/exhaustive-deps

  // Force a refresh whenever the tab/window regains focus. The WS hook stays
  // subscribed and will eventually catch up on reconnect, but background tabs
  // get heavily throttled by the browser (Chrome stops delivering messages,
  // suspends timers, sometimes drops the socket entirely) and the catch-up
  // backoff can stretch into seconds. Mobile does the same thing on app resume
  // (home_model.dart → `forceWsReconnect` → `_fetchAllData`). The rate-limit
  // guards against very rapid focus/blur cycles (e.g. window manager flicker).
  useEffect(() => {
    if (typeof document === 'undefined' || !api) return;
    let lastRefreshAt = 0;
    const REFRESH_RATE_LIMIT_MS = 2_000;
    const onResume = () => {
      if (document.visibilityState !== 'visible') return;
      const now = Date.now();
      if (now - lastRefreshAt < REFRESH_RATE_LIMIT_MS) return;
      lastRefreshAt = now;
      void refreshDataRef.current?.();
    };
    document.addEventListener('visibilitychange', onResume);
    window.addEventListener('focus', onResume);
    return () => {
      document.removeEventListener('visibilitychange', onResume);
      window.removeEventListener('focus', onResume);
    };
  }, [api]);

  // Function to manually update a specific instance status
  const updateInstanceStatus = (instanceId: string, status: string, latestMessage?: string) => {
    setRecentInstances(prevInstances => {
      // Create a completely new array to ensure React detects the change
      const updated = [...prevInstances].map(instance => {
        if (instance.id === instanceId) {
          return {
            ...instance,
            status: status as keyof AgentStatus,
            // Update latest_message and timestamp when provided
            ...(latestMessage && {
              latest_message: latestMessage,
              latest_message_at: new Date().toISOString()
            })
          };
        }
        return instance;
      });

      return updated;
    });

  };

  const updateInstance = (instanceId: string, updates: Partial<AgentInstanceResponse>) => {
    setRecentInstances((prevInstances) =>
      prevInstances.map((instance) => (
        instance.id === instanceId
          ? { ...instance, ...updates }
          : instance
      ))
    );
  };

  const removeInstance = (instanceId: string) => {
    setRecentInstances((prevInstances) => prevInstances.filter((instance) => instance.id !== instanceId));
  };

  // Coalesce new-message patches during streaming bursts. Agent streaming can
  // produce 10-50 msg/s; without buffering, each one triggers a fresh sidebar
  // render — but the visible "Xm ago" is minute-granular so sub-second updates
  // are pure waste. Buffer per-instance and flush a single setState every ~2s
  // (matches the vicoa-app home_model debounce).
  const pendingMessagePatches = useRef(
    new Map<string, { latest_message: string; latest_message_at: string }>(),
  );
  const messagePatchFlushTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Backs the orphan-instance recovery in `onInstanceUpdated` — see below.
  // A ref so the callback can read the latest list without depending on
  // `recentInstances` (would otherwise re-create the callback per render).
  const recentInstancesRef = useRef<AgentInstanceResponse[]>([]);
  recentInstancesRef.current = recentInstances;

  // Debounce flag for the orphan refresh. WS catch-up on reconnect can
  // deliver many `instance-update` frames before recentInstances is
  // populated; without this we'd schedule N refreshData() calls.
  const orphanRefreshScheduled = useRef(false);
  const orphanRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushMessagePatches = useCallback(() => {
    messagePatchFlushTimer.current = null;
    const patches = pendingMessagePatches.current;
    if (patches.size === 0) return;
    pendingMessagePatches.current = new Map();
    setRecentInstances((prev) =>
      prev.map((i) => {
        const patch = patches.get(i.id);
        if (!patch) return i;
        // Stale-arrival guard: REST may have given us a fresher timestamp.
        if (i.latest_message_at && i.latest_message_at >= patch.latest_message_at) return i;
        return { ...i, ...patch };
      }),
    );
  }, []);

  useEffect(() => {
    return () => {
      if (messagePatchFlushTimer.current) {
        clearTimeout(messagePatchFlushTimer.current);
        messagePatchFlushTimer.current = null;
      }
      if (orphanRefreshTimer.current) {
        clearTimeout(orphanRefreshTimer.current);
        orphanRefreshTimer.current = null;
        orphanRefreshScheduled.current = false;
      }
    };
  }, []);

  // Realtime instance-list updates over the shared WebSocket.
  // onInstanceCreated fetches the full instance (to get joined fields like agent_type_name)
  // then prepends it. onInstanceUpdated merges field changes directly.
  // Keep the WS instance stream attached as long as the dashboard is mounted —
  // mirrors vicoa-app's home_model behavior (always-on). Gating on document
  // visibility caused the sidebar to lag behind the chat page after a tab
  // refocus while catch-up was still in flight. The shared client's idle/grace
  // close handles the actual socket lifecycle.
  useInstanceStream({
    enabled: !!api,
    onInstanceCreated: useCallback((instance: AgentInstanceResponse) => {
      setRecentInstances((prev) => {
        if (prev.some((i) => i.id === instance.id)) return prev;
        return [instance, ...prev];
      });

    }, []),
    onInstanceUpdated: useCallback((update: Partial<AgentInstanceResponse> & { id: string }) => {
      // Read latest list via ref — keeps the callback identity stable across
      // renders (depending on `recentInstances` would re-fire the WS hook's
      // effect chain).
      const known = recentInstancesRef.current.some((i) => i.id === update.id);

      if (known) {
        setRecentInstances((prev) =>
          prev.map((i) => (i.id === update.id ? { ...i, ...update } : i)),
        );
        return;
      }

      // Unknown id — catch-up on reconnect surfaced a session created during
      // the disconnect window (§2.6), or a live `instance-update` reordered
      // ahead of its `instance-created` (rare). Earlier versions fired a
      // per-id detail fetch inline, which on first WS catch-up over an empty
      // list could spam N parallel REST calls and cascade through the sidebar
      // auto-loadMore effect into a setState loop. Mirror vicoa-app's
      // home_model.dart fallback instead: trigger one debounced refreshData()
      // so all orphans backfill in a single REST list call.
      if (orphanRefreshScheduled.current) return;
      orphanRefreshScheduled.current = true;
      orphanRefreshTimer.current = setTimeout(() => {
        orphanRefreshTimer.current = null;
        orphanRefreshScheduled.current = false;
        void refreshDataRef.current?.();
      }, 500);
    }, []),
    // The WS `instance-update` body doesn't carry message metadata, so without
    // this the sidebar's "Xm ago" goes stale until the next REST refresh. Use
    // the message's own `created_at` so we stay aligned with what REST would
    // compute (REST returns max(messages.created_at)). Patches are buffered
    // and flushed via the debounce above — see `flushMessagePatches`.
    onNewMessage: useCallback((msg: NewMessageBody) => {
      if (!msg.created_at) return;
      const created = msg.created_at;
      const existing = pendingMessagePatches.current.get(msg.instance_id);
      if (existing && existing.latest_message_at >= created) return;
      pendingMessagePatches.current.set(msg.instance_id, {
        latest_message: msg.content,
        latest_message_at: created,
      });
      if (!messagePatchFlushTimer.current) {
        messagePatchFlushTimer.current = setTimeout(flushMessagePatches, 2000);
      }
    }, [flushMessagePatches]),
  });


  const value: AgentDashboardContextType = {
    api,
    recentInstances,
    billingSubscription,
    isLoading,
    isLoadingMoreInstances,
    hasMoreInstances,
    error,
    activeOnly,
    setActiveOnly,
    syncUser,
    refreshData,
    loadMoreInstances,
    updateInstanceStatus,
    updateInstance,
    removeInstance,
  };

  return (
    <AgentDashboardContext.Provider value={value}>
      {children}
    </AgentDashboardContext.Provider>
  );
}
