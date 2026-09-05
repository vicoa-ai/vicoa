import { describe, expect, test } from 'vitest';
import { modelListWidthClass, modelSublabel } from './session-config-dropdown';

describe('modelSublabel', () => {
  test('shows the raw id for provider-qualified models', () => {
    // Pi / Oh My Pi / OpenCode / Kimi front many providers, and one machine
    // routinely offers several builds under one friendly name — so the label
    // alone cannot be picked from.
    expect(
      modelSublabel({ id: 'anthropic/claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' }),
    ).toBe('anthropic/claude-haiku-4-5-20251001');
    expect(modelSublabel({ id: 'openai/gpt-5.2', label: 'GPT-5.2' })).toBe('openai/gpt-5.2');
    expect(modelSublabel({ id: 'moonshot-ai/kimi-k2.5', label: 'Kimi K2.5' })).toBe(
      'moonshot-ai/kimi-k2.5',
    );
  });

  test('shows the raw id for bracketed variants', () => {
    // Cursor distinguishes builds this way; the label drops the distinction.
    expect(modelSublabel({ id: 'gpt-5.4[context=272k]', label: 'gpt-5.4' })).toBe(
      'gpt-5.4[context=272k]',
    );
  });

  test('stays quiet for single-provider agents whose id follows the label', () => {
    // Showing "claude-sonnet-5" under "Sonnet 5" is noise, not information.
    expect(modelSublabel({ id: 'claude-sonnet-5', label: 'Sonnet 5' })).toBeNull();
    expect(modelSublabel({ id: 'gpt-5.5', label: 'GPT-5.5' })).toBeNull();
    expect(modelSublabel({ id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' })).toBeNull();
  });

  test('stays quiet for the defer-to-the-agent sentinel', () => {
    expect(modelSublabel({ id: 'default', label: 'Default' })).toBeNull();
    expect(modelSublabel({ id: 'auto', label: 'Default' })).toBeNull();
  });

  test('never repeats a label that is already the id', () => {
    expect(modelSublabel({ id: 'anthropic/x', label: 'anthropic/x' })).toBeNull();
  });
});

describe('modelListWidthClass', () => {
  test('widens only when some entry needs a second line', () => {
    expect(modelListWidthClass([{ id: 'claude-sonnet-5', label: 'Sonnet 5' }])).toBe('w-56');
    expect(
      modelListWidthClass([
        { id: 'default', label: 'Default' },
        { id: 'anthropic/claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' },
      ]),
    ).toBe('w-80');
  });

  test('falls back to the narrow default for an absent list', () => {
    expect(modelListWidthClass(null)).toBe('w-56');
    expect(modelListWidthClass([])).toBe('w-56');
  });
});
