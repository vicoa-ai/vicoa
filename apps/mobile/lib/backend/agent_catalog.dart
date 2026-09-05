/// Per-agent catalog + session-config types backing the new-session sheet.
///
/// Mirrors `plans/new-session-model-selection.md` §3.3, §4.1, §7.1. The
/// baked-in fallback at the bottom of this file is the source of truth when
/// `/api/v1/agent-catalog` is unreachable on cold start.
library;

import 'dart:convert';

import '/flutter_flow/app_locale.dart';

/// Capitalize the first character — used as a label fallback when a catalog
/// entry omits the `label` field. Keeps the rest of the id untouched so we
/// don't fight camelCase-vs-hyphenation edge cases ("acceptEdits" → "AcceptEdits").
String _labelFallback(String id) => id.isEmpty ? id : '${id[0].toUpperCase()}${id.substring(1)}';

/// Per-agent permission_mode / thinking_effort / reasoning_effort / opencode mode entries.
///
/// `optIn: true` marks an entry as model-specific — only visible when the
/// active model's per-model array explicitly opts in by id. Entries without
/// the flag are "common" and shown for every model.
class CatalogEnumEntry {
  CatalogEnumEntry({required this.id, required this.label, this.isDefault = false, this.optIn = false, this.description});
  final String id;
  final String label;
  final bool isDefault;
  final bool optIn;
  final String? description;

  factory CatalogEnumEntry.fromJson(Map<String, dynamic> json) => CatalogEnumEntry(
        id: json['id'] as String,
        label: (json['label'] as String?) ?? _labelFallback(json['id'] as String),
        isDefault: json['is_default'] as bool? ?? false,
        optIn: json['opt_in'] as bool? ?? false,
        description: json['description'] as String?,
      );
}

class CatalogModel {
  CatalogModel({required this.id, required this.label, this.description, this.isDefault = false, this.thinkingEfforts, this.permissionModes, this.defaultThinkingEffort});
  final String id;
  final String label;
  final String? description;
  final bool isDefault;
  /// Per-model filter over agent-level `thinkingEfforts`. Currently every
  /// Claude model supports the full set, so this stays null in the catalog;
  /// the field exists for future per-model gating.
  final List<String>? thinkingEfforts;
  /// Per-model filter over agent-level `permissionModes`. Same shape as
  /// `thinkingEfforts` — Sonnet 4.6+ and Opus 4.7+ add `auto`; older models omit it.
  final List<String>? permissionModes;
  /// Override the agent-level `thinkingEfforts is_default` for this model.
  /// Opus 4.7+ default to `xhigh` (they're the only models with the depth
  /// to justify going above the agent-level `high` baseline).
  final String? defaultThinkingEffort;

  factory CatalogModel.fromJson(Map<String, dynamic> json) => CatalogModel(
        id: json['id'] as String,
        label: (json['label'] as String?) ?? _labelFallback(json['id'] as String),
        description: json['description'] as String?,
        isDefault: json['is_default'] as bool? ?? false,
        thinkingEfforts: (json['thinking_efforts'] as List?)?.map((e) => e as String).toList(),
        permissionModes: (json['permission_modes'] as List?)?.map((e) => e as String).toList(),
        defaultThinkingEffort: json['default_thinking_effort'] as String?,
      );
}

class CatalogAgent {
  CatalogAgent({
    required this.id,
    required this.label,
    required this.models,
    required this.thinkingEfforts,
    required this.reasoningEfforts,
    required this.permissionModes,
    required this.modes,
  });

  final String id;
  final String label;
  /// Null when this agent has no model selector (OpenCode in v1).
  final List<CatalogModel>? models;
  final List<CatalogEnumEntry> thinkingEfforts;
  final List<CatalogEnumEntry> reasoningEfforts;
  final List<CatalogEnumEntry> permissionModes;
  /// OpenCode-only `build|plan`.
  final List<CatalogEnumEntry> modes;

