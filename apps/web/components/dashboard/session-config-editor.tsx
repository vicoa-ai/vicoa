'use client';

import { useMemo } from 'react';
import {
  AGENT_CATALOG_FALLBACK,
  agentById,
  agentPickerLabel,
  defaultsFor,
  reconcileAgainst,
  type AgentCatalog,
  type CatalogEnumEntry,
  type CatalogModel,
  type SessionConfig,
} from '@/lib/agent-catalog';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import {
  ChipDropdown,
  ModeIcon,
  TickItem,
} from '@/components/dashboard/session-config-dropdown';

/**
 * Agent / model / effort / permission-mode picker as inline chips, driven by a
 * single {@link SessionConfig}. Same catalog logic as the new-session flow
 * (per-model opt-in filtering, reconcile-on-model-change) but self-contained and
 * controlled — used by the automation editor, where one config is stored per
 * automation (no per-agent memory).
 */
export function SessionConfigEditor({
  value,
  onChange,
  catalog = AGENT_CATALOG_FALLBACK,
  disabled,
  side = 'bottom',
}: {
  value: SessionConfig;
  onChange: (next: SessionConfig) => void;
  catalog?: AgentCatalog;
  disabled?: boolean;
  /** Preferred open direction for the chip dropdowns (default down). */
  side?: 'top' | 'bottom';
}) {
  const agentEntries = useMemo(
    () => catalog.agents.map((a) => ({ id: a.id, label: agentPickerLabel(a.id, a.label) })),
    [catalog],
  );
  const activeAgentDef = useMemo(
    () => agentById(catalog, value.agent),
    [catalog, value.agent],
  );
  const activeModelDef = useMemo<CatalogModel | undefined>(
    () => activeAgentDef?.models?.find((m) => m.id === value.model),
    [activeAgentDef, value.model],
  );
  const modelEntries = activeAgentDef?.models ?? null;

  const visibleThinking: CatalogEnumEntry[] = useMemo(() => {
    if (!activeAgentDef?.thinking_efforts?.length) return [];
    const optIns = new Set(activeModelDef?.thinking_efforts ?? []);
    return activeAgentDef.thinking_efforts.filter((e) => !e.opt_in || optIns.has(e.id));
  }, [activeAgentDef, activeModelDef]);

  const visibleReasoning: CatalogEnumEntry[] = activeAgentDef?.reasoning_efforts ?? [];

  const visiblePermission: CatalogEnumEntry[] = useMemo(() => {
    if (!activeAgentDef?.permission_modes?.length) return [];
    const optIns = new Set(activeModelDef?.permission_modes ?? []);
    return activeAgentDef.permission_modes.filter((e) => !e.opt_in || optIns.has(e.id));
  }, [activeAgentDef, activeModelDef]);

  const visibleModes: CatalogEnumEntry[] = activeAgentDef?.modes ?? [];

  const switchAgent = (agentId: string) => {
    onChange(defaultsFor(catalog, agentId));
  };

  const updateField = (patch: Partial<SessionConfig>) => {
    const merged: SessionConfig = { ...value, ...patch, agent: value.agent };
    onChange(patch.model !== undefined ? reconcileAgainst(merged, catalog) : merged);
  };

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <ChipDropdown
        title="Agent"
        disabled={disabled}
        side={side}
        contentClassName="w-52"
        chip={
          <>
            <AgentTypeIcon agentTypeName={value.agent} size={12} whiteForOpenAI />
            <span className="min-w-0 truncate">
              {agentEntries.find((a) => a.id === value.agent)?.label ?? value.agent}
            </span>
          </>
        }
      >
        {(close) =>
          agentEntries.map((a) => (
            <TickItem
              key={a.id}
              label={a.label}
              leading={<AgentTypeIcon agentTypeName={a.id} size={12} whiteForOpenAI />}
              isSelected={a.id === value.agent}
              isPending={false}
              onClick={() => {
                switchAgent(a.id);
                close();
              }}
            />
          ))
        }
      </ChipDropdown>

      {modelEntries && modelEntries.length > 0 && (
        <ChipDropdown
          title="Model"
          disabled={disabled}
          side={side}
          contentClassName="w-56"
          chip={
            <span className="min-w-0 truncate">
              {modelEntries.find((m) => m.id === value.model)?.label ?? value.model ?? 'Model'}
            </span>
          }
        >
          {(close) =>
            modelEntries.map((m) => (
              <TickItem
                key={m.id}
                label={m.label}
                isSelected={m.id === value.model}
                isPending={false}
                onClick={() => {
                  updateField({ model: m.id });
                  close();
                }}
              />
            ))
          }
        </ChipDropdown>
      )}

      {visibleThinking.length > 0 && (
        <ChipDropdown
          title="Effort"
          disabled={disabled}
          side={side}
          contentClassName="w-44"
          chip={
            <span className="min-w-0 truncate">
              {visibleThinking.find((e) => e.id === value.thinking_effort)?.label ?? 'Effort'}
            </span>
          }
        >
          {(close) =>
            visibleThinking.map((e) => (
              <TickItem
                key={e.id}
                label={e.label}
                isSelected={e.id === value.thinking_effort}
                isPending={false}
                onClick={() => {
                  updateField({ thinking_effort: e.id });
                  close();
                }}
              />
            ))
          }
        </ChipDropdown>
      )}

      {visibleReasoning.length > 0 && (
        <ChipDropdown
          title="Effort"
          disabled={disabled}
          side={side}
          contentClassName="w-44"
          chip={
            <span className="min-w-0 truncate">
              {visibleReasoning.find((e) => e.id === value.reasoning_effort)?.label ?? 'Effort'}
            </span>
          }
        >
          {(close) =>
            visibleReasoning.map((e) => (
              <TickItem
                key={e.id}
                label={e.label}
                isSelected={e.id === value.reasoning_effort}
                isPending={false}
                onClick={() => {
                  updateField({ reasoning_effort: e.id });
                  close();
                }}
              />
            ))
          }
        </ChipDropdown>
      )}

      {visiblePermission.length > 0 && (
        <ChipDropdown
          title="Permission mode"
          disabled={disabled}
          side={side}
          contentClassName="w-52"
          chip={
            <>
              <ModeIcon value={value.permission_mode ?? 'default'} className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="min-w-0 truncate">
                {visiblePermission.find((p) => p.id === value.permission_mode)?.label ?? 'Permission'}
              </span>
            </>
          }
        >
          {(close) =>
            visiblePermission.map((p) => (
              <TickItem
                key={p.id}
                label={p.label}
                leading={<ModeIcon value={p.id} className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />}
                isSelected={p.id === value.permission_mode}
                isPending={false}
                onClick={() => {
                  updateField({ permission_mode: p.id });
                  close();
                }}
              />
            ))
          }
        </ChipDropdown>
      )}

      {visibleModes.length > 0 && (
        <ChipDropdown
          title="Mode"
          disabled={disabled}
          side={side}
          contentClassName="w-44"
          chip={
            <>
              <ModeIcon value={value.opencode_mode ?? 'build'} className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="min-w-0 truncate">
                {visibleModes.find((m) => m.id === value.opencode_mode)?.label ?? 'Mode'}
              </span>
            </>
          }
        >
          {(close) =>
            visibleModes.map((m) => (
              <TickItem
                key={m.id}
                label={m.label}
                leading={<ModeIcon value={m.id} className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />}
                isSelected={m.id === value.opencode_mode}
                isPending={false}
                onClick={() => {
                  updateField({ opencode_mode: m.id });
                  close();
                }}
              />
            ))
          }
        </ChipDropdown>
      )}
    </div>
  );
}
