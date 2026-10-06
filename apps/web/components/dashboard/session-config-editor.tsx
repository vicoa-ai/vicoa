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
import type { AgentProfile, TeamSummary } from '@/lib/backend-api';
import { agentPrincipal } from '@/lib/use-agent-profiles';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { SavedAgentItems } from '@/components/dashboard/saved-agent-items';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import {
  ChipDropdown,
  ModeIcon,
  PERMISSION_LIST_WIDTH_CLASS,
  TickItem,
  modelListWidthClass,
  modelSublabel,
} from '@/components/dashboard/session-config-dropdown';

/** Saved agents offered at the top of the Agent dropdown. */
export interface SavedAgentChoice {
  profiles: AgentProfile[];
  teams: TeamSummary[] | undefined;
  selectedId: string | null;
  /** The machine it will run on, for the instructions gate. */
  machine: { metadata?: Record<string, unknown> | null } | null | undefined;
  /** A saved agent, or null when the user picks a plain agent instead. */
  onSelect: (profile: AgentProfile | null) => void;
}

/**
 * Agent / model / effort / permission-mode picker as inline chips, driven by a
 * single {@link SessionConfig}. Same catalog logic as the new-session flow
 * (per-model opt-in filtering, reconcile-on-model-change) but self-contained and
 * controlled — used by the automation editor, where one config is stored per
 * automation (no per-agent memory).
 *
 * With `savedAgents`, the Agent dropdown lists them above the plain agents, as
 * the new-session picker does. While one is selected the other chips are
 * hidden: the run takes that agent's own config at the time it fires, so
 * editable chips would show something the run won't use. Picking a plain agent
 * brings them back.
 */
export function SessionConfigEditor({
  value,
  onChange,
  catalog = AGENT_CATALOG_FALLBACK,
  disabled,
  side = 'bottom',
  savedAgents,
}: {
  value: SessionConfig;
  onChange: (next: SessionConfig) => void;
  catalog?: AgentCatalog;
  disabled?: boolean;
  /** Preferred open direction for the chip dropdowns (default down). */
  side?: 'top' | 'bottom';
  savedAgents?: SavedAgentChoice;
}) {
  const selectedProfile =
    savedAgents?.profiles.find((p) => p.id === savedAgents.selectedId) ?? null;
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

  const pickPlainAgent = (agentId: string) => {
    if (selectedProfile) {
      savedAgents?.onSelect(null);
      // Same provider: keep the saved agent's settings as the starting point
      // rather than resetting them, so the chips come back showing what it ran.
      if (agentId === value.agent) return;
    }
    switchAgent(agentId);
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
          selectedProfile ? (
            <>
              <PrincipalAvatar principal={agentPrincipal(selectedProfile)} size="xs" plain />
              <span className="min-w-0 truncate">{selectedProfile.name}</span>
            </>
          ) : (
            <>
              <AgentTypeIcon agentTypeName={value.agent} size={12} whiteForOpenAI />
              <span className="min-w-0 truncate">
                {agentEntries.find((a) => a.id === value.agent)?.label ?? value.agent}
              </span>
            </>
          )
        }
      >
        {(close) => (
          <>
            {savedAgents && (
              <SavedAgentItems
                profiles={savedAgents.profiles}
                teams={savedAgents.teams}
                selectedId={savedAgents.selectedId}
                machine={savedAgents.machine}
                onPick={(profile) => {
                  savedAgents.onSelect(profile);
                  close();
                }}
              />
            )}
            {agentEntries.map((a) => (
              <TickItem
                key={a.id}
                label={a.label}
                leading={<AgentTypeIcon agentTypeName={a.id} size={12} whiteForOpenAI />}
                isSelected={!selectedProfile && a.id === value.agent}
                isPending={false}
                onClick={() => {
                  pickPlainAgent(a.id);
                  close();
                }}
              />
            ))}
          </>
        )}
      </ChipDropdown>

      {!selectedProfile && modelEntries && modelEntries.length > 0 && (
        <ChipDropdown
          title="Model"
          disabled={disabled}
          side={side}
          contentClassName={modelListWidthClass(modelEntries)}
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
                sublabel={modelSublabel(m)}
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

      {!selectedProfile && visibleThinking.length > 0 && (
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

      {!selectedProfile && visibleReasoning.length > 0 && (
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

      {!selectedProfile && visiblePermission.length > 0 && (
        <ChipDropdown
          title="Permission mode"
          disabled={disabled}
          side={side}
          contentClassName={PERMISSION_LIST_WIDTH_CLASS}
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

      {!selectedProfile && visibleModes.length > 0 && (
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