  factory CatalogAgent.fromJson(Map<String, dynamic> json) => CatalogAgent(
        id: json['id'] as String,
        label: (json['label'] as String?) ?? (json['id'] as String),
        models: (json['models'] as List?)?.map((m) => CatalogModel.fromJson(Map<String, dynamic>.from(m as Map))).toList(),
        thinkingEfforts: ((json['thinking_efforts'] as List?) ?? const []).map((e) => CatalogEnumEntry.fromJson(Map<String, dynamic>.from(e as Map))).toList(),
        reasoningEfforts: ((json['reasoning_efforts'] as List?) ?? const []).map((e) => CatalogEnumEntry.fromJson(Map<String, dynamic>.from(e as Map))).toList(),
        permissionModes: ((json['permission_modes'] as List?) ?? const []).map((e) => CatalogEnumEntry.fromJson(Map<String, dynamic>.from(e as Map))).toList(),
        modes: ((json['modes'] as List?) ?? const []).map((e) => CatalogEnumEntry.fromJson(Map<String, dynamic>.from(e as Map))).toList(),
      );
}

class AgentCatalog {
  AgentCatalog({required this.version, required this.minCliVersion, required this.minClientVersion, required this.agents});
  final String version;
  final String minCliVersion;
  final String minClientVersion;
  final List<CatalogAgent> agents;

  CatalogAgent? agentById(String id) {
    for (final a in agents) {
      if (a.id == id) return a;
    }
    return null;
  }

  factory AgentCatalog.fromJson(Map<String, dynamic> json) => AgentCatalog(
        version: (json['version'] as String?) ?? '',
        minCliVersion: (json['min_cli_version'] as String?) ?? '0.0.0',
        minClientVersion: (json['min_client_version'] as String?) ?? '0.0.0',
        agents: ((json['agents'] as List?) ?? const []).map((a) => CatalogAgent.fromJson(Map<String, dynamic>.from(a as Map))).toList(),
      );
}

/// Per-agent selected config. Discriminated by [agent].
/// Persisted to FFAppState as JSON; see also api_spawn_session_ws metadata builder.
class SessionConfig {
  SessionConfig({required this.agent, this.model, this.thinkingEffort, this.reasoningEffort, this.permissionMode, this.opencodeMode});
  final String agent; // 'claude' | 'codex' | 'opencode'
  final String? model;
  final String? thinkingEffort; // claude
  final String? reasoningEffort; // codex
  final String? permissionMode; // claude / codex
  final String? opencodeMode; // opencode `build|plan`

  Map<String, dynamic> toJson() => <String, dynamic>{
        'agent': agent,
        if (model != null) 'model': model,
        if (thinkingEffort != null) 'thinking_effort': thinkingEffort,
        if (reasoningEffort != null) 'reasoning_effort': reasoningEffort,
        if (permissionMode != null) 'permission_mode': permissionMode,
        if (opencodeMode != null) 'opencode_mode': opencodeMode,
      };

  factory SessionConfig.fromJson(Map<String, dynamic> json) => SessionConfig(
        agent: (json['agent'] as String?) ?? 'claude',
        model: json['model'] as String?,
        thinkingEffort: json['thinking_effort'] as String?,
        reasoningEffort: json['reasoning_effort'] as String?,
        permissionMode: json['permission_mode'] as String?,
        opencodeMode: json['opencode_mode'] as String? ?? json['mode'] as String?,
      );

