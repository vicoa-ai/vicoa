'use client';

/**
 * First-load trust prompt. A plugin reported by a machine's daemon contributes
 * nothing until the user approves it here (the registry filters on
 * `enabled && trusted`). Editing a plugin's manifest changes its hash on the
 * daemon side, which flips it back to untrusted and re-arms this prompt.
 *
 * The prompt says where the plugin came from, which machine it is on, and what
 * each of its contributions does when used (`describeContributions`).
 *
 * Prompts one pending plugin at a time; "Not now" dismisses for this session
 * (it reappears next launch until trusted). Renders nothing when there's
 * nothing to approve.
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { getLocalMachineId } from '@/lib/local-machine';
import { usePluginRegistry } from '@/lib/plugins/hooks';
import { grantPluginTrust } from '@/lib/plugins/actions';
import type { RegisteredPlugin } from '@/lib/plugins/registry';
import { describeAccess, describeContributions } from '@/lib/plugins/trust-summary';
import { toast } from '@/lib/toast';

function machineText(plugin: RegisteredPlugin): string {
  const isLocal = plugin.machineId === getLocalMachineId();
  if (plugin.machineLabel) return isLocal ? `${plugin.machineLabel} (this machine)` : plugin.machineLabel;
  return isLocal ? 'This machine' : plugin.machineId;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 gap-2 text-xs">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate font-mono text-foreground/80" title={value}>
        {value}
      </span>
    </div>
  );
}

export function PluginTrustGate() {
  const all = usePluginRegistry();
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const pending = all.filter(
    (p) =>
      !p.builtin &&
      !p.trusted &&
      p.enabled &&
      !dismissed.has(`${p.machineId}::${p.pluginId}`),
  );
  const current = pending[0];
  if (!current) return null;

  const key = `${current.machineId}::${current.pluginId}`;
  const name = current.manifest.name ?? current.pluginId;
  const lines = describeContributions(current.manifest);
  const access = describeAccess(current.manifest);

  const onTrust = async () => {
    setBusy(true);
    const result = await grantPluginTrust(current.machineId, current.pluginId, current.manifestHash);
    setBusy(false);
    if (result === 'changed') {
      toast.error(`${name} changed while you were reviewing it`, {
        description: 'Vicoa is loading the new version so you can review that instead.',
      });
    } else if (result === 'failed') {
      toast.error(`Couldn't trust ${name}`);
    }
  };

  const onDismiss = () => {
    setDismissed((prev) => new Set(prev).add(key));
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onDismiss()}>
      <DialogContent className="custom-scrollbar max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Trust {name}?</DialogTitle>
          <DialogDescription>
            This plugin was found on one of your machines. It changes nothing in
            Vicoa until you approve it.
          </DialogDescription>
        </DialogHeader>
        <div className="min-w-0 space-y-1.5 rounded-lg border border-border/60 bg-foreground/[0.03] p-3">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate font-medium">{name}</span>
            <span className="shrink-0 font-mono text-xs text-muted-foreground">
              {current.pluginId}
              {current.manifest.version ? ` ${current.manifest.version}` : ''}
            </span>
          </div>
          {current.manifest.description && (
            <div className="text-xs text-muted-foreground">{current.manifest.description}</div>
          )}
          {current.manifest.author && <Fact label="Author" value={current.manifest.author} />}
          {current.source && <Fact label="From" value={current.source} />}
          <Fact label="Machine" value={machineText(current)} />
        </div>
        <div className="min-w-0">
          <div className="mb-1.5 text-[0.8rem] text-muted-foreground">What it adds</div>
          {lines.length === 0 ? (
            <div className="text-xs text-muted-foreground">Nothing this version of Vicoa shows.</div>
          ) : (
            <ul className="custom-scrollbar max-h-56 space-y-1.5 overflow-y-auto pr-1">
              {lines.map((line, i) => (
                <li key={i} className="min-w-0 text-xs">
                  <div className="truncate">
                    <span className="text-muted-foreground">{line.kind}:</span>{' '}
                    <span className="font-medium">{line.label}</span>
                  </div>
                  <div className="truncate text-muted-foreground" title={line.detail}>
                    {line.detail}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        {access.any ? (
          <div className="min-w-0 space-y-1.5">
            <div className="text-[0.8rem] text-muted-foreground">What its pages can do</div>
            <ul className="space-y-1 text-xs">
              {access.permissions.length === 0 ? (
                <li className="text-muted-foreground">Nothing beyond showing its own page</li>
              ) : (
                access.permissions.map((text) => <li key={text}>{text}</li>)
              )}
              {access.files.length > 0 && (
                <li>
                  Read these files on this machine:
                  {access.files.map((f) => (
                    <div key={f} className="truncate font-mono text-[11px] text-muted-foreground" title={f}>
                      {f}
                    </div>
                  ))}
                </li>
              )}
              <li>
                {access.network.length === 0 ? (
                  'No internet access'
                ) : (
                  <>
                    Load from:
                    {access.network.map((n) => (
                      <div key={n} className="truncate font-mono text-[11px] text-muted-foreground" title={n}>
                        {n}
                      </div>
                    ))}
                  </>
                )}
              </li>
              {access.runsCode && (
                <li className="font-medium text-destructive">Runs its own code on this machine, with your access</li>
              )}
            </ul>
          </div>
        ) : null}
        <p className="text-xs text-muted-foreground">
          Only approve plugins from sources you trust. You can turn it off or
          remove it later in Settings &rsaquo; Plugins.
        </p>
        <DialogFooter>
          <Button variant="ghost" onClick={onDismiss} disabled={busy}>
            Not now
          </Button>
          <Button onClick={onTrust} disabled={busy}>
            {busy ? 'Trusting…' : 'Trust plugin'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
