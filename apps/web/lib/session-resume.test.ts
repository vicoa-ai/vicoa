import { describe, expect, it } from 'vitest';

import { beforeEach } from 'vitest';

import {
  agentSessionHandle,
  clearResumeGrace,
  isWithinResumeGrace,
  markResumed,
  canResumeSession,
  expandProjectPath,
  resumeAgentSlug,
  resumeBlockedMessage,
  resumeBlockedReason,
  type ResumableInstance,
} from './session-resume';

const base: ResumableInstance = {
  id: 'inst-1',
  status: 'COMPLETED',
  machine_id: 'machine-1',
  project: '~/projects/vicoa',
  home_dir: '/Users/dev',
  agent_type_name: 'Claude Code',
  instance_metadata: null,
};

const inst = (o: Partial<ResumableInstance> = {}): ResumableInstance => ({
  ...base,
  ...o,
});

describe('canResumeSession', () => {
  it('offers resume for a stopped session', () => {
    expect(canResumeSession(inst(), 'agent_stopped')).toBe(true);
  });

  it('still offers it while the computer is offline', () => {
    // Shown disabled with a reason. Hiding it would read as "this feature
    // doesn't exist" rather than "not right now".
    expect(canResumeSession(inst(), 'machine_offline')).toBe(true);
  });

  it('does not offer resume for a running session', () => {
    // Non-closed status: the session is genuinely working, so resuming would
    // spawn a second agent against the same row. (A closed session is
    // resumable regardless of liveness — see the "archived sessions" block.)
    expect(canResumeSession(inst({ status: 'ACTIVE' }), 'live')).toBe(false);
    expect(canResumeSession(inst({ status: 'ACTIVE' }), 'reconnecting')).toBe(false);
  });

  it('refuses a deleted session', () => {
    // Delete hard-deletes the messages, so there is no transcript to continue.
    expect(canResumeSession(inst({ status: 'DELETED' }), 'agent_stopped')).toBe(
      false
    );
  });

  it('refuses a session with no machine linkage', () => {
    // Legacy TUI-started rows: no daemon to address the relaunch to.
    expect(canResumeSession(inst({ machine_id: null }), 'agent_stopped')).toBe(
      false
    );
  });

  it('refuses a session with no recorded folder', () => {
    expect(canResumeSession(inst({ project: null }), 'agent_stopped')).toBe(false);
  });
});

describe('resumeBlockedReason', () => {
  it('is null when resume can proceed', () => {
    expect(resumeBlockedReason(inst(), 'agent_stopped')).toBeNull();
  });

  it.each([
    [{ status: 'DELETED' }, 'agent_stopped', 'deleted'],
    [{ machine_id: null }, 'agent_stopped', 'no-machine'],
    [{ project: null }, 'agent_stopped', 'no-directory'],
    [{}, 'machine_offline', 'machine-offline'],
    [{ status: 'ACTIVE' }, 'live', 'already-running'],
  ] as const)('reports %o / %s as %s', (patch, live, expected) => {
    expect(resumeBlockedReason(inst(patch), live)).toBe(expected);
  });

  it('gives every reason user-facing copy', () => {
    for (const reason of [
      'deleted',
      'no-machine',
      'no-directory',
      'machine-offline',
      'already-running',
    ] as const) {
      expect(resumeBlockedMessage(reason).length).toBeGreaterThan(0);
    }
  });
});

describe('agentSessionHandle', () => {
  it('finds the codex thread id', () => {
    expect(
      agentSessionHandle(inst({ instance_metadata: { codex_thread_id: 'th-1' } }))
    ).toBe('th-1');
  });

  it('finds the ACP session id', () => {
    expect(
      agentSessionHandle(inst({ instance_metadata: { acp_session_id: 'ses-1' } }))
    ).toBe('ses-1');
  });

  it('is undefined when the previous run recorded none', () => {
    // Normal for older sessions and for agents that can't reload — the
    // relaunch still happens, just without prior context.
    expect(agentSessionHandle(inst())).toBeUndefined();
    expect(agentSessionHandle(inst({ instance_metadata: {} }))).toBeUndefined();
  });
});