  /// Build the daemon-bound `metadata` payload (plan §3.6 wire format).
  /// Dual-writes `enable_thinking` for old daemons when thinking_effort is set.
  Map<String, dynamic> toSpawnMetadata({String? prompt}) {
    final m = <String, dynamic>{};
    if (prompt != null) m['prompt'] = prompt;
    if (agent == 'claude') {
      if (model != null) m['model'] = model;
      if (thinkingEffort != null) {
        m['thinking_effort'] = thinkingEffort;
        // Dual-write for old daemons (plan §3.6): off → disabled; everything
        // else → enabled. Old daemons ignore thinking_effort and use this.
        m['enable_thinking'] = thinkingEffort != 'off';
      }
      if (permissionMode != null) m['permission_mode'] = permissionMode;
    } else if (agent == 'codex') {
      if (model != null) m['model'] = model;
      if (reasoningEffort != null) m['reasoning_effort'] = reasoningEffort;
      if (permissionMode != null) m['permission_mode'] = permissionMode;
    } else if (agent == 'omp' || agent == 'pi') {
      // Pi family (native RPC, not ACP): model + thinking effort + (omp only)
      // permission mode. No legacy `enable_thinking` to dual-write.
      // `default`/`auto` means "keep the agent's own configured model".
      if (model != null && model != 'default' && model != 'auto') {
        m['model'] = model;
      }
      if (thinkingEffort != null) m['thinking_effort'] = thinkingEffort;
      if (permissionMode != null) m['permission_mode'] = permissionMode;
    } else if (agent == 'opencode') {
      if (opencodeMode != null) m['agent_mode'] = opencodeMode;
      // `default`/`auto` = keep OpenCode's own configured model (don't force
      // one); anything else is an explicit provider/model the user picked.
      if (model != null && model != 'default' && model != 'auto') m['model'] = model;
    } else {
      // Generic ACP agents (cursor/gemini/copilot/kimi/hermes): model +
      // permission_mode pass through; the wrapper applies them best-effort
      // against the agent's live ACP session state.
      if (model != null) m['model'] = model;
      if (permissionMode != null) m['permission_mode'] = permissionMode;
    }
    return m;
  }

  /// Initialize a config from catalog defaults — used when no prior selection
  /// exists for [agentId], or when the prior selection contains stale values
  /// no longer in the catalog (plan §3.5 field-init order: stored → default).
  static SessionConfig defaultsFor(AgentCatalog catalog, String agentId) {
    final agent = catalog.agentById(agentId);
    if (agent == null) return SessionConfig(agent: agentId);
    String? defaultOf(List<CatalogEnumEntry> entries) {
      for (final e in entries) {
        if (e.isDefault) return e.id;
      }
      return entries.isNotEmpty ? entries.first.id : null;
    }

    String? defaultModel;
    if (agent.models != null && agent.models!.isNotEmpty) {
      defaultModel = agent.models!.firstWhere((m) => m.isDefault, orElse: () => agent.models!.first).id;
    }
    return SessionConfig(
      agent: agentId,
      model: defaultModel,
      thinkingEffort: agent.thinkingEfforts.isNotEmpty ? defaultOf(agent.thinkingEfforts) : null,
      reasoningEffort: agent.reasoningEfforts.isNotEmpty ? defaultOf(agent.reasoningEfforts) : null,
      permissionMode: agent.permissionModes.isNotEmpty ? defaultOf(agent.permissionModes) : null,
      opencodeMode: agent.modes.isNotEmpty ? defaultOf(agent.modes) : null,
    );
  }

