import { useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';

export function useSessionOperations(instanceId?: string) {
  const { api, refreshData, recentInstances } = useAgentDashboard();
  const router = useRouter();

  const renameSession = useCallback(async (sessionId: string, newName: string) => {
    if (!api) {
      alert('API not initialized');
      return;
    }

    try {
      await api.updateAgentInstance(sessionId, { name: newName });
      await refreshData();
    } catch (error) {
      console.error('Failed to rename session:', error);
      alert('Failed to rename session');
    }
  }, [api, refreshData]);

  const deleteSession = useCallback(async (sessionId: string, navigateToNextSession = false) => {
    if (!api) {
      alert('API not initialized');
      return;
    }

    try {
      // Find the next session to navigate to if requested
      let nextSessionId: string | null = null;

      if (navigateToNextSession && instanceId === sessionId && recentInstances.length > 1) {
        // Sort instances by latest message time (same logic as in sidebar)
        const sortedInstances = [...recentInstances].sort((a, b) => {
          const aTime = new Date(a.latest_message_at || a.started_at).getTime();
          const bTime = new Date(b.latest_message_at || b.started_at).getTime();
          return bTime - aTime;
        });

        // Find current index
        const currentIndex = sortedInstances.findIndex(inst => inst.id === sessionId);

        if (currentIndex !== -1) {
          // Try next item first, then previous
          if (currentIndex < sortedInstances.length - 1) {
            nextSessionId = sortedInstances[currentIndex + 1].id;
          } else if (currentIndex > 0) {
            nextSessionId = sortedInstances[currentIndex - 1].id;
          }
        }
      }

      await api.deleteAgentInstance(sessionId);
      await refreshData();

      // Navigate if this is the current session being deleted
      if (instanceId === sessionId) {
        if (nextSessionId) {
          router.push(`/dashboard/agents/${nextSessionId}`);
        } else {
          router.push('/dashboard');
        }
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
      alert('Failed to delete session');
    }
  }, [api, refreshData, recentInstances, instanceId, router]);

  const markAsComplete = useCallback(async (sessionId: string) => {
    if (!api) {
      alert('API not initialized');
      return;
    }

    try {
      await api.updateAgentStatus(sessionId, { status: 'COMPLETED' });
      await refreshData();
    } catch (error) {
      console.error('Failed to mark session as completed:', error);
      alert('Failed to mark session as completed');
    }
  }, [api, refreshData]);

  const markAsUnread = useCallback(async (sessionId: string) => {
    if (!api) {
      alert('API not initialized');
      return;
    }

    try {
      await api.updateAgentStatus(sessionId, { status: 'AWAITING_INPUT' });
      await refreshData();
    } catch (error) {
      console.error('Failed to mark session as unread:', error);
      alert('Failed to mark session as unread');
    }
  }, [api, refreshData]);

  const togglePin = useCallback(async (sessionId: string, pinned: boolean): Promise<boolean> => {
    if (!api) {
      return false;
    }
    try {
      await api.updateAgentInstance(sessionId, { pinned });
      return true;
    } catch (error) {
      console.error('Failed to toggle pin:', error);
      return false;
    }
  }, [api]);

  return { renameSession, deleteSession, markAsComplete, markAsUnread, togglePin };
}

export function useCopyToClipboard(timeout = 2000) {
  const [copied, setCopied] = useState<string | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const copy = useCallback(async (text: string, id?: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id || text);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => {
        setCopied(null);
      }, timeout);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  }, [timeout]);

  return { copied, copy };
}
