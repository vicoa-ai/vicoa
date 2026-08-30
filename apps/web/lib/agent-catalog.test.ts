import { describe, test, expect } from 'vitest';
import { agentPickerLabel, catalogWithCachedModels, AGENT_CATALOG_FALLBACK } from './agent-catalog';

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
    // catalog's per-model arrays would hide the `auto` permission mode and the
    // Opus xhigh thinking default from the new-session picker.
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
    expect(models?.find((m) => m.id === 'claude-sonnet-5')?.permission_modes).toEqual(['auto']);
    expect(models?.find((m) => m.id === 'claude-sonnet-5')?.is_default).toBe(true);
    expect(models?.find((m) => m.id === 'claude-opus-4-8')?.default_thinking_effort).toBe('xhigh');
    // A slug the catalog has never heard of gets the common set only.
    expect(models?.find((m) => m.id === 'my-org/custom-sonnet')?.permission_modes).toBeUndefined();
  });

  test('empty cache returns the base catalog unchanged', () => {
    expect(catalogWithCachedModels(AGENT_CATALOG_FALLBACK, {})).toBe(AGENT_CATALOG_FALLBACK);
  });
});