  /// Reconcile a stored config against the live catalog: stale values fall
  /// back to catalog defaults silently (plan §3.5 step 3). Returns a new
  /// SessionConfig — never mutates.
  SessionConfig reconcileAgainst(AgentCatalog catalog) {
    final agent = catalog.agentById(this.agent);
    if (agent == null) return SessionConfig.defaultsFor(catalog, this.agent);

    bool inEnum(List<CatalogEnumEntry> entries, String? v) => v != null && entries.any((e) => e.id == v);
    String? defaultEnum(List<CatalogEnumEntry> entries) {
      for (final e in entries) {
        if (e.isDefault) return e.id;
      }
      return entries.isNotEmpty ? entries.first.id : null;
    }

    String? nextModel = model;
    CatalogModel? modelDef;
    if (agent.models != null) {
      // No stored model yet — fall back to the catalog default. If the
      // stored slug isn't in the catalog (e.g. the binary advertises a
      // model not yet listed here), KEEP the stored value so the
      // dropdown reflects what's actually running rather than silently
      // swapping to a catalog default the session isn't using.
      nextModel ??= agent.models!.firstWhere((m) => m.isDefault, orElse: () => agent.models!.first).id;
      modelDef = agent.models!.firstWhere((m) => m.id == nextModel, orElse: () => CatalogModel(id: nextModel!, label: nextModel));
    } else {
      nextModel = null;
    }

    // Per-model filter helper — keeps every "common" entry (opt_in=false)
    // PLUS any opt-in entries the model's per-model array names. Mirrors
    // the additive shape: agent-level is the basic set + label registry;
    // per-model arrays add extras.
    bool isVisibleForModel(CatalogEnumEntry entry, List<String>? optIns) {
      if (!entry.optIn) return true;
      return optIns != null && optIns.contains(entry.id);
    }

    String? pickWithModelFilter(
      List<CatalogEnumEntry> entries,
      List<String>? optIns,
      String? current, {
      String? perModelDefault,
    }) {
      if (entries.isEmpty) return null;
      final visible = entries.where((e) => isVisibleForModel(e, optIns)).toList();
      if (visible.isEmpty) return defaultEnum(entries);
      if (current != null && visible.any((e) => e.id == current)) return current;
      // Per-model default overrides agent-level is_default (e.g. Opus 4.7+
      // pick xhigh instead of the agent-level `high` baseline).
      if (perModelDefault != null && visible.any((e) => e.id == perModelDefault)) {
        return perModelDefault;
      }
      return visible.firstWhere((e) => e.isDefault, orElse: () => visible.first).id;
    }

    return SessionConfig(
      agent: this.agent,
      model: nextModel,
      thinkingEffort: pickWithModelFilter(agent.thinkingEfforts, modelDef?.thinkingEfforts, thinkingEffort, perModelDefault: modelDef?.defaultThinkingEffort),
      reasoningEffort: agent.reasoningEfforts.isEmpty ? null : (inEnum(agent.reasoningEfforts, reasoningEffort) ? reasoningEffort : defaultEnum(agent.reasoningEfforts)),
      permissionMode: pickWithModelFilter(agent.permissionModes, modelDef?.permissionModes, permissionMode),
      opencodeMode: agent.modes.isEmpty ? null : (inEnum(agent.modes, opencodeMode) ? opencodeMode : defaultEnum(agent.modes)),
    );
  }
}

/// Two-row breakdown of a SessionConfig for the new-session card. Row 1 is
/// the agent + model (identity); row 2 is the "permission / effort" group
/// so a tall card stays legible without one runaway truncation.
List<List<String>> sessionConfigSummaryRows(AgentCatalog catalog, SessionConfig config) {
  final agent = catalog.agentById(config.agent);
  final row1 = <String>[agent?.label ?? config.agent];
  if (config.model != null && agent?.models != null) {
    final m = agent!.models!.firstWhere(
      (m) => m.id == config.model,
      orElse: () => CatalogModel(id: config.model!, label: config.model!),
    );
    row1.add(m.label);
  }

  final row2 = <String>[];
  if (config.permissionMode != null && agent?.permissionModes.isNotEmpty == true) {
    final p = agent!.permissionModes.firstWhere(
      (e) => e.id == config.permissionMode,
      orElse: () => CatalogEnumEntry(id: config.permissionMode!, label: config.permissionMode!),
    );
    row2.add(p.label);
  }
  if (config.agent == 'claude' && config.thinkingEffort != null && agent?.thinkingEfforts.isNotEmpty == true) {
    final t = agent!.thinkingEfforts.firstWhere(
      (e) => e.id == config.thinkingEffort,
      orElse: () => CatalogEnumEntry(id: config.thinkingEffort!, label: config.thinkingEffort!),
    );
    row2.add(tr().agentCatalogThinkingLabel(t.label));
  }
  if (config.agent == 'codex' && config.reasoningEffort != null && agent?.reasoningEfforts.isNotEmpty == true) {
    final r = agent!.reasoningEfforts.firstWhere(
      (e) => e.id == config.reasoningEffort,
      orElse: () => CatalogEnumEntry(id: config.reasoningEffort!, label: config.reasoningEffort!),
    );
    row2.add(tr().agentCatalogReasoningLabel(r.label));
  }
  if (config.agent == 'opencode' && config.opencodeMode != null && agent?.modes.isNotEmpty == true) {
    final m = agent!.modes.firstWhere(
      (e) => e.id == config.opencodeMode,
      orElse: () => CatalogEnumEntry(id: config.opencodeMode!, label: config.opencodeMode!),
    );
    row2.add(m.label);
  }

  return [row1, if (row2.isNotEmpty) row2];
}

