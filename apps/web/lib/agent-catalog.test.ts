import { describe, test, expect } from 'vitest';
import {
  agentPickerLabel,
  catalogWithCachedModels,
  customAgentLabel,
  defaultsFor,
  reconcileAgainst,
  toSpawnMetadata,
  AGENT_CATALOG_FALLBACK,
} from './agent-catalog';

describe('agentPickerLabel', () => {
  test('every agent renders with its plain label (no "(Beta)" suffix)', () => {
    expect(agentPickerLabel('claude', 'Claude Code')).toBe('Claude Code');
    expect(agentPickerLabel('codex', 'Codex')).toBe('Codex');
    expect(agentPickerLabel('gemini', 'Gemini')).toBe('Gemini');
    expect(agentPickerLabel('copilot', 'Copilot')).toBe('Copilot');
    expect(agentPickerLabel('opencode', 'OpenCode')).toBe('OpenCode');
  });
});

describe('catalogWithCachedModels', () => {
  test('replaces an agent\'s models with the cached list (keeping the defer sentinel), others untouched', () => {
    const base = AGENT_CATALOG_FALLBACK;
    const merged = catalogWithCachedModels(base, {
      cursor: [
        { id: 'composer-2.5[fast=true]', label: 'composer-2.5' },
        { id: 'gpt-5.4[context=272k]', label: 'gpt-5.4' },
      ],
    });
    const cursor = merged.agents.find((a) => a.id === 'cursor');
    // The is_default catalog sentinel (`auto`) stays at the top so a stored
    // default remains selectable once the real models load.
    expect(cursor?.models?.map((m) => m.id)).toEqual([
      'auto',
      'composer-2.5[fast=true]',
      'gpt-5.4[context=272k]',
    ]);
    expect(cursor?.models?.find((m) => m.id === 'auto')?.is_default).toBe(true);
    // An agent without a cached entry keeps its catalog models.
    const claude = merged.agents.find((a) => a.id === 'claude');
    const baseClaude = base.agents.find((a) => a.id === 'claude');
    expect(claude?.models?.map((m) => m.id)).toEqual(baseClaude?.models?.map((m) => m.id));
  });

  test('does not duplicate the sentinel when the cached list already includes it', () => {
    const merged = catalogWithCachedModels(AGENT_CATALOG_FALLBACK, {
      cursor: [
        { id: 'auto', label: 'Default' },
        { id: 'composer-2.5', label: 'composer-2.5' },
      ],
    });
    const cursor = merged.agents.find((a) => a.id === 'cursor');
    expect(cursor?.models?.map((m) => m.id)).toEqual(['auto', 'composer-2.5']);
  });

  test('keeps per-model capability metadata for ids the catalog knows', () => {
    // Headless Claude reports its real model list (catalog + the machine's
    // custom slugs). The cached entries carry only {id, label}; dropping the
    // catalog's per-model fields would lose the default model and the Opus
    // xhigh thinking default from the new-session picker.
    const merged = catalogWithCachedModels(AGENT_CATALOG_FALLBACK, {
      claude: [
        { id: 'claude-sonnet-5', label: 'Sonnet 5' },
        { id: 'claude-opus-4-8', label: 'Opus 4.8' },
        { id: 'my-org/custom-sonnet', label: 'my-org/custom-sonnet' },
      ],
    });
    const models = merged.agents.find((a) => a.id === 'claude')?.models;
    expect(models?.map((m) => m.id)).toEqual([
      'claude-sonnet-5',
      'claude-opus-4-8',
      'my-org/custom-sonnet',
    ]);
    expect(models?.find((m) => m.id === 'claude-sonnet-5')?.is_default).toBe(true);
    expect(models?.find((m) => m.id === 'claude-opus-4-8')?.default_thinking_effort).toBe('xhigh');
    // A slug the catalog has never heard of gets no per-model extras.
    expect(models?.find((m) => m.id === 'my-org/custom-sonnet')?.default_thinking_effort).toBeUndefined();
  });

  test('a Claude model the catalog predates still gets auto mode', () => {
    // `auto` is common, not opt_in, so a model shipped after this build (only
    // known from the machine's reported list) offers and defaults to it.
    const merged = catalogWithCachedModels(AGENT_CATALOG_FALLBACK, {
      claude: [{ id: 'claude-opus-9', label: 'Opus 9' }],
    });
    expect(reconcileAgainst({ agent: 'claude', model: 'claude-opus-9' }, merged).permission_mode).toBe('auto');
    expect(reconcileAgainst({ agent: 'claude', model: 'claude-opus-9', permission_mode: 'default' }, merged).permission_mode).toBe('default');
  });

  test('empty cache returns the base catalog unchanged', () => {
    expect(catalogWithCachedModels(AGENT_CATALOG_FALLBACK, {})).toBe(AGENT_CATALOG_FALLBACK);
  });

  test('synthesizes an entry for a cached agent the static catalog cannot describe', () => {
    // A catalog-added agent (Qwen Code) that was probed or ran once: the cache
    // has its models and modes, the daemon's agent_labels has its name. Before
    // this the picker rendered no model/mode dropdown at all for it.
    const merged = catalogWithCachedModels(
      AGENT_CATALOG_FALLBACK,
      { qwen: [{ id: 'qwen3-coder-plus', label: 'Qwen3 Coder Plus' }, { id: 'qwen3-max', label: 'Qwen3 Max' }] },
      {
        modes: { qwen: [{ id: 'default', label: 'Default' }, { id: 'plan', label: 'Plan' }] },
        labels: { qwen: 'Qwen Code' },
      },
    );
    expect(merged.agents.length).toBe(AGENT_CATALOG_FALLBACK.agents.length + 1);
    const qwen = merged.agents[merged.agents.length - 1];
    expect(qwen.id).toBe('qwen');
    expect(qwen.label).toBe('Qwen Code');
    // `default` sentinel first (never sent as a model), then the real list.
    expect(qwen.models?.map((m) => m.id)).toEqual(['default', 'qwen3-coder-plus', 'qwen3-max']);
    expect(qwen.models?.[0].is_default).toBe(true);
    // Cached modes become permission_modes — the field the generic ACP spawn
    // path forwards — with the agent's first mode as its default.
    expect(qwen.permission_modes).toEqual([
      { id: 'default', label: 'Default', is_default: true },
      { id: 'plan', label: 'Plan' },
    ]);
    expect(qwen.thinking_efforts).toBeUndefined();
    expect(qwen.reasoning_efforts).toBeUndefined();
    expect(qwen.modes).toBeUndefined();
    // Static agents are untouched.
    expect(merged.agents.slice(0, -1).map((a) => a.id)).toEqual(AGENT_CATALOG_FALLBACK.agents.map((a) => a.id));
  });

  test('synthesized entry falls back to a derived label and skips modes when none are cached', () => {
    const merged = catalogWithCachedModels(AGENT_CATALOG_FALLBACK, {
      'kimi-work': [{ id: 'default', label: 'Default' }, { id: 'moonshot-ai/kimi-k2.6', label: 'Kimi K2.6' }],
    });
    const kimi = merged.agents.find((a) => a.id === 'kimi-work');
    expect(kimi?.label).toBe('Kimi Work');
    // A cached `default` is not duplicated behind the sentinel.
    expect(kimi?.models?.map((m) => m.id)).toEqual(['default', 'moonshot-ai/kimi-k2.6']);
    expect(kimi?.permission_modes).toBeUndefined();
  });

  test('synthesized entry drives defaultsFor / reconcileAgainst / toSpawnMetadata', () => {
    const merged = catalogWithCachedModels(
      AGENT_CATALOG_FALLBACK,
      { qwen: [{ id: 'qwen3-max', label: 'Qwen3 Max' }] },
      { modes: { qwen: [{ id: 'default', label: 'Default' }, { id: 'plan', label: 'Plan' }] } },
    );
    const defaults = defaultsFor(merged, 'qwen');
    expect(defaults).toEqual({
      agent: 'qwen',
      model: 'default',
      thinking_effort: undefined,
      reasoning_effort: undefined,
      permission_mode: 'default',
      opencode_mode: undefined,
    });
    // The sentinel is never sent as a model; a real pick + mode are.
    expect(toSpawnMetadata(defaults)).toEqual({ permission_mode: 'default' });
    expect(toSpawnMetadata({ agent: 'qwen', model: 'qwen3-max', permission_mode: 'plan' })).toEqual({
      model: 'qwen3-max',
      permission_mode: 'plan',
    });
    // A config saved before the cache existed (model undefined) reconciles to
    // the defaults; a stale mode snaps back too.
    expect(reconcileAgainst({ agent: 'qwen', permission_mode: 'yolo' }, merged)).toMatchObject({
      model: 'default',
      permission_mode: 'default',
    });
  });

  test('cached modes fill in a static agent that has no curated mode list, but not one that does', () => {
    const merged = catalogWithCachedModels(
      AGENT_CATALOG_FALLBACK,
      { copilot: [{ id: 'gpt-5-mini', label: 'GPT-5 mini' }] },
      {
        modes: {
          copilot: [{ id: 'agent', label: 'Agent' }, { id: 'plan', label: 'Plan' }],
          cursor: [{ id: 'weird', label: 'Weird' }],
        },
      },
    );
    const copilot = merged.agents.find((a) => a.id === 'copilot');
    expect(copilot?.permission_modes?.map((m) => m.id)).toEqual(['agent', 'plan']);
    expect(copilot?.models?.map((m) => m.id)).toEqual(['default', 'gpt-5-mini']);
    // Cursor ships a verified static list; the cache doesn't override it. And
    // an agent with cached modes but no cached models still gets the modes.
    const cursor = merged.agents.find((a) => a.id === 'cursor');
    expect(cursor?.permission_modes).toEqual(AGENT_CATALOG_FALLBACK.agents.find((a) => a.id === 'cursor')?.permission_modes);
    const onlyModes = catalogWithCachedModels(
      AGENT_CATALOG_FALLBACK,
      { claude: [{ id: 'claude-sonnet-5', label: 'Sonnet 5' }] },
      { modes: { hermes: [{ id: 'default', label: 'Default' }] } },
    );
    expect(onlyModes.agents.find((a) => a.id === 'hermes')?.permission_modes?.map((m) => m.id)).toEqual(['default']);
  });
});

describe('customAgentLabel', () => {
  test('makes a readable name out of a provider id', () => {
    expect(customAgentLabel('kimi-work')).toBe('Kimi Work');
    expect(customAgentLabel('goose')).toBe('Goose');
    expect(customAgentLabel('gemini-nightly-2')).toBe('Gemini Nightly 2');
  });

  test('survives ids with stray separators', () => {
    expect(customAgentLabel('a--b')).toBe('A B');
    expect(customAgentLabel('')).toBe('');
  });
});
