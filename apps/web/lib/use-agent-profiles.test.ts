import { describe, expect, it } from 'vitest';

import type { AgentProfile } from '@/lib/backend-api';
import { agentProfileBlockedReason } from './use-agent-profiles';

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

function machine(capabilities?: unknown) {
  return { metadata: capabilities === undefined ? {} : { capabilities } };
}

describe('agentProfileBlockedReason', () => {
  it('allows instructions on a daemon that advertises the capability', () => {
    expect(
      agentProfileBlockedReason(profile(), machine(['worktree', 'system-prompt'])),
    ).toBeNull();
  });

  it('blocks instructions on a daemon that does not, which would drop them silently', () => {
    expect(agentProfileBlockedReason(profile(), machine(['worktree']))).toContain(
      'Update Vicoa',
    );
  });

  it('never gates a plain model/config preset — any daemon can carry that', () => {
    for (const systemPrompt of [null, '', '   ']) {
      expect(
        agentProfileBlockedReason(profile({ system_prompt: systemPrompt }), machine([])),
      ).toBeNull();
    }
  });

  it('fails closed on missing or malformed capability metadata', () => {
    // A nudge to update costs one click; failing open costs an agent that
    // silently ignores its instructions — much harder to diagnose.
    expect(agentProfileBlockedReason(profile(), undefined)).toContain('Update Vicoa');
    expect(agentProfileBlockedReason(profile(), null)).toContain('Update Vicoa');
    expect(agentProfileBlockedReason(profile(), machine())).toContain('Update Vicoa');
    expect(agentProfileBlockedReason(profile(), machine('system-prompt'))).toContain(
      'Update Vicoa',
    );
    expect(agentProfileBlockedReason(profile(), { metadata: null })).toContain(
      'Update Vicoa',
    );
  });
});