describe('resumeAgentSlug', () => {
  it('prefers the catalog id recorded at spawn', () => {
    // session_config.agent is what the daemon validates against.
    expect(
      resumeAgentSlug(
        inst({ session_config: { agent: 'opencode' }, agent_type_name: 'My Agent' })
      )
    ).toBe('opencode');
  });

  it('does not fall back to claude for an unrecognised display name', () => {
    // The bug this replaced: agent_type_name is the UserAgent row's name and is
    // user-editable, so every agent whose name lacked a known keyword silently
    // resolved to "claude" and launched the wrong wrapper.
    expect(
      resumeAgentSlug(
        inst({ session_config: { agent: 'cursor' }, agent_type_name: 'Renamed By User' })
      )
    ).toBe('cursor');
  });

  it.each([
    ['Claude Code', 'claude'],
    ['Codex', 'codex'],
    ['OpenCode', 'opencode'],
    ['Cursor', 'cursor'],
    ['Gemini', 'gemini'],
    [null, 'claude'],
    ['Something Unknown', 'claude'],
  ] as const)('falls back to the display name: %s -> %s', (name, expected) => {
    expect(
      resumeAgentSlug(inst({ agent_type_name: name, session_config: null }))
    ).toBe(expected);
  });
});

describe('expandProjectPath', () => {
  it('expands a tilde against the recorded home directory', () => {
    // The daemon needs a real path; project is stored tilde-collapsed.
    expect(expandProjectPath('~/projects/vicoa', '/Users/dev')).toBe(
      '/Users/dev/projects/vicoa'
    );
  });

  it('leaves absolute paths alone', () => {
    expect(expandProjectPath('/srv/app', '/Users/dev')).toBe('/srv/app');
  });

  it('leaves the tilde when no home directory was recorded', () => {
    expect(expandProjectPath('~/projects/vicoa', null)).toBe('~/projects/vicoa');
  });

  it('does not double the separator', () => {
    expect(expandProjectPath('~/x', '/Users/dev/')).toBe('/Users/dev/x');
  });
});


describe('resume grace', () => {
  beforeEach(() => clearResumeGrace());

  it('is false for an instance that was never resumed', () => {
    expect(isWithinResumeGrace('inst-1')).toBe(false);
    expect(isWithinResumeGrace(null)).toBe(false);
  });

  it('holds right after a resume', () => {
    // Covers the sidebar path: Resume is clicked while the chat page isn't
    // mounted, and the page must still know on arrival — otherwise the
    // composer stays locked until a manual refresh.
    markResumed('inst-1', 1_000);
    expect(isWithinResumeGrace('inst-1', 1_000)).toBe(true);
    expect(isWithinResumeGrace('inst-1', 1_000 + 60_000)).toBe(true);
  });

  it('expires once the agent has had time to heartbeat', () => {
    markResumed('inst-1', 1_000);
    expect(isWithinResumeGrace('inst-1', 1_000 + 200_000)).toBe(false);
  });

  it('does not leak across instances', () => {
    markResumed('inst-1', 1_000);
    expect(isWithinResumeGrace('inst-2', 1_000)).toBe(false);
  });
});

describe('archived sessions', () => {
  const archived = (status: string) => inst({ status });

  it.each(['COMPLETED', 'FAILED', 'KILLED', 'DISCONNECTED'])(
    'offers Resume immediately for a %s session',
    (status) => {
      // The heartbeat can linger for the whole online threshold while the
      // agent shuts down. Waiting it out made Resume appear a minute or two
      // after archiving, which reads as the button being broken.
      expect(canResumeSession(archived(status), 'live')).toBe(true);
      expect(resumeBlockedReason(archived(status), 'live')).toBeNull();
    }
  );

  it('still refuses a deleted session', () => {
    expect(canResumeSession(archived('DELETED'), 'agent_stopped')).toBe(false);
  });

  it('still reports an offline computer for an archived session', () => {
    expect(resumeBlockedReason(archived('COMPLETED'), 'machine_offline')).toBe(
      'machine-offline'
    );
  });

  it('keeps the already-running guard for a non-closed session', () => {
    expect(resumeBlockedReason(inst({ status: 'ACTIVE' }), 'live')).toBe(
      'already-running'
    );
  });
});