/// Hydrate the SessionConfig the chat-header gear-icon pill should show.
///
/// Prefers the canonical spawn-time snapshot persisted on the row
/// (`instanceData['session_config']`) — this surfaces model + thinking/
/// reasoning effort, which the live pill state doesn't track. Falls back
/// to whatever the live state currently is (permission/opencode mode kept
/// up to date mid-chat by `_hydrateControlSettingsFromMessages`) when the
/// column is null — legacy sessions spawned before the column existed.
///
/// Does NOT call `reconcileAgainst(catalog)` because that synthesizes
/// catalog defaults for missing fields — e.g., a session that's running
/// on `default` permission_mode but whose row hasn't yet been PATCHed
/// would be shown as `acceptEdits` (the catalog's old default). For the
/// chat-header gear the truth source is what's stored or what the live
/// state reports; missing fields stay null so the pill renders nothing
/// rather than lying. The new-session picker still uses
/// `SessionConfig.defaultsFor` separately to populate defaults at spawn
/// time — that's the right place for the catalog default.
SessionConfig initialPillConfigFor({
  required Map<dynamic, dynamic>? instanceData,
  required AgentCatalog catalog,
  required String fallbackAgentId,
  required String? livePermissionMode,
  required String? liveOpencodeMode,
}) {
  final stored = instanceData?['session_config'];
  if (stored is Map) {
    final fromStored = SessionConfig.fromJson(Map<String, dynamic>.from(stored));
    return SessionConfig(
      // ALWAYS use the caller's agent (derived from instanceData['agent_type'])
      // — that's the authoritative source. The session_config column's agent
      // field is just a copy from spawn time and may be missing entirely on
      // a row whose first PATCH was a partial update (e.g. Rust bridge sending
      // {model: X} without an agent key) — SessionConfig.fromJson defaults
      // missing agent to 'claude', which would otherwise mis-render the
      // gear pill's dropdowns as Claude's models on a Codex session.
      agent: fallbackAgentId,
      model: fromStored.model,
      thinkingEffort: fromStored.thinkingEffort,
      reasoningEffort: fromStored.reasoningEffort,
      // Live state from the message-scan beats a stale stored value for
      // the mid-chat-editable dimensions (permission/opencode mode), and
      // beats null when the row hasn't been PATCHed yet.
      permissionMode: fromStored.permissionMode ?? livePermissionMode,
      opencodeMode: fromStored.opencodeMode ?? liveOpencodeMode,
    );
  }
  return SessionConfig(
    agent: fallbackAgentId,
    permissionMode: livePermissionMode,
    opencodeMode: liveOpencodeMode,
  );
}

