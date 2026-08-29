import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/api_resume_session.dart';

/// Mirrors vicoa-web/lib/session-resume.test.ts.
///
/// The two clients derive Resume eligibility independently, and they drifted:
/// the app kept an ad-hoc heartbeat check while the web moved to these rules,
/// so an archived Kimi session offered Resume on the web and hid it in the app,
/// and an offline machine offered a Resume the app couldn't complete (the RPC
/// came back as no_handler and surfaced as a raw RpcException).
void main() {
  const machineId = 'machine-1';
  const project = '~/projects/vicoa';

  String? blocked({
    String status = 'COMPLETED',
    String? machine = machineId,
    String? dir = project,
    String? liveState = 'agent_stopped',
  }) =>
      resumeBlockedReason(status: status, machineId: machine, project: dir, liveState: liveState);

  bool can({
    String status = 'COMPLETED',
    String? machine = machineId,
    String? dir = project,
    String? liveState = 'agent_stopped',
  }) =>
      canResumeSession(status: status, machineId: machine, project: dir, liveState: liveState);

  group('canResumeSession', () {
    test('offers resume for a stopped session', () {
      expect(can(status: 'ACTIVE', liveState: 'agent_stopped'), isTrue);
    });

    test('offers resume for an archived session immediately', () {
      // The reported bug: a just-archived session's heartbeat lingers for the
      // whole online threshold, so a liveness-only rule hid Resume for ~90s.
      for (final status in ['COMPLETED', 'FAILED', 'KILLED', 'DISCONNECTED']) {
        expect(can(status: status, liveState: 'live'), isTrue, reason: status);
      }
    });

    test('still offers it while the computer is offline', () {
      // Shown disabled with a reason; hiding it reads as "unsupported".
      expect(can(status: 'ACTIVE', liveState: 'machine_offline'), isTrue);
    });

    test('refuses a deleted session', () {
      expect(can(status: 'DELETED'), isFalse);
    });

    test('refuses a session with no machine or folder', () {
      expect(can(machine: null), isFalse);
      expect(can(machine: ''), isFalse);
      expect(can(dir: null), isFalse);
    });

    test('does not offer resume for a session that is genuinely running', () {
      expect(can(status: 'ACTIVE', liveState: 'live'), isFalse);
      expect(can(status: 'ACTIVE', liveState: 'reconnecting'), isFalse);
    });

    test('does not offer resume when liveness is unknown', () {
      // Legacy rows we can't judge — better silent than a Resume that fails.
      expect(can(status: 'ACTIVE', liveState: 'unknown'), isFalse);
    });
  });

  group('resumeBlockedReason', () {
    test('is null when resume can proceed', () {
      expect(blocked(), isNull);
      expect(blocked(status: 'ACTIVE', liveState: 'agent_stopped'), isNull);
    });

    test('blocks on an offline computer before anything else', () {
      // This is what produced RpcException(no_handler): the app fired the RPC
      // at a daemon that wasn't connected.
      expect(blocked(liveState: 'machine_offline'), contains('offline'));
    });

    test('blocks a deleted session', () {
      expect(blocked(status: 'DELETED'), contains('deleted'));
    });

    test('blocks when there is no machine or folder', () {
      expect(blocked(machine: null), contains('computer'));
      expect(blocked(dir: ''), contains('folder'));
    });

    test('blocks a session that is already running', () {
      expect(blocked(status: 'ACTIVE', liveState: 'live'), contains('already running'));
    });

    test('an archived session outranks the already-running guard', () {
      // Closed on purpose: the user knows it isn't working, even if the
      // heartbeat hasn't aged out yet.
      expect(blocked(status: 'COMPLETED', liveState: 'live'), isNull);
    });
  });

  group('resumeAgentSlug', () {
    test('maps display names to daemon slugs', () {
      expect(resumeAgentSlug('Claude Code'), 'claude');
      expect(resumeAgentSlug('Codex'), 'codex');
      expect(resumeAgentSlug('OpenCode'), 'opencode');
      expect(resumeAgentSlug('Cursor'), 'cursor');
      expect(resumeAgentSlug(null), 'claude');
    });
  });

  group('resumeExpandProjectPath', () {
    test('expands a tilde against the recorded home directory', () {
      expect(resumeExpandProjectPath('~/projects/vicoa', '/Users/dev'), '/Users/dev/projects/vicoa');
    });

    test('leaves absolute paths and unknown homes alone', () {
      expect(resumeExpandProjectPath('/srv/app', '/Users/dev'), '/srv/app');
      expect(resumeExpandProjectPath('~/x', null), '~/x');
    });

    test('does not double the separator', () {
      expect(resumeExpandProjectPath('~/x', '/Users/dev/'), '/Users/dev/x');
    });
  });

  group('resumeAgentSessionHandle', () {
    test('finds either agent handle', () {
      expect(resumeAgentSessionHandle({'codex_thread_id': 'th-1'}), 'th-1');
      expect(resumeAgentSessionHandle({'acp_session_id': 'ses-1'}), 'ses-1');
    });

    test('is null when the previous run recorded none', () {
      expect(resumeAgentSessionHandle(null), isNull);
      expect(resumeAgentSessionHandle({}), isNull);
      expect(resumeAgentSessionHandle({'codex_thread_id': ''}), isNull);
    });
  });

  group('resume grace registry', () {
    test('is false for a session that was never resumed', () {
      expect(isWithinResumeGrace('never-resumed-id'), isFalse);
      expect(isWithinResumeGrace(null), isFalse);
      expect(isWithinResumeGrace(''), isFalse);
    });

    test('holds right after a resume', () {
      // Covers both surfaces: the chat composer and the home-list dot read
      // this same registry, so a just-resumed session reads reachable on both.
      markResumed('grace-inst-1');
      expect(isWithinResumeGrace('grace-inst-1'), isTrue);
    });

    test('does not leak across instances', () {
      markResumed('grace-inst-2');
      expect(isWithinResumeGrace('grace-inst-3'), isFalse);
    });

    test('ignores an empty instance id', () {
      markResumed('');
      expect(isWithinResumeGrace(''), isFalse);
    });
  });
}
