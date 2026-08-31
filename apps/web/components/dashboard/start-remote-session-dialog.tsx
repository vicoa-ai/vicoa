'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { getWsClient, RpcError } from '@/lib/ws-client';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RefreshCw, Loader2, Circle, Folder, ChevronDown } from 'lucide-react';
import type BackendAPI from '@/lib/backend-api';
import type { MachineSummary, RemoteAgentType } from '@/lib/backend-api';
import { StartEllipsisText } from '@/components/ui/start-ellipsis-text';
import { isMachineOnline as isMachineOnlineShared } from '@/lib/session-liveness';
import { currentPathname, openCreatedSession } from '@/lib/new-session-navigation';

const LAST_REMOTE_SESSION_SELECTION_KEY = 'vicoa:last-remote-session-selection';
const REMOTE_AGENT_OPTIONS: Array<{ value: RemoteAgentType; label: string }> = [
  { value: 'claude', label: 'Claude Code' },
  { value: 'codex', label: 'Codex' },
  { value: 'opencode', label: 'OpenCode' },
];

interface StartRemoteSessionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  api: BackendAPI | null;
  onSessionRequested: () => void;
}

export function StartRemoteSessionDialog({
  open,
  onOpenChange,
  api,
  onSessionRequested,
}: StartRemoteSessionDialogProps) {
  const router = useRouter();
  const [machines, setMachines] = useState<MachineSummary[]>([]);
  const [isLoadingMachines, setIsLoadingMachines] = useState(false);
  const [selectedMachineId, setSelectedMachineId] = useState<string>('');
  const [selectedAgent, setSelectedAgent] = useState<RemoteAgentType>('claude');
  const [directory, setDirectory] = useState('');
  const [prompt, setPrompt] = useState('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [statusVariant, setStatusVariant] = useState<'success' | 'error'>('success');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Shared with the session list and the backend's own threshold — see
  // lib/session-liveness.ts. Previously a local copy using a 2-minute window,
  // which disagreed with both the other copy and the server.
  const isMachineOnline = useCallback(
    (machine: MachineSummary) => isMachineOnlineShared(machine),
    []
  );

  const getDisplayName = useCallback((machine: MachineSummary) => {
    if (machine.display_name) return machine.display_name;
    if (machine.hostname) return machine.hostname;
    return `Machine ${machine.machine_id.slice(0, 6)}`;
  }, []);

  const getRecentDirectories = useCallback((machine: MachineSummary) => {
    if (Array.isArray(machine.recent_directories)) {
      return machine.recent_directories;
    }
    if (
      machine.metadata &&
      typeof machine.metadata === 'object' &&
      Array.isArray((machine.metadata as Record<string, unknown>).recent_directories)
    ) {
      return ((machine.metadata as Record<string, unknown>).recent_directories as unknown[]).map(String);
    }
    return [];
  }, []);

  const initialDirectoryForMachine = useCallback((machine: MachineSummary) => {
    const recent = getRecentDirectories(machine);
    if (recent.length > 0) {
      return recent[0];
    }
    const metadata = machine.metadata as Record<string, unknown> | null | undefined;
    if (metadata && typeof metadata.home_dir === 'string' && metadata.home_dir.length > 0) {
      return metadata.home_dir;
    }
    return '~/';
  }, [getRecentDirectories]);

  const isRemoteAgentType = useCallback((value: unknown): value is RemoteAgentType => {
    return typeof value === 'string' && REMOTE_AGENT_OPTIONS.some((item) => item.value === value);
  }, []);

  const loadLastSelection = useCallback((): { machineId?: string; agent?: RemoteAgentType } => {
    if (typeof window === 'undefined') {
      return {};
    }
    try {
      const raw = window.localStorage.getItem(LAST_REMOTE_SESSION_SELECTION_KEY);
      if (!raw) {
        return {};
      }
      const parsed = JSON.parse(raw) as { machineId?: unknown; agent?: unknown };
      return {
        machineId: typeof parsed.machineId === 'string' ? parsed.machineId : undefined,
        agent: isRemoteAgentType(parsed.agent) ? parsed.agent : undefined,
      };
    } catch {
      return {};
    }
  }, [isRemoteAgentType]);

  const saveLastSelection = useCallback((machineId: string, agent: RemoteAgentType) => {
    if (typeof window === 'undefined') {
      return;
    }
    try {
      window.localStorage.setItem(
        LAST_REMOTE_SESSION_SELECTION_KEY,
        JSON.stringify({ machineId, agent })
      );
    } catch {
      // Ignore storage failures.
    }
  }, []);

  const loadMachines = useCallback(async () => {
    if (!api) {
      setMachines([]);
      setStatusVariant('error');
      setStatusMessage('Unable to connect to the API. Ensure you are signed in.');
      return;
    }

    try {
      setIsLoadingMachines(true);
      setStatusMessage(null);
      const response = await api.listMachines();
      setMachines(response);
      if (response.length > 0) {
        const lastSelection = loadLastSelection();
        const preferredMachine = response.find((machine) => machine.machine_id === lastSelection.machineId) || response[0];
        setSelectedMachineId(preferredMachine.machine_id);
        setDirectory(initialDirectoryForMachine(preferredMachine));
        if (lastSelection.agent) {
          setSelectedAgent(lastSelection.agent);
        }
      } else {
        setSelectedMachineId('');
        setDirectory('~/');
        setStatusVariant('error');
        setStatusMessage('No machines registered yet. Start the Vicoa daemon on a machine to enable remote sessions.');
      }
    } catch (error) {
      console.error('Failed to load machines', error);
      setMachines([]);
      setSelectedMachineId('');
      setStatusVariant('error');
      setStatusMessage('Failed to load machines. Please try again.');
    } finally {
      setIsLoadingMachines(false);
    }
  }, [api, initialDirectoryForMachine, loadLastSelection]);

  useEffect(() => {
    if (open) {
      loadMachines();
    } else {
      setStatusMessage(null);
      setIsSubmitting(false);
    }
  }, [open, loadMachines]);

  const handleSubmit = async () => {
    if (!api || !selectedMachineId || !directory.trim()) {
      return;
    }

    // Where the user launched from — if they navigate away during the spawn we
    // leave them there instead of opening the new session (see openCreatedSession).
    const startPath = currentPathname();

    try {
      setIsSubmitting(true);
      setStatusMessage(null);

      // Spawn over WebSocket RPC (§2.8): the call resolves once the daemon has
      // launched the agent, so there is no spawn-request row to poll.
      const result = await getWsClient().callRpc(
        selectedMachineId,
        'spawn-session',
        {
          directory: directory.trim(),
          agent: selectedAgent,
          metadata: { enable_thinking: true, prompt: prompt.trim() || undefined },
        },
      );
      if (result.error) {
        setStatusVariant('error');
        setStatusMessage(String(result.error));
        setIsSubmitting(false);
        return;
      }
      saveLastSelection(selectedMachineId, selectedAgent);

      setMachines(prevMachines =>
        prevMachines.map(machine => {
          if (machine.machine_id === selectedMachineId) {
            const currentRecent = getRecentDirectories(machine);
            const trimmedDir = directory.trim();
            if (!currentRecent.includes(trimmedDir)) {
              return {
                ...machine,
                recent_directories: [trimmedDir, ...currentRecent].slice(0, 10),
              };
            }
          }
          return machine;
        })
      );

      // Wait for the daemon-spawned agent to self-register its row over the
      // shared WS (`instance-created` broadcast) before navigating —
      // otherwise the detail page 404s on its initial fetch and flashes
      // "Failed to fetch instance details". No REST polling needed: the
      // user-scoped socket is already pushing the event.
      const newInstanceId = String(result.agent_instance_id ?? '');
      await getWsClient().waitForEntity('agent_instances', newInstanceId);

      onSessionRequested();
      onOpenChange(false);
      setStatusMessage(null);
      // Only open the session if the user hasn't navigated away while it spawned;
      // otherwise leave them on their current page (it's already in the sidebar
      // via onSessionRequested).
      openCreatedSession(router, startPath, `/dashboard/agents/${newInstanceId}`);
    } catch (error) {
      console.error('Failed to spawn remote session', error);
      setStatusVariant('error');
      // Map each RPC error code to copy that explains the actual failure
      // mode (§2.8). `no_handler` = the targeted daemon isn't registered;
      // `target_disconnected` = the daemon dropped mid-request; `timeout` =
      // the daemon never replied within the 30s server-side window. Each
      // suggests a different user action; collapsing them was making
      // "should I retry, restart the daemon, or check the machine?"
      // indistinguishable.
      let message = 'Failed to start session. Please verify the daemon is running.';
      if (error instanceof RpcError) {
        if (error.code === 'no_handler') {
          message = 'That machine is offline. Make sure the Vicoa daemon is running.';
        } else if (error.code === 'timeout') {
          message = "The daemon didn't respond in time. It may be busy — try again.";
        } else if (error.code === 'target_disconnected') {
          message = 'The daemon disconnected before responding. Try again in a moment.';
        }
      }
      setStatusMessage(message);
      setIsSubmitting(false);
    }
  };

  const currentMachine = machines.find((machine) => machine.machine_id === selectedMachineId) || null;
  const recentDirectories = currentMachine ? getRecentDirectories(currentMachine) : [];
  const isCurrentMachineOnline = currentMachine ? isMachineOnline(currentMachine) : false;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto font-mono sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Start Remote Session</DialogTitle>
          <DialogDescription>
            Launch a new session on a registered machine and directory.
          </DialogDescription>
        </DialogHeader>

        {!api && (
          <div className="bg-destructive/10 text-destructive text-sm px-3 py-2 rounded-md">
            API client unavailable. Try refreshing the page.
          </div>
        )}

        {statusMessage && (
          <div
            className={`text-sm px-3 py-2 rounded-md ${
              statusVariant === 'success'
                ? 'bg-emerald-500/10 text-emerald-600'
                : 'bg-destructive/10 text-destructive'
            }`}
          >
            {statusMessage}
          </div>
        )}

        {currentMachine && !isCurrentMachineOnline && (
          <div className="bg-orange-500/10 text-orange-600 dark:text-orange-500 text-sm px-3 py-2 rounded-md">
            This machine is currently offline. Sessions can only be started on online machines.
          </div>
        )}

        <div className="grid gap-4 py-4">
          <div className="flex items-start gap-4">
            <Label htmlFor="machine" className="min-w-[72px] pt-2">
              Machine
            </Label>
            <div className="flex-1 space-y-2">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <select
                    id="machine"
                    value={selectedMachineId}
                    onChange={(event) => {
                      const nextId = event.target.value;
                      setSelectedMachineId(nextId);
                      const machine = machines.find((item) => item.machine_id === nextId);
                      if (machine) {
                        setDirectory(initialDirectoryForMachine(machine));
                      }
                    }}
className="w-full border-[0.5px] rounded-md px-3 py-2 pr-8 bg-background text-sm appearance-none"
                    disabled={isLoadingMachines || !api || machines.length === 0}
                  >
                    {machines.length === 0 ? (
                      <option value="">
                        {isLoadingMachines ? 'Loading machines...' : 'No machines available'}
                      </option>
                    ) : (
                      machines.map((machine) => (
                        <option key={machine.machine_id} value={machine.machine_id}>
                          {getDisplayName(machine)}
                        </option>
                      ))
                    )}
                  </select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                </div>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={loadMachines}
                  disabled={isLoadingMachines || !api}
                  title="Refresh machines"
                >
                  {isLoadingMachines ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                </Button>
              </div>
              {currentMachine && (
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-xs">
                    <Circle
                      className={`h-2 w-2 ${isCurrentMachineOnline ? 'fill-green-500 text-green-500' : 'fill-red-500 text-red-500'}`}
                    />
                    <span className={isCurrentMachineOnline ? 'text-green-600 dark:text-green-500' : 'text-red-600 dark:text-red-500'}>
                      {isCurrentMachineOnline ? 'Online' : 'Offline'}
                    </span>
                    {currentMachine.last_heartbeat_at && (
                      <span className="text-muted-foreground">
                        • Last seen {(() => {
                          const lastHeartbeat = new Date(currentMachine.last_heartbeat_at);
                          const now = new Date();
                          const diffMs = now.getTime() - lastHeartbeat.getTime();
                          const diffMinutes = Math.floor(diffMs / (1000 * 60));
                          const diffHours = Math.floor(diffMinutes / 60);
                          const diffDays = Math.floor(diffHours / 24);

                          if (diffMinutes < 1) return 'just now';
                          if (diffMinutes < 60) return `${diffMinutes}m ago`;
                          if (diffHours < 24) return `${diffHours}h ago`;
                          return `${diffDays}d ago`;
                        })()}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-start gap-4">
            <Label htmlFor="directory" className="min-w-[72px] pt-2">
              Directory
            </Label>
            <div className="flex-1 space-y-2">
              <Input
                id="directory"
                value={directory}
                onChange={(event) => setDirectory(event.target.value)}
                placeholder="~/projects/my-app"
                className="bg-transparent dark:bg-transparent"
                disabled={!api || machines.length === 0 || !isCurrentMachineOnline}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !isSubmitting && api && selectedMachineId && directory.trim() && isCurrentMachineOnline) {
                    handleSubmit();
                  }
                }}
              />
              {recentDirectories.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-xs text-muted-foreground">
                    Recent directories:
                  </div>
                  <div className="space-y-1.5 max-h-[120px] overflow-y-auto custom-scrollbar pr-1">
                    {recentDirectories.map((path) => (
                      <button
                        key={path}
                        type="button"
                        onClick={() => setDirectory(path)}
                        disabled={!api || machines.length === 0 || !isCurrentMachineOnline}
                        className="flex w-full items-center gap-1.5 rounded-md bg-secondary px-2.5 py-1 text-xs text-secondary-foreground transition-colors hover:bg-secondary/80 disabled:cursor-not-allowed disabled:opacity-50"
                        title={path}
                      >
                        <Folder className="h-3 w-3 flex-shrink-0" />
                        <StartEllipsisText value={path} className="min-w-0 flex-1 text-xs" />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-start gap-4">
            <Label htmlFor="prompt" className="min-w-[72px] pt-2">
              Prompt
            </Label>
            <textarea
              id="prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Optional: initial prompt to send when the session starts"
              rows={3}
              className="flex-1 resize-none rounded-md border-[0.5px] bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!api || machines.length === 0 || !isCurrentMachineOnline || isSubmitting}
            />
          </div>

          <div className="flex items-start gap-4">
            <Label htmlFor="agent" className="min-w-[72px] pt-2">
              Agent
            </Label>
            <div className="relative flex-1">
              <select
                id="agent"
                value={selectedAgent}
                onChange={(event) => setSelectedAgent(event.target.value as RemoteAgentType)}
                className="w-full border-[0.5px] rounded-md px-3 py-2 pr-8 bg-background text-sm appearance-none"
                disabled={!api || machines.length === 0 || !isCurrentMachineOnline || isSubmitting}
              >
                {REMOTE_AGENT_OPTIONS.map((agent) => (
                  <option key={agent.value} value={agent.value}>
                    {agent.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={
              isSubmitting ||
              !api ||
              !selectedMachineId ||
              !directory.trim() ||
              !isCurrentMachineOnline
            }
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Starting...
              </>
            ) : (
              'Start session'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