/// Human-readable chip label: "Claude · Sonnet 4.6 · Accept Edits".
String sessionConfigSummary(AgentCatalog catalog, SessionConfig config) {
  final agent = catalog.agentById(config.agent);
  final parts = <String>[];
  parts.add(agent?.label ?? config.agent);

  if (config.model != null && agent?.models != null) {
    final m = agent!.models!.firstWhere(
      (m) => m.id == config.model,
      orElse: () => CatalogModel(id: config.model!, label: config.model!),
    );
    parts.add(m.label);
  }

  if (config.agent == 'opencode' && config.opencodeMode != null) {
    final mode = agent!.modes.firstWhere((e) => e.id == config.opencodeMode, orElse: () => CatalogEnumEntry(id: config.opencodeMode!, label: config.opencodeMode!));
    parts.add(mode.label);
  } else if (config.permissionMode != null && agent?.permissionModes.isNotEmpty == true) {
    final p = agent!.permissionModes.firstWhere((e) => e.id == config.permissionMode, orElse: () => CatalogEnumEntry(id: config.permissionMode!, label: config.permissionMode!));
    parts.add(p.label);
  }

  return parts.join(' · ');
}

/// Baked-in fallback used at cold start when the catalog endpoint is
/// unreachable. Keep in sync with `vicoa-backend/src/shared/agent_catalog.py`.
/// Refresh process and upstream slug discovery: docs/agents/agent-catalog.md.
/// Version 2026-06-14-9.
///
/// **Never delete a model entry, even after upstream retires it.** Spawn-time
/// `session_config` rows persisted on `agent_instances` reference model ids
/// forever (plan plans/session-config-storage.md §3.5). The chat-header pill
/// resolves model labels through this catalog — deleting an entry degrades
/// old-session display to a raw id like `claude-opus-4-7`. When a model is
/// retired, add `deprecated: true` (future field) so the new-session picker
/// hides it while the header label resolution keeps working. No model needs
/// the flag today; this comment is the rule.
const String _agentCatalogFallbackJson = r'''
{
  "version": "2026-09-05-1",
  "min_cli_version": "1.20.0",
  "min_client_version": "0.42.0",
  "agents": [
    {
      "id": "claude",
      "label": "Claude Code",
      "models": [
        {"id": "claude-fable-5", "label": "Fable 5", "default_thinking_effort": "xhigh", "permission_modes": ["auto"]},
        {"id": "claude-opus-5", "label": "Opus 5", "default_thinking_effort": "xhigh", "permission_modes": ["auto"]},
        {"id": "claude-opus-4-8", "label": "Opus 4.8", "default_thinking_effort": "xhigh", "permission_modes": ["auto"]},
        {"id": "claude-opus-4-8[1m]", "label": "Opus 4.8 1M", "default_thinking_effort": "xhigh", "permission_modes": ["auto"]},
        {"id": "claude-opus-4-7", "label": "Opus 4.7", "default_thinking_effort": "xhigh", "permission_modes": ["auto"]},
        {"id": "claude-opus-4-7[1m]", "label": "Opus 4.7 1M", "default_thinking_effort": "xhigh", "permission_modes": ["auto"]},
        {"id": "claude-opus-4-6", "label": "Opus 4.6"},
        {"id": "claude-opus-4-6[1m]", "label": "Opus 4.6 1M"},
        {"id": "claude-sonnet-5", "label": "Sonnet 5", "is_default": true, "permission_modes": ["auto"]},
        {"id": "claude-sonnet-5[1m]", "label": "Sonnet 5 1M", "permission_modes": ["auto"]},
        {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6", "permission_modes": ["auto"]},
        {"id": "claude-sonnet-4-6[1m]", "label": "Sonnet 4.6 1M", "permission_modes": ["auto"]},
        {"id": "claude-haiku-4-5", "label": "Haiku 4.5"}
      ],
      "thinking_efforts": [
        {"id": "max", "label": "Max"},
        {"id": "xhigh", "label": "Extra High"},
        {"id": "high", "label": "High", "is_default": true},
        {"id": "medium", "label": "Medium"},
        {"id": "low", "label": "Low"},
        {"id": "off", "label": "Off"}
      ],
      "permission_modes": [
        {"id": "default", "label": "Default"},
        {"id": "auto", "label": "Auto mode", "opt_in": true, "is_default": true},
        {"id": "acceptEdits", "label": "Accept Edits"},
        {"id": "plan", "label": "Plan"},
        {"id": "bypassPermissions", "label": "Skip permissions (Yolo)"}
      ]
    },
    {
      "id": "codex",
      "label": "Codex",
      "models": [
        {"id": "gpt-5.5", "label": "GPT-5.5", "is_default": true},
        {"id": "gpt-5.4", "label": "GPT-5.4"},
        {"id": "gpt-5.4-mini", "label": "GPT-5.4-Mini"}
      ],
      "reasoning_efforts": [
        {"id": "low", "label": "Low"},
        {"id": "medium", "label": "Medium", "is_default": true},
        {"id": "high", "label": "High"},
        {"id": "xhigh", "label": "Extra High"}
      ],
      "permission_modes": [
        {"id": "default", "label": "Default", "is_default": true},
        {"id": "bypassPermissions", "label": "Full Access"}
      ]
    },
    {
      "id": "opencode",
      "label": "OpenCode",
      "models": [
        {"id": "default", "label": "Default", "is_default": true},
        {"id": "opencode/big-pickle", "label": "OpenCode Zen - big-pickle"}
      ],
      "modes": [
        {"id": "build", "label": "Build", "is_default": true},
        {"id": "plan", "label": "Plan"}
      ]
    },
    {
      "id": "omp",
      "label": "Oh My Pi",
      "models": [
        {"id": "default", "label": "Default", "is_default": true}
      ],
      "thinking_efforts": [
        {"id": "max", "label": "Max"},
        {"id": "xhigh", "label": "Extra High"},
        {"id": "high", "label": "High"},
        {"id": "medium", "label": "Medium", "is_default": true},
        {"id": "low", "label": "Low"},
        {"id": "off", "label": "Off"}
      ],
      "permission_modes": [
        {"id": "default", "label": "Always Ask", "is_default": true},
        {"id": "acceptEdits", "label": "Write Approval"},
        {"id": "bypassPermissions", "label": "Skip permissions (Yolo)"}
      ]
    },
    {
      "id": "pi",
      "label": "Pi",
      "models": [
        {"id": "default", "label": "Default", "is_default": true}
      ],
      "thinking_efforts": [
        {"id": "max", "label": "Max"},
        {"id": "xhigh", "label": "Extra High"},
        {"id": "high", "label": "High"},
        {"id": "medium", "label": "Medium", "is_default": true},
        {"id": "low", "label": "Low"},
        {"id": "off", "label": "Off"}
      ]
    },
    {
      "id": "cursor",
      "label": "Cursor",
      "models": [
        {"id": "auto", "label": "Default", "is_default": true},
        {"id": "composer-2.5", "label": "Composer 2.5"}
      ],
      "permission_modes": [
        {"id": "agent", "label": "Agent", "is_default": true},
        {"id": "plan", "label": "Plan"},
        {"id": "ask", "label": "Ask"}
      ]
    },
    {
      "id": "gemini",
      "label": "Gemini",
      "models": [
        {"id": "auto", "label": "Default", "is_default": true},
        {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite"},
        {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
        {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"}
      ],
      "permission_modes": [
        {"id": "default", "label": "Default", "is_default": true},
        {"id": "autoEdit", "label": "Auto Edit"},
        {"id": "plan", "label": "Plan"},
        {"id": "yolo", "label": "Skip permissions (Yolo)"}
      ]
    },
    {
      "id": "copilot",
      "label": "Copilot",
      "models": [
        {"id": "default", "label": "Default", "is_default": true},
        {"id": "gpt-5-mini", "label": "GPT-5 mini"},
        {"id": "claude-haiku-4.5", "label": "Claude Haiku 4.5"}
      ]
    },
    {
      "id": "kimi",
      "label": "Kimi",
      "models": [
        {"id": "auto", "label": "Default", "is_default": true},
        {"id": "moonshot-ai/kimi-k2.5", "label": "Kimi K2.5"},
        {"id": "moonshot-ai/kimi-k2.6", "label": "Kimi K2.6"},
        {"id": "moonshot-ai/kimi-k2.7-code", "label": "Kimi K2.7 Code"}
      ]
    },
    {
      "id": "hermes",
      "label": "Hermes",
      "models": [
        {"id": "default", "label": "Provider default", "is_default": true}
      ]
    }
  ]
}
''';

