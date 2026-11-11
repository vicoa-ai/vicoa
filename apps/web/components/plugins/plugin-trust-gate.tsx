'use client';

/**
 * First-load trust prompt. A plugin reported by a machine's daemon contributes
 * nothing until the user approves it here (the registry filters on
 * `enabled && trusted`). Editing a plugin's manifest changes its hash on the
 * daemon side, which flips it back to untrusted and re-arms this prompt; the
 * grant carries the hash of the manifest shown, so a plugin can't change what
 * it asks for while the prompt is open.
 *
 * It leads with a few short lines (`summarizeTrust`): what the plugin adds,
 * what its pages can read and do, which local files, and whether it reaches
 * the internet. Where it came from and the item-by-item list are one click
 * away under Details.
 *
 * Prompts one pending plugin at a time; "Not now" dismisses for this session
 * (it reappears next launch until trusted). Renders nothing when there's
 * nothing to approve.
 */

import { useState } from 'react';
import {
  ChevronDown,
  Eye,
  FileText,
  Globe,
  LayoutGrid,
  PenLine,
  TerminalSquare,
  WifiOff,
  type LucideIcon,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getLocalMachineId } from '@/lib/local-machine';
import { usePluginRegistry } from '@/lib/plugins/hooks';
import { grantPluginTrust } from '@/lib/plugins/actions';
import type { RegisteredPlugin } from '@/lib/plugins/registry';
import { describeContributions, summarizeTrust, type SummaryLine } from '@/lib/plugins/trust-summary';
import { toast } from '@/lib/toast';

function machineText(plugin: RegisteredPlugin): string {
  const isLocal = plugin.machineId === getLocalMachineId();
  if (plugin.machineLabel) return isLocal ? `${plugin.machineLabel} (this machine)` : plugin.machineLabel;
  return isLocal ? 'This machine' : plugin.machineId;
}

function lineIcon(line: SummaryLine): LucideIcon {
  switch (line.kind) {
    case 'adds':
      return LayoutGrid;
    case 'reads':
      return Eye;
    case 'acts':
      return PenLine;
    case 'files':
      return FileText;
    case 'network':
      return line.text === 'No internet access' ? WifiOff : Globe;
    case 'code':
      return TerminalSquare;
  }
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 gap-3">
      <span className="w-14 shrink-0 text-muted-foreground">{label}</span>
      <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">{children}</div>
    </div>
  );
}

export function PluginTrustGate() {
  const all = usePluginRegistry();
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

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
  const { manifest } = current;
  const name = manifest.name ?? current.pluginId;
  const summary = summarizeTrust(manifest);
  const items = describeContributions(manifest);
  const meta = [
    manifest.version ? `${current.pluginId} ${manifest.version}` : current.pluginId,
    manifest.author,
    machineText(current),
  ].filter(Boolean);

  const onTrust = async () => {
    setBusy(true);
    const result = await grantPluginTrust(current.machineId, current.pluginId, current.manifestHash);
    setBusy(false);
    setShowDetails(false);
    if (result === 'changed') {
      toast.error(`${name} changed while you were reviewing it`, {
        description: 'Vicoa is loading the new version so you can review that instead.',
      });
    } else if (result === 'failed') {
      toast.error(`Couldn't trust ${name}`);
    }
  };

  const onDismiss = () => {
    setShowDetails(false);
    setDismissed((prev) => new Set(prev).add(key));
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onDismiss()}>
      <DialogContent className="custom-scrollbar max-h-[90vh] gap-5 overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Trust {name}?</DialogTitle>
          <DialogDescription>
            {manifest.description ?? 'A plugin found on one of your machines. It does nothing until you trust it.'}
          </DialogDescription>
        </DialogHeader>

        <ul className="space-y-2.5 text-sm">
          {summary.map((line) => {
            const Icon = lineIcon(line);
            return (
              <li
                key={line.kind}
                className={cn(
                  'flex min-w-0 items-start gap-2.5',
                  line.tone === 'warn' && 'text-warning',
                  line.tone === 'danger' && 'text-destructive',
                )}
              >
                <Icon className={cn('mt-0.5 size-4 shrink-0', !line.tone && 'text-muted-foreground')} />
                <span className="min-w-0">
                  {line.text}
                  {line.code ? (
                    <>
                      {' '}
                      <code className="rounded bg-foreground/[0.06] px-1 py-0.5 font-mono text-xs [overflow-wrap:anywhere]">
                        {line.code}
                      </code>
                    </>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>

        <div className="space-y-3">
          <button
            type="button"
            onClick={() => setShowDetails((v) => !v)}
            aria-expanded={showDetails}
            className="flex w-full min-w-0 cursor-pointer items-center gap-1.5 text-left text-xs text-muted-foreground hover:text-foreground"
          >
            <span className="min-w-0 truncate">{meta.join(' · ')}</span>
            <span className="ml-auto flex shrink-0 items-center gap-0.5">
              Details
              <ChevronDown className={cn('size-3.5 transition-transform', showDetails && 'rotate-180')} />
            </span>
          </button>
          {showDetails ? (
            <div className="space-y-2 rounded-lg border border-border/60 bg-foreground/[0.03] p-3 text-xs">
              {current.source ? (
                <Detail label="From">
                  <span className="font-mono text-foreground/80">{current.source}</span>
                </Detail>
              ) : null}
              {items.map((item, i) => (
                <Detail key={i} label={i === 0 ? 'Adds' : ''}>
                  <div>
                    {item.kind} <span className="font-medium">{item.label}</span>
                  </div>
                  <div className="text-muted-foreground">{item.detail}</div>
                </Detail>
              ))}
              {(manifest.files?.length ?? 0) > 1 ? (
                <Detail label="Files">
                  {manifest.files?.map((f) => (
                    <div key={f} className="font-mono text-foreground/80">
                      {f}
                    </div>
                  ))}
                </Detail>
              ) : null}
              {(manifest.network?.length ?? 0) > 2 ? (
                <Detail label="Sites">
                  {manifest.network?.map((n) => (
                    <div key={n} className="font-mono text-foreground/80">
                      {n}
                    </div>
                  ))}
                </Detail>
              ) : null}
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onDismiss} disabled={busy}>
            Not now
          </Button>
          <Button onClick={onTrust} disabled={busy}>
            {busy ? 'Trusting…' : 'Trust'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
