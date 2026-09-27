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

    test('existing carries the subfolder into the worktree', () {
      // A monorepo session picked at `repo/apps/web` on a worktree starts at
      // `<worktree>/apps/web`, not at the worktree root.
      final r = resolveWorktreeSpawn(
        mode: WorktreeMode.existing,
        baseDirectory: '~/projects/app/apps/web',
        subpath: 'apps/web',
        selectedWorktreePath: '/Users/u/vicoa/workspaces/app-1a2b/brave-river',
      );
      expect(r.directory, '/Users/u/vicoa/workspaces/app-1a2b/brave-river/apps/web');
      expect(r.worktree, isNull);
    });

    test('newWorktree sends the subfolder itself — the daemon forks the repo', () {
      final r = resolveWorktreeSpawn(
        mode: WorktreeMode.newWorktree,
        baseDirectory: '~/projects/app/apps/web',
        subpath: 'apps/web',
      );
      expect(r.directory, '~/projects/app/apps/web');
      expect(r.worktree, {'new': true});
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

    test('every not-closed status counts as active, as on the web', () {
      for (final status in [
        'STARTING',
        'AWAITING_INPUT',
        'PAUSED',
        'STALE',
        'REVIEWED',
      ]) {
        expect(
          worktreeHasActiveSession(wt, [
            {'project': wt, 'status': status},
          ]),
          isTrue,
          reason: status,
        );
      }
    });

    test('false when every session in the worktree is closed', () {
      final sessions = [
        for (final status in [
          'COMPLETED',
          'FAILED',
          'KILLED',
          'DELETED',
          'DISCONNECTED',
        ])
          {'project': wt, 'status': status},
      ];
      expect(worktreeHasActiveSession(wt, sessions), isFalse);
    });

    test('a session in a folder inside the worktree counts', () {
      final sessions = [
        {'project': '$wt/apps/web', 'status': 'ACTIVE'},
      ];
      expect(worktreeHasActiveSession(wt, sessions), isTrue);
    });

    test('a sibling worktree sharing the name prefix does not', () {
      final sessions = [
        {'project': '$wt-2', 'status': 'ACTIVE'},
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

  group('worktreeActiveSessionIds', () {
    const wt = '/Users/u/vicoa/workspaces/app-1a2b/brave-river';

    test('the live sessions in the worktree, the ones a removal archives', () {
      final sessions = [
        {'id': 'root', 'project': wt, 'status': 'ACTIVE'},
        {'id': 'sub', 'project': '$wt/apps/web', 'status': 'STALE'},
        {'id': 'done', 'project': wt, 'status': 'COMPLETED'},
        {'id': 'elsewhere', 'project': '/some/other/dir', 'status': 'ACTIVE'},
        {'project': wt, 'status': 'ACTIVE'}, // no id: nothing to archive
      ];
      expect(worktreeActiveSessionIds(wt, sessions), ['root', 'sub']);
    });

    test('matches the ~-form session project against the absolute path', () {
      final sessions = [
        {
          'id': 'a',
          'project': '~/vicoa/workspaces/app-1a2b/brave-river',
          'status': 'AWAITING_INPUT',
        },
      ];
      expect(
        worktreeActiveSessionIds(wt, sessions, homeDir: '/Users/u'),
        ['a'],
      );
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
