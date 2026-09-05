import { normalizeModelLabel } from '@/lib/agent-catalog';

export interface SessionConfigSnapshot {
  agent: string | null;
  model: string | null;
  effort: string | null;
  permissionMode: string | null;
  opencodeMode: string | null;
}

export function buildModelControlMessage(slug: string): string {
  const control = JSON.stringify({ type: 'control', setting: 'model', value: slug });
  return `Change the model to ${slug}. ${control}`;
}

export function buildEffortControlMessage(slug: string): string {
  const control = JSON.stringify({ type: 'control', setting: 'effort', value: slug });
  return `Change the effort to ${slug}. ${control}`;
}

export function extractSessionConfigFromInstance(
  instance: { session_config?: Record<string, unknown> | null } | null,
): SessionConfigSnapshot {
  const sc = instance?.session_config;
  if (!sc) return { agent: null, model: null, effort: null, permissionMode: null, opencodeMode: null };

  const agent = typeof sc.agent === 'string' ? sc.agent : null;
  const model = typeof sc.model === 'string' ? sc.model : null;
  const permissionMode = typeof sc.permission_mode === 'string' ? sc.permission_mode : null;
  const opencodeMode = typeof sc.opencode_mode === 'string' ? sc.opencode_mode : null;

  let effort: string | null = null;
  if (typeof sc.thinking_effort === 'string') effort = sc.thinking_effort;
  else if (typeof sc.reasoning_effort === 'string') effort = sc.reasoning_effort;

  return { agent, model, effort, permissionMode, opencodeMode };
}

/**
 * Live, switchable models/modes an ACP agent (cursor / gemini / copilot / kimi
 * / …) advertised onto `session_config` via its `session/new` response — the
 * same `available_models` / `available_modes` lists the mobile app reads
 * (`agent_chat_model.dart` `acpAvailable*`). Lets the web gear show a real
 * config panel for agents the static catalog doesn't cover.
 */
export interface AcpControlsSnapshot {
  models: { id: string; label: string }[];
  modes: { value: string; label: string }[];
  currentModel: string | null;
  currentMode: string | null;
}

function parseEntryList(raw: unknown): { id: string; label: string }[] {
  if (!Array.isArray(raw)) return [];
  const out: { id: string; label: string }[] = [];
  for (const e of raw) {
    if (e && typeof e === 'object' && (e as { id?: unknown }).id != null) {
      const id = String((e as { id: unknown }).id);
      const label = String((e as { label?: unknown }).label ?? id);
      // A running session pins whatever its daemon reported at bring-up, so an
      // older daemon's `(provider)` suffix persists for that session's whole
      // life. Strip it here rather than waiting for a restart.
      out.push({ id, label: normalizeModelLabel(id, label) });
    }
  }
  return out;
}

export function extractAcpControlsFromInstance(
  instance: { session_config?: Record<string, unknown> | null } | null,
): AcpControlsSnapshot {
  const sc = instance?.session_config;
  if (!sc) return { models: [], modes: [], currentModel: null, currentMode: null };

  const models = parseEntryList(sc.available_models);
  const modes = parseEntryList(sc.available_modes).map((e) => ({ value: e.id, label: e.label }));
  const currentModel =
    typeof sc.current_model === 'string' ? sc.current_model
      : typeof sc.model === 'string' ? sc.model
      : null;
  const currentMode =
    typeof sc.current_mode === 'string' ? sc.current_mode
      : typeof sc.permission_mode === 'string' ? sc.permission_mode
      : null;

  return { models, modes, currentModel, currentMode };
}
