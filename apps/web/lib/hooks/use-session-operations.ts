import { useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { toast } from '@/lib/toast';
import { applyStandingAnswerToTasks } from '@/lib/archive-task';
import { refusalReason } from '@/lib/backend-api';

export function useSessionOperations(instanceId?: string) {
  const { api, refreshData, recentInstances } = useAgentDashboard();
  const router = useRouter();

  const renameSession = useCallback(async (sessionId: string, newName: string) => {
    if (!api) {
      toast.error("Couldn't rename session");
      return;
    }

    try {
      await api.updateAgentInstance(sessionId, { name: newName });
      await refreshData();
    } catch (error) {
      console.error('Failed to rename session:', error);
      toast.error("Couldn't rename session");
    }
  }, [api, refreshData]);

  const deleteSession = useCallback(async (sessionId: string, navigateToNextSession = false) => {
    if (!api) {
      toast.error("Couldn't delete session");
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
          router.push(`/dashboard/sessions/${nextSessionId}`);
        } else {
          router.push('/dashboard');
        }
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
      toast.error("Couldn't delete session");
    }
  }, [api, refreshData, recentInstances, instanceId, router]);

  // The session menus call this Archive, so the failure says so. Resolves to
  // whether it worked, so a caller moves the session's task only after it.
  const markAsComplete = useCallback(async (sessionId: string): Promise<boolean> => {
    if (!api) {
      toast.error("Couldn't archive session");
      return false;
    }

    try {
      await api.updateAgentStatus(sessionId, { status: 'COMPLETED' });
      await refreshData();
      return true;
    } catch (error) {
      console.error('Failed to mark session as completed:', error);
      toast.error("Couldn't archive session", { description: refusalReason(error) });
      return false;
    }
  }, [api, refreshData]);

  /** Archive several sessions at once — one round-trip for the lot, not one
   *  per session — and let the caller decide when to refresh. Rejects on the
   *  first failure (no toast), for flows that surface errors in their own UI.
   *  Then applies the standing answer (Settings → Tasks) to their tasks; a
   *  task it could not update is a toast, since the sessions did archive. */
  const archiveSessions = useCallback(async (sessions: { id: string; task_id?: string | null }[]) => {
    if (!api) throw new Error('API not initialized');
    await Promise.all(
      sessions.map((s) => api.updateAgentStatus(s.id, { status: 'COMPLETED' })),
    );
    const failed = await applyStandingAnswerToTasks(api, sessions);
    if (failed.length > 0) {
      toast.error(failed.length === 1 ? "Couldn't update the task" : "Couldn't update the tasks");
    }
  }, [api]);

  const markAsUnread = useCallback(async (sessionId: string) => {
    if (!api) {
      toast.error("Couldn't mark session as unread");
      return;
    }

    try {
      await api.updateAgentStatus(sessionId, { status: 'AWAITING_INPUT' });
      await refreshData();
    } catch (error) {
      console.error('Failed to mark session as unread:', error);
      toast.error("Couldn't mark session as unread");
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
      // Reported here so every Pin (session header, sidebar row) says so; the
      // boolean is for callers that rolled back an optimistic update.
      toast.error(pinned ? "Couldn't pin session" : "Couldn't unpin session");
      return false;
    }
  }, [api]);

  return { renameSession, deleteSession, markAsComplete, archiveSessions, markAsUnread, togglePin };
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
