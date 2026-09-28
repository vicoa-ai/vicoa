/**
 * Per-agent catalog + session-config types backing the new-session pickers.
 *
 * Mirrors plans/new-session-model-selection.md §3.3, §4.1, §6.1 and the Dart
 * version at vicoa-app/lib/backend/agent_catalog.dart. The baked-in fallback
 * at the bottom is the source of truth when /api/v1/agent-catalog is
 * unreachable on cold start.
 */

import type { RemoteAgentType } from "@/lib/backend-api";

export interface CatalogEnumEntry {
  id: string;
  label: string;
  is_default?: boolean;
  /**
   * Marks the entry as model-specific. When `true`, it only renders if the
   * active model's per-model array names it; "common" entries (the default)
   * are always shown. Mirrors the additive shape in the backend catalog.
   */
  opt_in?: boolean;
  description?: string;
}

export interface CatalogModel {
  id: string;
  label: string;
  description?: string;
  is_default?: boolean;
  /** Per-model filter over the agent-level `thinking_efforts`. Currently every Claude model supports the full set; field stays for future gating. */
  thinking_efforts?: string[];
  /** Override the agent-level `is_default` for this model (Opus 4.7+ → `xhigh`). */
  default_thinking_effort?: string;
  /** Per-model filter over the agent-level `permission_modes` (Sonnet 4.6+ and Opus 4.7+ carry `auto`). */
  permission_modes?: string[];
}

export interface CatalogAgent {
  id: string;
  label: string;
  /** The wrapper can deliver a queued message into the *running* turn (the
   *  queue bar's Steer button). Codex (`turn/steer`), Claude Code (streaming
   *  stdin, picked up at the next tool boundary) and pi/omp (`steer` RPC);
   *  absent for ACP agents and OpenCode, which only queue. */
  supports_steer?: boolean;
  models: CatalogModel[] | null;
  thinking_efforts?: CatalogEnumEntry[];
  reasoning_efforts?: CatalogEnumEntry[];
  permission_modes?: CatalogEnumEntry[];
  modes?: CatalogEnumEntry[];
}

/**
 * One ACP agent a machine can add with one click (backend
 * `protocol/acp_catalog.py`). `command` is the whole launch argv; it goes
 * into the machine's `~/.vicoa/config.json` verbatim.
 */
export interface AcpCatalogEntry {
  id: string;
  label: string;
  description: string;
  command: string[];
  env?: Record<string, string>;
  install_url: string;
  version?: string;
}

export interface AgentCatalog {
  version: string;
  min_cli_version: string;
  min_client_version: string;
  agents: CatalogAgent[];
  /**
   * Agents a machine can add from Settings → Providers. Not in `agents`: a
   * daemon only knows them once they are in its config, and they carry no
   * model/mode lists — an ACP agent reports those at session/new. Absent
   * from the baked-in fallback; the server fills it.
   */
  acp_catalog?: AcpCatalogEntry[];
}

export function agentById(catalog: AgentCatalog, id: string): CatalogAgent | undefined {
  return catalog.agents.find((a) => a.id === id);
}

/** Picker label for an agent — every agent renders with its plain label. */
export function agentPickerLabel(_agentId: string, label: string): string {
  return label;
}

/**
 * A display label for an agent id the catalog has never heard of.
 *
 * User-defined providers (`agents.providers` in `~/.vicoa/config.json`) exist
 * only on the user's own machine, so the catalog shipped with this client
 * cannot describe them — that is the point of the feature. The daemon reports
 * them in `available_agents`; this makes a readable label out of the id, which
 * is all we have. `kimi-work` -> `Kimi Work`.
 */
