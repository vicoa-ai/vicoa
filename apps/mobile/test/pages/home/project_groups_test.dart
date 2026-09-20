// Spec for the home list's "Project" grouping — the Dart mirror of the web
// sidebar's `groupSessions(..., 'project')` in `session-grouping.test.ts`:
//   - grouped on `project_id`, labelled with the DB project's name;
//   - ordered the way the projects list is (the user's synced drag order,
//     then recency), unknown folder groups alphabetical, No Project last;
//   - a session with no linked project groups under its folder basename.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/pages/home/project_groups.dart';

Map<String, dynamic> session(String id, {String? projectId, String? project}) =>
    {'id': id, 'project_id': projectId, 'project': project};

Map<String, dynamic> project(String id, String name) => {'id': id, 'name': name};

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
      expect(grouped.keys.toList(), ['Gamma', 'Beta', 'Alpha']);
      expect(grouped['Beta']!.map((s) => s['id']).toList(), ['s1', 's3']);
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
      expect(grouped.keys.toList(), ['Known', 'mu', 'unloaded-folder', 'zeta', kNoProjectGroup]);
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
      expect(grouped.keys.toList(), ['alpha', 'bravo', kNoProjectGroup]);
    });

    test('a linked session with no folder still labels with its project name', () {
      final grouped = groupSessionsByProject(
        [session('s', projectId: 'p-1', project: null)],
        [project('p-1', 'Named')],
      );
      expect(grouped.keys.toList(), ['Named']);
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
