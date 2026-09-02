'use client';

/**
 * Settings → Machines: every machine registered to the account — a machine is
 * a host running the desktop app or `vicoa daemon` — online first, then by
 * most recent heartbeat. Rendered by both the desktop settings surface and the
 * web settings page.
 *
 * Online is heartbeat freshness (lib/session-liveness mirrors the backend's
 * 90s threshold), so the list re-fetches on a 30s cadence: it picks up new
 * machines and lets a machine that went quiet decay to offline while the tab
 * is open.
 *
 * Remove is a hard delete (the machine's sessions survive with their machine
 * link cleared; the machine reappears if its daemon re-registers). It is
 * hidden for "this computer" in the desktop app — its daemon is running right
 * here and would just re-register — and in desktop local-only mode, where the
 * local daemon has no delete endpoint.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ExternalLink, Loader2, Monitor, Server, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { CopyCommand } from '@/components/copy-command';
import type { MachineSummary } from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { ensureLocalMachineId } from '@/lib/local-machine';
import {
  lastSeenLabel,
  machineCliVersion,
  machineDisplayName,
  machinePlatformLabel,
} from '@/lib/machine-display';
import { openExternalUrl } from '@/lib/open-external';
import { getDesktopConfig, isDesktopLocal } from '@/lib/runtime-config';
import { isMachineOnline, sortMachinesOnlineFirst } from '@/lib/session-liveness';

const MACHINE_REFRESH_INTERVAL_MS = 30_000;
const DESKTOP_DOWNLOAD_URL = 'https://vicoa.ai/download';
// Keep in sync with CLI_INSTALL_COMMAND in components/download/download-catalog.ts
// (`daemon` appended: servers connect headless, no interactive session).
const CLI_DAEMON_COMMAND = 'npm i -g @vicoa/cli && vicoa daemon';

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="divide-y divide-border/50 overflow-hidden rounded-xl border border-border/60 bg-foreground/[0.03]">
      {children}
    </div>
  );
}

function MachineRow({
  machine,
  isThisComputer,
  canRemove,
  onRemove,
  now,
}: {
  machine: MachineSummary;
  isThisComputer: boolean;
  canRemove: boolean;
  onRemove: () => void;
  now: number;
}) {
  const online = isMachineOnline(machine, now);
  const platform = machinePlatformLabel(machine.platform);
  const version = machineCliVersion(machine);
  const name = machineDisplayName(machine);
  const PlatformIcon = platform === 'Linux' ? Server : Monitor;
  const detail =
    [platform, version ? `vicoa v${version}` : null].filter(Boolean).join(' · ') ||
    machine.hostname ||
    '—';

  return (
    <div className="flex items-center gap-3 px-4 py-3.5">
      <PlatformIcon className="h-[18px] w-[18px] shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[13px] text-foreground">{name}</span>
          {isThisComputer && (
            <span className="shrink-0 rounded border border-border/70 bg-foreground/[0.06] px-1.5 py-px text-[10px] text-muted-foreground">
              This computer
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground">{detail}</div>
      </div>
      <span
        className={cn(
          'flex shrink-0 items-center gap-1.5 text-xs',
          online ? 'text-muted-foreground' : 'text-muted-foreground/70',
        )}
      >
        <span className={cn('h-1.5 w-1.5 rounded-full', online ? 'bg-green-500' : 'bg-border')} />
        {lastSeenLabel(machine, now)}
      </span>
      {canRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${name}`}
          title="Remove machine"
          className="shrink-0 cursor-pointer rounded-md p-1.5 text-muted-foreground/60 transition-colors hover:bg-muted/60 hover:text-foreground"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

export function MachinesSettingsSection() {
  const { api } = useAgentDashboard();
  const [machines, setMachines] = useState<MachineSummary[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [localMachineId, setLocalMachineId] = useState<string | null>(null);
  const [localMode, setLocalMode] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<MachineSummary | null>(null);
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);

  // Desktop only: learn this computer's machine id (badges the row, hides its
  // Remove). Reads runtime config post-mount, per the SSR-consistency rule.
  useEffect(() => {
    setLocalMode(isDesktopLocal());
    if (getDesktopConfig()) {
      void ensureLocalMachineId().then(setLocalMachineId);
    }
  }, []);

  const load = useCallback(async () => {
    if (!api) return;
    try {
      setMachines(await api.listMachines());
      setLoadError(false);
    } catch {
      setLoadError(true);
      setMachines((prev) => prev ?? []);
    }
  }, [api]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), MACHINE_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  // One clock per render keeps every row's dot and label consistent; the 30s
  // refetch re-renders often enough for liveness to decay on screen.
  const now = Date.now();
  const sorted = useMemo(() => sortMachinesOnlineFirst(machines ?? []), [machines]);

  const confirmRemove = useCallback(async () => {
    if (!api || !removeTarget || removing) return;
    setRemoving(true);
    setRemoveError(null);
    try {
      await api.deleteMachine(removeTarget.machine_id);
      setMachines((prev) => prev?.filter((m) => m.machine_id !== removeTarget.machine_id) ?? prev);
      setRemoveTarget(null);
    } catch (error) {
      setRemoveError(error instanceof Error ? error.message : 'Failed to remove machine');
    } finally {
      setRemoving(false);
    }
  }, [api, removeTarget, removing]);

  const loading = machines === null;

  return (
    <section>
      <h1 className="text-2xl font-light tracking-tight text-foreground">Machines</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Machines are the computers your agents run on — laptops with the desktop app, or servers
        running the Vicoa CLI.
      </p>

      <div className="mt-8">
        <h2 className="mb-3 text-sm text-foreground/90">Your machines</h2>
        <SectionCard>
          {loading ? (
            <div className="flex items-center gap-2.5 px-4 py-5 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading machines…
            </div>
          ) : sorted.length === 0 ? (
            <div className="px-4 py-5 text-sm text-muted-foreground">
              No machines connected yet — add one below.
            </div>
          ) : (
            sorted.map((machine) => (
              <MachineRow
                key={machine.machine_id}
                machine={machine}
                now={now}
                isThisComputer={machine.machine_id === localMachineId}
                canRemove={!localMode && machine.machine_id !== localMachineId}
                onRemove={() => {
                  setRemoveError(null);
                  setRemoveTarget(machine);
                }}
              />
            ))
          )}
        </SectionCard>
        {loadError && (
          <p className="mt-2 text-xs text-warning">
            Couldn’t reach the server — this list may be out of date.
          </p>
        )}
      </div>

      <div className="mt-8">
        <h2 className="mb-3 text-sm text-foreground/90">Add a machine</h2>
        <SectionCard>
          <div className="px-4 py-3.5">
            <div className="text-[13px] text-foreground">Mac &amp; Windows</div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              Install the Vicoa desktop app and sign in with the same account. The machine connects automatically.
            </div>
            <div className="mt-2.5">
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => openExternalUrl(DESKTOP_DOWNLOAD_URL)}
              >
                Download desktop app
                <ExternalLink className="h-3 w-3" />
              </Button>
            </div>
          </div>
          <div className="px-4 py-3.5">
            <div className="text-[13px] text-foreground">Servers &amp; headless machines</div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              Install the Vicoa CLI, then run{' '}
              <code className="rounded bg-foreground/[0.06] px-1 py-0.5 font-mono text-[11px]">
                vicoa daemon
              </code>{' '}
              (or{' '}
              <code className="rounded bg-foreground/[0.06] px-1 py-0.5 font-mono text-[11px]">
                vicoa
              </code>{' '}
              for an interactive session) to connect the machine. The CLI also works on macOS and
              Windows.
            </div>
            <div className="mt-2.5">
              <CopyCommand command={CLI_DAEMON_COMMAND} />
            </div>
          </div>
        </SectionCard>
      </div>

      <Dialog
        open={removeTarget !== null}
        onOpenChange={(open) => {
          if (!open && !removing) setRemoveTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove machine</DialogTitle>
            <DialogDescription>
              Remove “{removeTarget ? machineDisplayName(removeTarget) : ''}” from your account?
              Its sessions stay in your history. If its daemon reconnects, the machine is added
              again.
            </DialogDescription>
          </DialogHeader>
          {removeError && <p className="text-sm text-destructive">{removeError}</p>}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={removing}
              onClick={() => setRemoveTarget(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={removing}
              onClick={() => void confirmRemove()}
            >
              {removing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Removing
                </>
              ) : (
                'Remove'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