export function customAgentLabel(agentId: string): string {
  return agentId
    .split('-')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

/**
 * Drop a trailing `(provider)` that an older daemon baked into a model label.
 *
 * Daemons up to and including the 1.7.x line labelled Pi/Oh My Pi models
 * `"Claude Haiku 4.5 (anthropic)"`. The provider now rides in the muted id
 * shown beside the name, so that suffix reads as a stutter — and it outlives
 * the daemon that produced it, because labels are cached per machine
 * (`machine_agent_models`) and pinned on running sessions' `session_config`.
 *
 * Deliberately narrow: only a trailing parenthetical whose content is exactly
 * the id's own provider segment. Pi genuinely ships
 * `"Claude Haiku 4.5 (latest)"` — a real distinction between the moving alias
 * and the dated build — and that must survive untouched.
 */
export function normalizeModelLabel(id: string, label: string): string {
  const provider = id.includes('/') ? id.slice(0, id.indexOf('/')) : '';
  if (!provider) return label;
  const suffix = ` (${provider})`;
  return label.endsWith(suffix) ? label.slice(0, -suffix.length) : label;
}

/** One cached `{id, label}` entry as the machine's `machine_agent_models` row stores it. */
export interface CachedAgentEntry {
  id: string;
  label: string;
}

/**
 * What the machine's `machine_agent_models` cache knows besides the model
 * lists. `modes` is the agent's ACP session modes (only for agents whose
 * source reported them); `labels` is the daemon's `agent_labels` map, the
 * only display name a client can have for a provider that exists solely in
 * that machine's config.
 */
export interface CachedAgentExtras {
  modes?: Record<string, CachedAgentEntry[]>;
  labels?: Record<string, string>;
}

/** The "defer to the agent's own model" sentinel a synthesized entry gets. */
const SYNTHESIZED_DEFAULT_MODEL: CatalogModel = { id: 'default', label: 'Default', is_default: true };

/**
 * Return `base` with each agent's model list replaced by the machine's cached
 * real models when present (keyed by agent id). Agents without a cached entry
 * keep their static catalog defaults. Lets the new-session picker show a
 * machine's actual models once an ACP agent has run there once — or, since a
 * daemon `provider-probe` also fills the cache, once it has been Checked or
 * Added from Settings → Providers.
 *
 * Cached ids the static catalog has never heard of (a catalog agent such as
 * Qwen Code, or a provider hand-written into the machine's config) get a
 * synthesized entry appended, so the picker can render a real model / mode
 * dropdown for them instead of nothing at all. It carries the `default`
 * sentinel (never sent as a model — `toSpawnMetadata`'s rule) plus the cached
 * models, and the cached modes as `permission_modes` — the field the generic
 * ACP spawn path forwards as the initial session mode. No efforts: nothing
 * the cache knows maps to them.
 */
export function catalogWithCachedModels(
  base: AgentCatalog,
  cachedByAgent: Record<string, CachedAgentEntry[]>,
  extras: CachedAgentExtras = {},
): AgentCatalog {
  if (!cachedByAgent || Object.keys(cachedByAgent).length === 0) return base;
  const known = new Set(base.agents.map((a) => a.id));
  const synthesized: CatalogAgent[] = Object.keys(cachedByAgent)
    .filter((id) => !known.has(id) && (cachedByAgent[id]?.length ?? 0) > 0)
    .sort()
    .map((id) => {
      const models: CatalogModel[] = [
        { ...SYNTHESIZED_DEFAULT_MODEL },
        ...cachedByAgent[id]
          .filter((m) => m.id !== SYNTHESIZED_DEFAULT_MODEL.id)
          .map((m) => ({ id: m.id, label: normalizeModelLabel(m.id, m.label || m.id) })),
      ];
      const entry: CatalogAgent = {
        id,
        label: extras.labels?.[id] || customAgentLabel(id),
        models,
      };
      const modes = cachedModesAsPermissionModes(extras.modes?.[id]);
      if (modes) entry.permission_modes = modes;
      return entry;
    });
  return {
    ...base,
    agents: [...base.agents.map((a) => {
      const cached = cachedByAgent[a.id];
      // A static entry with no curated mode list (Copilot, Kimi, Hermes: "source
      // modes from the live session") takes the machine's cached ones. Cursor
      // and Gemini keep their verified catalog lists.
      const cachedModes = a.permission_modes?.length ? undefined : cachedModesAsPermissionModes(extras.modes?.[a.id]);
      if (!cached || cached.length === 0) return cachedModes ? { ...a, permission_modes: cachedModes } : a;
      // A machine reports only `{id, label}` — no capability metadata. Carry the
      // catalog entry's fields over for ids we already know (`is_default`,
      // `permission_modes`, `default_thinking_effort`, …); without this, the
      // pickers silently lose per-model behaviour (the Opus `xhigh` default)
      // the moment an agent starts reporting its models — which is exactly
      // what happened when headless Claude began PATCHing `available_models`.
      // Genuinely custom ids (a user's ANTHROPIC_MODEL slug, an ACP variant)
      // keep the common set only.
      const catalogById = new Map((a.models ?? []).map((m) => [m.id, m] as const));
      const cachedModels: CatalogModel[] = cached.map((m) => {
        const known = catalogById.get(m.id);
        const label = normalizeModelLabel(m.id, m.label || m.id);
        return known ? { ...known, label: m.label ? label : known.label } : { id: m.id, label };
      });
      // Keep the agent's "defer to its own model" sentinel (the is_default
      // catalog entry, e.g. `auto`/`default`) at the top of the list. The
      // cached list is the machine's *real* models and never includes that
      // synthetic id, so without this a stored default would no longer match
      // any entry — the picker would render "—" and the spawn would lose the
      // defer behaviour (toSpawnMetadata skips sending a model for auto/default).
      const sentinel = a.models?.find((m) => m.is_default);
      const models = sentinel && !cachedModels.some((m) => m.id === sentinel.id)
        ? [{ ...sentinel }, ...cachedModels]
        : cachedModels;
      return cachedModes ? { ...a, models, permission_modes: cachedModes } : { ...a, models };
    }), ...synthesized],
  };
}

/**
 * An ACP agent's cached session modes as a `permission_modes` enum. The
 * agent's first advertised mode is its own default (that is what `session/new`
 * starts in), so it carries `is_default`. `undefined` when nothing is cached.
 */
function cachedModesAsPermissionModes(modes: CachedAgentEntry[] | undefined): CatalogEnumEntry[] | undefined {
  if (!modes || modes.length === 0) return undefined;
  return modes.map((m, i) => ({
    id: m.id,
    label: m.label || m.id,
    ...(i === 0 ? { is_default: true } : {}),
  }));
}

/**
 * Per-agent selected config. Persisted to localStorage per plan §3.5; built
 * into `metadata` on the spawn-session RPC per §3.6.
 */
export interface SessionConfig {
  agent: RemoteAgentType | string;
  model?: string;
  /** claude */
  thinking_effort?: string;
  /** codex */
  reasoning_effort?: string;
  /** claude / codex */
  permission_mode?: string;
  /** opencode `build|plan` */
  opencode_mode?: string;
}

/** Default config for a given agent, sourced from `is_default` in the catalog. */
export function defaultsFor(catalog: AgentCatalog, agentId: string): SessionConfig {
  const agent = agentById(catalog, agentId);
  if (!agent) return { agent: agentId };

  const defaultOf = (entries?: CatalogEnumEntry[]) => {
    if (!entries || entries.length === 0) return undefined;
    return entries.find((e) => e.is_default)?.id ?? entries[0].id;
  };

  let defaultModel: string | undefined;
  if (agent.models && agent.models.length > 0) {
    defaultModel = (agent.models.find((m) => m.is_default) ?? agent.models[0]).id;
  }

  return {
    agent: agentId,
    model: defaultModel,
    thinking_effort: defaultOf(agent.thinking_efforts),
    reasoning_effort: defaultOf(agent.reasoning_efforts),
    permission_mode: defaultOf(agent.permission_modes),
    opencode_mode: defaultOf(agent.modes),
  };
}

/**
 * Reconcile a stored config against the live catalog. Stale values silently
 * fall back to catalog defaults (plan §3.5 step 3); never mutates input.
 */
export function reconcileAgainst(config: SessionConfig, catalog: AgentCatalog): SessionConfig {
  const agent = agentById(catalog, config.agent);
  if (!agent) return defaultsFor(catalog, config.agent);

  const inEnum = (entries: CatalogEnumEntry[] | undefined, v: string | undefined) =>
    v != null && (entries ?? []).some((e) => e.id === v);
  const defaultEnum = (entries: CatalogEnumEntry[] | undefined) => {
    if (!entries || entries.length === 0) return undefined;
    return entries.find((e) => e.is_default)?.id ?? entries[0].id;
  };

  let nextModel: string | undefined = config.model;
  let modelDef: CatalogModel | undefined;
  if (agent.models) {
    const ids = new Set(agent.models.map((m) => m.id));
    if (!nextModel || !ids.has(nextModel)) {
      nextModel = (agent.models.find((m) => m.is_default) ?? agent.models[0])?.id;
    }
    modelDef = agent.models.find((m) => m.id === nextModel) ?? agent.models[0];
  } else {
    nextModel = undefined;
  }

  // Common + per-model opt-ins: every entry without `opt_in` is shown;
  // opt_in entries only when the model names them.
  const pickWithModelFilter = (
    entries: CatalogEnumEntry[] | undefined,
    optIns: string[] | undefined,
    current: string | undefined,
    perModelDefault?: string,
  ): string | undefined => {
    if (!entries || entries.length === 0) return undefined;
    const optInSet = new Set(optIns ?? []);
    const filtered = entries.filter((e) => !e.opt_in || optInSet.has(e.id));
    if (filtered.length === 0) return defaultEnum(entries);
    if (current && filtered.some((e) => e.id === current)) return current;
    // Per-model default overrides agent-level is_default (Opus 4.7+ → xhigh).
    if (perModelDefault && filtered.some((e) => e.id === perModelDefault)) {
      return perModelDefault;
    }
    return (filtered.find((e) => e.is_default) ?? filtered[0]).id;
  };

  return {
    agent: config.agent,
    model: nextModel,
    thinking_effort: pickWithModelFilter(agent.thinking_efforts, modelDef?.thinking_efforts, config.thinking_effort, modelDef?.default_thinking_effort),
    reasoning_effort: !agent.reasoning_efforts?.length
      ? undefined
      : inEnum(agent.reasoning_efforts, config.reasoning_effort)
        ? config.reasoning_effort
        : defaultEnum(agent.reasoning_efforts),
    permission_mode: pickWithModelFilter(agent.permission_modes, modelDef?.permission_modes, config.permission_mode),
    opencode_mode: !agent.modes?.length
      ? undefined
      : inEnum(agent.modes, config.opencode_mode)
        ? config.opencode_mode
        : defaultEnum(agent.modes),
  };
}

/**
 * Build the daemon-bound `metadata` payload (plan §3.6). Dual-writes
 * `enable_thinking` for old daemons when `thinking_effort` is set.
 */
export function toSpawnMetadata(config: SessionConfig, prompt?: string): Record<string, unknown> {
  const m: Record<string, unknown> = {};
  if (prompt != null) m.prompt = prompt;
  if (config.agent === "claude") {
    if (config.model) m.model = config.model;
    if (config.thinking_effort) {
      m.thinking_effort = config.thinking_effort;
      // Dual-write for old daemons (plan §3.6). Old daemons ignore
      // thinking_effort entirely and only see `enable_thinking`.
      m.enable_thinking = config.thinking_effort !== "off";
    }
    if (config.permission_mode) m.permission_mode = config.permission_mode;
  } else if (config.agent === "codex") {
    if (config.model) m.model = config.model;
    if (config.reasoning_effort) m.reasoning_effort = config.reasoning_effort;
    if (config.permission_mode) m.permission_mode = config.permission_mode;
  } else if (config.agent === "omp" || config.agent === "pi") {
    // Pi family: model + thinking effort + (omp only) permission mode. Unlike
    // Claude there is no legacy `enable_thinking` to dual-write.
    // `default`/`auto` means "keep the agent's own configured model".
    if (config.model && config.model !== "default" && config.model !== "auto") {
      m.model = config.model;
    }
    if (config.thinking_effort) m.thinking_effort = config.thinking_effort;
    if (config.permission_mode) m.permission_mode = config.permission_mode;
  } else if (config.agent === "opencode") {
    if (config.opencode_mode) m.agent_mode = config.opencode_mode;
    // `default`/`auto` = keep OpenCode's own configured model (don't force
    // one); anything else is an explicit provider/model the user picked.
    if (config.model && config.model !== "default" && config.model !== "auto") {
      m.model = config.model;
    }
  } else {
    // Generic ACP agents (cursor/gemini/copilot/kimi/hermes and any
    // catalog-added or synthesized one) and Antigravity: model +
    // permission_mode pass through;
    // the wrapper applies them best-effort against the agent's live ACP
    // session state. `default`/`auto` is the "keep the agent's own model"
    // sentinel and is not sent (the wrapper would skip it anyway).
    if (config.model && config.model !== "default" && config.model !== "auto") {
      m.model = config.model;
    }
    if (config.permission_mode) m.permission_mode = config.permission_mode;
  }
  return m;
}

/**
 * Two-row breakdown for the card summary. Row 1 = identity (agent + model);
 * Row 2 = configuration knobs (permission + effort/mode). Keep in sync with
 * the Dart `sessionConfigSummaryRows`.
 */
export function sessionConfigSummaryRows(catalog: AgentCatalog, config: SessionConfig): string[][] {
  const agent = agentById(catalog, config.agent);
  const row1: string[] = [agent?.label ?? config.agent];
  if (config.model && agent?.models) {
    const m = agent.models.find((m) => m.id === config.model);
    row1.push(m?.label ?? config.model);
  }

  const row2: string[] = [];
  if (config.permission_mode && agent?.permission_modes?.length) {
    const p = agent.permission_modes.find((e) => e.id === config.permission_mode);
    row2.push(p?.label ?? config.permission_mode);
  }
  if (config.agent === "claude" && config.thinking_effort && agent?.thinking_efforts?.length) {
    const t = agent.thinking_efforts.find((e) => e.id === config.thinking_effort);
    row2.push(`Thinking - ${t?.label ?? config.thinking_effort}`);
  }
  if (config.agent === "codex" && config.reasoning_effort && agent?.reasoning_efforts?.length) {
    const r = agent.reasoning_efforts.find((e) => e.id === config.reasoning_effort);
    row2.push(`Reasoning - ${r?.label ?? config.reasoning_effort}`);
  }
  if (config.agent === "opencode" && config.opencode_mode && agent?.modes?.length) {
    const m = agent.modes.find((e) => e.id === config.opencode_mode);
    row2.push(m?.label ?? config.opencode_mode);
  }

  return row2.length > 0 ? [row1, row2] : [row1];
}

// ---------------------------------------------------------------------------
// Persistence (per-agent memory, plan §3.5)
// ---------------------------------------------------------------------------

const PERSIST_KEY_V2 = "vicoa:last-remote-session-selection-v2";
const PERSIST_KEY_V1 = "vicoa:last-remote-session-selection";

/** Worktree selection remembered for `lastMachineId` + `lastDirectory`.
 * `mode` is a `WorktreeMode` string ('none' is never stored — a none selection
 * clears the field). Kept loosely typed here so this leaf module stays free of
 * a worktree-selection import. */
export interface PersistedWorktree {
  mode: string;
  path?: string | null;
  branch?: string | null;
}

export interface PersistedSelection {
  lastMachineId?: string;
  lastAgent?: string;
  perAgent: Record<string, SessionConfig>;
  /** Working directory last used with `lastMachineId`; restored only when that
   * machine is re-selected, else the machine's own default stands. */
  lastDirectory?: string;
  /** Worktree last used with `lastMachineId` + `lastDirectory`; restored only
   * when both still match, since a worktree path is repo-specific. */
  lastWorktree?: PersistedWorktree;
  /** Task chip last selected (web only); restored on mount, cleared on submit. */
  lastTaskId?: string;
}

export function loadPersistedSelection(): PersistedSelection {
  if (typeof window === "undefined") return { perAgent: {} };
  try {
    const rawV2 = window.localStorage.getItem(PERSIST_KEY_V2);
    if (rawV2) {
      const parsed = JSON.parse(rawV2) as Partial<PersistedSelection>;
      return {
        lastMachineId: parsed.lastMachineId,
        lastAgent: parsed.lastAgent,
        perAgent: parsed.perAgent ?? {},
        lastDirectory: parsed.lastDirectory,
        lastWorktree: parsed.lastWorktree,
        lastTaskId: parsed.lastTaskId,
      };
    }
    // Silent v1 → v2 migration (plan §3.5). v1 stored {machineId, agent}.
    const rawV1 = window.localStorage.getItem(PERSIST_KEY_V1);
    if (rawV1) {
      const v1 = JSON.parse(rawV1) as { machineId?: string; agent?: string };
      const migrated: PersistedSelection = {
        lastMachineId: v1.machineId,
        lastAgent: v1.agent,
        perAgent: {},
      };
      window.localStorage.setItem(PERSIST_KEY_V2, JSON.stringify(migrated));
      window.localStorage.removeItem(PERSIST_KEY_V1);
      return migrated;
    }
  } catch {
    /* swallow — fall through to defaults */
  }
  return { perAgent: {} };
}

/** Merge `payload` into the stored selection rather than overwriting it, so a
 * partial write (e.g. just `lastDirectory`) never drops sibling fields written
 * elsewhere (agent/config vs. machine/directory/worktree/task live on the same
 * blob but are saved from different call sites). Passing a field as `undefined`
 * clears it — `JSON.stringify` drops the key so it reads back absent. */
export function savePersistedSelection(payload: Partial<PersistedSelection>): void {
  if (typeof window === "undefined") return;
  try {
    const merged = { ...loadPersistedSelection(), ...payload };
    window.localStorage.setItem(PERSIST_KEY_V2, JSON.stringify(merged));
  } catch {
    /* ignore quota errors */
  }
}

// ---------------------------------------------------------------------------
// Baked-in fallback — keep in sync with `vicoa-backend/src/shared/agent_catalog.py`.
// Refresh process and upstream slug discovery: docs/agents/agent-catalog.md.
//
// **Never delete a model entry, even after upstream retires it.** Spawn-time
// `session_config` rows persisted on `agent_instances` reference model ids
// forever (plan plans/session-config-storage.md §3.5). Display surfaces
// resolve model labels through this catalog — deleting an entry degrades
// old-session display to a raw id like `claude-opus-4-7`. When a model is
// retired, add `deprecated: true` (future field) so the new-session picker
// hides it while the header label resolution keeps working. No model needs
// the flag today; this comment is the rule.
// ---------------------------------------------------------------------------

export const AGENT_CATALOG_FALLBACK: AgentCatalog = {
  version: "2026-09-26-1",
  min_cli_version: "1.20.0",
  min_client_version: "0.42.0",
  agents: [
    {
      id: "claude",
      label: "Claude Code",
      supports_steer: true,
      models: [
        // Opus 4.7+ default to xhigh via `default_thinking_effort` (per-model
        // override of the agent-level `high` is_default).
        // Fable 5, Opus 5 and Opus 5.5 are natively 1M-context (no `[1m]` variant);
        // Fable 5 is premium-priced and thinking-always-on — offered but not the picker default.
        // Opus 5.5 carries no `default_thinking_effort` on purpose: Claude Code's own
        // default for it is `medium`, so it takes the agent-level `high`, not Opus 5's `xhigh`.
        { id: "claude-fable-5", label: "Fable 5", default_thinking_effort: "xhigh" },
        { id: "claude-opus-5-5", label: "Opus 5.5" },
        { id: "claude-opus-5", label: "Opus 5", default_thinking_effort: "xhigh" },
        { id: "claude-opus-4-8", label: "Opus 4.8", default_thinking_effort: "xhigh" },
        { id: "claude-opus-4-8[1m]", label: "Opus 4.8 1M", default_thinking_effort: "xhigh" },
        { id: "claude-opus-4-7", label: "Opus 4.7", default_thinking_effort: "xhigh" },
        { id: "claude-opus-4-7[1m]", label: "Opus 4.7 1M", default_thinking_effort: "xhigh" },
        { id: "claude-opus-4-6", label: "Opus 4.6" },
        { id: "claude-opus-4-6[1m]", label: "Opus 4.6 1M" },
        { id: "claude-sonnet-5", label: "Sonnet 5", is_default: true },
        { id: "claude-sonnet-5[1m]", label: "Sonnet 5 1M" },
        { id: "claude-sonnet-4-6", label: "Sonnet 4.6" },
        { id: "claude-sonnet-4-6[1m]", label: "Sonnet 4.6 1M" },
        { id: "claude-haiku-4-5", label: "Haiku 4.5" },
      ],
      thinking_efforts: [
        { id: "max", label: "Max" },
        { id: "xhigh", label: "Extra High" },
        { id: "high", label: "High", is_default: true },
        { id: "medium", label: "Medium" },
        { id: "low", label: "Low" },
        { id: "off", label: "Off" },
      ],
      // `auto` is the default for every model, mirroring Claude Code. It is
      // deliberately not `opt_in`, so a model this fallback predates still gets
      // it (see the canonical catalog in backend/src/protocol/agent_catalog.py).
      permission_modes: [
        { id: "default", label: "Default" },
        { id: "auto", label: "Auto mode", is_default: true },
        { id: "acceptEdits", label: "Accept Edits" },
        { id: "plan", label: "Plan" },
        { id: "bypassPermissions", label: "Skip permissions (Yolo)" },
      ],
    },
    {
      id: "codex",
      label: "Codex",
      supports_steer: true,
      // Refresh per docs/agents/agent-catalog.md. Do NOT source from
      // ~/.codex/models_cache.json — that file is per-user / per-account
      // and reflects entitlements rather than the canonical slug list.
      models: [
        { id: "gpt-5.5", label: "GPT-5.5", is_default: true },
        { id: "gpt-5.6-sol", label: "GPT-5.6-Sol" },
        { id: "gpt-5.6-terra", label: "GPT-5.6-Terra" },
        { id: "gpt-5.6-luna", label: "GPT-5.6-Luna" },
        { id: "gpt-5.4", label: "GPT-5.4" },
        { id: "gpt-5.4-mini", label: "GPT-5.4-Mini" },
      ],
      reasoning_efforts: [
        { id: "low", label: "Low" },
        { id: "medium", label: "Medium", is_default: true },
        { id: "high", label: "High" },
        { id: "xhigh", label: "Extra High" },
      ],
      // Vicoa permission_mode is a BUNDLED abstraction — each slug collapses
      // 2-3 codex settings (approval_policy + sandbox_mode + collaboration_mode).
      // Spawn-time mapping lives in integrations/headless/codex/permission_translate.py;
      // the Rust bridge mirrors the same bundle mid-session.
      permission_modes: [
        { id: "default", label: "Default", is_default: true },
        { id: "bypassPermissions", label: "Full Access" },
      ],
    },
    {
      id: "opencode",
      label: "OpenCode",
      // `default` keeps the user's own configured model (no --model at spawn);
      // the rest is a starter set. The real per-config list is reported live to
      // the mid-session gear (the wrapper PATCHes available_models).
      models: [
        { id: "default", label: "Default", is_default: true },
        { id: "opencode/big-pickle", label: "OpenCode Zen - big-pickle" },
      ],
      modes: [
        { id: "build", label: "Build", is_default: true },
        { id: "plan", label: "Plan" },
      ],
    },
    // Generic ACP agents (vicoa-backend integrations/headless/generic_acp.py).
    // `models` is a STATIC default set shown in the new-session picker —
    // account/version-specific upstream, so not exhaustive (an install's
    // other models appear in the mid-session gear, sourced live from
    // session/new). `auto`/`default` lets the user defer to the agent's own
    // choice. Modes ARE applied at spawn via set_mode. Verified June 2026:
    // cursor = agent/plan/ask; gemini = default/autoEdit(camelCase)/plan/yolo;
    // kimi = `default` only; copilot ACP mode ids undocumented.
    // Pi family (integrations/headless/pi_family/) — native RPC, not ACP.
    // Both proxy many providers whose real model list is per-machine config,
    // so like OpenCode `default` is the only static entry and the true list
    // arrives live in the mid-session gear. The CLIs also accept `minimal`
    // (both) and `auto` (omp) thinking levels; they are deliberately omitted
    // so the shared effort enum isn't widened for every agent.
    {
      id: "omp",
      label: "Oh My Pi",
      supports_steer: true,
      models: [{ id: "default", label: "Default", is_default: true }],
      thinking_efforts: [
        { id: "max", label: "Max" },
        { id: "xhigh", label: "Extra High" },
        { id: "high", label: "High" },
        { id: "medium", label: "Medium", is_default: true },
        { id: "low", label: "Low" },
        { id: "off", label: "Off" },
      ],
      // -> omp's `--approval-mode`. Reusing Vicoa's existing slugs keeps the
      // shared mode picker unchanged; the backend spec table owns the
      // translation. `default` means always-ask here.
      permission_modes: [
        { id: "default", label: "Always Ask", is_default: true },
        { id: "acceptEdits", label: "Write Approval" },
        { id: "bypassPermissions", label: "Skip permissions (Yolo)" },
      ],
    },
    {
      id: "pi",
      label: "Pi",
      supports_steer: true,
      models: [{ id: "default", label: "Default", is_default: true }],
      thinking_efforts: [
        { id: "max", label: "Max" },
        { id: "xhigh", label: "Extra High" },
        { id: "high", label: "High" },
        { id: "medium", label: "Medium", is_default: true },
        { id: "low", label: "Low" },
        { id: "off", label: "Off" },
      ],
      // Pi has no approval-mode flag at all, so no mode picker.
    },
    // Antigravity CLI (integrations/headless/antigravity/) — Google's `agy`,
    // driven over its stream-json stdio; neither ACP nor an SDK. Models are the
    // 2026-09-16 `agy models` list; every id already encodes its effort and
    // `--effort` hard-fails on a mismatch, so there is no thinking picker. The
    // wrapper PATCHes the live list into available_models at session start.
    // Headless agy cannot prompt: `default` auto-denies writes and commands,
    // `acceptEdits` allows workspace writes, `bypassPermissions` allows all.
    // No `supports_steer` — the CLI must not be written to mid-turn.
    {
      id: "antigravity",
      label: "Antigravity",
      models: [
        { id: "default", label: "Default", is_default: true },
        { id: "gemini-3.8-flash-high", label: "Gemini 3.8 Flash (High)" },
        { id: "gemini-3.8-flash-medium", label: "Gemini 3.8 Flash (Medium)" },
        { id: "gemini-3.8-flash-low", label: "Gemini 3.8 Flash (Low)" },
        { id: "gemini-3.7-flash-high", label: "Gemini 3.7 Flash (High)" },
        { id: "gemini-3.7-flash-medium", label: "Gemini 3.7 Flash (Medium)" },
        { id: "gemini-3.7-flash-low", label: "Gemini 3.7 Flash (Low)" },
        { id: "gemini-3.6-flash-high", label: "Gemini 3.6 Flash (High)" },
        { id: "gemini-3.6-flash-medium", label: "Gemini 3.6 Flash (Medium)" },
        { id: "gemini-3.6-flash-low", label: "Gemini 3.6 Flash (Low)" },
        { id: "gemini-3.1-pro-high", label: "Gemini 3.1 Pro (High)" },
        { id: "gemini-3.1-pro-low", label: "Gemini 3.1 Pro (Low)" },
        { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6 (Thinking)" },
        { id: "claude-opus-4-6-thinking", label: "Claude Opus 4.6 (Thinking)" },
        { id: "gpt-oss-120b-medium", label: "GPT-OSS 120B (Medium)" },
      ],
      permission_modes: [
        { id: "default", label: "Read only (auto-deny writes & commands)", is_default: true },
        { id: "acceptEdits", label: "Write approval (auto-deny commands)" },
        { id: "plan", label: "Plan" },
        { id: "bypassPermissions", label: "Skip permissions (Yolo)" },
      ],
    },
    {
      id: "cursor",
      label: "Cursor",
      models: [{ id: "auto", label: "Default", is_default: true },
        { id: "composer-2.5", label: "Composer 2.5" },
      ],
      permission_modes: [
        { id: "agent", label: "Agent", is_default: true },
        { id: "plan", label: "Plan" },
        { id: "ask", label: "Ask" },
      ],
    },
    {
      id: "gemini",
      label: "Gemini",
      models: [
        { id: "auto", label: "Default", is_default: true },
        { id: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash Lite" },
        { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
        { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
      ],
      permission_modes: [
        { id: "default", label: "Default", is_default: true },
        // Wire id is camelCase `autoEdit`, not the `auto_edit` flag spelling.
        { id: "autoEdit", label: "Auto Edit" },
        { id: "plan", label: "Plan" },
        { id: "yolo", label: "Skip permissions (Yolo)" },
      ],
    },
    {
      id: "copilot",
      label: "Copilot",
      // Copilot's default install offers these; richer model access is
      // subscription-gated. A starter set — an install's real options show in
      // the live gear, and the catalog id is resolved against live values at spawn.
      models: [
        { id: "default", label: "Default", is_default: true },
        { id: "gpt-5-mini", label: "GPT-5 mini" },
        { id: "claude-haiku-4.5", label: "Claude Haiku 4.5" },
      ],
      // ACP mode ids undocumented (Copilot CLI is closed source) — source
      // modes from the live session rather than guessing.
    },
    {
      id: "kimi",
      label: "Kimi",
      // `auto` skips --model (Kimi uses its config default_model); the rest
      // are common namespaced aliases. An install's real aliases show live.
      models: [
        { id: "auto", label: "Default", is_default: true },
        { id: "moonshot-ai/kimi-k2.5", label: "Kimi K2.5" },
        { id: "moonshot-ai/kimi-k2.6", label: "Kimi K2.6" },
        { id: "moonshot-ai/kimi-k2.7-code", label: "Kimi K2.7 Code" },
      ],
      // Kimi advertises only a single `default` ACP mode — no mode picker.
    },
    {
      id: "hermes",
      label: "Hermes",
      models: [{ id: "default", label: "Provider default", is_default: true }],
    },
  ],
};

export function agentCatalogFallback(): AgentCatalog {
  return AGENT_CATALOG_FALLBACK;
}
