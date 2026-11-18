import { describe, expect, it, vi } from 'vitest';

import { beforeEach } from 'vitest';

const callRpc = vi.fn();
vi.mock('@/lib/ws-client', () => ({ getWsClient: () => ({ callRpc }) }));

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
  resumeOnSendPlaceholder,
  resumeSession,
  resumeSpawnMetadata,
  shouldResumeOnSend,
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

describe('resumeSpawnMetadata', () => {
  it('rebuilds the daemon metadata from the stored config so resume keeps model/effort/mode', () => {
    // The bug this fixes: resume sent no metadata, so the daemon fell back to
    // permission mode `default` — an `auto` session came back as `default`.
    expect(
      resumeSpawnMetadata(
        inst({
          session_config: {
            agent: 'claude',
            model: 'claude-opus-5',
            thinking_effort: 'xhigh',
            permission_mode: 'auto',
          },
        })
      )
    ).toEqual({
      model: 'claude-opus-5',
      thinking_effort: 'xhigh',
      // Dual-written for old daemons alongside thinking_effort.
      enable_thinking: true,
      permission_mode: 'auto',
    });
  });

  it('maps codex reasoning_effort', () => {
    expect(
      resumeSpawnMetadata(
        inst({
          agent_type_name: 'Codex',
          session_config: {
            agent: 'codex',
            model: 'gpt-5.5',
            reasoning_effort: 'high',
            permission_mode: 'default',
          },
        })
      )
    ).toEqual({ model: 'gpt-5.5', reasoning_effort: 'high', permission_mode: 'default' });
  });

  it('is empty for a legacy row with no stored config (daemon keeps its fallback)', () => {
    expect(resumeSpawnMetadata(inst({ session_config: null }))).toEqual({});
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

describe('resumeSession with a prompt (automation run in a session)', () => {
  beforeEach(() => {
    callRpc.mockReset();
    clearResumeGrace();
  });

  it('carries the prompt as the launch prompt', async () => {
    callRpc.mockResolvedValue({ agent_instance_id: 'inst-1' });

    const result = await resumeSession(
      inst({ session_config: { agent: 'claude', model: 'opus' } }),
      { prompt: 'Is CI green yet?' }
    );

    const [machineId, method, params] = callRpc.mock.calls[0];
    expect(machineId).toBe('machine-1');
    expect(method).toBe('spawn-session');
    expect(params.resume).toEqual({ agent_instance_id: 'inst-1', agent_session_id: undefined });
    expect(params.metadata).toMatchObject({ model: 'opus', prompt: 'Is CI green yet?' });
    expect(result.alreadyRunning).toBe(false);
  });

  it('says when the daemon reopened a running agent instead', async () => {
    callRpc.mockResolvedValue({ agent_instance_id: 'inst-1', already_running: true });

    const result = await resumeSession(inst(), { prompt: 'go' });

    expect(result.alreadyRunning).toBe(true);
  });

  it('sends no prompt for a plain Resume', async () => {
    callRpc.mockResolvedValue({ agent_instance_id: 'inst-1' });

    await resumeSession(inst({ session_config: { agent: 'claude', model: 'opus' } }));

    expect(callRpc.mock.calls[0][2].metadata.prompt).toBeUndefined();
  });
});

describe('shouldResumeOnSend', () => {
  const owner = { isOwner: true, withinResumeGrace: false };

  it.each(['COMPLETED', 'FAILED', 'KILLED', 'DISCONNECTED'])(
    'keeps the composer open for a closed %s session, so a send resumes it',
    (status) => {
      expect(shouldResumeOnSend(inst({ status }), 'agent_stopped', owner)).toBe(true);
    }
  );

  it('resumes an archived session whose agent is still shutting down', () => {
    // The heartbeat lingers after archiving. Resume is offered straight away,
    // so a send resumes too; the daemon reports an agent still running and
    // the message posted first reaches it over the live broadcast.
    expect(shouldResumeOnSend(inst({ status: 'COMPLETED' }), 'live', owner)).toBe(true);
  });

  it('resumes a session whose agent stopped while its status still reads open', () => {
    expect(
      shouldResumeOnSend(inst({ status: 'AWAITING_INPUT' }), 'agent_stopped', owner)
    ).toBe(true);
  });

  it('sends normally to a running session', () => {
    expect(shouldResumeOnSend(inst({ status: 'AWAITING_INPUT' }), 'live', owner)).toBe(false);
    expect(
      shouldResumeOnSend(inst({ status: 'ACTIVE' }), 'reconnecting', owner)
    ).toBe(false);
    expect(shouldResumeOnSend(inst({ status: 'ACTIVE' }), 'unknown', owner)).toBe(false);
  });

  it('keeps the composer locked when the computer is offline', () => {
    expect(
      shouldResumeOnSend(inst({ status: 'COMPLETED' }), 'machine_offline', owner)
    ).toBe(false);
    expect(
      shouldResumeOnSend(inst({ status: 'AWAITING_INPUT' }), 'machine_offline', owner)
    ).toBe(false);
  });

  it('keeps it locked when there is no machine or folder to resume on', () => {
    expect(shouldResumeOnSend(inst({ machine_id: null }), 'agent_stopped', owner)).toBe(false);
    expect(shouldResumeOnSend(inst({ project: null }), 'agent_stopped', owner)).toBe(false);
  });

  it('keeps a deleted session locked', () => {
    expect(shouldResumeOnSend(inst({ status: 'DELETED' }), 'agent_stopped', owner)).toBe(false);
  });

  it('leaves a collaborator on the locked composer: the relaunch is the owner\'s', () => {
    expect(
      shouldResumeOnSend(inst(), 'agent_stopped', { isOwner: false, withinResumeGrace: false })
    ).toBe(false);
  });

  it('does not resume again while a resume is still coming up', () => {
    expect(
      shouldResumeOnSend(inst(), 'agent_stopped', { isOwner: true, withinResumeGrace: true })
    ).toBe(false);
  });

  it('is false with no session loaded', () => {
    expect(shouldResumeOnSend(null, 'agent_stopped', owner)).toBe(false);
  });
});

describe('resumeOnSendPlaceholder', () => {
  it('says a closed session resumes on send', () => {
    expect(resumeOnSendPlaceholder('COMPLETED')).toBe(
      'Session closed. Send a message to resume it.'
    );
  });

  it('says a stopped agent resumes on send', () => {
    expect(resumeOnSendPlaceholder('KILLED')).toMatch(/Send a message to resume it\.$/);
  });
});
