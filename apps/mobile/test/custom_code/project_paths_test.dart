// Spec for the project-first picker's path helpers — the Dart mirror of the
// web's `lib/project-paths.test.ts`.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/project_paths.dart';

const home = '/Users/nick';

Map<String, dynamic> project(
  String name,
  List<Map<String, String>> directories, {
  String? lastActivityAt,
  bool archived = false,
}) =>
    {
      'id': 'id-$name',
      'name': name,
      'is_archived': archived,
      'last_activity_at': lastActivityAt,
      'directories': directories,
    };

void main() {
  group('canonicalPath', () {
    test('expands ~ and drops trailing slashes', () {
      expect(canonicalPath('~/src/app/', home), '/Users/nick/src/app');
      expect(canonicalPath('/', home), '/');
    });

    test('leaves ~ alone when the home dir is unknown', () {
      expect(canonicalPath('~/src/app', null), '~/src/app');
    });
  });

  group('relativeSubpath', () {
    test('is empty for the root itself, in either form', () {
      expect(relativeSubpath('~/src/app', '/Users/nick/src/app', home), '');
      expect(relativeSubpath('/Users/nick/src/app/', '~/src/app', home), '');
    });

    test('is the part below the root', () {
      expect(relativeSubpath('~/src/app/apps/web', '~/src/app', home), 'apps/web');
    });

    test('is null outside the root, on a path boundary', () {
      expect(relativeSubpath('~/src/apple', '~/src/app', home), isNull);
      // A worktree lives OUTSIDE the repo — never "inside" its root.
      expect(
        relativeSubpath('~/vicoa/workspaces/app-worktrees/feat/app', '~/src/app', home),
        isNull,
      );
    });
  });

  group('joinSubpath', () {
    test('joins without doubled slashes and keeps a bare base', () {
      expect(joinSubpath('/wt/app/', 'apps/web'), '/wt/app/apps/web');
      expect(joinSubpath('/wt/app', ''), '/wt/app');
      expect(joinSubpath('/', 'x'), '/x');
    });
  });

  group('resolveProjectForDirectory', () {
    final projects = [
      project('vicoa', [
        {'machine_id': 'm1', 'local_path': '~/projects/vicoa-ai/vicoa'},
        {'machine_id': 'm2', 'local_path': '/srv/vicoa'},
      ]),
      project('umbrella', [
        {'machine_id': 'm1', 'local_path': '~/projects/vicoa-ai'},
      ]),
    ];

    test('picks the longest linked folder on the machine and splits the subpath', () {
      final match = resolveProjectForDirectory(
        '~/projects/vicoa-ai/vicoa/apps/web',
        'm1',
        projects,
        home,
      );
      expect(match?.projectName, 'vicoa');
      expect(match?.root, '~/projects/vicoa-ai/vicoa');
      expect(match?.subpath, 'apps/web');
    });

    test('falls back to the enclosing project for a sibling folder', () {
      final match =
          resolveProjectForDirectory('~/projects/vicoa-ai/plans', 'm1', projects, home);
      expect(match?.projectName, 'umbrella');
      expect(match?.subpath, 'plans');
    });

    test('only considers folders on the selected machine', () {
      expect(resolveProjectForDirectory('/srv/vicoa', 'm1', projects, home), isNull);
      expect(
        resolveProjectForDirectory('/srv/vicoa', 'm2', projects, home)?.projectName,
        'vicoa',
      );
    });

    test('is null for a folder no project claims', () {
      expect(resolveProjectForDirectory('~/scratch', 'm1', projects, home), isNull);
      expect(resolveProjectForDirectory('', 'm1', projects, home), isNull);
    });
  });

  group('projectsOnMachine', () {
    test('lists linked projects newest activity first, archived excluded', () {
      final rows = projectsOnMachine(
        [
          project('old', [{'machine_id': 'm1', 'local_path': '/a'}],
              lastActivityAt: '2026-01-01T00:00:00Z'),
          project('new', [{'machine_id': 'm1', 'local_path': '/b'}],
              lastActivityAt: '2026-02-01T00:00:00Z'),
          project('never', [{'machine_id': 'm1', 'local_path': '/c'}]),
          project('elsewhere', [{'machine_id': 'm2', 'local_path': '/d'}]),
          project('gone', [{'machine_id': 'm1', 'local_path': '/e'}], archived: true),
        ],
        'm1',
      );
      expect(rows.map((r) => r.name).toList(), ['new', 'old', 'never']);
      expect(rows.first.path, '/b');
    });
  });

  group('directoryChipLabel', () {
    final vicoa = project('vicoa', [{'machine_id': 'm1', 'local_path': '~/src/vicoa'}]);

    test('is the project name, with the subfolder when below the root', () {
      expect(
        directoryChipLabel(
          '~/src/vicoa',
          ProjectDirectoryMatch(project: vicoa, root: '~/src/vicoa', subpath: ''),
        ),
        'vicoa',
      );
      expect(
        directoryChipLabel(
          '~/src/vicoa/apps/web',
          ProjectDirectoryMatch(project: vicoa, root: '~/src/vicoa', subpath: 'apps/web'),
        ),
        'vicoa · apps/web',
      );
    });

    test("is the folder's own name when no project claims it", () {
      expect(directoryChipLabel('~/scratch/thing/', null), 'thing');
    });
  });
}
