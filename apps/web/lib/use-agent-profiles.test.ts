import { describe, expect, it } from 'vitest';

import type { AgentProfile } from '@/lib/backend-api';
import {
  MIN_DAEMON_VERSION_FOR_SYSTEM_PROMPT,
  agentProfileBlockedReason,
} from './use-agent-profiles';

function profile(overrides: Partial<AgentProfile> = {}): AgentProfile {
  return {
    id: 'p1',
    name: 'Refactorer',
    description: null,
    avatar_image_uri: null,
    avatar_source: null,
    color: null,
    emoji: null,
    agent: 'claude',
    config: { agent: 'claude' },
    system_prompt: 'Refactor ruthlessly.',
    default_machine_id: null,
    default_project_id: null,
    position: 0,
    is_archived: false,
    created_at: '2026-09-09T00:00:00Z',
    updated_at: '2026-09-09T00:00:00Z',
    ...overrides,
  };
}

describe('agentProfileBlockedReason', () => {
  it('allows a profile with instructions on a new enough daemon', () => {
    expect(
      agentProfileBlockedReason(profile(), MIN_DAEMON_VERSION_FOR_SYSTEM_PROMPT),
    ).toBeNull();
    expect(agentProfileBlockedReason(profile(), '1.8.0')).toBeNull();
    expect(agentProfileBlockedReason(profile(), '2.0.0')).toBeNull();
  });

  it('blocks instructions on an older daemon, which would drop them silently', () => {
    expect(agentProfileBlockedReason(profile(), '1.7.19')).toContain('Update Vicoa');
    expect(agentProfileBlockedReason(profile(), '1.6.0')).toContain('Update Vicoa');
  });

  it('never gates a plain model/config preset — any daemon can carry that', () => {
    for (const systemPrompt of [null, '', '   ']) {
      expect(agentProfileBlockedReason(profile({ system_prompt: systemPrompt }), '1.0.0')).toBeNull();
    }
  });

  it('fails closed on an unknown or unparseable version', () => {
    // A nudge to update costs the user one click; failing open costs them an
    // agent that silently ignores its instructions.
    expect(agentProfileBlockedReason(profile(), undefined)).toContain('Update Vicoa');
    expect(agentProfileBlockedReason(profile(), null)).toContain('Update Vicoa');
    expect(agentProfileBlockedReason(profile(), '')).toContain('Update Vicoa');
    expect(agentProfileBlockedReason(profile(), 'dev')).toContain('Update Vicoa');
  });

  it('compares numerically, not lexically', () => {
    // "1.7.9" > "1.7.20" as strings; the whole gate would invert.
    expect(agentProfileBlockedReason(profile(), '1.7.9')).toContain('Update Vicoa');
    expect(agentProfileBlockedReason(profile(), '1.10.0')).toBeNull();
  });

  it('treats a shorter version as zero-padded', () => {
    expect(agentProfileBlockedReason(profile(), '1.8')).toBeNull();
    expect(agentProfileBlockedReason(profile(), '1.7')).toContain('Update Vicoa');
  });
});
