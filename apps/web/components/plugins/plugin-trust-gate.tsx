'use client';

/**
 * First-load trust prompt. A plugin reported by a machine's daemon contributes
 * nothing until the user approves it here (the registry filters on
 * `enabled && trusted`). Editing a plugin's manifest changes its hash on the
 * daemon side, which flips it back to untrusted and re-arms this prompt.
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
import { usePluginRegistry } from '@/lib/plugins/hooks';
import { grantPluginTrust } from '@/lib/plugins/actions';

function contributionSummary(manifest: {
  themes?: unknown[];
  sidebarItems?: unknown[];
  composerActions?: unknown[];
  slashCommands?: unknown[];
}): string {
  const parts: string[] = [];
  if (manifest.themes?.length) parts.push(`${manifest.themes.length} theme(s)`);
  if (manifest.sidebarItems?.length) parts.push(`${manifest.sidebarItems.length} sidebar item(s)`);
  if (manifest.composerActions?.length)
    parts.push(`${manifest.composerActions.length} composer action(s)`);
  if (manifest.slashCommands?.length)
    parts.push(`${manifest.slashCommands.length} slash command(s)`);
  return parts.join(' · ') || 'no visible contributions';
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

  const onTrust = async () => {
    setBusy(true);
    await grantPluginTrust(current.machineId, current.pluginId);
    setBusy(false);
  };

  const onDismiss = () => {
    setDismissed((prev) => new Set(prev).add(key));
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onDismiss()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Trust this plugin?</DialogTitle>
          <DialogDescription>
            A plugin was found on one of your machines. Approve it to let it
            change Vicoa&apos;s appearance and add sidebar / composer actions.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 rounded-lg border border-border/60 bg-foreground/[0.03] p-3 text-sm">
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium">{current.manifest.name ?? current.pluginId}</span>
            <span className="font-mono text-xs text-muted-foreground">{current.pluginId}</span>
          </div>
          {current.manifest.description && (
            <div className="text-xs text-muted-foreground">{current.manifest.description}</div>
          )}
          <div className="text-xs text-muted-foreground">
            Contributes: {contributionSummary(current.manifest)}
          </div>
          <div className="truncate text-xs text-muted-foreground">
            Machine: <span className="font-mono">{current.machineId}</span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Only approve plugins from sources you trust. You can disable or remove
          it later in Settings &rsaquo; Plugins.
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
