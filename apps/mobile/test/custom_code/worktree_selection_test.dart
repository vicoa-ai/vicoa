// Spec for the new-session worktree decision logic:
//   - machineSupportsWorktree: capability gate (the §8 correctness landmine —
//     an old daemon that omits `capabilities` must read as UNsupported).
//   - resolveWorktreeSpawn: maps a worktree selection onto spawn-session args.
//
// Covers `plans/todos/vicoa-app-worktree.md` §5.2 / §5.3.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/machine_utils.dart';
import 'package:vicoa/custom_code/utils/worktree_selection.dart';

void main() {
  group('machineSupportsWorktree', () {
    test('true when metadata.capabilities lists worktree', () {
      final machine = {
        'machine_id': 'm',
        'metadata': {
          'capabilities': ['worktree'],
        },
      };
      expect(machineSupportsWorktree(machine), isTrue);
    });

    test('false when capabilities is absent (old daemon)', () {
      // The landmine: an old daemon silently ignores the worktree param, so a
      // missing capability MUST read as unsupported (hide the option).
      final machine = {
        'machine_id': 'm',
        'metadata': {
          'available_agents': {'claude': true},
        },
      };
      expect(machineSupportsWorktree(machine), isFalse);
    });

    test('false when capabilities present but lacks worktree', () {
      final machine = {
        'metadata': {
          'capabilities': ['something-else'],
        },
      };
      expect(machineSupportsWorktree(machine), isFalse);
    });

    test('false for null / malformed machine', () {
      expect(machineSupportsWorktree(null), isFalse);
      expect(machineSupportsWorktree('nope'), isFalse);
    });

    test('reads the WS-envelope metadata shape too', () {
      final machine = {
        'id': 'm',
        'machine_metadata': {
          'capabilities': ['worktree'],
        },
      };
      expect(machineSupportsWorktree(machine), isTrue);
    });
  });

  group('resolveWorktreeSpawn', () {
    test('none → spawn the base directory, no worktree param', () {
      final r = resolveWorktreeSpawn(
        mode: WorktreeMode.none,
        baseDirectory: '~/projects/app',
      );
      expect(r.directory, '~/projects/app');
      expect(r.worktree, isNull);
    });

    test('newWorktree → base directory + worktree:{new:true}', () {
      final r = resolveWorktreeSpawn(
        mode: WorktreeMode.newWorktree,
        baseDirectory: '~/projects/app',
      );
      expect(r.directory, '~/projects/app');
      expect(r.worktree, {'new': true});
    });

    test('existing → spawn the selected worktree path, no worktree param', () {
      final r = resolveWorktreeSpawn(
        mode: WorktreeMode.existing,
        baseDirectory: '~/projects/app',
        selectedWorktreePath: '/Users/u/vicoa/workspaces/app-1a2b/brave-river',
      );
      expect(r.directory, '/Users/u/vicoa/workspaces/app-1a2b/brave-river');
      expect(r.worktree, isNull);
    });

    test('existing with no selected path falls back to base directory', () {
      final r = resolveWorktreeSpawn(
        mode: WorktreeMode.existing,
        baseDirectory: '~/projects/app',
        selectedWorktreePath: null,
      );
      expect(r.directory, '~/projects/app');
      expect(r.worktree, isNull);
    });
  });

  group('worktreeHasActiveSession', () {
    const wt = '/Users/u/vicoa/workspaces/app-1a2b/brave-river';

    test('true when a session in the worktree is active', () {
      final sessions = [
        {'project': wt, 'status': 'ACTIVE'},
      ];
      expect(worktreeHasActiveSession(wt, sessions), isTrue);
    });

    test('AWAITING_INPUT and REVIEWED also count as active', () {
      expect(
        worktreeHasActiveSession(wt, [
          {'project': wt, 'status': 'AWAITING_INPUT'},
        ]),
        isTrue,
      );
      expect(
        worktreeHasActiveSession(wt, [
          {'project': wt, 'status': 'REVIEWED'},
        ]),
        isTrue,
      );
    });

    test('false when the only session in the worktree is COMPLETED', () {
      final sessions = [
        {'project': wt, 'status': 'COMPLETED'},
      ];
      expect(worktreeHasActiveSession(wt, sessions), isFalse);
    });

    test('false when no session runs in that worktree', () {
      final sessions = [
        {'project': '/some/other/dir', 'status': 'ACTIVE'},
      ];
      expect(worktreeHasActiveSession(wt, sessions), isFalse);
    });

    test('ignores malformed entries', () {
      final sessions = [
        'not-a-map',
        {'status': 'ACTIVE'}, // no project
        {'project': wt}, // no status
      ];
      expect(worktreeHasActiveSession(wt, sessions), isFalse);
    });
  });

  group('isManagedWorktreePath', () {
    test('true for a path under vicoa/workspaces', () {
      expect(
        isManagedWorktreePath('/Users/u/vicoa/workspaces/app-1a2b/brave-river'),
        isTrue,
      );
    });

    test('false for an ordinary project directory', () {
      expect(isManagedWorktreePath('/Users/u/projects/my-app'), isFalse);
    });

    test('false for empty', () {
      expect(isManagedWorktreePath(''), isFalse);
    });
  });
}
