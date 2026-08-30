'use client';

import { useState, useMemo, useEffect } from 'react';
import { Check, ChevronDown, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  agentById,
  type AgentCatalog,
  type CatalogEnumEntry,
  type CatalogModel,
} from '@/lib/agent-catalog';
import type { SessionConfigSnapshot } from '@/lib/session-config-utils';

export interface SessionConfigChanges {
  model?: string;
  effort?: string;
  permissionMode?: string;
  opencodeMode?: string;
}

interface SessionConfigModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  catalog: AgentCatalog;
  agentId: string;
  initial: SessionConfigSnapshot;
  isReadOnly: boolean;
  onConfirm: (changes: SessionConfigChanges) => void;
}

interface LocalConfig {
  model: string | null;
  effort: string | null;
  permissionMode: string | null;
  opencodeMode: string | null;
}

function pickDefault(entries: CatalogEnumEntry[]): string | null {
  if (!entries.length) return null;
  return (entries.find((e) => e.is_default) ?? entries[0]).id;
}

function reconcileEffortForModel(
  effort: string | null,
  agentId: string,
  modelId: string | null,
  agent: ReturnType<typeof agentById>,
): string | null {
  const effortEntries = agentId === 'codex' ? agent?.reasoning_efforts : agent?.thinking_efforts;
  if (!effortEntries?.length) return effort;

  const model = agent?.models?.find((m) => m.id === modelId);
  const optIns = new Set(agentId === 'codex' ? [] : (model?.thinking_efforts ?? []));
  const visible = effortEntries.filter((e) => !e.opt_in || optIns.has(e.id));

  if (visible.some((e) => e.id === effort)) return effort;

  // Per-model default overrides agent-level is_default
  const perModelDefault = agentId !== 'codex' ? model?.default_thinking_effort : undefined;
  if (perModelDefault && visible.some((e) => e.id === perModelDefault)) return perModelDefault;

  return pickDefault(visible);
}

