import { describe, expect, test } from 'vitest';
import { modelListWidthClass, modelSublabel } from './session-config-dropdown';
import { normalizeModelLabel } from '@/lib/agent-catalog';

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
  test('sizes to content only when some entry trails a raw id', () => {
    // A fixed width would truncate the id's tail — the very part that tells
    // two builds sharing a display name apart.
    expect(modelListWidthClass([{ id: 'claude-sonnet-5', label: 'Sonnet 5' }])).toBe('w-56');
    expect(
      modelListWidthClass([
        { id: 'default', label: 'Default' },
        { id: 'anthropic/claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' },
      ]),
    ).toBe('w-auto min-w-56 max-w-[32rem]');
  });

  test('falls back to the narrow default for an absent list', () => {
    expect(modelListWidthClass(null)).toBe('w-56');
    expect(modelListWidthClass([])).toBe('w-56');
  });
});

describe('normalizeModelLabel', () => {
  test('drops a provider suffix an older daemon baked into the label', () => {
    // Daemons up to 1.7.x labelled these "<name> (<provider>)"; the provider
    // now rides in the muted id beside the name, so the suffix stutters. It
    // outlives its daemon because labels are cached per machine and pinned on
    // running sessions.
    expect(
      normalizeModelLabel('anthropic/claude-haiku-4-5', 'Claude Haiku 4.5 (anthropic)'),
    ).toBe('Claude Haiku 4.5');
    expect(normalizeModelLabel('openai/gpt-5.2', 'GPT-5.2 (openai)')).toBe('GPT-5.2');
  });

  test('keeps a parenthetical that is not the provider', () => {
    // Pi genuinely ships this: the moving alias vs the dated build.
    expect(
      normalizeModelLabel('anthropic/claude-haiku-4-5', 'Claude Haiku 4.5 (latest)'),
    ).toBe('Claude Haiku 4.5 (latest)');
    expect(normalizeModelLabel('anthropic/x', 'X (preview)')).toBe('X (preview)');
  });

  test('leaves unqualified ids and clean labels alone', () => {
    expect(normalizeModelLabel('claude-sonnet-5', 'Sonnet 5 (anthropic)')).toBe(
      'Sonnet 5 (anthropic)',
    );
    expect(normalizeModelLabel('anthropic/claude-haiku-4-5', 'Claude Haiku 4.5')).toBe(
      'Claude Haiku 4.5',
    );
  });

  test('only strips a trailing suffix, never a mid-label match', () => {
    expect(normalizeModelLabel('anthropic/x', '(anthropic) X')).toBe('(anthropic) X');
  });
});
