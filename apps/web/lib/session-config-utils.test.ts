import { describe, test, expect } from 'vitest';
import {
  buildModelControlMessage,
  buildEffortControlMessage,
  extractSessionConfigFromInstance,
} from './session-config-utils';

describe('buildModelControlMessage', () => {
  test('includes human-readable prefix with model slug', () => {
    const msg = buildModelControlMessage('claude-sonnet-4-6');
    expect(msg).toContain('claude-sonnet-4-6');
    expect(msg.startsWith('Change the model')).toBe(true);
  });

  test('embeds control JSON with setting=model', () => {
    const msg = buildModelControlMessage('claude-opus-4-7');
    expect(msg).toContain('"type":"control"');
    expect(msg).toContain('"setting":"model"');
    expect(msg).toContain('"value":"claude-opus-4-7"');
  });

  test('works for codex model slugs', () => {
    const msg = buildModelControlMessage('gpt-5.5');
    expect(msg).toContain('"value":"gpt-5.5"');
  });
});

describe('buildEffortControlMessage', () => {
  test('embeds control JSON with setting=effort', () => {
    const msg = buildEffortControlMessage('high');
    expect(msg).toContain('"type":"control"');
    expect(msg).toContain('"setting":"effort"');
    expect(msg).toContain('"value":"high"');
  });

  test('works for xhigh effort', () => {
    const msg = buildEffortControlMessage('xhigh');
    expect(msg).toContain('"value":"xhigh"');
  });
});

describe('extractSessionConfigFromInstance', () => {
  test('reads model from session_config', () => {
    const result = extractSessionConfigFromInstance({ session_config: { agent: 'claude', model: 'claude-opus-4-7' } });
    expect(result.model).toBe('claude-opus-4-7');
  });

  test('reads thinking_effort as effort for claude', () => {
    const result = extractSessionConfigFromInstance({ session_config: { agent: 'claude', thinking_effort: 'xhigh' } });
    expect(result.effort).toBe('xhigh');
  });

  test('reads reasoning_effort as effort for codex', () => {
    const result = extractSessionConfigFromInstance({ session_config: { agent: 'codex', reasoning_effort: 'high' } });
    expect(result.effort).toBe('high');
  });

  test('prefers thinking_effort over reasoning_effort when both present', () => {
    const result = extractSessionConfigFromInstance({ session_config: { thinking_effort: 'low', reasoning_effort: 'high' } });
    expect(result.effort).toBe('low');
  });

  test('reads permission_mode', () => {
    const result = extractSessionConfigFromInstance({ session_config: { permission_mode: 'acceptEdits' } });
    expect(result.permissionMode).toBe('acceptEdits');
  });

  test('reads opencode_mode', () => {
    const result = extractSessionConfigFromInstance({ session_config: { opencode_mode: 'plan' } });
    expect(result.opencodeMode).toBe('plan');
  });

  test('reads agent', () => {
    const result = extractSessionConfigFromInstance({ session_config: { agent: 'codex' } });
    expect(result.agent).toBe('codex');
  });

  test('returns all nulls when session_config is null', () => {
    const result = extractSessionConfigFromInstance({ session_config: null });
    expect(result.model).toBeNull();
    expect(result.effort).toBeNull();
    expect(result.permissionMode).toBeNull();
    expect(result.opencodeMode).toBeNull();
    expect(result.agent).toBeNull();
  });

  test('returns all nulls when session_config is absent', () => {
    const result = extractSessionConfigFromInstance({});
    expect(result.model).toBeNull();
    expect(result.effort).toBeNull();
  });

  test('returns all nulls when instance is null', () => {
    const result = extractSessionConfigFromInstance(null);
    expect(result.model).toBeNull();
    expect(result.effort).toBeNull();
  });

  test('ignores non-string values in session_config', () => {
    const result = extractSessionConfigFromInstance({ session_config: { model: 42, thinking_effort: true } });
    expect(result.model).toBeNull();
    expect(result.effort).toBeNull();
  });
});