export function SessionConfigModal({
  open,
  onOpenChange,
  catalog,
  agentId,
  initial,
  isReadOnly,
  onConfirm,
}: SessionConfigModalProps) {
  const agent = useMemo(() => agentById(catalog, agentId), [catalog, agentId]);

  const [local, setLocal] = useState<LocalConfig>({
    model: initial.model,
    effort: initial.effort,
    permissionMode: initial.permissionMode,
    opencodeMode: initial.opencodeMode,
  });

  // Reset local state to the latest initial values each time the modal opens.
  useEffect(() => {
    if (!open) return;
    setLocal({
      model: initial.model,
      effort: initial.effort,
      permissionMode: initial.permissionMode,
      opencodeMode: initial.opencodeMode,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const activeModelDef = useMemo<CatalogModel | undefined>(
    () => agent?.models?.find((m) => m.id === local.model) ?? undefined,
    [agent, local.model],
  );

  const visibleEffort: CatalogEnumEntry[] = useMemo(() => {
    const entries = agentId === 'codex' ? agent?.reasoning_efforts : agent?.thinking_efforts;
    if (!entries?.length) return [];
    if (agentId === 'codex') return entries;
    const optIns = new Set(activeModelDef?.thinking_efforts ?? []);
    return entries.filter((e) => !e.opt_in || optIns.has(e.id));
  }, [agentId, agent, activeModelDef]);

  const visiblePermission: CatalogEnumEntry[] = useMemo(() => {
    if (!agent?.permission_modes?.length) return [];
    const optIns = new Set(activeModelDef?.permission_modes ?? []);
    return agent.permission_modes.filter((e) => !e.opt_in || optIns.has(e.id));
  }, [agent, activeModelDef]);

  function updateModel(modelId: string) {
    const nextEffort = reconcileEffortForModel(local.effort, agentId, modelId, agent);
    setLocal((prev) => ({ ...prev, model: modelId, effort: nextEffort }));
  }

  function handleConfirm() {
    const changes: SessionConfigChanges = {};
    if (local.model != null && local.model !== initial.model) changes.model = local.model;
    if (local.effort != null && local.effort !== initial.effort) changes.effort = local.effort;
    if (local.permissionMode != null && local.permissionMode !== initial.permissionMode) changes.permissionMode = local.permissionMode;
    if (local.opencodeMode != null && local.opencodeMode !== initial.opencodeMode) changes.opencodeMode = local.opencodeMode;
    onConfirm(changes);
    onOpenChange(false);
  }

  if (!agent) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm p-0 gap-0 overflow-hidden">
        <DialogHeader className="flex flex-row items-center justify-between px-4 py-3 border-b border-border">
          <DialogTitle className="text-sm font-medium font-mono">Session Config</DialogTitle>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 rounded-full"
            onClick={() => onOpenChange(false)}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </DialogHeader>

        <div className="p-4 space-y-2">
          {agent.models && agent.models.length > 0 && (
            <ConfigRow label="Model" disabled={isReadOnly}>
              <ModelDropdown
                models={agent.models}
                value={local.model}
                disabled={isReadOnly}
                onChange={updateModel}
              />
            </ConfigRow>
          )}

          {agentId !== 'opencode' && visibleEffort.length > 0 && (
            <ConfigRow label={agentId === 'codex' ? 'Reasoning' : 'Thinking'} disabled={isReadOnly}>
              <EnumDropdown
                entries={visibleEffort}
                value={local.effort}
                disabled={isReadOnly}
                onChange={(id) => setLocal((prev) => ({ ...prev, effort: id }))}
              />
            </ConfigRow>
          )}

          {agentId !== 'opencode' && visiblePermission.length > 0 && (
            <ConfigRow label="Permission" disabled={isReadOnly}>
              <EnumDropdown
                entries={visiblePermission}
                value={local.permissionMode}
                disabled={isReadOnly}
                onChange={(id) => setLocal((prev) => ({ ...prev, permissionMode: id }))}
              />
            </ConfigRow>
          )}

          {agentId === 'opencode' && agent.modes && agent.modes.length > 0 && (
            <ConfigRow label="Mode" disabled={isReadOnly}>
              <EnumDropdown
                entries={agent.modes}
                value={local.opencodeMode}
                disabled={isReadOnly}
                onChange={(id) => setLocal((prev) => ({ ...prev, opencodeMode: id }))}
              />
            </ConfigRow>
          )}

          {isReadOnly && (
            <p className="text-xs text-muted-foreground font-mono pt-1">Session is closed. Config is read-only.</p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border">
          <Button variant="ghost" size="sm" className="font-mono text-xs h-7" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" className="font-mono text-xs h-7" onClick={handleConfirm} disabled={isReadOnly}>
            Confirm
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const DROPDOWN_CLASSES =
  'w-[var(--radix-dropdown-menu-trigger-width)] py-1 font-mono border-2 border-foreground/15 shadow-xl';

function ConfigRow({
  label,
  disabled,
  children,
}: {
  label: string;
  disabled: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={`rounded-xl border border-border bg-card overflow-hidden flex items-stretch ${disabled ? 'opacity-50' : ''}`}>
      <div className="flex items-center px-4 w-28 shrink-0">
        <span className="text-xs text-muted-foreground font-mono">{label}</span>
      </div>
      <div className="flex-1 border-l border-border/50">{children}</div>
    </div>
  );
}

function ModelDropdown({
  models,
  value,
  disabled,
  onChange,
}: {
  models: CatalogModel[];
  value: string | null;
  disabled: boolean;
  onChange: (id: string) => void;
}) {
  const selected = models.find((m) => m.id === value);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={disabled || models.length === 0}>
        <button
          type="button"
          className="w-full flex items-center justify-between gap-2 px-4 py-2.5 text-sm font-mono bg-muted/30 hover:bg-muted/50 disabled:cursor-not-allowed transition-colors"
        >
          <span className="truncate">{selected?.label ?? '—'}</span>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={8} className={DROPDOWN_CLASSES}>
        {models.map((m) => (
          <DropdownMenuItem
            key={m.id}
            onClick={() => onChange(m.id)}
            className="flex items-start gap-2 px-3 py-2 text-sm cursor-pointer"
          >
            <span className="flex-1 min-w-0">
              <span className="block truncate">{m.label}</span>
              {m.description && (
                <span className="block text-xs text-muted-foreground truncate">{m.description}</span>
              )}
            </span>
            {m.id === value && <Check className="h-3.5 w-3.5 ml-auto flex-shrink-0 mt-1" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function EnumDropdown({
  entries,
  value,
  disabled,
  onChange,
}: {
  entries: CatalogEnumEntry[];
  value: string | null;
  disabled: boolean;
  onChange: (id: string) => void;
}) {
  const selected = entries.find((e) => e.id === value);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={disabled || entries.length === 0}>
        <button
          type="button"
          className="w-full flex items-center justify-between gap-2 px-4 py-2.5 text-sm font-mono bg-muted/30 hover:bg-muted/50 disabled:cursor-not-allowed transition-colors"
        >
          <span className="truncate">{selected?.label ?? '—'}</span>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={8} className={DROPDOWN_CLASSES}>
        {entries.map((e) => (
          <DropdownMenuItem
            key={e.id}
            onClick={() => onChange(e.id)}
            className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer"
          >
            <span className="flex-1 truncate">{e.label}</span>
            {e.id === value && <Check className="h-3.5 w-3.5 ml-auto flex-shrink-0" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
