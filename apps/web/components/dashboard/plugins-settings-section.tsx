'use client';

/**
 * Settings > Plugins. The management surface for locally-installed plugins,
 * grouped by machine. Reads each online machine's `plugin-list` RPC (the
 * authoritative management view — includes malformed plugins and raw enable
 * state) and drives enable / trust / remove through the daemon, updating the
 * shared registry optimistically so the rest of the app reflects changes at
 * once. Each plugin can open its settings (drawn from its schema) and its log.
 * Shown in both the desktop and the web settings.
 */

import { useCallback, useEffect, useState } from 'react';
import { FileText, Loader2, Puzzle, Settings2, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import type { MachineSummary } from '@/lib/backend-api';
import { getRpcClient } from '@/lib/ws-client';
import { isMachineOnline, sortMachinesOnlineFirst } from '@/lib/session-liveness';
import { getDesktopConfig } from '@/lib/runtime-config';
import { ensureLocalMachineId } from '@/lib/local-machine';
import { pluginRegistry } from '@/lib/plugins/registry';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { toast } from '@/lib/toast';
import { PluginSettingsForm } from '@/components/plugins/plugin-settings-form';
import { grantPluginTrust } from '@/lib/plugins/actions';

interface PluginListItem {
  id: string;
  dir: string;
  name: string;
  valid: boolean;
  errors: string[];
  enabled: boolean;
  trusted: boolean;
  source?: string | null;
  contributes: Record<string, number>;
  /** A development folder linked with `vicoa plugin link` (older daemons omit it). */
  linked?: boolean;
  requirements_ok?: boolean;
  requirement_error?: string | null;
  manifest_sha256?: string | null;
}

type Open = { machineId: string; dir: string; view: 'settings' | 'logs' } | null;

interface PluginListPayload {
  plugins_enabled: boolean;
  plugins: PluginListItem[];
}

interface MachinePlugins {
  machine: MachineSummary;
  data: PluginListPayload | null;
  error: boolean;
}

function machineLabel(m: MachineSummary): string {
  return m.display_name || m.hostname || m.machine_id;
}

function contributionText(contributes: Record<string, number>): string {
  const parts = Object.entries(contributes)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${k}`);
  return parts.join(' · ') || 'no visible contributions';
}

export function PluginsSettingsSection() {
  const { api } = useAgentDashboard();
  const [groups, setGroups] = useState<MachinePlugins[] | null>(null);
  const [open, setOpen] = useState<Open>(null);
  const [removing, setRemoving] = useState<{ machineId: string; plugin: PluginListItem } | null>(null);

  const load = useCallback(async () => {
    let machines: MachineSummary[] = [];
    if (api) {
      try {
        machines = await api.listMachines();
      } catch {
        machines = [];
      }
    }
    const now = Date.now();
    const online = sortMachinesOnlineFirst(machines.filter((m) => isMachineOnline(m, now)));

    // On desktop, always include this computer — its local daemon is reachable
    // even in logged-out local mode, where `listMachines` may return nothing.
    if (getDesktopConfig()) {
      const localId = await ensureLocalMachineId();
      if (localId && !online.some((m) => m.machine_id === localId)) {
        online.unshift({ machine_id: localId, display_name: 'This machine', recent_directories: [] });
      }
    }

    const results = await Promise.all(
      online.map(async (machine): Promise<MachinePlugins> => {
        try {
          const data = (await getRpcClient(machine.machine_id).callRpc(
            machine.machine_id,
            'plugin-list',
            {},
          )) as unknown as PluginListPayload;
          return { machine, data, error: false };
        } catch {
          return { machine, data: null, error: true };
        }
      }),
    );
    setGroups(results);
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  const setEnabledGlobally = async (machineId: string, enabled: boolean) => {
    try {
      await getRpcClient(machineId).callRpc(machineId, 'plugin-set-enabled', { enabled });
    } catch {
      /* ignore */
    }
    await load();
  };

  const setEnabled = async (machineId: string, dir: string, enabled: boolean) => {
    try {
      await getRpcClient(machineId).callRpc(machineId, 'plugin-enable', {
        plugin_id: dir,
        enabled,
      });
      pluginRegistry.setEnabled(machineId, dir, enabled);
    } catch {
      /* ignore */
    }
    await load();
  };

  const trust = async (machineId: string, plugin: PluginListItem) => {
    const result = await grantPluginTrust(machineId, plugin.dir, plugin.manifest_sha256);
    if (result === 'changed') toast.error(`${plugin.name} changed just now`, { description: 'Look at it again before you trust it.' });
    else if (result === 'failed') toast.error(`Couldn't trust ${plugin.name}`);
    await load();
  };

  const remove = async (machineId: string, dir: string) => {
    try {
      await getRpcClient(machineId).callRpc(machineId, 'plugin-remove', { plugin_id: dir });
      pluginRegistry.removePlugin(machineId, dir);
    } catch {
      toast.error("Couldn't remove the plugin");
    }
    await load();
  };

  const toggle = (machineId: string, dir: string, view: 'settings' | 'logs') =>
    setOpen((cur) =>
      cur && cur.machineId === machineId && cur.dir === dir && cur.view === view ? null : { machineId, dir, view },
    );

  return (
    <section>
      <h1 className="text-2xl font-light tracking-tight text-foreground">Plugins</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
        Plugins customize Vicoa from files on your machine: themes, sidebar
        entries, composer actions, and pages of their own. Install with{' '}
        <code className="rounded bg-foreground/10 px-1 py-0.5 text-xs">vicoa plugin add</code>.
        Approve a new plugin before it takes effect; disable or remove any here.
      </p>

      {groups === null ? (
        <div className="mt-8 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading plugins…
        </div>
      ) : groups.length === 0 ? (
        <p className="mt-8 text-sm text-muted-foreground">
          No machines are online. Connect a machine to manage its plugins.
        </p>
      ) : (
        groups.map(({ machine, data, error }) => (
          <div key={machine.machine_id} className="mt-8">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-sm text-foreground/90">{machineLabel(machine)}</h2>
              {data && (
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  Plugins enabled
                  <Switch
                    checked={data.plugins_enabled}
                    onCheckedChange={(v) => void setEnabledGlobally(machine.machine_id, v)}
                  />
                </label>
              )}
            </div>

            {error || !data ? (
              <p className="text-xs text-muted-foreground">
                Couldn&apos;t reach this machine&apos;s daemon.
              </p>
            ) : data.plugins.length === 0 ? (
              <div className="flex items-center gap-2 rounded-xl border border-dashed border-border/60 px-4 py-6 text-sm text-muted-foreground">
                <Puzzle className="h-4 w-4" /> No plugins installed on this machine.
              </div>
            ) : (
              <div className="divide-y divide-border/50 rounded-xl border border-border/60 bg-foreground/[0.03]">
                {data.plugins.map((p) => (
                  <div key={p.dir}>
                  <div className="flex items-start justify-between gap-4 px-4 py-3.5">
                    <div className="min-w-0 space-y-0.5">
                      <div className="flex items-center gap-2 text-[13px] text-foreground">
                        {p.name}
                        <span className="font-mono text-xs text-muted-foreground">{p.id}</span>
                        {!p.valid && (
                          <span className="rounded bg-destructive/15 px-1.5 py-0.5 text-[10px] text-destructive">
                            invalid
                          </span>
                        )}
                        {p.valid && !p.trusted && (
                          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-warning">
                            untrusted
                          </span>
                        )}
                        {p.linked && (
                          <span
                            className="rounded bg-foreground/10 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                            title={p.source ?? undefined}
                          >
                            linked
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {p.valid ? contributionText(p.contributes) : p.errors[0] ?? 'unreadable manifest'}
                      </div>
                      {p.requirements_ok === false && p.requirement_error && (
                        <div className="text-xs text-warning">{p.requirement_error}</div>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {p.valid && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7 text-muted-foreground"
                          title="Settings"
                          aria-label="Plugin settings"
                          onClick={() => toggle(machine.machine_id, p.dir, 'settings')}
                        >
                          <Settings2 className="h-4 w-4" />
                        </Button>
                      )}
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-muted-foreground"
                        title="Log"
                        aria-label="Plugin log"
                        onClick={() => toggle(machine.machine_id, p.dir, 'logs')}
                      >
                        <FileText className="h-4 w-4" />
                      </Button>
                      {p.valid && !p.trusted && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs"
                          onClick={() => void trust(machine.machine_id, p)}
                        >
                          Trust
                        </Button>
                      )}
                      {p.valid && (
                        <Switch
                          checked={p.enabled}
                          onCheckedChange={(v) => void setEnabled(machine.machine_id, p.dir, v)}
                          aria-label="Enable plugin"
                        />
                      )}
                      <Button
                        size="icon"
                        variant="ghost"
                        className={cn('h-7 w-7 text-muted-foreground hover:text-destructive')}
                        title="Remove plugin"
                        onClick={() => setRemoving({ machineId: machine.machine_id, plugin: p })}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  {open && open.machineId === machine.machine_id && open.dir === p.dir && (
                    <div className="border-t border-border/50 px-4 py-4">
                      {open.view === 'settings' ? (
                        <PluginSettingsForm machineId={machine.machine_id} pluginId={p.dir} />
                      ) : (
                        <PluginLog machineId={machine.machine_id} pluginId={p.dir} />
                      )}
                    </div>
                  )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))
      )}
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Remove plugin?"
        description={
          removing?.plugin.linked
            ? 'Vicoa forgets this linked plugin. Your development folder stays as it is.'
            : 'Its installed copy on this machine is deleted, along with its settings.'
        }
        preview={removing ? `${removing.plugin.name} (${removing.plugin.id})` : undefined}
        confirmLabel="Remove"
        onConfirm={() => {
          if (removing) void remove(removing.machineId, removing.plugin.dir);
          setRemoving(null);
        }}
      />
    </section>
  );
}

/** The newest lines of a plugin's log: its pages' `vicoa.log` calls and errors. */
function PluginLog({ machineId, pluginId }: { machineId: string; pluginId: string }) {
  const [lines, setLines] = useState<string[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      const res = await getRpcClient(machineId).callRpc(machineId, 'plugin-logs-read', {
        plugin_id: pluginId,
        limit: 200,
      });
      if (res.error) throw new Error(String(res.error));
      setLines(Array.isArray(res.lines) ? res.lines.map(String) : []);
    } catch {
      setFailed(true);
    }
  }, [machineId, pluginId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (failed) return <p className="text-xs text-muted-foreground">Couldn&apos;t read the log. Update Vicoa on this machine if it persists.</p>;
  if (lines === null) return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[0.8rem] text-muted-foreground">Newest last</span>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => void load()}>
          Refresh
        </Button>
      </div>
      {lines.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nothing logged yet.</p>
      ) : (
        <pre className="custom-scrollbar max-h-72 overflow-auto rounded-md bg-foreground/[0.04] p-3 font-mono text-[11px] leading-relaxed text-foreground/80">
          {lines.join('\n')}
        </pre>
      )}
    </div>
  );
}
