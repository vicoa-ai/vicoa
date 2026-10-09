// Spec for the home list's "Project" grouping — the Dart mirror of the web
// sidebar's `groupSessions(..., 'project')` in `session-grouping.test.ts`:
//   - grouped on `project_id`, labelled with the DB project's name;
//   - ordered the way the projects list is (the user's synced drag order,
//     then recency), unknown folder groups alphabetical, No Project last;
//   - a session with no linked project groups under its folder basename;
//   - two projects sharing a name stay two groups;
//   - sessions of an archived project leave the list.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/pages/home/project_groups.dart';

Map<String, dynamic> session(String id, {String? projectId, String? project}) =>
    {'id': id, 'project_id': projectId, 'project': project};

Map<String, dynamic> project(String id, String name, {bool archived = false}) =>
    {'id': id, 'name': name, 'is_archived': archived};

List<String> labels(List<SessionGroup> groups) => groups.map((g) => g.label).toList();

void main() {
  group('groupSessionsByProject', () {
    test('follows the project list order and labels with the DB name', () {
      final grouped = groupSessionsByProject(
        [
          session('s1', projectId: 'p-beta', project: '/x/beta-folder'),
          session('s2', projectId: 'p-alpha', project: '/x/alpha-folder'),
          session('s3', projectId: 'p-beta', project: '/x/beta-folder'),
          session('s4', projectId: 'p-gamma', project: '/x/gamma-folder'),
        ],
        // The backend's order: the user dragged Gamma above Beta above Alpha.
        [project('p-gamma', 'Gamma'), project('p-beta', 'Beta'), project('p-alpha', 'Alpha')],
      );
      expect(labels(grouped), ['Gamma', 'Beta', 'Alpha']);
      expect(grouped[1].sessions.map((s) => s['id']).toList(), ['s1', 's3']);
    });

    test('unknown groups trail alphabetically, No Project is always last', () {
      final grouped = groupSessionsByProject(
        [
          session('n', project: null),
          session('z', project: '/x/zeta'),
          session('m', project: '/x/mu/'),
          session('k', projectId: 'p-known', project: '/x/known'),
          session('u', projectId: 'p-unloaded', project: '/x/unloaded-folder'),
        ],
        [project('p-known', 'Known')],
      );
      expect(labels(grouped), ['Known', 'mu', 'unloaded-folder', 'zeta', kNoProjectGroup]);
      expect(grouped.last.isNoProject, isTrue);
    });

    test('with no project list at all it degrades to alphabetical basenames', () {
      final grouped = groupSessionsByProject(
        [
          session('b', projectId: 'p-b', project: '/x/bravo'),
          session('a', projectId: 'p-a', project: '/x/alpha'),
          session('n', project: ''),
        ],
        const [],
      );
      expect(labels(grouped), ['alpha', 'bravo', kNoProjectGroup]);
    });

    test('a linked session with no folder still labels with its project name', () {
      final grouped = groupSessionsByProject(
        [session('s', projectId: 'p-1', project: null)],
        [project('p-1', 'Named')],
      );
      expect(labels(grouped), ['Named']);
    });

    test('two projects with the same name stay two groups', () {
      final grouped = groupSessionsByProject(
        [
          session('a', projectId: 'p-1', project: '/work/app'),
          session('b', projectId: 'p-2', project: '/personal/app'),
        ],
        [project('p-1', 'app'), project('p-2', 'app')],
      );
      expect(grouped.map((g) => g.key).toList(), ['p-1', 'p-2']);
      expect(labels(grouped), ['app', 'app']);
    });

    test('a group carries its DB project for the header icon', () {
      final grouped = groupSessionsByProject(
        [
          session('k', projectId: 'p-1', project: '/x/known'),
          session('f', project: '/x/folder'),
        ],
        [{...project('p-1', 'Known'), 'icon': '🚀'}],
      );
      expect(grouped.every((g) => g.isProject), isTrue);
      expect(grouped[0].project?['icon'], '🚀');
      expect(grouped[1].project, isNull); // a folder no project claims
    });
  });

  group('withoutArchivedProjects', () {
    test('drops sessions filed under an archived project', () {
      final kept = withoutArchivedProjects(
        [
          session('live', projectId: 'p-live', project: '/x/live'),
          session('gone', projectId: 'p-old', project: '/x/old'),
          session('folder', project: '/x/folder'),
          session('unloaded', projectId: 'p-new', project: '/x/new'),
        ],
        [project('p-live', 'Live'), project('p-old', 'Old', archived: true)],
      );
      expect(kept.map((s) => s['id']).toList(), ['live', 'folder', 'unloaded']);
    });

    test('keeps everything before the project list loads', () {
      final sessions = [session('a', projectId: 'p-old', project: '/x/old')];
      expect(withoutArchivedProjects(sessions, const []), sessions);
    });
  });

  group('sessionProjectKey', () {
    test('prefers project_id, then the folder basename', () {
      expect(sessionProjectKey({'project_id': 'p', 'project': '/x/y'}), 'p');
      expect(sessionProjectKey({'project_id': '', 'project': '/x/y/'}), 'y');
      expect(sessionProjectKey({'project': null}), isNot('y'));
    });
  });
}