AgentCatalog agentCatalogFallback() => AgentCatalog.fromJson(json.decode(_agentCatalogFallbackJson) as Map<String, dynamic>);

/// Return [base] with each agent's model list replaced by the machine's cached
/// real models when present (keyed by agent id, `{agentId: [{id,label}]}`).
/// Agents without a cached entry keep their static catalog defaults. Used so
/// the new-session picker shows a machine's actual models once an agent has
/// run there once (the catalog only ships placeholders for ACP agents, and for
/// Claude it can't know the machine's own custom slugs).
///
/// Keep in sync with `vicoa-web/lib/agent-catalog.ts` `catalogWithCachedModels`.
AgentCatalog catalogWithCachedModels(
    AgentCatalog base, Map<String, List<Map<String, String>>> cachedByAgent) {
  if (cachedByAgent.isEmpty) return base;
  final agents = base.agents.map((a) {
    final cached = cachedByAgent[a.id];
    if (cached == null || cached.isEmpty) return a;
    // A machine reports only `{id, label}` — no capability metadata. Carry the
    // catalog entry's fields over for ids we already know (isDefault,
    // permissionModes, defaultThinkingEffort, …); without this, the opt-in
    // gates see an empty per-model array and silently drop `auto` / `xhigh`
    // from the pickers the moment an agent starts reporting its models —
    // which is what happened when headless Claude began PATCHing
    // `available_models`. Unknown slugs (a user's ANTHROPIC_MODEL) keep the
    // common set only.
    final catalogById = {for (final m in a.models ?? const <CatalogModel>[]) m.id: m};
    final models = cached.map((e) {
      final id = e['id']!;
      final label = e['label'] ?? id;
      final known = catalogById[id];
      if (known == null) return CatalogModel(id: id, label: label);
      return CatalogModel(
        id: known.id,
        label: label.isEmpty ? known.label : label,
        description: known.description,
        isDefault: known.isDefault,
        thinkingEfforts: known.thinkingEfforts,
        permissionModes: known.permissionModes,
        defaultThinkingEffort: known.defaultThinkingEffort,
      );
    }).toList();
    // Keep the agent's "defer to its own model" sentinel (the isDefault
    // catalog entry, e.g. `auto`/`default`) at the top. The cached list is the
    // machine's *real* models and never includes that synthetic id, so without
    // this a stored default would no longer match any entry — the picker would
    // render "—" and the spawn would lose the defer behaviour
    // (toSpawnMetadata skips sending a model for auto/default).
    CatalogModel? sentinel;
    for (final m in a.models ?? const <CatalogModel>[]) {
      if (m.isDefault) {
        sentinel = m;
        break;
      }
    }
    if (sentinel != null && !models.any((m) => m.id == sentinel!.id)) {
      models.insert(0, sentinel);
    }
    return CatalogAgent(
      id: a.id,
      label: a.label,
      models: models,
      thinkingEfforts: a.thinkingEfforts,
      reasoningEfforts: a.reasoningEfforts,
      permissionModes: a.permissionModes,
      modes: a.modes,
    );
  }).toList();
  return AgentCatalog(version: base.version, minCliVersion: base.minCliVersion, minClientVersion: base.minClientVersion, agents: agents);
}
